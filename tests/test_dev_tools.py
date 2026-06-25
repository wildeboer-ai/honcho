from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI

import src.dev_tools as dev_tools
from src.config import DevToolsSettings


def test_setup_dev_tools_disabled_returns_empty_handles() -> None:
    handles = dev_tools.setup_dev_tools(
        "honcho-test",
        dev_tools_settings=DevToolsSettings(
            ENABLED=False,
            TRACING_ENABLED=True,
            LOKI_ENABLED=True,
            VAULT_ENABLED=True,
        ),
    )

    assert handles.tracer_provider is None
    assert handles.loki_logger is None
    assert handles.vault is None


def test_setup_dev_tools_calls_enabled_integrations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    tracer = object()
    vault = object()
    loki_logger = logging.getLogger("test-loki")

    def fake_tracing(
        service_name: str,
        *,
        app: FastAPI | None,
        dev_tools_settings: DevToolsSettings,
    ) -> object:
        assert service_name == "honcho-test"
        assert app is test_app
        assert dev_tools_settings.TRACING_ENABLED
        calls.append("tracing")
        return tracer

    def fake_loki(
        service_name: str,
        *,
        dev_tools_settings: DevToolsSettings,
    ) -> logging.Logger:
        assert service_name == "honcho-test"
        assert dev_tools_settings.LOKI_ENABLED
        calls.append("loki")
        return loki_logger

    def fake_vault(dev_tools_settings: DevToolsSettings) -> object:
        assert dev_tools_settings.VAULT_ENABLED
        calls.append("vault")
        return vault

    monkeypatch.setattr(dev_tools, "setup_otel_tracing", fake_tracing)
    monkeypatch.setattr(dev_tools, "setup_loki_logging", fake_loki)
    monkeypatch.setattr(dev_tools, "setup_vault", fake_vault)

    test_app = FastAPI()
    handles = dev_tools.setup_dev_tools(
        "honcho-test",
        app=test_app,
        dev_tools_settings=DevToolsSettings(
            ENABLED=True,
            TRACING_ENABLED=True,
            LOKI_ENABLED=True,
            VAULT_ENABLED=True,
        ),
    )

    assert calls == ["tracing", "loki", "vault"]
    assert handles.tracer_provider is tracer
    assert handles.loki_logger is loki_logger
    assert handles.vault is vault


def test_setup_vault_uses_configured_token_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str | None] = {}

    class FakeVaultClient:
        def __init__(self, *, addr: str, token: str | None) -> None:
            captured["addr"] = addr
            captured["token"] = token

    monkeypatch.setenv("HONCHO_TEST_VAULT_TOKEN", "test-token")
    monkeypatch.setattr(dev_tools, "VaultClient", FakeVaultClient)

    vault = dev_tools.setup_vault(
        DevToolsSettings(
            VAULT_ENABLED=True,
            VAULT_ADDR="http://vault.local:8200",
            VAULT_TOKEN_ENV="HONCHO_TEST_VAULT_TOKEN",
        )
    )

    assert isinstance(vault, FakeVaultClient)
    assert captured == {
        "addr": "http://vault.local:8200",
        "token": "test-token",
    }


def test_setup_vault_prefers_explicit_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str | None] = {}

    class FakeVaultClient:
        def __init__(self, *, addr: str, token: str | None) -> None:
            captured["addr"] = addr
            captured["token"] = token

    monkeypatch.setenv("HONCHO_TEST_VAULT_TOKEN", "env-token")
    monkeypatch.setattr(dev_tools, "VaultClient", FakeVaultClient)

    dev_tools.setup_vault(
        DevToolsSettings(
            VAULT_ENABLED=True,
            VAULT_ADDR="http://vault.local:8200",
            VAULT_TOKEN="explicit-token",
            VAULT_TOKEN_ENV="HONCHO_TEST_VAULT_TOKEN",
        )
    )

    assert captured["token"] == "explicit-token"
