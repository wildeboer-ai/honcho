# pyright: reportPrivateUsage=false

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.dialectic.chat import workspace_chat, workspace_chat_stream
from src.dialectic.workspace import WORKSPACE_PEER_NAME, WorkspaceDialecticAgent
from src.utils.agent_tools import create_workspace_tool_executor


def _tool_names(tools: list[dict[str, object]]) -> list[str]:
    return [str(tool["name"]) for tool in tools]


def test_workspace_agent_uses_workspace_prompt_tools_and_telemetry() -> None:
    agent = WorkspaceDialecticAgent(
        workspace_name="workspace-1",
        reasoning_level="minimal",
    )

    assert "workspace-level analysis agent" in agent.messages[0]["content"]
    assert _tool_names(agent._get_tools()) == [
        "get_workspace_stats",
        "get_active_peers",
        "search_memory",
        "search_messages",
    ]

    telemetry = agent._telemetry_context()
    assert telemetry.workspace_name == "workspace-1"
    assert telemetry.agent_type == "workspace_dialectic"
    assert telemetry.peer_name == WORKSPACE_PEER_NAME
    assert agent._event_peer_name() == WORKSPACE_PEER_NAME
    assert agent._performance_trace_name() == "workspace_chat"


@pytest.mark.asyncio
async def test_workspace_tool_executor_rejects_search_memory_without_peer_pair() -> None:
    executor = await create_workspace_tool_executor(workspace_name="workspace-1")

    result = await executor("search_memory", {"query": "budget"})

    assert "'observer' and 'observed' are required" in result


@pytest.mark.asyncio
async def test_workspace_tool_executor_search_messages_has_no_peer_filter() -> None:
    executor = await create_workspace_tool_executor(workspace_name="workspace-1")

    with (
        patch(
            "src.utils.agent_tools.embedding_client.embed",
            new=AsyncMock(return_value=[0.1, 0.2]),
        ),
        patch(
            "src.utils.agent_tools.crud.search_messages",
            new=AsyncMock(return_value=[]),
        ) as mock_search_messages,
    ):
        result = await executor("search_messages", {"query": "budget"})

    assert result == "No messages found for query 'budget'"
    await_args = mock_search_messages.await_args
    if await_args is None:
        raise AssertionError("expected search_messages call")
    assert await_args.kwargs["workspace_name"] == "workspace-1"
    assert await_args.kwargs["observer"] == ""
    assert await_args.kwargs["peer_name"] is None


@pytest.mark.asyncio
async def test_workspace_chat_releases_preflight_session_before_agent_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_sessions = 0

    @asynccontextmanager
    async def fake_tracked_db(
        _: str | None = None, *, read_only: bool = False
    ) -> AsyncGenerator[object, None]:
        nonlocal active_sessions
        assert read_only is True
        active_sessions += 1
        try:
            yield object()
        finally:
            active_sessions -= 1

    async def fake_get_session(*args: Any, **kwargs: Any) -> object:
        _ = (args, kwargs)
        assert active_sessions == 1
        return object()

    async def fake_answer(_self: object, query: str) -> str:
        assert query == "What changed?"
        assert active_sessions == 0
        return "ok"

    monkeypatch.setattr("src.dialectic.chat.tracked_db", fake_tracked_db)
    monkeypatch.setattr("src.dialectic.chat.crud.get_session", fake_get_session)
    monkeypatch.setattr(
        "src.dialectic.chat.WorkspaceDialecticAgent.answer", fake_answer
    )

    result = await workspace_chat("workspace", "session", "What changed?")

    assert result == "ok"


@pytest.mark.asyncio
async def test_workspace_chat_stream_releases_preflight_session_before_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_sessions = 0

    @asynccontextmanager
    async def fake_tracked_db(
        _: str | None = None, *, read_only: bool = False
    ) -> AsyncGenerator[object, None]:
        nonlocal active_sessions
        assert read_only is True
        active_sessions += 1
        try:
            yield object()
        finally:
            active_sessions -= 1

    async def fake_get_session(*args: Any, **kwargs: Any) -> object:
        _ = (args, kwargs)
        assert active_sessions == 1
        return object()

    async def fake_answer_stream(
        _self: object, query: str
    ) -> AsyncIterator[str]:
        assert query == "Stream it"
        assert active_sessions == 0
        yield "chunk-1"
        assert active_sessions == 0
        yield "chunk-2"

    monkeypatch.setattr("src.dialectic.chat.tracked_db", fake_tracked_db)
    monkeypatch.setattr("src.dialectic.chat.crud.get_session", fake_get_session)
    monkeypatch.setattr(
        "src.dialectic.chat.WorkspaceDialecticAgent.answer_stream",
        fake_answer_stream,
    )

    chunks = [
        chunk
        async for chunk in workspace_chat_stream("workspace", "session", "Stream it")
    ]

    assert chunks == ["chunk-1", "chunk-2"]
