from __future__ import annotations

import pytest

from src.config import ConfiguredModelSettings, DeriverSettings
from src.llm.registry import get_ollama_client


def _local_model() -> ConfiguredModelSettings:
    return ConfiguredModelSettings(
        transport="ollama",
        model="llama3.1:8b",
        overrides={"base_url": "http://host.docker.internal:11434"},
    )


def test_local_only_deriver_accepts_approved_ollama_route() -> None:
    settings = DeriverSettings(LOCAL_ONLY=True, MODEL_CONFIG=_local_model())
    assert settings.MODEL_CONFIG.transport == "ollama"


def test_local_only_deriver_rejects_remote_primary() -> None:
    with pytest.raises(ValueError, match="local-only policy requires transport='ollama'"):
        DeriverSettings(
            LOCAL_ONLY=True,
            MODEL_CONFIG=ConfiguredModelSettings(transport="openai", model="gpt-5.4-mini"),
        )


def test_local_only_deriver_rejects_remote_fallback() -> None:
    with pytest.raises(ValueError, match="forbids fallback models"):
        DeriverSettings(
            LOCAL_ONLY=True,
            MODEL_CONFIG=ConfiguredModelSettings(
                transport="ollama",
                model="llama3.1:8b",
                overrides={"base_url": "http://host.docker.internal:11434"},
                fallback={"transport": "openai", "model": "gpt-5.4-mini"},
            ),
        )


def test_ollama_registry_rejects_nonlocal_url() -> None:
    get_ollama_client.cache_clear()
    with pytest.raises(Exception, match="approved local HTTP endpoint"):
        get_ollama_client("https://example.invalid")
