"""Validate the deliberately small local Ollama endpoint contract.

Host aliases are operator-controlled routing assertions, not DNS attestation.
"""

from urllib.parse import urlsplit

LOCAL_HOSTS = frozenset(
    {"localhost", "127.0.0.1", "::1", "host.docker.internal", "ollama"}
)


def local_ollama_url(value: str | None, *, openai: bool = False) -> str:
    raw = "http://127.0.0.1:11434" if value is None else value
    try:
        parsed = urlsplit(raw)
        valid = (
            raw == raw.strip()
            and not any(ord(char) < 32 for char in raw)
            and parsed.scheme == "http"
            and parsed.hostname in LOCAL_HOSTS
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and parsed.path in ("", "/", "/v1", "/v1/")
            and (parsed.port is None or 0 < parsed.port < 65536)
        )
    except ValueError as exc:
        raise ValueError(
            "Ollama transport requires an approved local HTTP endpoint"
        ) from exc
    if not valid:
        raise ValueError("Ollama transport requires an approved local HTTP endpoint")
    origin = f"http://{parsed.netloc}"
    return origin + "/v1" if openai else origin
