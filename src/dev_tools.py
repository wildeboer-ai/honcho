"""Optional development observability integrations.

This module is intentionally opt-in. Normal Honcho startup should not attempt
to contact Jaeger, Loki, or Vault unless DEV_TOOLS_ENABLED and the specific
sub-integration toggles are enabled.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from fastapi import FastAPI

from src.config import DevToolsSettings, settings

logger = logging.getLogger(__name__)
_LOKI_HANDLER_NAME = "honcho-dev-tools-loki"


@dataclass(slots=True)
class DevToolsHandles:
    """Handles initialized by dev-tools setup."""

    tracer_provider: object | None = None
    loki_logger: logging.Logger | None = None
    vault: VaultClient | None = None


class VaultClient:
    """Small wrapper around hvac.Client for optional local secret access."""

    def __init__(self, *, addr: str, token: str | None) -> None:
        self.addr: str = addr
        self._client: Any | None = None

        try:
            import hvac
        except ImportError:
            logger.warning("Vault support requested but hvac is not installed")
            return

        if not token:
            logger.warning("Vault support requested but no token was configured")
            return

        self._client = hvac.Client(url=addr, token=token)
        try:
            self._client.sys.read_health_status()
        except Exception as exc:
            logger.warning("Vault connection failed for %s: %s", addr, exc)
            self._client = None
            return

        logger.info("Vault dev-tools client initialized for %s", addr)

    def read_secret(self, path: str, key: str | None = None) -> object | None:
        """Read a Vault KV v2 secret, returning a key value or the full data dict."""
        if self._client is None:
            logger.warning("Vault unavailable; cannot read %s", path)
            return None

        try:
            secret_obj: object = self._client.secrets.kv.v2.read_secret_version(
                path=path
            )
        except Exception as exc:
            logger.error("Failed to read Vault secret %s: %s", path, exc)
            return None

        if not isinstance(secret_obj, dict):
            return None
        secret = cast(dict[str, object], secret_obj)
        envelope_obj = secret.get("data")
        if not isinstance(envelope_obj, dict):
            return None
        envelope = cast(dict[str, object], envelope_obj)
        data_obj = envelope.get("data")
        if not isinstance(data_obj, dict):
            return None
        data = cast(dict[str, object], data_obj)
        if key is not None:
            return data.get(key)
        return dict(data)

    def write_secret(self, path: str, secret_dict: Mapping[str, object]) -> bool:
        """Write a Vault KV v2 secret."""
        if self._client is None:
            logger.warning("Vault unavailable; cannot write %s", path)
            return False

        try:
            self._client.secrets.kv.v2.create_or_update_secret(
                path=path,
                secret=dict(secret_dict),
            )
        except Exception as exc:
            logger.error("Failed to write Vault secret %s: %s", path, exc)
            return False

        logger.info("Vault secret written to %s", path)
        return True


def setup_otel_tracing(
    service_name: str,
    *,
    app: FastAPI | None,
    dev_tools_settings: DevToolsSettings,
) -> object | None:
    """Initialize OpenTelemetry tracing and optional library instrumentation."""
    if not dev_tools_settings.TRACING_ENABLED:
        return None

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.warning("OTEL tracing requested but dependencies are missing: %s", exc)
        return None

    resource = Resource.create(
        {
            "service.name": service_name,
            "deployment.environment": dev_tools_settings.ENVIRONMENT,
        }
    )
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=dev_tools_settings.OTLP_TRACES_ENDPOINT)
        )
    )

    try:
        trace.set_tracer_provider(tracer_provider)
    except Exception as exc:
        logger.warning("OTEL tracer provider was not installed: %s", exc)
        return trace.get_tracer_provider()

    if dev_tools_settings.INSTRUMENT_FASTAPI:
        try:
            if app is not None:
                FastAPIInstrumentor.instrument_app(app)
        except Exception as exc:
            logger.warning("FastAPI OTEL instrumentation failed: %s", exc)

    def instrument_sqlalchemy() -> None:
        SQLAlchemyInstrumentor().instrument()

    def instrument_redis() -> None:
        RedisInstrumentor().instrument()  # pyright: ignore[reportUnknownMemberType]

    def instrument_requests() -> None:
        RequestsInstrumentor().instrument()

    def instrument_httpx() -> None:
        HTTPXClientInstrumentor().instrument()

    instrumentation_calls: list[tuple[bool, str, Callable[[], None]]] = [
        (
            dev_tools_settings.INSTRUMENT_SQLALCHEMY,
            "SQLAlchemy",
            instrument_sqlalchemy,
        ),
        (
            dev_tools_settings.INSTRUMENT_REDIS,
            "Redis",
            instrument_redis,
        ),
        (
            dev_tools_settings.INSTRUMENT_REQUESTS,
            "Requests",
            instrument_requests,
        ),
        (
            dev_tools_settings.INSTRUMENT_HTTPX,
            "HTTPX",
            instrument_httpx,
        ),
    ]
    for enabled, name, instrument in instrumentation_calls:
        if not enabled:
            continue
        try:
            instrument()
        except Exception as exc:
            logger.warning("%s OTEL instrumentation failed: %s", name, exc)

    logger.info(
        "OTEL tracing initialized for %s via %s",
        service_name,
        dev_tools_settings.OTLP_TRACES_ENDPOINT,
    )
    return tracer_provider


def setup_loki_logging(
    service_name: str,
    *,
    dev_tools_settings: DevToolsSettings,
) -> logging.Logger | None:
    """Attach a Loki handler to the root logger when enabled."""
    if not dev_tools_settings.LOKI_ENABLED:
        return None

    try:
        from logging_loki import LokiHandler
        from pythonjsonlogger.json import JsonFormatter
    except ImportError as exc:
        logger.warning("Loki logging requested but dependencies are missing: %s", exc)
        return None

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        if handler.name == _LOKI_HANDLER_NAME:
            return root_logger

    tags = {
        "service": service_name,
        "environment": dev_tools_settings.ENVIRONMENT,
        **dev_tools_settings.LOKI_TAGS,
    }
    loki_url = dev_tools_settings.LOKI_URL.rstrip("/")
    handler = LokiHandler(
        url=f"{loki_url}/loki/api/v1/push",
        tags=tags,
        version="1",
    )
    handler.name = _LOKI_HANDLER_NAME
    handler.setFormatter(
        JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    )
    root_logger.addHandler(handler)
    logger.info("Loki logging initialized for %s via %s", service_name, loki_url)
    return root_logger


def setup_vault(dev_tools_settings: DevToolsSettings) -> VaultClient | None:
    """Initialize the optional Vault client."""
    if not dev_tools_settings.VAULT_ENABLED:
        return None
    token = dev_tools_settings.VAULT_TOKEN or os.getenv(
        dev_tools_settings.VAULT_TOKEN_ENV
    )
    return VaultClient(addr=dev_tools_settings.VAULT_ADDR, token=token)


def setup_dev_tools(
    service_name: str,
    *,
    app: FastAPI | None = None,
    dev_tools_settings: DevToolsSettings | None = None,
) -> DevToolsHandles:
    """Initialize enabled dev-tools integrations for a service."""
    active_settings = dev_tools_settings or settings.DEV_TOOLS
    if not active_settings.ENABLED:
        return DevToolsHandles()

    return DevToolsHandles(
        tracer_provider=setup_otel_tracing(
            service_name,
            app=app,
            dev_tools_settings=active_settings,
        ),
        loki_logger=setup_loki_logging(
            service_name,
            dev_tools_settings=active_settings,
        ),
        vault=setup_vault(active_settings),
    )
