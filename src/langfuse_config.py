"""Explicit caller-owned Langfuse v3 observation helpers, dormant by default.

No SDK client, environment, credential or destination is discovered here. An
already configured client is a trusted dependency supplied by an authorized
caller. Current local-only policy suppresses both helper operations.
"""

from contextlib import nullcontext
from typing import Any


def get_langfuse_client(*, client: Any = None, enabled: bool = False) -> Any:
    """Admit a supplied client only after an explicit enable and local policy."""
    if enabled is not True:
        return None
    from src.config import settings

    if (
        settings.LLM.LOCAL_ONLY
        or settings.DERIVER.LOCAL_ONLY
        or settings.DIALECTIC.LOCAL_ONLY
    ):
        return None
    if client is None:
        raise ValueError("Enabled tracing requires an explicitly configured client")
    return client


def langfuse(*, client: Any = None, enabled: bool = False) -> Any:
    """Compatibility accessor without a global cached identity or ambient client."""
    return get_langfuse_client(client=client, enabled=enabled)


def trace_llm_call(
    name: str,
    model: str,
    prompt: str,
    response: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    metadata: dict[str, Any] | None = None,
    *,
    client: Any = None,
    enabled: bool = False,
) -> Any:
    """Record one span and child generation using the current v3 interface."""
    selected = langfuse(client=client, enabled=enabled)
    if selected is None:
        return None
    if (
        type(tokens_in) is not int
        or type(tokens_out) is not int
        or min(tokens_in, tokens_out) < 0
    ):
        raise ValueError("Token counts must be nonnegative integers")
    trace = selected.start_observation(name=name, as_type="span")
    try:
        generation = trace.start_observation(
            name=f"{model}_call",
            as_type="generation",
            model=model,
            input=prompt,
            output=response,
            usage_details={"input": tokens_in, "output": tokens_out},
            metadata=metadata or {},
        )
        generation.end()
        return trace, generation
    finally:
        trace.end()


def trace_span(
    name: str,
    metadata: dict[str, Any] | None = None,
    *,
    client: Any = None,
    enabled: bool = False,
) -> Any:
    """Return the selected v3 managed span or a no-effect context manager."""
    selected = langfuse(client=client, enabled=enabled)
    if selected is None:
        return nullcontext()
    return selected.start_as_current_observation(
        name=name,
        as_type="span",
        metadata=metadata or {},
    )
