import asyncio
import io
import json
import subprocess
from pathlib import Path
from types import TracebackType
from typing import Any, ClassVar
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

import src.utils.files as file_utils
from src.config import settings
from src.exceptions import FileProcessingError, ValidationException
from src.llm.audio import transcribe_audio
from src.utils.files import (
    AudioProcessor,
    FileProcessingService,
    JSONProcessor,
    PDFProcessor,
)


class _FakeMistralOCRResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "pages": [
                {"index": 0, "markdown": "# Page 1\nHello"},
                {"index": 1, "markdown": "Page 2 text"},
            ],
            "usage_info": {"pages_processed": 2},
        }


class _FakeAsyncClient:
    posted_json: dict[str, Any] | None = None
    posted_headers: dict[str, str] | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> _FakeMistralOCRResponse:
        assert url == "https://api.mistral.ai/v1/ocr"
        self.__class__.posted_headers = headers
        self.__class__.posted_json = json
        return _FakeMistralOCRResponse()


class _FailingAsyncClient(_FakeAsyncClient):
    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> _FakeMistralOCRResponse:
        raise httpx.ConnectError("Mistral unavailable")


class _FakePDFPage:
    def __init__(self, text: str | None) -> None:
        self._text: str | None = text

    def extract_text(self) -> str | None:
        return self._text


class _FakePDFReader:
    pages: ClassVar[list[_FakePDFPage]] = [
        _FakePDFPage("First page"),
        _FakePDFPage(None),
        _FakePDFPage("Second page"),
    ]

    def __enter__(self) -> "_FakePDFReader":
        return self

    def __exit__(self, *args: Any) -> None:
        return None


class _FakeTranscriptions:
    kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> str:
        self.__class__.kwargs = kwargs
        return " hello from whisper "


class _FakeAudio:
    transcriptions: _FakeTranscriptions = _FakeTranscriptions()


class _FakeOpenAIClient:
    audio: _FakeAudio = _FakeAudio()


@pytest.mark.asyncio
async def test_json_processor_returns_empty_string_for_blank_content():
    processor = JSONProcessor()

    assert await processor.extract_text(b"") == ""
    assert await processor.extract_text(b"   \n\t") == ""


@pytest.mark.asyncio
async def test_json_processor_preserves_valid_json_behavior():
    processor = JSONProcessor()

    result = await processor.extract_text(b'{"name": "test", "count": 1}')

    assert json.loads(result) == {"name": "test", "count": 1}


@pytest.mark.asyncio
async def test_json_processor_rejects_non_utf8_content():
    processor = JSONProcessor()

    with pytest.raises(ValidationException, match="UTF-8"):
        await processor.extract_text(b"\xff\xfe\x00{")


@pytest.mark.asyncio
async def test_json_processor_rejects_invalid_json_content():
    processor = JSONProcessor()

    with pytest.raises(ValidationException, match="invalid"):
        await processor.extract_text(b'{"name": }')


@pytest.mark.asyncio
async def test_pdf_processor_extracts_markdown_with_mistral_ocr(
    monkeypatch: pytest.MonkeyPatch,
):
    processor = PDFProcessor()
    _FakeAsyncClient.posted_json = None
    _FakeAsyncClient.posted_headers = None
    monkeypatch.setattr(settings, "MISTRAL_OCR_API_KEY", "test-mistral-key")
    monkeypatch.setattr(settings, "MISTRAL_OCR_MODEL", "mistral-ocr-test")
    monkeypatch.setattr(settings, "MISTRAL_OCR_TIMEOUT_SECONDS", 12.5)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    result = await processor.extract_text(b"%PDF test bytes")

    assert result == "# Page 1\nHello\n\nPage 2 text"
    assert _FakeAsyncClient.posted_headers == {
        "Authorization": "Bearer test-mistral-key",
        "Content-Type": "application/json",
    }
    assert _FakeAsyncClient.posted_json == {
        "model": "mistral-ocr-test",
        "document": {
            "type": "document_url",
            "document_url": "data:application/pdf;base64,JVBERiB0ZXN0IGJ5dGVz",
        },
        "include_image_base64": False,
    }


@pytest.mark.asyncio
async def test_pdf_processor_falls_back_to_pdfplumber_without_mistral_key(
    monkeypatch: pytest.MonkeyPatch,
):
    processor = PDFProcessor()

    def open_fake_pdf(*_args: object, **_kwargs: object) -> _FakePDFReader:
        return _FakePDFReader()

    monkeypatch.setattr(settings, "MISTRAL_OCR_API_KEY", None)
    monkeypatch.setattr("src.utils.files.pdfplumber.open", open_fake_pdf)

    result = await processor.extract_text(b"%PDF test bytes")

    assert result == "[Page 1]\nFirst page\n\n[Page 3]\nSecond page"


@pytest.mark.asyncio
async def test_pdf_processor_falls_back_to_pdfplumber_when_mistral_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    processor = PDFProcessor()

    def open_fake_pdf(*_args: object, **_kwargs: object) -> _FakePDFReader:
        return _FakePDFReader()

    monkeypatch.setattr(settings, "MISTRAL_OCR_API_KEY", "test-mistral-key")
    monkeypatch.setattr(httpx, "AsyncClient", _FailingAsyncClient)
    monkeypatch.setattr("src.utils.files.pdfplumber.open", open_fake_pdf)

    result = await processor.extract_text(b"%PDF test bytes")

    assert result == "[Page 1]\nFirst page\n\n[Page 3]\nSecond page"


