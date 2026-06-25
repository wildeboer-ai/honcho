# Honcho audio upload branch closure receipt

Date: 2026-06-25

Source branches:

- `origin/feat/sync-audio-upload-clean`
- `origin/feat/sync-audio-upload-inline`

Disposition: integrated into `main` through `lawfirm/integrate/honcho-audio-upload`.

Integrated capability:

- Added `.mp3` and `.wav` upload recognition on the existing `/v3/workspaces/{workspace_id}/sessions/{session_id}/messages/upload` path.
- Added OpenAI Whisper transcription through the current `src.llm` provider registry, not the removed legacy `src/utils/clients.py` module.
- Added ffprobe validation off the event loop, temp-file cleanup, timeout handling, and validation fallback behavior for the larger audio-specific route limit.
- Preserved current PDF/Mistral OCR behavior by layering audio support into `src/utils/files.py` rather than replaying the older branch file.
- Stored audio provenance in each created message's `internal_metadata`: `processing_type`, `audio_segment_count`, and `transcription_provider`.
- Added deployment-level audio settings via `AUDIO_*` and `[audio]`.
- Added Docker `ffmpeg` installation so containerized self-hosted deployments include `ffprobe`.
- Updated v3 file upload docs and focused utility/route tests.

Inline branch handling:

- `feat/sync-audio-upload-inline` contains an earlier implementation plus `docs/superpowers/specs/2026-04-07-audio-upload-ingestion-design.md`.
- The earlier implementation is superseded by `feat/sync-audio-upload-clean`.
- The design doc's active upload-route, audio-type, provider, metadata, and size-policy intent is represented by this integration.
- Its future raw-audio segmentation and bounded intra-file parallel transcription notes remain design-only follow-up work; neither audio source branch had a complete production implementation of that larger segmentation design.
- The source branch commits are preserved in repository history by an `ours` ancestry merge before remote branch deletion.

Validation:

- `uv run ruff check --fix src/config.py src/llm/__init__.py src/llm/audio.py src/routers/messages.py src/utils/files.py tests/utils/test_files.py tests/routes/test_files.py`
- `uv run pytest tests/utils/test_files.py`
- `uv run ruff check src/config.py src/llm/__init__.py src/llm/audio.py src/routers/messages.py src/utils/files.py tests/utils/test_files.py tests/routes/test_files.py`
- `uv run basedpyright src/config.py src/llm/__init__.py src/llm/audio.py src/routers/messages.py src/utils/files.py tests/utils/test_files.py tests/routes/test_files.py`
- `uv run basedpyright`
- `git diff --check`

Local DB-backed route tests attempted:

- `uv run pytest tests/routes/test_files.py -k 'mp3_file or audio_upload_over_generic_limit'`
- Blocked locally because PostgreSQL was not listening on `localhost:5432`; GitHub Actions should run these with the test database service.

Repo-wide lint note:

- `uv run ruff check` was attempted and failed on unrelated pre-existing lint issues outside this integration, including `.claude/skills/...`, `examples/...`, and `honcho-cli/...`.
