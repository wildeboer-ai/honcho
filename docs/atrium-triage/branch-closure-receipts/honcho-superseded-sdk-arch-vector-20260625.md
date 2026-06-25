# Honcho Superseded SDK, Architecture, and Vector Branches

Date: 2026-06-25

This receipt records stale Honcho branches whose capabilities are already
represented on current `main` in newer form. The branches were merged with the
`ours` strategy only to preserve ancestry before remote branch deletion.

## Sources

- `ben/sdks-add-set-peer-card`
  - `2522cc5` / PR #371 includes the set-peer-card SDK work, `.get_card` /
    `.set_card` documentation, non-creating `get_peer_card`, and
    `ResourceNotFoundException` contract update.
  - Current `main` has later SDK and peer-card route/test updates.
- `vineeth/dev-1034-2`
  - This old checkpoint rewrites the removed `src/utils/clients.py` LLM path.
  - The same branch family was already recorded as superseded by current
    `src/llm/api.py`, `src/llm/structured_output.py`, and backend-specific
    structured-output repair in
    `honcho-superseded-llm-deps-20260625.md`.
- `vineeth/dev-1297`
  - `578ef2c` / PR #309 includes the backwards-compatible conclusion and queue
    endpoint work as part of the agentic dreamer/dialectic merge.
  - Current `main` has `src/routers/conclusions.py`,
    `src/crud/deriver.py`, `src/routers/workspaces.py`, queue-status tests,
    conclusion tests, and generated docs for conclusions.
- `vineeth/dev-656`
  - `8588d36` / PR #95 includes the peer/scoped-auth release-candidate work,
    JWT expiry, route parameter annotation cleanup, Langfuse tracing, and
    related documentation updates.
  - Current `main` has the newer peer paradigm, scoped API keys, JWT helper
    script, scoped API tests, and migrations.
- `vineeth/dev-692`
  - `8ff3cd7` / PR #115 includes central configuration, pydantic settings,
    DB pool/tracing settings, validation, docs, and Dockerfile/config updates.
  - Current `main` keeps the centralized settings path in `src/config.py` and
    newer config templates.
- `vineeth/dev-769`
  - `c22cc50` / PR #112 includes the chat/session DB scoping work, summary
    save fix, and route-scoped DB reduction.
  - Current `main` has the newer tracked DB dependency path, operation names,
    read-only DB support, and later session-context/chat scoping.
- `vineeth/dev-857`
  - `657feac` / PR #131 and adjacent main commits include the peer paradigm
    migration, deriver-status route updates, and required message/session
    migration changes.
  - Current `main` uses the active `peers`, `workspaces`, and `sessions`
    routers; the old app/user/collection surfaces should not be restored.
- `vineeth/turbopuffer`
  - `833a89e` / PR #287 includes Turbopuffer and LanceDB integration,
    reconciliation, compose vector-store setup, soft-delete behavior, and
    migration/test work.
  - Current `main` has newer `src/vector_store/*`, `src/reconciler/*`,
    vector-store tests, and later fixes from PRs #561 and #682.

## Closure

No stale source code was replayed into `main`. The source branches can be
deleted after this receipt reaches `main` and `git merge-base --is-ancestor`
confirms each source branch is contained in `main`.