def test_audio_processor_supports_mp3_and_wav_content_types():
    processor = AudioProcessor()

    assert processor.supports_file_type("audio/mpeg")
    assert processor.supports_file_type("audio/wave")
    assert processor.supports_file_type("audio/wav")
    assert processor.supports_file_type("audio/x-wav")
    assert not processor.supports_file_type("text/plain")


def test_audio_defaults_use_openai_whisper():
    assert settings.AUDIO.PROVIDER == "openai"
    assert settings.AUDIO.MODEL == "whisper-1"


def test_probe_audio_duration_cleans_up_temp_file_on_write_failure():
    processor = AudioProcessor()

    class FailingTempFile:
        name: str = "/tmp/test-audio-probe.mp3"

        def __enter__(self) -> "FailingTempFile":
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: TracebackType | None,
        ) -> bool:
            return False

        def write(self, _content: bytes) -> int:
            raise OSError("disk full")

    with (
        patch("src.utils.files.tempfile.NamedTemporaryFile", return_value=FailingTempFile()),
        patch("src.utils.files.Path.unlink") as mock_unlink,
        pytest.raises(OSError, match="disk full"),
    ):
        processor._probe_audio_duration_seconds(b"audio-bytes", ".mp3")  # pyright: ignore[reportPrivateUsage]

    mock_unlink.assert_called_once_with(missing_ok=True)


def test_probe_audio_duration_timeout_raises_file_processing_error():
    processor = AudioProcessor()

    with (
        patch("src.utils.files.sentry_sdk.capture_exception") as mock_capture,
        patch(
            "src.utils.files.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=10),
        ),
        pytest.raises(FileProcessingError, match="Audio validation timed out"),
    ):
        processor.probe_audio_duration_seconds_from_path(Path("/tmp/audio.mp3"))

    mock_capture.assert_called_once()


@pytest.mark.asyncio
async def test_audio_upload_requires_openai_client_before_processing():
    file = UploadFile(
        file=io.BytesIO(b"audio-bytes"),
        filename="voice.mp3",
        headers=Headers({"content-type": "audio/mpeg"}),
    )
    service = FileProcessingService()

    with (
        patch.dict("src.utils.files.CLIENTS", {}, clear=True),
        patch.object(service.audio_processor, "extract_text", new=AsyncMock()) as mock_extract,
        pytest.raises(
            ValidationException,
            match="Audio uploads require OpenAI transcription credentials",
        ),
    ):
        await service.extract_text_from_upload(file)

    mock_extract.assert_not_awaited()


@pytest.mark.asyncio
async def test_filename_audio_extension_does_not_override_explicit_text_plain_mime():
    file = UploadFile(
        file=io.BytesIO(b"plain text body"),
        filename="notes.mp3",
        headers=Headers({"content-type": "text/plain"}),
    )
    service = FileProcessingService()

    with patch.object(service.audio_processor, "extract_text", new=AsyncMock()) as mock_extract:
        extracted = await service.extract_text_from_upload(file)

    assert extracted.text == "plain text body"
    mock_extract.assert_not_awaited()


@pytest.mark.asyncio
async def test_transcribe_audio_uses_openai_whisper():
    _FakeTranscriptions.kwargs = None

    with patch.dict("src.llm.audio.CLIENTS", {"openai": _FakeOpenAIClient()}, clear=True):
        text = await transcribe_audio(
            b"audio-bytes",
            filename="clip.mp3",
            content_type="audio/mpeg",
        )

    assert text == "hello from whisper"
    assert _FakeTranscriptions.kwargs is not None
    assert _FakeTranscriptions.kwargs["model"] == "whisper-1"
    assert _FakeTranscriptions.kwargs["response_format"] == "text"


@pytest.mark.asyncio
async def test_audio_processor_extract_text_transcribes_directly():
    processor = AudioProcessor()

    async def fake_transcribe(
        _content: bytes,
        filename: str,
        content_type: str,
        **_: object,
    ) -> str:
        assert filename == "seg-0.mp3"
        assert content_type == "audio/mpeg"
        await asyncio.sleep(0.01)
        return "first"

    with (
        patch.object(processor, "_probe_audio_duration_seconds", return_value=1.0),
        patch("src.utils.files.transcribe_audio", side_effect=fake_transcribe),
    ):
        extracted = await processor.extract_text(
            b"audio-bytes",
            filename="seg-0.mp3",
            content_type="audio/mpeg",
        )

    assert extracted.text == "first"
    assert extracted.metadata["processing_type"] == "audio_transcription"
    assert extracted.metadata["audio_segment_count"] == 1
    assert extracted.metadata["transcription_provider"] == "openai"


@pytest.mark.asyncio
async def test_empty_audio_upload_is_rejected_before_transcription():
    processor = AudioProcessor()

    with (
        patch("src.utils.files.transcribe_audio", new=AsyncMock()) as mock_transcribe,
        pytest.raises(ValidationException, match="Audio upload is empty"),
    ):
        await processor.extract_text(
            b"",
            filename="empty.mp3",
            content_type="audio/mpeg",
        )

    mock_transcribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_validated_audio_upload_returns_false_on_probe_timeout():
    file = UploadFile(
        file=io.BytesIO(b"audio-bytes"),
        filename="voice.mp3",
        headers=Headers({"content-type": "audio/mpeg"}),
    )

    with patch.object(
        AudioProcessor,
        "probe_audio_duration_seconds_from_path",
        side_effect=FileProcessingError("Audio validation timed out"),
    ):
        is_valid = await file_utils.is_validated_audio_upload(file)

    assert is_valid is False
    assert file.file.tell() == 0
