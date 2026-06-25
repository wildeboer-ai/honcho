# Superseded Search And Metrics Branch Closure Receipt

- Observed: 2026-06-25
- Base: `main` at `af1daa6896856dc467eb97aba52c43788f425bc2`
- Integration branch: `lawfirm/merge-promote/honcho-superseded-search-metrics-20260625T115805Z`

## Source Branches

- `vineeth/dev-1473` at `a26cfb2baf726adf42a4a00b89029c57e7679aba`
- `rajat/align-metrics-to-OpenMetrics` at `556530366c34fcbd3cf15593d917d5bc401b48f6`

## Resolution

Both source branches were merged for ancestry preservation with current `main`
kept as the authoritative tree.

- `vineeth/dev-1473` added external-vector-store message search oversampling and
  deduplication. Current `main` already includes the equivalent behavior in
  `src/crud/message.py`, including external search oversampling and message ID
  deduplication, plus newer pgvector fallback handling.
- `rajat/align-metrics-to-OpenMetrics` updated an older OTel metrics module for
  OpenMetrics `_total` naming. Current `main` has moved the active metrics path
  to `src/telemetry/prometheus/metrics.py`, so resurrecting the deleted OTel
  module would be a regression.

After this receipt PR is merged, both source branches can be deleted only after
Git verifies they are ancestors of `main`.
