"""Reverse-engineer a minimal reasoning trace from a known answer.

This utility is intended for offline evaluation and training-data generation:
given a conversation, a question, and the accepted answer, it asks the deriver
model for the smallest set of explicit facts, implied facts, deductions, and
peer-card entries sufficient to support that answer.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field, field_validator

from src.config import ConfiguredModelSettings, ModelConfig, settings
from src.llm import HonchoLLMCallResponse, honcho_llm_call
from src.utils.representation import DeductiveObservationBase, ExplicitObservationBase

logger = logging.getLogger(__name__)


class ReverseEngineerDeduction(BaseModel):
    """A deduction produced by reverse-engineering an answer trace."""

    premises: list[str] = Field(default_factory=list)
    conclusion: str


class ReverseEngineerLLMResponse(BaseModel):
    """Structured response requested from the LLM."""

    explicit: list[str] = Field(default_factory=list)
    implicit: list[str] = Field(default_factory=list)
    deductions: list[ReverseEngineerDeduction] = Field(default_factory=list)
    observer_card: list[str] | None = None
    observed_card: list[str] | None = None

    @field_validator("explicit", "implicit", "deductions", mode="before")
    @classmethod
    def _none_to_empty_list(cls, value: Any) -> Any:
        if value is None:
            return []
        return value


class ReverseEngineerTrace(BaseModel):
    """Current-code representation of the reverse-engineered trace."""

    explicit: list[ExplicitObservationBase] = Field(default_factory=list)
    implicit: list[ExplicitObservationBase] = Field(default_factory=list)
    deductive: list[DeductiveObservationBase] = Field(default_factory=list)
    observer_card: list[str] | None = None
    observed_card: list[str] | None = None

    @classmethod
    def from_llm_response(
        cls, response: ReverseEngineerLLMResponse
    ) -> ReverseEngineerTrace:
        return cls(
            explicit=[
                ExplicitObservationBase(content=content)
                for content in response.explicit
            ],
            implicit=[
                ExplicitObservationBase(content=content)
                for content in response.implicit
            ],
            deductive=[
                DeductiveObservationBase(
                    premises=deduction.premises,
                    conclusion=deduction.conclusion,
                )
                for deduction in response.deductions
            ],
            observer_card=response.observer_card,
            observed_card=response.observed_card,
        )


def _message_value(message: Mapping[str, Any], key: str, default: str) -> str:
    value = message.get(key)
    if value is None:
        return default
    return str(value)


def _format_messages(messages: Sequence[Mapping[str, Any]]) -> str:
    lines: list[str] = []
    for message in messages:
        role = _message_value(message, "role", "message").strip() or "message"
        content = _message_value(message, "content", "").strip()
        if content:
            lines.append(f"{role.upper()}: {content}")
    if not lines:
        return "(no messages provided)"
    return "\n\n".join(lines)


def reverse_engineer_prompt(
    messages: Sequence[Mapping[str, Any]],
    question: str,
    answer: str,
    *,
    observer: str | None = None,
    observed: str | None = None,
) -> str:
    """Build the prompt used to reverse-engineer a minimal answer trace."""

    perspective_context = ""
    if observer and observed:
        if observer == observed:
            perspective_context = (
                f"\nThe conversation involves {observer} observing themselves."
            )
        else:
            perspective_context = f"\nThe question is asked by {observer} about {observed}."

    observer_label = observer or "the observer"
    observed_label = observed or "the observed"

    return f"""You are a knowledge extraction system that reverse-engineers the MINIMAL set of observations needed to answer a question.

# Conversation History
{_format_messages(messages)}
{perspective_context}

# Question
{question}

# Correct Answer
{answer}

# Task
Extract the MINIMAL set of atomic propositions, deductions, and peer biographical information from the conversation that would be sufficient to answer the question correctly.

Follow these rules:
- Extract explicit atomic propositions directly stated in the conversation.
- Extract implicit atomic propositions only when they are certainly implied, not speculative.
- Generate deductions only when the conclusion necessarily follows from the premises.
- Include only facts and deductions needed to support the correct answer.
- Extract peer-card entries only from conversation messages, never from the supplied answer.
- Prefer permanent biographical entries over transient events.
- Use null for peer-card fields when no relevant information exists.
- For self-queries where observer and observed are the same peer, populate only observer_card.

Return JSON with these keys:
- "explicit": array of explicit atomic proposition strings.
- "implicit": array of implicit atomic proposition strings.
- "deductions": array of objects with "premises" and "conclusion".
- "observer_card": array of biographical strings for {observer_label}, or null.
- "observed_card": array of biographical strings for {observed_label}, or null.
"""


async def reverse_engineer_trace(
    messages: Sequence[Mapping[str, Any]],
    question: str,
    answer: str,
    *,
    observer: str | None = None,
    observed: str | None = None,
    model_config: ConfiguredModelSettings | ModelConfig | None = None,
    max_tokens: int | None = None,
    max_input_tokens: int | None = None,
) -> ReverseEngineerTrace:
    """Call the deriver model and return a reverse-engineered answer trace."""

    selected_model_config = model_config or settings.DERIVER.MODEL_CONFIG
    selected_max_tokens = (
        max_tokens
        or selected_model_config.max_output_tokens
        or settings.LLM.DEFAULT_MAX_TOKENS
    )

    response: HonchoLLMCallResponse[ReverseEngineerLLMResponse] = (
        await honcho_llm_call(
            model_config=selected_model_config,
            prompt=reverse_engineer_prompt(
                messages,
                question,
                answer,
                observer=observer,
                observed=observed,
            ),
            max_tokens=selected_max_tokens,
            track_name="Reverse Engineer Trace",
            response_model=ReverseEngineerLLMResponse,
            json_mode=True,
            max_input_tokens=max_input_tokens or settings.DERIVER.MAX_INPUT_TOKENS,
            enable_retry=True,
            retry_attempts=3,
            trace_name="reverse_engineer_trace",
            request_metadata={"namespace": settings.NAMESPACE},
        )
    )

    trace = ReverseEngineerTrace.from_llm_response(response.content)
    logger.debug(
        "Reverse engineered trace: %d explicit, %d implicit, %d deductive, observer_card=%s, observed_card=%s",
        len(trace.explicit),
        len(trace.implicit),
        len(trace.deductive),
        trace.observer_card is not None,
        trace.observed_card is not None,
    )
    return trace


__all__ = [
    "ReverseEngineerDeduction",
    "ReverseEngineerLLMResponse",
    "ReverseEngineerTrace",
    "reverse_engineer_prompt",
    "reverse_engineer_trace",
]
