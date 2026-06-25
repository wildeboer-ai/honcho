# Superseded LLM And Dependency Branch Closure Receipt

- Observed: 2026-06-25
- Base: `main` at `dde671855e81c840bb55490f6299a9244f8c8aa8`
- Integration branch: `lawfirm/merge-promote/honcho-superseded-llm-deps-20260625T121149Z`

## Source Branches

- `vineeth/dev-1328` at `082f8b34b067752440ee116fadf2d0680ebdae74`
- `rajat/add-levels-to-conclusion-delete` at `aaf4917308576d02e7f0586efbc450f8af0f9035`
- `vineeth/dev-1454` at `744a20de0ae3a666cd04f267a9ec8d7a54f4dc8d`
- `vineeth/dev-1034` at `550c33def8663253561e74bc09a818e972e6a4c5`

## Resolution

These source branches were merged for ancestry preservation with current `main`
kept as the authoritative tree.

- `vineeth/dev-1328` is patch-equivalent to current `main` by `git cherry`.
  Current `pyproject.toml` and `uv.lock` already pin `cashews[redis]==7.4.4`.
- `rajat/add-levels-to-conclusion-delete` is patch-equivalent to current `main`
  by `git cherry`; the AgentToolConclusionsDeletedEvent level fields are already
  represented in the active schema/event path.
- `vineeth/dev-1454` added JSON repair for truncated structured LLM responses
  and Gemini thinking budget handling in the old `src/utils/clients.py` path.
  Current `main` has replaced that monolith with `src/llm/structured_output.py`
  and provider backends under `src/llm/backends/`, with tests covering
  LengthFinishReasonError repair, provider repair paths, and thinking-budget
  propagation.
- `vineeth/dev-1034` was an interim structured-output workaround in
  `src/deriver/deriver.py` plus basedpyright cleanup against the old
  `src/utils/clients.py` stack. Current `main` has a clean `basedpyright` gate
  and the active LLM stack handles structured output through the refactored
  `src/llm` modules, so importing the direct OpenAI debug path would regress the
  current architecture.

After this receipt PR is merged, these source branches can be deleted only
after Git verifies they are ancestors of `main`.
