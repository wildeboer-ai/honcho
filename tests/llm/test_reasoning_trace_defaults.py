from unittest.mock import AsyncMock, patch

import pytest

from src.config import ModelConfig
from src.llm.api import honcho_llm_call
from src.llm.types import HonchoLLMCallResponse


def _response() -> HonchoLLMCallResponse[str]:
    return HonchoLLMCallResponse(
        content="ok",
        input_tokens=3,
        output_tokens=2,
        finish_reasons=["stop"],
    )


@pytest.mark.asyncio
async def test_toolless_call_logs_untagged_trace_without_trace_name() -> None:
    config = ModelConfig(model="gpt-4.1-mini", transport="openai")
    response = _response()

    with (
        patch.dict("src.llm.registry.CLIENTS", {"openai": object()}),
        patch(
            "src.llm.api.honcho_llm_call_inner",
            new=AsyncMock(return_value=response),
        ),
        patch("src.llm.api.log_reasoning_trace") as mock_trace,
    ):
        result = await honcho_llm_call(
            model_config=config,
            prompt="hello",
            max_tokens=16,
            enable_retry=False,
        )

    assert result is response
    mock_trace.assert_called_once()
    assert mock_trace.call_args.kwargs["task_type"] == "untagged"


@pytest.mark.asyncio
async def test_tool_loop_call_logs_untagged_trace_without_trace_name() -> None:
    config = ModelConfig(model="gpt-4.1-mini", transport="openai")
    response = _response()

    async def tool_executor(_name: str, _arguments: dict[str, object]) -> object:
        return {}

    with (
        patch(
            "src.llm.api.execute_tool_loop",
            new=AsyncMock(return_value=response),
        ),
        patch("src.llm.api.log_reasoning_trace") as mock_trace,
    ):
        result = await honcho_llm_call(
            model_config=config,
            prompt="hello",
            max_tokens=16,
            tools=[{"name": "noop"}],
            tool_executor=tool_executor,
            enable_retry=False,
        )

    assert result is response
    mock_trace.assert_called_once()
    assert mock_trace.call_args.kwargs["task_type"] == "untagged"
