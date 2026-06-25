# Honcho Integrated Queue Work-Units Branch

Date: 2026-06-25

Source branch: `vineeth/dev-1790`
Source tip: `31c2149b9e6618a3142f78af0729921c0a57e1ee`

This receipt records the useful capability ported from `vineeth/dev-1790` before
the branch is closed.

## Integrated Capability

- Added stalled vs ready pending work-unit counts to `/v3/workspaces/{workspace_id}/queue/status`.
- Added cursor-paginated `/v3/workspaces/{workspace_id}/queue/work-units`.
- Added per-work-unit token totals, in-progress state, and threshold
  classification against `DERIVER_REPRESENTATION_BATCH_MAX_TOKENS` and
  `DERIVER_FLUSH_ENABLED`.
- Added focused route tests for empty results, stalled representation work, and
  cursor navigation.
- Added `sqlakeyset`, required by `fastapi-pagination` cursor pagination.

## Not Replayed

The source branch also contains broad SDK churn, generated OpenAPI changes,
examples, CI/config changes, and stale deletions unrelated to the queue
debugging surface. Those changes were not replayed into current `main`.

The branch will be merged with the `ours` strategy after the scoped capability
port so the original source history remains reachable from `main` before remote
branch deletion.
