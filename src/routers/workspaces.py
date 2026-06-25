"""FastAPI routes for workspace resources and workspace-scoped operations."""

import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Response
from fastapi.responses import StreamingResponse
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy.ext.asyncio import AsyncSession

from src import crud, schemas
from src.config import settings
from src.dependencies import db, read_db, tracked_db
from src.deriver.enqueue import enqueue_deletion, enqueue_dream
from src.dialectic.chat import workspace_chat, workspace_chat_stream
from src.dreamer.introspection import get_latest_introspection_report
from src.exceptions import AuthenticationException
from src.feedback import process_feedback
from src.security import JWTParams, require_auth
from src.telemetry import prometheus_metrics
from src.utils.search import search

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/workspaces",
    tags=["workspaces"],
)


@router.post("", response_model=schemas.Workspace)
async def get_or_create_workspace(
    response: Response,
    workspace: schemas.WorkspaceCreate = Body(
        ..., description="Workspace creation parameters"
    ),
    jwt_params: JWTParams = Depends(require_auth()),
    db: AsyncSession = db,
):
    """
    Get a Workspace by ID.

    If workspace_id is provided as a query parameter, it uses that (must match JWT workspace_id).
    Otherwise, it uses the workspace_id from the JWT.
    """
    # If workspace_id provided in query, check if it matches jwt or user is admin
    if workspace.name:
        if not jwt_params.ad and jwt_params.w != workspace.name:
            raise AuthenticationException("Unauthorized access to resource")
    else:
        # Use workspace_id from JWT
        if not jwt_params.w:
            raise AuthenticationException(
                "Workspace ID not found in query parameter or JWT"
            )
        workspace.name = jwt_params.w

    result = await crud.get_or_create_workspace(db, workspace=workspace)
    await db.commit()
    await result.post_commit()
    response.status_code = 201 if result.created else 200
    return result.resource


@router.post(
    "/list",
    response_model=Page[schemas.Workspace],
    dependencies=[Depends(require_auth(admin=True))],
)
async def get_all_workspaces(
    options: schemas.WorkspaceGet | None = Body(
        None, description="Filtering and pagination options for the workspaces list"
    ),
    reverse: bool = Query(False, description="Whether to reverse the order of results"),
    db: AsyncSession = read_db,
):
    """Get all Workspaces, paginated with optional filters."""
    filter_param = None
    if options and hasattr(options, "filters"):
        filter_param = options.filters
        if filter_param == {}:
            filter_param = None

    return await apaginate(
        db,
        await crud.get_all_workspaces(filters=filter_param, reverse=reverse),
    )


@router.put(
    "/{workspace_id}",
    response_model=schemas.Workspace,
    dependencies=[Depends(require_auth(workspace_name="workspace_id"))],
)
async def update_workspace(
    workspace_id: str = Path(...),
    workspace: schemas.WorkspaceUpdate = Body(
        ..., description="Updated workspace parameters"
    ),
    db: AsyncSession = db,
):
    """Update Workspace metadata and/or configuration."""
    if workspace.metadata and "_agent_config" in workspace.metadata:
        try:
            schemas.WorkspaceAgentConfig.model_validate(
                workspace.metadata["_agent_config"]
            )
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid _agent_config in metadata: {e}",
            ) from e

    # ResourceNotFoundException will be caught by global handler if workspace not found
    honcho_workspace = await crud.update_workspace(
        db, workspace_name=workspace_id, workspace=workspace
    )
    return honcho_workspace


@router.delete(
    "/{workspace_id}",
    status_code=202,
    dependencies=[Depends(require_auth(workspace_name="workspace_id"))],
)
async def delete_workspace(
    workspace_id: str = Path(...),
    db: AsyncSession = db,
):
    """
    Delete a Workspace. This accepts the deletion request and processes it in the background,
    permanently deleting all peers, messages, conclusions, and other resources associated
    with the workspace.

    Returns 409 Conflict if the workspace contains active sessions.
    Delete all sessions first, then delete the workspace.

    This action cannot be undone.
    """
    # Verify workspace exists
    await crud.get_workspace(db, workspace_name=workspace_id)

    # Check for active sessions before accepting
    await crud.check_no_active_sessions(db, workspace_name=workspace_id)

    # Enqueue for background deletion
    await enqueue_deletion(workspace_id, "workspace", workspace_id, db_session=db)
    await db.commit()

    return {"message": "Workspace deletion accepted"}


