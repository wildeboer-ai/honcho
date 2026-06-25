# Honcho Integrated PDF Mistral OCR Branch

Date: 2026-06-25

Source branch: `adavya/pdf-mistral-ocr`

This receipt records the useful capability ported from `adavya/pdf-mistral-ocr`
before the branch is closed.

## Integrated Capability

- Added optional Mistral OCR extraction for PDF uploads when
  `MISTRAL_OCR_API_KEY` is configured.
- Added `MISTRAL_OCR_MODEL` and `MISTRAL_OCR_TIMEOUT_SECONDS` settings.
- Kept pdfplumber as the default path and as the fallback when Mistral OCR is
  unavailable or returns an unexpected response shape.
- Added unit tests for OCR success and fallback behavior.
- Marked `tests/utils/test_files.py` as a pure utility test that does not need
  DB runtime mocks.

## Not Replayed

The source branch also moved file extraction before creating a tracked DB
session. Current `main` already uses lazy DB checkout in `src/dependencies.py`,
so the upload route does not pin a pooled connection while file extraction or
remote OCR runs before the first DB operation. That older route/test change was
not replayed.

The branch will be merged with the `ours` strategy after this scoped port so the
original source history remains reachable from `main` before remote branch
deletion.
