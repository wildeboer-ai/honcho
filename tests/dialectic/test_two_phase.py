import time
from unittest.mock import AsyncMock, patch

import pytest

from src.config import ConfiguredModelSettings, settings
from src.dialectic.core import DialecticAgent
from src.llm import HonchoLLMCallResponse


@pytest.mark.asyncio
async def test_dialectic_answer_uses_configured_two_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synthesis_config = ConfiguredModelSettings(
        transport="anthropic",
        model="claude-opus-4-5",
        thinking_budget_tokens=1024,
        max_output_tokens=4096,
    )
    monkeypatch.setattr(
        settings.DIALECTIC.LEVELS["medium"],
        "SYNTHESIS_MODEL_CONFIG",
        synthesis_config,
    )
    agent = DialecticAgent(
        workspace_name="workspace",
        session_name="session",
        observer="observer",
        observed="observed",
        reasoning_level="medium",
    )
    search_response = HonchoLLMCallResponse(
        content="search notes",
        input_tokens=100,
        output_tokens=20,
        cache_read_input_tokens=3,
        cache_creation_input_tokens=4,
        finish_reasons=["stop"],
        tool_calls_made=[{"name": "search_memory", "input": {}}],
        iterations=2,
        messages=[
            {"role": "system", "content": "system"},
            {"role": "user", "content": "Query: what?"},
            {"role": "assistant", "content": "search notes"},
        ],
    )
    synthesis_response = HonchoLLMCallResponse(
        content="final answer",
        input_tokens=50,
        output_tokens=10,
        finish_reasons=["stop"],
        iterations=1,
    )

    with (
        patch.object(
            DialecticAgent,
            "_prepare_query",
            new=AsyncMock(
                return_value=(AsyncMock(), "task", "run", time.perf_counter())
            ),
        ),
        patch.object(DialecticAgent, "_log_response_metrics") as mock_log,
        patch(
            "src.dialectic.core.honcho_llm_call",
            new=AsyncMock(side_effect=[search_response, synthesis_response]),
        ) as mock_llm_call,
    ):
        result = await agent.answer("What do you know?")

    assert result == "final answer"
    assert mock_llm_call.await_count == 2
    search_kwargs = mock_llm_call.await_args_list[0].kwargs
    synthesis_kwargs = mock_llm_call.await_args_list[1].kwargs
    assert search_kwargs["model_config"] == settings.DIALECTIC.LEVELS[
        "medium"
    ].MODEL_CONFIG
    assert search_kwargs["tools"]
    assert synthesis_kwargs["model_config"] == synthesis_config
    assert synthesis_kwargs.get("tools") is None
    assert "search notes" in synthesis_kwargs["messages"][-1]["content"]

    log_kwargs = mock_log.call_args.kwargs
    assert log_kwargs["two_phase_mode"] is True
    assert log_kwargs["input_tokens"] == 150
    assert log_kwargs["output_tokens"] == 30
    assert log_kwargs["tool_calls_count"] == 1
    assert [phase.phase_name for phase in log_kwargs["phases"]] == [
        "search",
        "synthesis",
    ]


def test_synthesis_message_builder_serializes_tool_results() -> None:
    agent = DialecticAgent(
        workspace_name="workspace",
        session_name="session",
        observer="observer",
        observed="observed",
    )

    messages = agent._build_synthesis_messages(  # pyright: ignore[reportPrivateUsage]
        [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "Query: status?"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "search_memory", "input": {"q": "x"}}
                ],
            },
            {"role": "tool", "tool_call_id": "tool-1", "content": {"answer": "yes"}},
        ],
        "fallback",
    )

    assert messages[0] == {"role": "system", "content": "system"}
    synthesis_prompt = messages[-1]["content"]
    assert "[TOOL CALL: search_memory]" in synthesis_prompt
    assert "[TOOL RESULT (tool-1)]" in synthesis_prompt
    assert '"answer": "yes"' in synthesis_prompt
