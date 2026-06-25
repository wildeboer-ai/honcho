# Honcho summary branch closure receipt

Date: 2026-06-25

Source branch:

- `origin/summary` at `9dddf3b`

Disposition: superseded by current `main`; ancestry preserved through `lawfirm/integrate/honcho-summary`.

Source branch capability:

- Added a legacy `chat_history()` helper in `src/agent.py` that summarized a session's raw messages with Anthropic and returned `"None"` when no messages were available.
- Added Langfuse trace tags for legacy dialectic and summarization calls.
- Threaded summarized conversation history into the old dialectic agent path.
- Modified the old deriver/VOE implementation in `src/deriver/voe.py` and `src/deriver/consumer.py`.

Current main replacement:

- `src/agent.py` and `src/deriver/voe.py` no longer exist on current `main`, so replaying this diff would resurrect deleted architecture.
- `src/utils/summarizer.py` now implements the active summary system with short and long summaries, previous-summary rollup, prompt token estimation, fallback handling for empty or blocked LLM output, telemetry, and schema conversion.
- `src/deriver/enqueue.py` creates typed summary queue work, and `src/deriver/consumer.py` validates and processes summary tasks using `SummaryPayload`.
- `src/routers/sessions.py` exposes session summaries and session context with `include_summary` support plus 40/60 token-budget selection between summaries and recent messages.
- `src/utils/agent_tools.py` exposes summary context through the current tool surface.
- The docs and OpenAPI surfaces describe `/{session_id}/summaries` and context responses with summaries, and `tests/utils/test_summarizer.py` covers the current summarizer fallback and model-routing behavior.
- Langfuse/OpenTelemetry coverage is now handled through the current LLM telemetry path and the opt-in dev-tools observability integration, instead of the old direct `langfuse.decorators` calls from this source branch.

Resolution:

- No source code from `origin/summary` was replayed because the branch is based on deleted files and its runtime behavior is superseded by the current queue-backed summarizer.
- The source branch commits are preserved in repository history by an `ours` ancestry merge before remote branch deletion.

Validation:

- `git diff --check`
