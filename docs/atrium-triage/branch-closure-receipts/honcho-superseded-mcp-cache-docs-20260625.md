# Superseded MCP, Cache, And Docs Branch Closure Receipt

- Observed: 2026-06-25
- Base: `main` at `f63cce124f3fc9757952ab5130514017217c917e`
- Integration branch: `lawfirm/merge-promote/honcho-superseded-mcp-cache-docs-20260625T122654Z`

## Source Branches

- `vineeth/dev-1320` at `7162608711f265dbe6fc30a41828aaaa87010841`
- `vineeth/dev-1380` at `08de2b1d22f671666bd387f78a6187eb70f7941e`
- `abigail/dev-1559` at `d384daacdad34584b8ccc4e94ec57e38f32eb95c`

## Resolution

These source branches were merged for ancestry preservation with current `main`
kept as the authoritative tree.

- `vineeth/dev-1320` updated the old MCP worker and primitive creation flow.
  Current `main` contains that work through the MCP worker update and the later
  MCP refactor into `mcp/src/*`; applying the branch tree would regress the
  newer module layout.
- `vineeth/dev-1380` added cache version keys and moved cache payloads away
  from live ORM objects. Current `main` has the `v2:` cache key templates,
  `lock:v2` prefixes, dictionary cache payloads, and
  `make_transient_to_detached` reconstruction in the active CRUD modules.
- `abigail/dev-1559` added early OpenCode documentation. Current `main` has the
  OpenCode integration guide and later improvements to install instructions,
  Windows coverage, navigation, and surrounding docs.

After this receipt PR is merged, these source branches can be deleted only
after Git verifies they are ancestors of `main`.
