from __future__ import annotations

import io
from typing import Any, cast

from openai import AsyncOpenAI

from src.config import settings
from src.exceptions import LLMError

from .registry import CLIENTS


async def transcribe_audio(
    content: bytes,
    *,
    filename: str,
    content_type: str,
    model: str | None = None,
) -> str:
    if not content_type.startswith("audio/"):
        raise LLMError(f"Unsupported audio content type: {content_type}")
    if "openai" not in CLIENTS:
        raise LLMError("Audio transcription provider 'openai' is not initialized")

    client = cast(AsyncOpenAI, CLIENTS["openai"])
    audio_buffer = io.BytesIO(content)
    audio_buffer.name = filename
    response = cast(
        Any,
        await client.audio.transcriptions.create(
            file=audio_buffer,
            model=model or settings.AUDIO.MODEL,
            response_format="text",
        ),
    )
    return response.strip() if isinstance(response, str) else str(response).strip()
