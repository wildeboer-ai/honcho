# Deriver Ownership Branch Closure Receipt

- Observed: 2026-06-25
- Base: `main` at `53a848be10f18bd3ae9f2de776d81edbf63628b3`
- Source branch: `rajat/deriver-fix-ownership`
- Source tip: `2c90974ea32f91cc450eb01365cff24837930582`
- Integration branch: `lawfirm/merge-promote/honcho-deriver-ownership-20260625`

## Resolution

The source branch was merged for ancestry preservation. The queue manager has
evolved substantially since the source branch, so the conflict was resolved
selectively:

- Kept current `main` batching, stale-cleanup gating, adaptive polling, and
  reconciler behavior.
- Integrated the low-risk ownership visibility improvement from the source
  branch: stale active queue session cleanup now selects `work_unit_key` along
  with `id` and logs the keys only when rows are actually deleted.
- Dropped the old per-poll diagnostic logging from the source branch because it
  would add a database count query and info logs on every polling loop.

After this PR is merged, `rajat/deriver-fix-ownership` can be deleted only after
Git verifies it is an ancestor of `main`.