@router.post(
    "/{workspace_id}/search",
    response_model=list[schemas.Message],
    dependencies=[Depends(require_auth(workspace_name="workspace_id"))],
)
async def search_workspace(
    workspace_id: str = Path(...),
    body: schemas.MessageSearchOptions = Body(
        ..., description="Message search parameters"
    ),
):
    """
    Search messages in a Workspace using optional filters. Use `limit` to control the number of
    results returned.
    """
    # take user-provided filter and add workspace_id to it
    filters = body.filters or {}
    filters["workspace_id"] = workspace_id
    return await search(body.query, filters=filters, limit=body.limit)


@router.get(
    "/{workspace_id}/queue/status",
    response_model=schemas.QueueStatus,
    dependencies=[Depends(require_auth(workspace_name="workspace_id"))],
)
async def get_queue_status(
    workspace_id: str = Path(...),
    observer_id: str | None = Query(
        None, description="Optional observer ID to filter by"
    ),
    sender_id: str | None = Query(None, description="Optional sender ID to filter by"),
    session_id: str | None = Query(
        None, description="Optional session ID to filter by"
    ),
    db: AsyncSession = read_db,
):
    """
    Get the processing queue status for a Workspace, optionally scoped to an observer, sender,
    and/or session.

    Only tracks user-facing task types (representation, summary, dream).
    Internal infrastructure tasks (reconciler, webhook, deletion) are excluded.
    Note: completed counts reflect items since the last periodic queue cleanup,
    not lifetime totals.
    """
    try:
        return await crud.get_queue_status(
            db,
            workspace_name=workspace_id,
            session_name=session_id,
            observer=observer_id,
            observed=sender_id,
        )
    except ValueError as e:
        logger.warning(f"Invalid request parameters: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get(
    "/{workspace_id}/queue/work-units",
    response_model=schemas.QueueWorkUnitsPage,
    dependencies=[Depends(require_auth(workspace_name="workspace_id"))],
)
async def get_queue_work_units(
    workspace_id: str = Path(...),
    observer_id: str | None = Query(
        None, description="Optional observer ID to filter by"
    ),
    sender_id: str | None = Query(None, description="Optional sender ID to filter by"),
    session_id: str | None = Query(
        None, description="Optional session ID to filter by"
    ),
    db: AsyncSession = read_db,
):
    """
    Return one row per unprocessed work unit in the Workspace's queue.

    The response includes token totals, in-progress state, and whether each
    representation work unit has reached the batch token threshold. Same filter
    semantics as /queue/status.
    """
    try:
        stmt = await crud.get_queue_work_units_query(
            workspace_name=workspace_id,
            session_name=session_id,
            observer=observer_id,
            observed=sender_id,
        )

        def transform(rows: Sequence[Any]) -> list[schemas.QueueWorkUnit]:
            items: list[schemas.QueueWorkUnit] = []
            for row in rows:
                hit_threshold, tokens_until_threshold = crud.classify_work_unit_row(row)
                items.append(
                    schemas.QueueWorkUnit(
                        work_unit_key=row.work_unit_key,
                        task_type=row.task_type,
                        session_id=row.session_id,
                        session_name=row.session_name,
                        observer=row.observer,
                        observed=row.observed,
                        pending_items=row.pending_items,
                        pending_tokens=row.pending_tokens,
                        tokens_until_threshold=tokens_until_threshold,
                        hit_threshold=hit_threshold,
                        in_progress=bool(row.in_progress),
                        oldest_item_at=row.oldest_item_at,
                        newest_item_at=row.newest_item_at,
                    )
                )
            return items

        return await apaginate(
            db,
            stmt,
            transformer=transform,
            additional_data={
                "representation_batch_max_tokens": (
                    settings.DERIVER.REPRESENTATION_BATCH_MAX_TOKENS
                ),
                "flush_enabled": settings.DERIVER.FLUSH_ENABLED,
            },
        )
    except ValueError as e:
        logger.warning(f"Invalid request parameters: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/{workspace_id}/chat",
    summary="Query workspace knowledge using natural language",
    responses={
        200: {
            "content": {
                "application/json": {
                    "schema": schemas.DialecticResponse.model_json_schema()
                },
                "text/event-stream": {},
            },
        },
    },
    dependencies=[Depends(require_auth(workspace_name="workspace_id"))],
)
async def chat(
    workspace_id: str = Path(...),
    options: schemas.WorkspaceChatOptions = Body(...),
):
    """
    Query the Workspace's collective knowledge using natural language.

    The workspace agent can discover relevant peers, search workspace messages,
    and drill into specific peer representations to synthesize an answer.
    """
    async with tracked_db("workspaces.chat.preflight", read_only=True) as session:
        await crud.get_workspace(session, workspace_name=workspace_id)

    if options.stream:

        async def format_sse_stream(
            chunks: AsyncIterator[str],
        ) -> AsyncIterator[str]:
            async for chunk in chunks:
                yield f"data: {json.dumps({'delta': {'content': chunk}, 'done': False})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"

        if settings.METRICS.ENABLED:
            prometheus_metrics.record_dialectic_call(
                workspace_name=workspace_id,
                reasoning_level=options.reasoning_level,
            )

        return StreamingResponse(
            format_sse_stream(
                workspace_chat_stream(
                    workspace_name=workspace_id,
                    session_name=options.session_id,
                    query=options.query,
                    reasoning_level=options.reasoning_level,
                )
            ),
            media_type="text/event-stream",
        )

    if settings.METRICS.ENABLED:
        prometheus_metrics.record_dialectic_call(
            workspace_name=workspace_id,
            reasoning_level=options.reasoning_level,
        )

    response = await workspace_chat(
        workspace_name=workspace_id,
        session_name=options.session_id,
        query=options.query,
        reasoning_level=options.reasoning_level,
    )

    return schemas.DialecticResponse(content=response if response else None)


