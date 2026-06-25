# Branch Closure Receipt: `eri/honcho-tui`

Date: 2026-06-25

Source branch: `origin/eri/honcho-tui`
Source head: `fd7461ddb9cd439fe175e1aae596ad0ff1fb610d`
Merge base audited: `58f9abba98c080a540ee168fe7a85b7d35652c0c`

## Integrated Capability

- Added the `honcho-tui` Textual interface as part of the existing
  `honcho-cli` package, including the three-pane session/transcript/peer view,
  queue and conclusion display, animated terminal widgets, and scoped
  dialectic querying.
- Added the `honcho-tui` console entry point and packaged `honcho_tui` modules
  alongside `honcho_cli`.
- Added TUI dependency coverage through `textual` in the root lockfile and
  bumped the CLI package/version metadata to `0.1.2`.
- Added the source branch's Honcho CLI skill files under
  `honcho-cli/src/honcho_cli/skills/`.
- Documented the TUI in the CLI README and changelog.

## Audit Notes

Current `main` already contained a newer `honcho-cli` implementation than the
source branch, including the refined help renderer, JSON array output contract,
resource-ID validation, safer config redaction/permissions, generated CLI docs
support, and expanded CLI tests.

Those newer CLI files were retained. The source branch's older overlapping
command implementations and package rename to `honcho-ai-cli` were not replayed;
the TUI capability was integrated additively under the existing `honcho-cli`
package name to avoid regressing the package already on `main`.

## Validation

- `uv run --with pytest --with pytest-mock pytest honcho-cli/tests`
- `uv run ruff check honcho-cli/src/honcho_tui honcho-cli/src/honcho_cli/main.py honcho-cli/src/honcho_cli/__init__.py`
- `uv run basedpyright`
- `uv run --package honcho-cli honcho --version`
- `uv run --package honcho-cli honcho-tui --version`
- `uv run --package honcho-cli python - <<'PY' ...` import smoke for
  `HonchoTUI` and `collect_page`
- `git diff --check`

Focused basedpyright over `honcho-cli/src/honcho_tui` reported `0 errors` and
strict warning noise from Textual/SDK unknown types; the repository-level CI
typecheck path passes cleanly.
