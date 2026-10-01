"""Single owner of provider runtime objects: clients, backends, history adapters.

Consolidates wiring that previously lived in both `src/llm/__init__.py` and
`src/utils/clients.py`. Everything that touches provider SDKs at runtime
(default client construction, override client caching, backend selection,
history adapter selection) lives here now.
"""

from __future__ import annotations

from functools import lru_cache
from typing import assert_never

import httpx
from anthropic import AsyncAnthropic
from google import genai
from google.genai import types as genai_types
from openai import AsyncOpenAI

from src.config import ModelConfig, ModelTransport, settings
from src.exceptions import ValidationException
from src.local_transport import local_ollama_url

from .backend import ProviderBackend
from .backends.anthropic import AnthropicBackend
from .backends.gemini import GeminiBackend
from .backends.openai import OpenAIBackend
from .credentials import default_transport_api_key
from .history_adapters import (
    AnthropicHistoryAdapter,
    GeminiHistoryAdapter,
    HistoryAdapter,
    OpenAIHistoryAdapter,
)
from .types import ProviderClient


def _local_ollama_v1_url(base_url: str | None) -> str:
    return local_ollama_url(
        settings.LLM.OLLAMA_BASE_URL if base_url is None else base_url, openai=True
    )


@lru_cache(maxsize=32)
def get_ollama_client(base_url: str | None) -> AsyncOpenAI:
    """No ambient proxy or redirect may change the selected local destination."""
    return AsyncOpenAI(
        api_key="ollama-local",
        base_url=_local_ollama_v1_url(base_url),
        http_client=httpx.AsyncClient(trust_env=False, follow_redirects=False),
    )


@lru_cache(maxsize=1)
def get_anthropic_client() -> AsyncAnthropic:
    """Default Anthropic client built from settings.LLM.ANTHROPIC_API_KEY."""
    return AsyncAnthropic(
        api_key=settings.LLM.ANTHROPIC_API_KEY,
        base_url=settings.LLM.ANTHROPIC_BASE_URL,
        timeout=600.0,
    )


@lru_cache(maxsize=1)
def get_openai_client() -> AsyncOpenAI:
    """Default OpenAI client built from settings.LLM.OPENAI_API_KEY."""
    return AsyncOpenAI(
        api_key=settings.LLM.OPENAI_API_KEY,
        base_url=settings.LLM.OPENAI_BASE_URL,
    )


@lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    """Default Gemini client built from settings.LLM.GEMINI_API_KEY."""
    http_options = (
        genai_types.HttpOptions(base_url=settings.LLM.GEMINI_BASE_URL)
        if settings.LLM.GEMINI_BASE_URL
        else None
    )
    return genai.Client(api_key=settings.LLM.GEMINI_API_KEY, http_options=http_options)


# Bounded cache — in practice the (base_url, api_key) key space is small
# and process-scoped, but maxsize=128 keeps worst-case memory predictable.
@lru_cache(maxsize=128)
def get_openai_override_client(
    base_url: str | None, api_key: str | None
) -> AsyncOpenAI:
    """OpenAI client for a specific (base_url, api_key) pair. Cached by key."""
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


@lru_cache(maxsize=128)
def get_anthropic_override_client(
    base_url: str | None,
    api_key: str | None,
) -> AsyncAnthropic:
    """Anthropic client for a specific (base_url, api_key) pair. Cached by key."""
    return AsyncAnthropic(api_key=api_key, base_url=base_url, timeout=600.0)


@lru_cache(maxsize=128)
def get_gemini_override_client(
    base_url: str | None, api_key: str | None
) -> genai.Client:
    """Gemini client for a specific (base_url, api_key) pair. Cached by key."""
    http_options = genai_types.HttpOptions(base_url=base_url) if base_url else None
    return genai.Client(api_key=api_key, http_options=http_options)


# Module-level default-client registry, populated at import time. Tests patch
# this dict via `patch.dict(CLIENTS, {...})` to inject mock provider clients.
CLIENTS: dict[ModelTransport, ProviderClient] = {}

if settings.LLM.ANTHROPIC_API_KEY:
    CLIENTS["anthropic"] = AsyncAnthropic(
        api_key=settings.LLM.ANTHROPIC_API_KEY,
        base_url=settings.LLM.ANTHROPIC_BASE_URL,
        timeout=600.0,
    )

