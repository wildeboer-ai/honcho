# Honcho Superseded Docs, Config, CI, and SDK Branches

Date: 2026-06-25

This receipt records stale Honcho branches whose substantive commits are already
present on `main` through newer merge commits, broader replacements, or both.
The branches were merged with the `ours` strategy only to preserve ancestry
before remote branch deletion.

## Sources

- `vineeth/dev-1459`
  - `ff116b0` / PR #510 includes the branch subjects for self-hosting,
    database-name, troubleshooting, and v2/v3 docs cleanup.
  - Current `main` has later self-hosting/config updates on top of that work.
- `vineeth/dev-1295`
  - `5978c67` / PR #321 includes the branch subjects for pagination binding,
    SDK test alignment, Dockerfile, and uv updates.
  - Current `main` has newer Docker and SDK test layouts.
- `rajat/DEV-1296`
  - `acfade7` / PR #291 includes all unified-test CI commits, including the
    `UNIFIED_TEST_LOG_LEVEL` default.
  - Current `main` still carries `.github/workflows/unified-tests.yml`.
- `pr-429`
  - `122ebfe` / PR #429 includes the docker-compose observability and
    `init.sql` fixes.
  - Current `main` also includes `docker/entrypoint.sh`,
    `docker/prometheus.yml`, and newer self-hosting docs.
- `rajat/DEV-1270`
  - `b3e715d` / PR #280 includes cache-log cleanup, cache-thrashing reduction,
    and new-session cache warming.
  - Current `main` has the later cache-v2 implementation and prompt-cache
    optimization work.
- `rajat/fix-message-id-range`
  - `a422528` / PR #300 includes the document `message_ids` validation fix,
    version bump, and dependency bump.
  - Current `main` has newer release and SDK state.
- `vineeth/dev-1048`
  - `0838a28` / PR #186 includes the session-observer-limit fix and exception
    type changes.
  - Current `main` keeps the observer-limit behavior in the current
    session/router schema.
- `vineeth/dev-1855`
  - `9f26fdd` / PR #765 includes deriver polling jitter and removal of
    connection retry logic.
  - Current `main` carries the later deriver polling behavior.
- `vineeth/dev-1166`
  - `73c5eb1` / PR #223 includes the SDK/session delete, streaming,
    pagination, metadata update, peer-card getter, and API-reference docs
    subjects.
  - Current `main` has later SDK and route updates on top of this work.
- `vineeth/dev-1193`
  - `822059b` / PR #241 includes the v2.4.0 docs reorganization and system
    diagram visibility work.
  - Current `main` has newer documentation structure and release notes.
- `vineeth/dev-1749`
  - `b84da15` / PR #678 includes all embedding configurability, vector
    dimensions, startup validator, configure script, docs, and CI fixes.
  - Current `main` has the embedding configurability path and tests.
- `vineeth/dev-1844`
  - `396976d` / PR #758 includes the DB connection retry/backoff, pool metrics,
    and session cleanup fixes.
  - Current `main` has later connection/polling changes, including PR #765.

## Closure

No code from these source branches was replayed because the current `main`
implementation is newer than the stale branch tips. After this receipt reaches
`main`, each source branch can be deleted once `git merge-base --is-ancestor`
confirms ancestry.
