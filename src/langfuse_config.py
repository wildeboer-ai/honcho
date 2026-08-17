"""Langfuse observability integration for Honcho.

Captures LLM calls, traces, and performance metrics to Langfuse for fleet-wide observability.
"""

import os
from langfuse import Langfuse
from langfuse.decorators import observe
from pydantic_settings import BaseSettings


class LangfuseSettings(BaseSettings):
    """Langfuse configuration from environment."""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_enabled: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = False


def get_langfuse_client() -> Langfuse | None:
    """Initialize Langfuse client if credentials are available."""
    settings = LangfuseSettings()
    
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        return None
    
    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        baseurl=settings.langfuse_host,
    )


# Singleton instance
_langfuse_client: Langfuse | None = None


def langfuse() -> Langfuse | None:
    """Get or create the Langfuse client."""
    global _langfuse_client
    if _langfuse_client is None:
        _langfuse_client = get_langfuse_client()
    return _langfuse_client


def trace_llm_call(
    name: str,
    model: str,
    prompt: str,
    response: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    metadata: dict = None,
):
    """Log an LLM call to Langfuse."""
    client = langfuse()
    if not client:
        return
    
    trace = client.trace(name=name)
    generation = trace.generation(
        name=f"{model}_call",
        model=model,
        prompt=prompt,
        completion=response,
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        metadata=metadata or {},
    )
    return trace, generation


def trace_span(name: str, metadata: dict = None):
    """Context manager for tracing a code span."""
    client = langfuse()
    if not client:
        class NoOpSpan:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        return NoOpSpan()
    
    return client.span(name=name, metadata=metadata or {})
