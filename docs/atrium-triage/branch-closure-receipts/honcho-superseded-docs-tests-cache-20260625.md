# Honcho Superseded Docs, Tests, Cache, and Compatibility Branches

Date: 2026-06-25

This receipt records stale Honcho branches whose capabilities are already on
current `main`, are obsolete under the current architecture, or are both. The
branches were merged with the `ours` strategy only to preserve ancestry before
remote branch deletion.

## Sources

- `abigail/dev-1372-new`
  - Current `main` already has the Gmail, Granola, MCP, and n8n guide/example
    surface in `docs/v3/guides/*`, `docs/v3/guides/integrations/*`, and
    `examples/{gmail,granola}/*`.
  - The branch docs are older than the current v3 documentation.
- `adavya/deriver-custom-instructions`
  - `a420264` / PR #609 landed deriver custom instructions.
  - Current `main` has the config fields, prompt wiring, schema validation, and
    tests in `src/config.py`, `src/deriver/*`,
    `src/schemas/configuration.py`, and the related test files.
- `additional-deriver-testing`
  - The branch tests target removed modules such as `src/deriver/queue.py`,
    `src/deriver/tom/*`, and `src/utils/model_client.py`.
  - Current `main` has deriver/dreamer/queue coverage under `tests/deriver/*`
    against `src/deriver/queue_manager.py`, `src/dreamer/*`, and `src/llm/*`.
- `ayush/dev-882`
  - The DIA/surprise proof-of-concept targets the retired `src/agent.py`,
    old `src/deriver/tom/*`, and old deriver queue structure.
  - Current `main` has the successor reasoning stack in `src/dreamer/*`,
    `src/dialectic/*`, and `src/utils/agent_tools.py`.
- `dani/dev-822`
  - The branch changes the old `src/agent.py` and legacy chat/router stack.
  - Current `main` already has CORS configuration through `src/config.py` and
    `src/main.py`, plus current LLM trace plumbing under `src/llm/*`.
- `deriver-unit-test`
  - These tests target removed deriver/TOM modules and are superseded by the
    current deriver queue and processing test suites.
- `eri/dev-1300`
  - The branch edits the retired `docs/v2.6.0-alpha/*` documentation tree.
  - Current `main` has the active v3 feature docs for reasoning configuration,
    queue status, streaming, summarizer, context, chat, and platform topics.
- `fix/implement-custom-instructions`
  - Current `main` already has deriver custom instructions from PR #609.
  - Its bundled prompt-cache work is superseded by the current `src/llm/*`
    cache/request-builder stack and associated `tests/llm/*` coverage.
- `fix/prefix-based-cache-optim`
  - The old prompt-cache branch family is superseded by current
    `src/llm/caching.py`, `src/llm/request_builder.py`, and cache-related
    request-builder tests.
- `peace-of-mind-test`
  - The LLM-as-judge and surprise-reasoner tests target removed
    `src.deriver.surprise_reasoner` and `src.deriver.tom.*` paths.
  - Current reasoning coverage lives in `src/dreamer/*`, `src/dialectic/*`,
    and `src/telemetry/reasoning_traces.py`.
- `pr-425-latest`
  - This is the same obsolete prompt-cache branch family as
    `fix/prefix-based-cache-optim`; current `main` has the newer LLM cache
    implementation and tests.
- `yuya/AI-130`
  - vLLM/OpenRouter/proxy compatibility is represented in current
    `src/llm/backends/openai.py`, `src/llm/structured_output.py`,
    `src/config.py`, and the current configuration docs.
  - The branch modifies the removed `src/utils/clients.py` path and should not
    be replayed.

## Closure

No stale source code was replayed into `main`. The source branches can be
deleted after this receipt reaches `main` and `git merge-base --is-ancestor`
confirms each source branch is contained in `main`.

`summary` is intentionally not included here because prior triage disagreed on
whether it is fully superseded. It remains open for explicit review or
integration.
