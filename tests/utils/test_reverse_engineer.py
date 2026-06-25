from unittest.mock import AsyncMock, patch

import pytest

from src.config import ModelConfig, settings
from src.llm import HonchoLLMCallResponse
from src.utils.reverse_engineer import (
    ReverseEngineerDeduction,
    ReverseEngineerLLMResponse,
    reverse_engineer_prompt,
    reverse_engineer_trace,
)


def test_reverse_engineer_prompt_renders_conversation_and_perspective() -> None:
    prompt = reverse_engineer_prompt(
        [
            {"role": "user", "content": "Alice likes pilsners."},
            {"role": "assistant", "content": "A lager would also work."},
        ],
        "What beer was recommended?",
        "A pilsner or lager.",
        observer="alice",
        observed="assistant",
    )

    assert "USER: Alice likes pilsners." in prompt
    assert "ASSISTANT: A lager would also work." in prompt
    assert "The question is asked by alice about assistant." in prompt
    assert "What beer was recommended?" in prompt
    assert '"deductions"' in prompt


def test_reverse_engineer_prompt_handles_empty_messages() -> None:
    prompt = reverse_engineer_prompt([], "question", "answer")

    assert "(no messages provided)" in prompt
    assert "question" in prompt
    assert "answer" in prompt


@pytest.mark.asyncio
async def test_reverse_engineer_trace_uses_current_llm_api_and_maps_response() -> None:
    llm_response = HonchoLLMCallResponse(
        content=ReverseEngineerLLMResponse(
            explicit=["The assistant recommended pilsner."],
            implicit=["Pilsner is a beer style."],
            deductions=[
                ReverseEngineerDeduction(
                    premises=["The assistant recommended pilsner."],
                    conclusion="Pilsner answers the user's beer question.",
                )
            ],
            observer_card=["Name: Alice"],
            observed_card=["Role: assistant"],
        ),
        input_tokens=10,
        output_tokens=20,
        finish_reasons=["stop"],
    )

    with patch(
        "src.utils.reverse_engineer.honcho_llm_call",
        new=AsyncMock(return_value=llm_response),
    ) as mock_llm_call:
        trace = await reverse_engineer_trace(
            [{"role": "user", "content": "What beer should I use?"}],
            "What beer was recommended?",
            "Pilsner.",
            observer="alice",
            observed="assistant",
        )

    assert [item.content for item in trace.explicit] == [
        "The assistant recommended pilsner."
    ]
    assert [item.content for item in trace.implicit] == ["Pilsner is a beer style."]
    assert trace.deductive[0].premises == ["The assistant recommended pilsner."]
    assert trace.deductive[0].conclusion == (
        "Pilsner answers the user's beer question."
    )
    assert trace.observer_card == ["Name: Alice"]
    assert trace.observed_card == ["Role: assistant"]

    await_args = mock_llm_call.await_args
    if await_args is None:
        raise AssertionError("expected reverse-engineer LLM call")
    kwargs = await_args.kwargs
    assert kwargs["model_config"] == settings.DERIVER.MODEL_CONFIG
    assert kwargs["max_tokens"] == (
        settings.DERIVER.MODEL_CONFIG.max_output_tokens
        or settings.LLM.DEFAULT_MAX_TOKENS
    )
    assert kwargs["response_model"] is ReverseEngineerLLMResponse
    assert kwargs["json_mode"] is True
    assert kwargs["track_name"] == "Reverse Engineer Trace"
    assert kwargs["max_input_tokens"] == settings.DERIVER.MAX_INPUT_TOKENS
    assert kwargs["request_metadata"] == {"namespace": settings.NAMESPACE}


@pytest.mark.asyncio
async def test_reverse_engineer_trace_accepts_model_config_override() -> None:
    model_config = ModelConfig(model="custom-model", transport="openai")
    llm_response = HonchoLLMCallResponse(
        content=ReverseEngineerLLMResponse(),
        input_tokens=1,
        output_tokens=1,
        finish_reasons=["stop"],
    )

    with patch(
        "src.utils.reverse_engineer.honcho_llm_call",
        new=AsyncMock(return_value=llm_response),
    ) as mock_llm_call:
        await reverse_engineer_trace(
            [{"role": "user", "content": "hello"}],
            "question",
            "answer",
            model_config=model_config,
            max_tokens=123,
            max_input_tokens=456,
        )

    await_args = mock_llm_call.await_args
    if await_args is None:
        raise AssertionError("expected reverse-engineer LLM call")
    assert await_args.kwargs["model_config"] == model_config
    assert await_args.kwargs["max_tokens"] == 123
    assert await_args.kwargs["max_input_tokens"] == 456
