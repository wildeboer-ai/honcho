"""Fictional HTTP and caller-owned observation fixtures; no service or SDK effects."""

import json
from unittest.mock import Mock

import httpx
import pytest
from pydantic import BaseModel

from src import langfuse_config as tracing
from src.config import ConfiguredModelSettings, LLMSettings, ModelConfig, settings
from src.exceptions import ValidationException
from src.llm.backends.ollama import OllamaBackend
from src.llm.registry import backend_for_provider, client_for_model_config


class Answer(BaseModel):
    answer: str


@pytest.fixture
def local_policy(monkeypatch):
    for section in (settings.LLM, settings.DERIVER, settings.DIALECTIC):
        monkeypatch.setattr(section, "LOCAL_ONLY", False)


@pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini"])
def test_global_local_policy_guards_both_factories(provider, monkeypatch, local_policy):
    monkeypatch.setattr(settings.LLM, "LOCAL_ONLY", True)
    with pytest.raises(ValidationException, match="Local-only"):
        client_for_model_config(
            provider, ModelConfig(model="fictional", transport=provider)
        )
    with pytest.raises(ValidationException, match="Local-only"):
        backend_for_provider(provider, object())


def test_global_setting_and_ollama_prefix(monkeypatch):
    monkeypatch.setenv("LLM_LOCAL_ONLY", "true")
    assert LLMSettings().LOCAL_ONLY is True
    configured = ConfiguredModelSettings(model="ollama/fictional")
    assert configured.transport == "ollama" and configured.model == "fictional"


def test_global_endpoint_checked_before_client_construction(monkeypatch, local_policy):
    from src.llm import registry

    monkeypatch.setattr(settings.LLM, "OLLAMA_BASE_URL", "https://remote.invalid")
    constructor = Mock(side_effect=AssertionError("client created"))
    monkeypatch.setattr(registry, "AsyncOpenAI", constructor)
    registry.get_ollama_client.cache_clear()
    with pytest.raises(ValueError, match="local HTTP"):
        client_for_model_config(
            "ollama", ModelConfig(model="fictional", transport="ollama")
        )
    constructor.assert_not_called()


@pytest.mark.parametrize(
    "base_url",
    [
        "https://remote.invalid",
        "http://user:pass@localhost:11434",
        "http://localhost:11434/proxy",
        "http://localhost:11434?token=x",
    ],
)
def test_direct_backend_rejects_unbound_endpoints(base_url):
    with pytest.raises(ValueError, match="local HTTP"):
        OllamaBackend(base_url=base_url)


@pytest.mark.asyncio
async def test_actual_native_http_schema_options_and_usage(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://forbidden.invalid")
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"answer":"fictional"}'},
                "prompt_eval_count": 7,
                "eval_count": 3,
                "done_reason": "stop",
                "done": True,
            },
        )

    backend = OllamaBackend(
        base_url="http://localhost:11434/v1", transport=httpx.MockTransport(respond)
    )
    try:
        result = await backend.complete(
            model="fictional",
            messages=[{"role": "user", "content": "fictional prompt"}],
            max_tokens=10,
            response_format=Answer,
            temperature=0,
            extra_params={"ollama_option__top_k": 3},
        )
        assert result.content == Answer(answer="fictional")
        assert (result.input_tokens, result.output_tokens) == (7, 3)
        request = requests.pop()
        assert str(request.url) == "http://localhost:11434/api/chat"
        assert "authorization" not in request.headers
        body = json.loads(request.content)
        assert body["format"]["title"] == "Answer"
        assert body["options"] == {"num_predict": 10, "temperature": 0, "top_k": 3}
    finally:
        await backend.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("native", [True, False])
async def test_native_and_whole_text_tool_calls(native):
    call = {"name": "search", "arguments": {"query": "fictional"}}
    message = (
        {"tool_calls": [{"function": call}]}
        if native
        else {"content": json.dumps(call)}
    )
    backend = OllamaBackend(
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"done": True, "message": message})
        ),
    )
    tools = [
        {
            "name": "search",
            "description": "source search",
            "input_schema": {"type": "object"},
        }
    ]
    try:
        result = await backend.complete(
            model="fictional", messages=[], max_tokens=10, tools=tools
        )
        assert result.tool_calls[0].name == "search"
        assert result.tool_calls[0].input == {"query": "fictional"}
    finally:
        await backend.aclose()


