# Superseded Runtime, Context, And Embedding Branch Closure Receipt

- Observed: 2026-06-25
- Base: `main` at `5a43ec70da96dbf066f414cbc3303824b04099f9`
- Integration branch: `lawfirm/merge-promote/honcho-superseded-runtime-context-20260625T121641Z`

## Source Branches

- `embedding/tiktoken-mismatch` at `ea8b1941aec739b6e2a9a0f5ab0744c72af06016`
- `yuya/trace_generation` at `56d26b2fa49237a9bf634f6650a76fd441b7441d`
- `eri/dev-742` at `29470586fd2a52cc9add59a49229d193fbf2d041`
- `devin/DEV-692-1748363968` at `7a27495e8ba2b893265c22310d38ab48c38cb43c`
- `devin/DEV-692-1748366728` at `51526e77644071ea9d85f4d266aa5c33f4170127`
- `kass/fix-peer-card-clean` at `6fe3f0f9312649ce0a243142ea87514490b0ba51`

## Resolution

These source branches were merged for ancestry preservation with current `main`
kept as the authoritative tree.

- `embedding/tiktoken-mismatch` is represented by current `main`'s newer
  deferred embedding path: `src/embedding_client.py` tokenizes with
  `tiktoken.encoding_for_model`, `src/crud/message.py` and
  `scripts/generate_message_embeddings.py` skip blank message content, and
  `tests/integration/test_message_embeddings.py` covers blank messages and
  pending chunk rows.
- `yuya/trace_generation` added trace names to the old `src/utils/clients.py`
  path. Current `main` has the active implementation in
  `src/telemetry/reasoning_traces.py` and logs reasoning traces from
  `src/llm/api.py`, so resurrecting the old client hook would regress the
  refactored LLM stack.
- `eri/dev-742` added an early deriver status endpoint. Current `main` has the
  queue/deriver status implementation in `src/crud/deriver.py`, router exposure,
  SDK coverage, and `tests/routes/test_queue_status.py`.
- `devin/DEV-692-1748363968` and `devin/DEV-692-1748366728` added the early
  session context endpoint and tests. Current `main` has
  `/{session_id}/context` in `src/routers/sessions.py` with broader parameters,
  response schemas, SDK coverage, and route tests.
- `kass/fix-peer-card-clean` improved peer-card attribution prompts. Current
  `main` has a newer typed peer-card policy in `src/dreamer/specialists.py`
  plus validation in `src/utils/agent_tools.py`: allowed entries are
  `IDENTITY`, `ATTRIBUTE`, `RELATIONSHIP`, and `INSTRUCTION`; cross-peer facts,
  behavioral `TRAIT` entries, and bare behavioral `PREFERENCE` entries are
  rejected.

After this receipt PR is merged, these source branches can be deleted only
after Git verifies they are ancestors of `main`.
