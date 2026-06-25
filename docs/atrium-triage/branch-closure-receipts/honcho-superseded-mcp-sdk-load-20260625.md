# Honcho Superseded MCP, SDK, and Load-Test Branches

Date: 2026-06-25

This receipt records stale Honcho branches whose capabilities are already on
current `main` or whose changes target removed implementation paths. The
branches were merged with the `ours` strategy only to preserve ancestry before
remote branch deletion.

## Sources

- `ben/mcp-server-improvements`
  - `cc3483b` / PR #379 includes the modular MCP server rewrite, workspace,
    session, peer, system, and conclusion tools, shared MCP types, pagination,
    nanoid alignment, CORS/default-route fixes, and documentation updates.
  - Current `main` has the newer MCP layout under `mcp/src/*`, plus later
    self-hosting/HONCHO_API_URL configuration.
- `rajat/dev-1091`
  - Current `main` already has message object APIs, message metadata update,
    session deletion, queue/status methods, and SDK coverage through the
    active `src/routers/messages.py`, `src/routers/sessions.py`, Python SDK,
    TypeScript SDK, and route/SDK tests.
  - The branch's SDK/API changes are older than the current generated clients
    and route surfaces.
- `rajat/fix-dialectic-held-connection`
  - `0533c6d` / PR #477 includes the dialectic held-connection fix,
    precomputed embeddings for agent tools, smaller DB-connection test
    patterns, vector-store-aware embedding client behavior, dedup count
    handling, and DB-free `query_documents` changes.
  - Current `main` has later dialectic, dreamer, vector-store, and DB-session
    scoping on top of that work.
- `rajat/honcho-load-test-patch`
  - This branch patches removed paths such as `src/agent.py`, `src/crud.py`,
    and `src/utils/model_client.py` to force OpenAI-compatible load-test
    behavior.
  - Current `main` has the replacement provider/configuration surface through
    `src/llm/backends/openai.py`, `LLM_OPENAI_BASE_URL`, and configurable
    `DB.POOL_CLASS="null"` in `src/config.py` and `src/db.py`.

## Closure

No stale source code was replayed into `main`. The source branches can be
deleted after this receipt reaches `main` and `git merge-base --is-ancestor`
confirms each source branch is contained in `main`.

Branches still open after this closure are integration or manual-review
candidates, not accidental leftovers.