@pytest.mark.asyncio
async def test_no_tools_keeps_json_text_and_required_tools_refuse():
    text = '{"name":"search", "arguments":{}}'
    seen = []

    def respond(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"done": True, "message": {"content": text}})

    backend = OllamaBackend(
        base_url="http://localhost:11434", transport=httpx.MockTransport(respond)
    )
    try:
        for tools, choice in [(None, None), ([{"name": "search"}], "none")]:
            result = await backend.complete(
                model="fictional",
                messages=[],
                max_tokens=10,
                tools=tools,
                tool_choice=choice,
            )
            assert result.content == text and not result.tool_calls
            assert "tools" not in seen[-1]
        with pytest.raises(ValidationException, match="required tool"):
            await backend.complete(
                model="fictional", messages=[], max_tokens=10, tool_choice="required"
            )
        assert len(seen) == 2
    finally:
        await backend.aclose()


@pytest.mark.asyncio
async def test_native_stream_completion_and_truncation():
    for completed in (True, False):
        rows = [{"message": {"content": "first"}}, {"message": {"content": "second"}}]
        if completed:
            rows.append({"done": True, "done_reason": "length", "eval_count": 4})
        body = "\n".join(json.dumps(row) for row in rows)
        backend = OllamaBackend(
            base_url="http://localhost:11434",
            transport=httpx.MockTransport(
                lambda request, body=body: httpx.Response(200, text=body)
            ),
        )
        try:
            chunks = []
            if not completed:
                with pytest.raises(ValidationException, match="without completion"):
                    async for chunk in backend.stream(
                        model="fictional", messages=[], max_tokens=10
                    ):
                        chunks.append(chunk)
                assert not any(chunk.is_done for chunk in chunks)
            else:
                chunks = [
                    chunk
                    async for chunk in backend.stream(
                        model="fictional", messages=[], max_tokens=10
                    )
                ]
                assert "".join(chunk.content for chunk in chunks) == "firstsecond"
                assert (
                    chunks[-1].is_done
                    and chunks[-1].finish_reason == "length"
                    and chunks[-1].output_tokens == 4
                )
        finally:
            await backend.aclose()


@pytest.mark.asyncio
async def test_native_redirect_error_and_unsupported_tool_stream():
    seen = []

    def respond(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://forbidden.invalid"})

    backend = OllamaBackend(
        base_url="http://localhost:11434", transport=httpx.MockTransport(respond)
    )
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await backend.complete(model="fictional", messages=[], max_tokens=10)
        with pytest.raises(ValidationException, match="tool streaming"):
            _ = [
                chunk
                async for chunk in backend.stream(
                    model="fictional",
                    messages=[],
                    max_tokens=10,
                    tools=[{"name": "search", "description": "x", "input_schema": {}}],
                )
            ]
        assert len(seen) == 1
    finally:
        await backend.aclose()


def test_tracing_default_off_even_with_supplied_client():
    client = Mock(side_effect=AssertionError("effect"))
    assert tracing.langfuse(client=client) is None
    assert (
        tracing.trace_llm_call("run", "model", "prompt", "response", client=client)
        is None
    )
    with tracing.trace_span("run", client=client):
        pass
    assert client.mock_calls == []


@pytest.mark.parametrize("section", ["LLM", "DERIVER", "DIALECTIC"])
def test_tracing_local_policy_suppresses_both_helpers(
    section, monkeypatch, local_policy
):
    monkeypatch.setattr(getattr(settings, section), "LOCAL_ONLY", True)
    client = Mock()
    assert (
        tracing.trace_llm_call(
            "run", "model", "prompt", "response", client=client, enabled=True
        )
        is None
    )
    with tracing.trace_span("run", client=client, enabled=True):
        pass
    assert client.mock_calls == []


def test_explicit_v3_generation_fields_and_cleanup(local_policy):
    client = Mock()
    span = client.start_observation.return_value
    generation = span.start_observation.return_value
    assert tracing.trace_llm_call(
        "run",
        "fictional",
        "prompt",
        "response",
        7,
        3,
        {"fixture": True},
        client=client,
        enabled=True,
    ) == (span, generation)
    client.start_observation.assert_called_once_with(name="run", as_type="span")
    span.start_observation.assert_called_once_with(
        name="fictional_call",
        as_type="generation",
        model="fictional",
        input="prompt",
        output="response",
        usage_details={"input": 7, "output": 3},
        metadata={"fixture": True},
    )
    generation.end.assert_called_once()
    span.end.assert_called_once()
    span.reset_mock()
    span.start_observation.side_effect = RuntimeError("fixture failure")
    with pytest.raises(RuntimeError, match="fixture failure"):
        tracing.trace_llm_call(
            "run", "model", "prompt", "response", client=client, enabled=True
        )
    span.end.assert_called_once()


def test_explicit_span_and_missing_client_refusal(local_policy):
    with pytest.raises(ValueError, match="explicitly configured"):
        tracing.get_langfuse_client(enabled=True)
    client = Mock()
    assert (
        tracing.trace_span("run", {"fixture": True}, client=client, enabled=True)
        is client.start_as_current_observation.return_value
    )
    client.start_as_current_observation.assert_called_once_with(
        name="run", as_type="span", metadata={"fixture": True}
    )


def test_global_policy_suppresses_existing_observers(monkeypatch, local_policy):
    from src.llm import runtime
    from src.telemetry import logging

    monkeypatch.setattr(settings.LLM, "LOCAL_ONLY", True)
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "fictional")
    observe = Mock(side_effect=AssertionError("observe"))
    monkeypatch.setattr(logging, "observe", observe)

    def function():
        return "local"

    assert logging.conditional_observe(function) is function
    assert observe.mock_calls == []
    import langfuse

    get_client = Mock(side_effect=AssertionError("ambient Langfuse client"))
    monkeypatch.setattr(langfuse, "get_client", get_client)
    runtime.update_current_langfuse_observation("ollama", "fictional")
    get_client.assert_not_called()


