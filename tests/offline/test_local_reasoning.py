"""Actual settings, registry and HTTP adapters with fictional transports only."""

import argparse
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from scripts import reconcile_message_vectors_local as reconcile
from src.config import (
    ConfiguredModelSettings,
    DeriverSettings,
    EmbeddingModelConfig,
    ModelConfig,
    settings,
)
from src.embedding_client import _EmbeddingClient
from src.llm import registry
from src.local_transport import local_ollama_url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid",
        "http://remote.invalid",
        "http://u:p@localhost",
        "http://localhost?key=x",
        "http://localhost#x",
        "http://localhost/else",
        "http://localhost:0",
        "http://localhost:70000",
        "http://localhost\n",
        "",
    ],
)
def test_endpoint_rejects_remote_credential_ambiguous_paths(url):
    with pytest.raises(ValueError):
        local_ollama_url(url)
    with pytest.raises(ValueError):
        _EmbeddingClient(
            EmbeddingModelConfig(transport="ollama", base_url=url),
            vector_dimensions=2,
            max_input_tokens=100,
            max_tokens_per_request=100,
            send_dimensions=False,
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:11434",
        "http://[::1]:11434",
        "http://localhost:11434/v1",
        "http://host.docker.internal:11434/",
        "http://ollama:11434",
    ],
)
def test_local_endpoint_and_compatible_path_normalization(url):
    assert local_ollama_url(url, openai=True).endswith("/v1")
    assert "/v1/v1" not in local_ollama_url(url, openai=True)
    assert not local_ollama_url(url).endswith("/v1")


def test_original_deleted_policy_intent_and_runtime_cache_enforcement(monkeypatch):
    local = ConfiguredModelSettings(
        transport="ollama",
        model="fictional",
        overrides={"base_url": "http://localhost:11434"},
    )
    assert local == DeriverSettings(LOCAL_ONLY=True, MODEL_CONFIG=local).MODEL_CONFIG
    with pytest.raises(ValueError, match="requires transport"):
        DeriverSettings(
            LOCAL_ONLY=True,
            MODEL_CONFIG=ConfiguredModelSettings(transport="openai", model="fictional"),
        )
    with pytest.raises(ValueError, match="fallback"):
        DeriverSettings(
            LOCAL_ONLY=True, MODEL_CONFIG=local.model_copy(update={"fallback": local})
        )
    monkeypatch.setitem(registry.CLIENTS, "ollama", object())
    config = ModelConfig(
        transport="ollama",
        model="fictional",
        fallback={"transport": "openai", "model": "fictional"},
    )
    with pytest.raises(Exception, match="fallback"):
        registry.client_for_model_config("ollama", config)
    monkeypatch.setattr(settings.DERIVER, "LOCAL_ONLY", True)
    with pytest.raises(Exception, match="Local-only"):
        registry.client_for_model_config(
            "openai", ModelConfig(transport="openai", model="fictional")
        )