if settings.LLM.OPENAI_API_KEY:
    CLIENTS["openai"] = AsyncOpenAI(
        api_key=settings.LLM.OPENAI_API_KEY,
        base_url=settings.LLM.OPENAI_BASE_URL,
    )

if settings.LLM.GEMINI_API_KEY:
    http_options = (
        genai_types.HttpOptions(base_url=settings.LLM.GEMINI_BASE_URL)
        if settings.LLM.GEMINI_BASE_URL
        else None
    )
    CLIENTS["gemini"] = genai.Client(
        api_key=settings.LLM.GEMINI_API_KEY,
        http_options=http_options,
    )


def client_for_model_config(
    provider: ModelTransport,
    model_config: ModelConfig,
) -> ProviderClient:
    """Resolve the provider client for a ModelConfig.

    Fast path: no overrides → reuse the module-level default client from
    CLIENTS (the test-mockable seam). Otherwise route through the cached
    override factories.
    """
    if (
        settings.LLM.LOCAL_ONLY
        or settings.DERIVER.LOCAL_ONLY
        or settings.DIALECTIC.LOCAL_ONLY
    ) and provider != "ollama":
        raise ValidationException("Local-only reasoning requires Ollama transport")
    if provider == "ollama":
        if model_config.api_key is not None:
            raise ValidationException(
                "Ollama transport does not accept model API credentials"
            )
        if model_config.fallback is not None:
            raise ValidationException(
                "Ollama transport does not permit fallback models"
            )
        _local_ollama_v1_url(model_config.base_url)
        # Validate before the test-mockable client seam, including fallback policy.
        if model_config.base_url is None and "ollama" in CLIENTS:
            return CLIENTS["ollama"]
        return get_ollama_client(
            settings.LLM.OLLAMA_BASE_URL
            if model_config.base_url is None
            else model_config.base_url
        )
    if model_config.api_key is None and model_config.base_url is None:
        existing_client = CLIENTS.get(provider)
        if existing_client is not None:
            return existing_client

    api_key = model_config.api_key or default_transport_api_key(provider)
    base_url = model_config.base_url
    if not api_key:
        raise ValidationException(f"Missing API key for {provider} model config")

    if provider == "anthropic":
        return get_anthropic_override_client(base_url, api_key)
    if provider == "openai":
        return get_openai_override_client(base_url, api_key)
    if provider == "gemini":
        return get_gemini_override_client(base_url, api_key)
    assert_never(provider)


def backend_for_provider(
    provider: ModelTransport,
    client: ProviderClient,
) -> ProviderBackend:
    """Wrap a raw provider SDK client in the matching ProviderBackend adapter."""
    if (
        settings.LLM.LOCAL_ONLY
        or settings.DERIVER.LOCAL_ONLY
        or settings.DIALECTIC.LOCAL_ONLY
    ) and provider != "ollama":
        raise ValidationException("Local-only reasoning requires Ollama transport")
    if provider == "ollama" and isinstance(client, AsyncOpenAI):
        _local_ollama_v1_url(str(client.base_url))
    if provider == "anthropic":
        return AnthropicBackend(client)
    if provider == "openai":
        return OpenAIBackend(client)
    if provider == "gemini":
        return GeminiBackend(client)
    if provider == "ollama":
        return OpenAIBackend(client)
    assert_never(provider)


def history_adapter_for_provider(provider: ModelTransport) -> HistoryAdapter:
    """Provider-appropriate HistoryAdapter for assistant/tool message formatting."""
    if provider == "anthropic":
        return AnthropicHistoryAdapter()
    if provider == "gemini":
        return GeminiHistoryAdapter()
    return OpenAIHistoryAdapter()


def get_backend(config: ModelConfig) -> ProviderBackend:
    """High-level one-shot backend factory: ModelConfig → ProviderBackend.

    Delegates client resolution to ``client_for_model_config``, which owns
    the CLIENTS fast-path and the missing-API-key validation. Both the
    production path (via ``honcho_llm_call_inner``) and the live-test path
    (via this function) now construct clients through the same helper, so
    validation behavior stays consistent.
    """
    client = client_for_model_config(config.transport, config)
    return backend_for_provider(config.transport, client)


__all__ = [
    "CLIENTS",
    "backend_for_provider",
    "client_for_model_config",
    "get_anthropic_client",
    "get_anthropic_override_client",
    "get_backend",
    "get_gemini_client",
    "get_gemini_override_client",
    "get_ollama_client",
    "get_openai_client",
    "get_openai_override_client",
    "history_adapter_for_provider",
]