def test_summary_route_from_compose_uses_explicit_local_model(
    monkeypatch, local_policy
):
    from pathlib import Path

    from src.config import SummarySettings

    text = Path("docker-compose.yml.example").read_text()
    api = text.split("  api:", 1)[1].split("  deriver:", 1)[0]
    deriver = text.split("  deriver:", 1)[1].split("  reconcile", 1)[0]
    for service in (api, deriver):
        values = {}
        for line in service.splitlines():
            prefix = "      - SUMMARY_MODEL_CONFIG__"
            if line.startswith(prefix):
                key, value = line.strip()[2:].split("=", 1)
                if "${" in value:
                    assert (
                        value
                        == "${HONCHO_LOCAL_SUMMARY_MODEL:?set HONCHO_LOCAL_SUMMARY_MODEL in .env}"
                    )
                    value = "fictional-installed-summary"
                values[key] = value
        assert len(values) == 3
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        configured = SummarySettings().MODEL_CONFIG
        assert configured.transport == "ollama"
        assert configured.model == "fictional-installed-summary"
        assert configured.overrides.base_url == "http://host.docker.internal:11434"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload", [["invalid"], {"message": []}, {"message": {"content": 7}}]
)
async def test_native_malformed_response_is_not_success(payload):
    backend = OllamaBackend(
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)
        ),
    )
    try:
        with pytest.raises(ValidationException):
            await backend.complete(model="fictional", messages=[], max_tokens=10)
    finally:
        await backend.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"done": False, "message": {"content": "partial"}},
        {"message": {"content": "missing completion"}},
        {"done": True},
        {"done": True, "message": {}},
        {"done": True, "message": {"content": "ignored"}, "error": "fixture failure"},
    ],
)
async def test_native_incomplete_or_error_envelope_refuses(payload):
    backend = OllamaBackend(
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)
        ),
    )
    try:
        with pytest.raises(ValidationException):
            await backend.complete(model="fictional", messages=[], max_tokens=10)
    finally:
        await backend.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("choice,declared", [("none", True), (None, False)])
async def test_native_unrequested_tool_calls_refuse(choice, declared):
    payload = {
        "done": True,
        "message": {"tool_calls": [{"function": {"name": "search", "arguments": {}}}]},
    }
    tools = (
        [{"type": "function", "function": {"name": "search", "parameters": {}}}]
        if declared
        else None
    )
    backend = OllamaBackend(
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)
        ),
    )
    try:
        with pytest.raises(ValidationException, match="unrequested tool"):
            await backend.complete(
                model="fictional",
                messages=[],
                max_tokens=10,
                tools=tools,
                tool_choice=choice,
            )
    finally:
        await backend.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ["invalid-json", "[]", [], None, 7, ""])
@pytest.mark.parametrize("native", [True, False])
async def test_native_malformed_tool_arguments_refuse(arguments, native):
    call = {"name": "search", "arguments": arguments}
    message = (
        {"tool_calls": [{"function": call}]}
        if native
        else {"content": json.dumps(call)}
    )
    payload = {"done": True, "message": message}
    backend = OllamaBackend(
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)
        ),
    )
    try:
        with pytest.raises(ValidationException, match="arguments"):
            await backend.complete(
                model="fictional",
                messages=[],
                max_tokens=10,
                tools=[
                    {
                        "type": "function",
                        "function": {"name": "search", "parameters": {}},
                    }
                ],
            )
    finally:
        await backend.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row",
    [
        {"done": True, "error": "fixture failure"},
        {
            "done": True,
            "message": {
                "tool_calls": [{"function": {"name": "search", "arguments": {}}}]
            },
        },
    ],
)
async def test_native_error_or_tool_stream_refuses(row):
    body = json.dumps(row)
    backend = OllamaBackend(
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body)),
    )
    try:
        with pytest.raises(ValidationException):
            _ = [
                chunk
                async for chunk in backend.stream(
                    model="fictional", messages=[], max_tokens=10
                )
            ]
    finally:
        await backend.aclose()