@router.post(
    "/{workspace_id}/schedule_dream",
    status_code=204,
    dependencies=[Depends(require_auth(workspace_name="workspace_id"))],
)
async def schedule_dream(
    workspace_id: str = Path(...),
    request: schemas.ScheduleDreamRequest = Body(
        ..., description="Dream scheduling parameters"
    ),
):
    """
    Manually schedule a dream task for a specific collection.

    This endpoint bypasses all automatic dream conditions (document threshold,
    minimum hours between dreams) and schedules the dream task for a future execution.

    Currently this endpoint only supports scheduling immediate dreams. In the future,
    users may pass a cron-style expression to schedule dreams at specific times.
    """
    # Check if dreams are enabled
    if not settings.DREAM.ENABLED:
        raise HTTPException(
            status_code=400,
            detail="Dreams are not enabled in the system configuration",
        )

    # Default observed to observer if not provided
    observer = request.observer
    observed = request.observed if request.observed is not None else request.observer
    dream_type = request.dream_type

    await enqueue_dream(
        workspace_id,
        observer=observer,
        observed=observed,
        dream_type=dream_type,
        session_name=request.session_id,
        # Manual route — explicit sentinels for the DreamRunEvent
        # scheduling-context fields. Auto-schedule threads concrete
        # threshold/delay reasons (see src/dreamer/dream_scheduler.py);
        # without these, manual dreams arrive with both null and break
        # analytics joins on `trigger_reason`.
        trigger_reason="manual",
        delay_reason="immediate",
    )

    logger.info(
        "Manually scheduled dream: %s for %s/%s/%s (session: %s)",
        dream_type.value,
        workspace_id,
        observer,
        observed,
        request.session_id,
    )


@router.post(
    "/{workspace_id}/feedback",
    response_model=schemas.FeedbackResponse,
    dependencies=[Depends(require_auth(workspace_name="workspace_id"))],
)
async def process_developer_feedback(
    workspace_id: str = Path(...),
    request: schemas.FeedbackRequest = Body(...),
    db: AsyncSession = db,
):
    """Process developer feedback and update workspace agent configuration."""
    introspection_report = None
    if request.include_introspection:
        introspection_report = await get_latest_introspection_report(db, workspace_id)

    return await process_feedback(db, workspace_id, request, introspection_report)


@router.get(
    "/{workspace_id}/introspection",
    response_model=schemas.IntrospectionReport,
    dependencies=[Depends(require_auth(workspace_name="workspace_id"))],
)
async def get_introspection_report(
    workspace_id: str = Path(...),
    db: AsyncSession = db,
):
    """Get the latest introspection report for a workspace."""
    report = await get_latest_introspection_report(db, workspace_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No introspection report found")
    return report
