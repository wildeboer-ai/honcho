# Honcho Superseded Gmail Docs Branch

Date: 2026-06-25

Source branch: `abigail/dev-1408`

This receipt records that the Gmail ingestion guide and example from
`abigail/dev-1408` are superseded by current `main`.

## Source Summary

The branch contains three Gmail tutorial/example commits:

- `e78b592` adds `examples/gmail/gmail_to_honcho.py`.
- `c344b6e` adds `docs/v3/guides/gmail.mdx` and docs navigation.
- `1c4f6e0` simplifies the script.

## Current Main Coverage

- `docs/v3/guides/gmail.mdx` already exists on `main` and is included in the
  v3 Chatbots docs navigation.
- `examples/gmail/honcho_gmail.py` already exists on `main` and implements the
  same Gmail-to-Honcho ingestion flow.
- The current example has newer RFC email-header parsing and safer peer ID
  normalization than the branch version.

## Closure

No source files were replayed. The branch is merged with the `ours` strategy to
preserve ancestry before remote branch deletion.
