# Branch Closure Receipt: `ben/agentic-fde-experiment`

Date: 2026-06-25

Source branch: `origin/ben/agentic-fde-experiment`
Source head: `e9c4a5dc244fc0ba669eae2befa39a5c3d032242`
Merge base audited: `4fcf6c4574c9014359ddab7cdf9dd9a7012e7354`

## Integrated Capability

- Added workspace agent configuration stored in workspace metadata under
  `_agent_config`, with `deriver_rules` and `dialectic_rules` helpers and
  validation.
- Threaded workspace deriver rules into the current Jinja deriver prompt while
  preserving existing reasoning `custom_instructions`.
- Threaded workspace dialectic rules into peer-level dialectic prompts without
  holding database sessions during LLM or tool execution.
- Added dialectic trace persistence, CRUD helpers, model and migration,
  including retrieved document IDs, tool calls, response metrics, and abstention
  statistics for introspection.
- Added developer feedback and introspection APIs, plus introspection dream
  dispatch and unified-test actions/cases for agent-config, feedback, and
  introspection workflows.

## Audit Notes

The source branch predated several current `main` changes in the dialectic,
dreamer, router, LLM, and unified-test harness paths. Its older implementations
held database sessions across LLM/tool work and used the removed
`src.utils.clients` LLM wrapper.

This integration retained current `main` behavior for the connection-safe
dialectic preflight pattern, two-phase dialectic flow, workspace chat route,
workspace deletion queueing, dream guard-field updates, queue work-unit route,
Jinja prompt templates, and `src.llm` API. The source branch capabilities were
ported additively onto those current paths.

## Validation

- `uv run ruff check ...` for touched source, route, CRUD, schema, dreamer,
  feedback, and unified runner files
- `uv run python - <<'PY' ...` smoke test for schema exports, prompt injection,
  document-ID extraction, and feedback response models
- `uv run basedpyright ...` for touched source and unified runner files
- `uv run basedpyright`
- `git diff --check --cached`

DB-backed pytest files were added and attempted locally:

- `uv run pytest tests/test_workspace_agent_config.py tests/test_dialectic_trace.py tests/test_feedback.py tests/test_introspection.py tests/routes/test_feedback.py`

That pytest run did not reach test behavior because no PostgreSQL server was
listening on `localhost:5432` in this worktree environment; every test errored
during database fixture setup with connection refused.