@pytest.mark.asyncio
async def test_real_embedding_http_adapter_and_redirect_refusal(monkeypatch):
    calls = []
    actual = httpx.AsyncClient
    # Preserve isinstance checks while injecting the real client's transport.
    original_init = actual.__init__

    def init(self, *args, **kwargs):
        assert (
            kwargs.get("trust_env") is False and kwargs.get("follow_redirects") is False
        )

        def respond(req):
            calls.append(req)
            data = json.loads(req.content)["input"]
            return httpx.Response(
                200,
                json={
                    "embeddings": [
                        [0.2, 0.4] for _ in (data if isinstance(data, list) else [data])
                    ]
                },
            )

        kwargs["transport"] = httpx.MockTransport(respond)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(actual, "__init__", init)
    client = _EmbeddingClient(
        EmbeddingModelConfig(transport="ollama", model="fictional"),
        vector_dimensions=2,
        max_input_tokens=100,
        max_tokens_per_request=100,
        send_dimensions=False,
    )
    try:
        assert await client.embed("fictional") == [0.2, 0.4]
        assert await client.simple_batch_embed(["a", "b"]) == [[0.2, 0.4], [0.2, 0.4]]
        assert all(str(req.url) == "http://127.0.0.1:11434/api/embed" for req in calls)
        assert all("authorization" not in req.headers for req in calls)
        client.client._transport = httpx.MockTransport(
            lambda _: httpx.Response(302, headers={"location": "http://remote.invalid"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await client.embed("fictional")
    finally:
        await client.client.aclose()


@pytest.mark.asyncio
async def test_real_sdk_client_has_no_proxy_or_redirect(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://remote.invalid:8888")
    registry.get_ollama_client.cache_clear()
    client = registry.get_ollama_client("http://localhost:11434/v1")
    try:
        assert str(client.base_url) == "http://localhost:11434/v1/"
        assert client._client.trust_env is False
        assert client._client.follow_redirects is False
    finally:
        await client.close()
    registry.get_ollama_client.cache_clear()


@pytest.mark.parametrize("value", ["0", "-1", "1001"])
def test_repair_bounds_are_enforced(value):
    with pytest.raises(argparse.ArgumentTypeError):
        reconcile._bounded_count(value)


@pytest.mark.asyncio
async def test_reconcile_preview_and_execute_actual_cli(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        reconcile, "_assert_local_embedding_provider", lambda: {"transport": "ollama"}
    )
    validate = AsyncMock()
    report = AsyncMock(return_value={"counts": {"fictional": 1}})
    create = AsyncMock(return_value=2)
    release = AsyncMock(return_value=1)
    batches = AsyncMock(return_value=reconcile.ReconciliationMetrics())
    for name, value in [
        ("validate_embedding_schema", validate),
        ("_vector_report", report),
        ("_create_missing_embedding_rows", create),
        ("_release_leased_pending_null_vectors", release),
        ("_run_batches", batches),
    ]:
        monkeypatch.setattr(reconcile, name, value)
    import sys

    command = [
        "reconcile",
        "--manifest-dir",
        str(tmp_path),
        "--max-batches",
        "2",
        "--max-repair-rows",
        "3",
        "--create-missing-embedding-rows",
        "--release-leased-pending",
    ]
    monkeypatch.setattr(sys, "argv", command)
    assert await reconcile._main() == 0
    create.assert_not_awaited()
    release.assert_not_awaited()
    batches.assert_not_awaited()
    monkeypatch.setattr(sys, "argv", command + ["--execute"])
    assert await reconcile._main() == 0
    create.assert_awaited_once_with(3)
    release.assert_awaited_once_with(3)
    batches.assert_awaited_once_with(2)
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 2
    assert {json.loads(p.read_text())["mode"] for p in files} == {"dry_run", "execute"}
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in files)


def test_reconcile_rejects_remote_embedding_and_exporters_before_store_access(
    monkeypatch,
):
    from src.config import ConfiguredEmbeddingModelSettings

    def configure(url="http://localhost:11434"):
        monkeypatch.setattr(
            settings.EMBEDDING,
            "MODEL_CONFIG",
            ConfiguredEmbeddingModelSettings(
                transport="ollama", model="fictional", overrides={"base_url": url}
            ),
        )

    configure()
    assert (
        reconcile._assert_local_embedding_provider()["base_url"]
        == "http://localhost:11434"
    )
    configure("http://remote.invalid")
    with pytest.raises(ValueError):
        reconcile._assert_local_embedding_provider()
    configure()
    monkeypatch.setattr(settings.VECTOR_STORE, "TYPE", "turbopuffer")
    with pytest.raises(SystemExit, match="PostgreSQL"):
        reconcile._assert_local_embedding_provider()
    monkeypatch.setattr(settings.VECTOR_STORE, "TYPE", "pgvector")
    monkeypatch.setattr(settings.TELEMETRY, "ENABLED", True)
    with pytest.raises(SystemExit, match="telemetry"):
        reconcile._assert_local_embedding_provider()


def test_local_reasoning_suppresses_both_langfuse_entrypoints(monkeypatch):
    import langfuse

    from src.llm.runtime import update_current_langfuse_observation
    from src.telemetry import logging as tracing

    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "fictional")
    monkeypatch.setattr(settings.DIALECTIC, "LOCAL_ONLY", True)

    def forbidden(*args, **kwargs):
        raise AssertionError("trace was attempted")

    monkeypatch.setattr(tracing, "observe", forbidden)
    monkeypatch.setattr(langfuse, "get_client", forbidden)

    def function():
        return "fictional"

    assert tracing.conditional_observe(function)() == "fictional"
    update_current_langfuse_observation("ollama", "fictional")


@pytest.mark.asyncio
async def test_repair_queries_bind_limits_and_only_write_explicit_sessions(monkeypatch):
    from contextlib import asynccontextmanager

    calls = []

    class Rows:
        def scalars(self):
            return self

        def all(self):
            return []

    class Session:
        async def execute(self, query):
            calls.append(query.compile().params)
            return Rows()

    @asynccontextmanager
    async def tracked(name, **kwargs):
        assert not kwargs.get("read_only", False)
        yield Session()

    monkeypatch.setattr(reconcile, "tracked_db", tracked)
    assert await reconcile._create_missing_embedding_rows(7) == 0
    assert await reconcile._release_leased_pending_null_vectors(9) == 0
    assert calls[0]["param_1"] == 7 and calls[1]["param_1"] == 9


@pytest.mark.asyncio
async def test_batch_stop_uses_actual_reconciler_contract(monkeypatch):
    monkeypatch.setattr(reconcile, "get_external_vector_store", lambda: None)
    call = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(reconcile, "_reconcile_message_embeddings_batch", call)
    metrics = await reconcile._run_batches(5)
    assert call.await_count == 2
    assert all(args.args == (None, metrics) for args in call.await_args_list)


def test_final_retry_cannot_skip_primary_local_policy(monkeypatch):
    from src.llm.runtime import plan_attempt

    config = ModelConfig(
        transport="ollama",
        model="fictional",
        fallback={"transport": "openai", "model": "fictional"},
    )
    with pytest.raises(Exception, match="fallback"):
        plan_attempt(
            runtime_model_config=config,
            attempt=3,
            retry_attempts=3,
            call_thinking_budget_tokens=None,
            call_reasoning_effort=None,
        )
    monkeypatch.setattr(settings.DERIVER, "LOCAL_ONLY", True)
    with pytest.raises(Exception, match="Local-only"):
        registry.backend_for_provider("openai", object())


@pytest.mark.parametrize("level", ["minimal", "low", "medium", "high", "max"])
@pytest.mark.parametrize("field", ["MODEL_CONFIG", "SYNTHESIS_MODEL_CONFIG"])
def test_each_dialectic_model_is_validated(level, field):
    from src.config import DialecticSettings

    local = ConfiguredModelSettings(transport="ollama", model="fictional")
    levels = DialecticSettings().LEVELS
    for value in levels.values():
        value.MODEL_CONFIG = local
        value.SYNTHESIS_MODEL_CONFIG = local
    assert DialecticSettings(LOCAL_ONLY=True, LEVELS=levels).LOCAL_ONLY
    levels[level] = levels[level].model_copy(
        update={field: ConfiguredModelSettings(transport="openai", model="fictional")}
    )
    with pytest.raises(ValueError, match="requires transport"):
        DialecticSettings(LOCAL_ONLY=True, LEVELS=levels)
