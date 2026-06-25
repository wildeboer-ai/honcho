"""Workspace-level Dialectic Agent implementation."""

import logging
import time
from collections.abc import Callable
from typing import Any

from nanoid import generate as generate_nanoid

import src.crud as crud
from src.config import ReasoningLevel, settings
from src.dependencies import tracked_db
from src.dialectic import prompts
from src.dialectic.core import DialecticAgent
from src.llm.types import LLMTelemetryContext
from src.telemetry.logging import accumulate_metric
from src.utils.agent_tools import (
    TOOLS,
    WORKSPACE_DIALECTIC_TOOLS,
    create_workspace_tool_executor,
)

logger = logging.getLogger(__name__)

WORKSPACE_PEER_NAME = "(workspace)"


class WorkspaceDialecticAgent(DialecticAgent):
    """Dialectic agent that answers queries across all peers in a workspace."""

    def __init__(
        self,
        workspace_name: str,
        session_name: str | None = None,
        reasoning_level: ReasoningLevel = "low",
    ) -> None:
        super().__init__(
            workspace_name=workspace_name,
            session_name=session_name,
            observer=WORKSPACE_PEER_NAME,
            observed=WORKSPACE_PEER_NAME,
            reasoning_level=reasoning_level,
        )
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompts.workspace_agent_system_prompt()}
        ]

    async def _prefetch_relevant_observations(self, query: str) -> str | None:
        """Prefetch workspace stats so the agent can orient itself cheaply."""
        _ = query
        async with tracked_db("dialectic.workspace_prefetch", read_only=True) as db:
            stats = await crud.get_workspace_stats(db, self.workspace_name)
        if stats.peer_count == 0:
            return None

        lines = [
            f"Peers: {stats.peer_count}",
            f"Sessions: {stats.session_count}",
            f"Messages: {stats.message_count}",
        ]
        if stats.oldest_message_at and stats.newest_message_at:
            lines.append(
                f"Date range: {stats.oldest_message_at:%Y-%m-%d} to {stats.newest_message_at:%Y-%m-%d}"
            )
        return "\n".join(lines)

    async def _prepare_query(
        self, query: str
    ) -> tuple[Callable[[str, dict[str, Any]], Any], str, str | None, float]:
        await self._initialize_session_history()

        run_id = generate_nanoid()
        task_name = f"workspace_chat_{run_id}"
        start_time = time.perf_counter()

        accumulate_metric(
            task_name,
            "context",
            (
                f"workspace: {self.workspace_name}\n"
                f"session: {self.session_name or '(global)'}\n"
                f"reasoning_level: {self.reasoning_level}"
            ),
            "blob",
        )
        accumulate_metric(task_name, "query", query, "blob")

        workspace_overview = await self._prefetch_relevant_observations(query)
        if workspace_overview:
            user_content = (
                f"Query: {query}\n\n"
                "## Workspace Overview\n"
                "Use this overview to decide whether to search messages, active peers, or specific peer representations.\n\n"
                f"{workspace_overview}"
            )
            accumulate_metric(
                task_name, "workspace_overview", workspace_overview, "blob"
            )
        else:
            user_content = f"Query: {query}"

        self.messages.append({"role": "user", "content": user_content})

        tool_executor = await create_workspace_tool_executor(
            workspace_name=self.workspace_name,
            session_name=self.session_name,
            include_observation_ids=True,
            history_token_limit=settings.DIALECTIC.HISTORY_TOKEN_LIMIT,
            run_id=self._run_id,
            agent_type="workspace_dialectic",
            parent_category="dialectic",
        )
        return tool_executor, task_name, run_id, start_time

    def _telemetry_context(self) -> LLMTelemetryContext:
        return LLMTelemetryContext(
            workspace_name=self.workspace_name,
            call_purpose="dialectic.answer",
            parent_category="dialectic",
            agent_type="workspace_dialectic",
            run_id=self._run_id,
            peer_name=WORKSPACE_PEER_NAME,
        )

    def _get_tools(self) -> list[dict[str, Any]]:
        if self.reasoning_level == "minimal":
            return [
                TOOLS["get_workspace_stats"],
                TOOLS["get_active_peers"],
                TOOLS["search_memory_workspace"],
                TOOLS["search_messages"],
            ]
        return WORKSPACE_DIALECTIC_TOOLS

    def _event_peer_name(self) -> str:
        return WORKSPACE_PEER_NAME

    def _performance_trace_name(self) -> str:
        return "workspace_chat"
