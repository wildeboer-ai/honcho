from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx
from pydantic import BaseModel

from src.exceptions import ValidationException
from src.llm.backend import CompletionResult, StreamChunk, ToolCallResult
from src.llm.structured_output import repair_response_model_json
from src.local_transport import local_ollama_url


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationException("Native Ollama returned a non-object response")
    return cast(dict[str, Any], value)


def _content(message: dict[str, Any]) -> str:
    value = message.get("content", "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationException("Native Ollama returned non-text content")
    return value


def _arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationException(
                "Native Ollama returned malformed tool arguments"
            ) from exc
    if not isinstance(value, dict):
        raise ValidationException("Native Ollama tool arguments must be an object")
    return cast(dict[str, Any], value)


class OllamaBackend:
    """Provider backend wrapping Ollama's local HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Explicit direct adapter; the registry retains its OpenAI-compatible route.

        An injected transport is a trusted caller dependency (used by offline
        tests). No endpoint, credentials, proxy or runtime is selected implicitly.
        """
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=local_ollama_url(base_url),
            timeout=120.0,
            trust_env=False,
            follow_redirects=False,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float | None = None,
        stop: list[str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        response_format: type[BaseModel] | dict[str, Any] | None = None,
        thinking_budget_tokens: int | None = None,
        thinking_effort: str | None = None,
        max_output_tokens: int | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> CompletionResult:
        del thinking_budget_tokens, thinking_effort

        request = self._build_request(
            model=model,
            messages=messages,
            max_tokens=max_output_tokens or max_tokens,
            temperature=temperature,
            stop=stop,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            stream=False,
            extra_params=extra_params,
        )
        response = await self._client.post("/api/chat", json=request)
        response.raise_for_status()
        payload = _object(response.json())
        return self._normalize_response(
            payload,
            response_format=response_format
            if isinstance(response_format, type)
            else None,
            model=model,
            tools=None if tool_choice == "none" else tools,
        )

    async def stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float | None = None,
        stop: list[str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        response_format: type[BaseModel] | dict[str, Any] | None = None,
        thinking_budget_tokens: int | None = None,
        thinking_effort: str | None = None,
        max_output_tokens: int | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        del thinking_budget_tokens, thinking_effort

        request = self._build_request(
            model=model,
            messages=messages,
            max_tokens=max_output_tokens or max_tokens,
            temperature=temperature,
            stop=stop,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            stream=True,
            extra_params=extra_params,
        )
        if tools:
            raise ValidationException("Native Ollama tool streaming is not supported")
        finish_reason = "stop"
        output_tokens = 0
        completed = False
        async with self._client.stream("POST", "/api/chat", json=request) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                payload = _object(json.loads(line))
                if "error" in payload:
                    raise ValidationException(
                        "Native Ollama returned an error response"
                    )
                message = _object(payload.get("message", {}))
                if message.get("tool_calls"):
                    raise ValidationException(
                        "Native Ollama tool streaming is not supported"
                    )
                content = _content(message)
                if content:
                    yield StreamChunk(content=content)
                if payload.get("eval_count"):
                    output_tokens = int(payload["eval_count"])
                if payload.get("done") is True:
                    completed = True
                    if payload.get("done_reason"):
                        finish_reason = str(payload["done_reason"])
                    break
        if not completed:
            raise ValidationException("Native Ollama stream ended without completion")
        yield StreamChunk(
            is_done=True,
            finish_reason=finish_reason,
            output_tokens=output_tokens or None,
        )

    def _build_request(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        temperature: float | None,
        stop: list[str] | None,
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
        response_format: type[BaseModel] | dict[str, Any] | None,
        stream: bool,
        extra_params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "options": {"num_predict": max_tokens},
        }
        if temperature is not None:
            request["options"]["temperature"] = temperature
        if stop:
            request["options"]["stop"] = stop
        if tool_choice not in (None, "auto", "none"):
            raise ValidationException(
                "Native Ollama cannot enforce required tool choice"
            )
        if tools and tool_choice != "none":
            request["tools"] = self._convert_tools(tools)
            # Ollama's native chat endpoint does not support OpenAI's
            # tool_choice field. The tool list still gives capable models the
            # affordance; required-tool policy belongs in the caller.
            del tool_choice

        if isinstance(response_format, type):
            request["format"] = response_format.model_json_schema()
        elif isinstance(response_format, dict):
            request["format"] = response_format
        elif extra_params and extra_params.get("json_mode"):
            request["format"] = "json"

        if extra_params:
            options = request.setdefault("options", {})
            for key in ("top_p", "top_k", "seed"):
                if key in extra_params:
                    options[key] = extra_params[key]
            for key, value in extra_params.items():
                if key.startswith("ollama_option__"):
                    options[key.removeprefix("ollama_option__")] = value
        return request

    def _normalize_response(
        self,
        payload: dict[str, Any],
        *,
        response_format: type[BaseModel] | None,
        model: str,
        tools: list[dict[str, Any]] | None,
    ) -> CompletionResult:
        if "error" in payload or payload.get("done") is not True:
            raise ValidationException(
                "Native Ollama response did not complete successfully"
            )
        message = _object(payload.get("message"))
        if "content" not in message and not message.get("tool_calls"):
            raise ValidationException(
                "Native Ollama response has no message content or tools"
            )
        raw_content = _content(message) or ""
        content: Any = raw_content
        tool_calls = self._normalize_tool_calls(message.get("tool_calls"))
        if tools and not tool_calls:
            tool_calls = self._normalize_tool_calls_from_content(raw_content)
            if tool_calls:
                content = ""
        if tool_calls:
            allowed = {
                tool["function"]["name"] for tool in self._convert_tools(tools or [])
            }
            if any(call.name not in allowed for call in tool_calls):
                raise ValidationException(
                    "Native Ollama returned an unrequested tool call"
                )
        if response_format is not None:
            if not raw_content:
                raise ValidationException("No content returned for structured output")
            content = repair_response_model_json(raw_content, response_format, model)

        return CompletionResult(
            content=content,
            input_tokens=int(payload.get("prompt_eval_count") or 0),
            output_tokens=int(payload.get("eval_count") or 0),
            finish_reason=str(payload.get("done_reason") or "stop"),
            tool_calls=tool_calls,
            raw_response=payload,
        )

    @staticmethod
    def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not tools or tools[0].get("type") == "function":
            return tools
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            }
            for tool in tools
        ]

    @staticmethod
    def _normalize_tool_calls(raw_tool_calls: Any) -> list[ToolCallResult]:
        if raw_tool_calls is None:
            return []
        if not isinstance(raw_tool_calls, list):
            raise ValidationException("Native Ollama tool calls must be a list")
        calls: list[ToolCallResult] = []
        for index, value in enumerate(cast(list[Any], raw_tool_calls)):
            raw_call = _object(value)
            function = _object(raw_call.get("function"))
            name = function.get("name")
            if not isinstance(name, str) or not name:
                raise ValidationException(
                    "Native Ollama returned a tool without a name"
                )
            calls.append(
                ToolCallResult(
                    id=str(raw_call.get("id") or f"ollama-tool-{index}"),
                    name=name,
                    input=_arguments(function.get("arguments", {})),
                )
            )
        return calls

    @staticmethod
    def _normalize_tool_calls_from_content(content: str) -> list[ToolCallResult]:
        """Parse Ollama template-emitted JSON tool calls from message text.

        Some Ollama model templates ask the model to emit a plain JSON object
        like ``{"name": "...", "parameters": {...}}`` instead of returning the
        newer ``message.tool_calls`` shape. Treat only whole-message JSON as a
        tool call so ordinary prose containing JSON is left untouched.
        """
        stripped = content.strip()
        if not stripped:
            return []

        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError:
            return []

        raw_calls: list[Any] = cast(list[Any], raw) if isinstance(raw, list) else [raw]
        tool_calls: list[ToolCallResult] = []
        for index, raw_call in enumerate(raw_calls):
            if not isinstance(raw_call, dict):
                continue
            raw_call = _object(raw_call)
            name = raw_call.get("name")
            if not isinstance(name, str) or not name:
                continue
            arguments = _arguments(
                raw_call.get("arguments", raw_call.get("parameters", {}))
            )
            tool_calls.append(
                ToolCallResult(
                    id=str(raw_call.get("id") or f"ollama-tool-text-{index}"),
                    name=name,
                    input=arguments,
                )
            )
        return tool_calls
