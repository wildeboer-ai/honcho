"""
Chat functionality for the Dialectic API.

Provides peer-level and workspace-level entry points for answering queries.
"""

import logging
from collections.abc import AsyncIterator

from src import crud, schemas
from src.config import ReasoningLevel
from src.dependencies import tracked_db
from src.dialectic.core import DialecticAgent
from src.dialectic.workspace import WorkspaceDialecticAgent
from src.utils.config_helpers import get_configuration

logger = logging.getLogger(__name__)


async def agentic_chat(
    workspace_name: str,
    session_name: str | None,
    query: str,
    observer: str,
    observed: str,
    reasoning_level: ReasoningLevel = "low",
) -> str:
    """
    Answer a query about a peer using the agentic dialectic.

    Args:
        workspace_name: Workspace identifier
        session_name: Session identifier (may be None for global queries)
        query: The question to answer about the peer
        observer: The peer making the query
        observed: The peer being queried about
        reasoning_level: Level of reasoning to apply

    Returns:
        The synthesized answer string
    """
    # Short-lived DB session for validation + config
    async with tracked_db("dialectic.preflight", read_only=True) as db:
        await crud.get_peer(db, workspace_name, schemas.PeerCreate(name=observer))
        if observer != observed:
            await crud.get_peer(db, workspace_name, schemas.PeerCreate(name=observed))

        session = None
        if session_name:
            session = await crud.get_session(
                db, workspace_name=workspace_name, session_name=session_name
            )
        workspace = await crud.get_workspace(db, workspace_name=workspace_name)
        configuration = get_configuration(None, session, workspace)
        agent_config = await crud.get_workspace_agent_config(db, workspace_name)

        observer_peer_card = None
        observed_peer_card = None
        if configuration.peer_card.use:
            observer_peer_card = await crud.get_peer_card(
                db, workspace_name, observer=observer, observed=observer
            )
            if observer != observed:
                observed_peer_card = await crud.get_peer_card(
                    db, workspace_name, observer=observer, observed=observed
                )
    # DB session closed — agent runs without holding a connection

    agent = DialecticAgent(
        workspace_name=workspace_name,
        session_name=session_name,
        observer=observer,
        observed=observed,
        observer_peer_card=observer_peer_card,
        observed_peer_card=observed_peer_card,
        reasoning_level=reasoning_level,
        custom_rules=agent_config.dialectic_rules,
    )

    return await agent.answer(query)


async def agentic_chat_stream(
    workspace_name: str,
    session_name: str | None,
    query: str,
    observer: str,
    observed: str,
    reasoning_level: ReasoningLevel = "low",
) -> AsyncIterator[str]:
    """
    Stream an answer to a query about a peer using the agentic dialectic.

    Args:
        workspace_name: Workspace identifier
        session_name: Session identifier (may be None for global queries)
        query: The question to answer about the peer
        observer: The peer making the query
        observed: The peer being queried about
        reasoning_level: Level of reasoning to apply

    Yields:
        Chunks of the response text as they are generated
    """
    # Short-lived DB session for validation + config
    async with tracked_db("dialectic.preflight", read_only=True) as db:
        await crud.get_peer(db, workspace_name, schemas.PeerCreate(name=observer))
        if observer != observed:
            await crud.get_peer(db, workspace_name, schemas.PeerCreate(name=observed))

        session = None
        if session_name:
            session = await crud.get_session(
                db, workspace_name=workspace_name, session_name=session_name
            )
        workspace = await crud.get_workspace(db, workspace_name=workspace_name)
        configuration = get_configuration(None, session, workspace)
        agent_config = await crud.get_workspace_agent_config(db, workspace_name)

        observer_peer_card = None
        observed_peer_card = None
        if configuration.peer_card.use:
            observer_peer_card = await crud.get_peer_card(
                db, workspace_name, observer=observer, observed=observer
            )
            if observer != observed:
                observed_peer_card = await crud.get_peer_card(
                    db, workspace_name, observer=observer, observed=observed
                )
    # DB session closed — agent streams without holding a connection

    agent = DialecticAgent(
        workspace_name=workspace_name,
        session_name=session_name,
        observer=observer,
        observed=observed,
        observer_peer_card=observer_peer_card,
        observed_peer_card=observed_peer_card,
        reasoning_level=reasoning_level,
        custom_rules=agent_config.dialectic_rules,
    )

    async for chunk in agent.answer_stream(query):
        yield chunk


async def workspace_chat(
    workspace_name: str,
    session_name: str | None,
    query: str,
    reasoning_level: ReasoningLevel = "low",
) -> str:
    """Answer a workspace-level query using the workspace dialectic agent."""
    async with tracked_db("dialectic.workspace_chat.preflight", read_only=True) as db:
        if session_name:
            await crud.get_session(
                db,
                workspace_name=workspace_name,
                session_name=session_name,
            )

    agent = WorkspaceDialecticAgent(
        workspace_name=workspace_name,
        session_name=session_name,
        reasoning_level=reasoning_level,
    )
    return await agent.answer(query)


async def workspace_chat_stream(
    workspace_name: str,
    session_name: str | None,
    query: str,
    reasoning_level: ReasoningLevel = "low",
) -> AsyncIterator[str]:
    """Stream a workspace-level query answer using the workspace dialectic agent."""
    async with tracked_db(
        "dialectic.workspace_chat_stream.preflight", read_only=True
    ) as db:
        if session_name:
            await crud.get_session(
                db,
                workspace_name=workspace_name,
                session_name=session_name,
            )

    agent = WorkspaceDialecticAgent(
        workspace_name=workspace_name,
        session_name=session_name,
        reasoning_level=reasoning_level,
    )
    async for chunk in agent.answer_stream(query):
        yield chunk
