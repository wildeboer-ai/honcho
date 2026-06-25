# Superseded Docs And Release Branch Closure Receipt

- Observed: 2026-06-25
- Base: `main` at `ffde564974035eed6eaec992df73e6d7962042f1`
- Integration branch: `lawfirm/merge-promote/honcho-superseded-docs-release-20260625T120450Z`

## Source Branches

- `vineeth/docs` at `9a79d0f5792b7851033924fa8e0d7638348c330f`
- `vineeth/changelog-chore` at `50adccd6e5187f6695d1b4b9fc8e7265d5af7f79`
- `vineeth/release-2.4.2` at `f4fe9fdabd03bae3dd45c6bf386b2fb0178e0553`
- `vineeth/v2.4.3-release-candidate` at `4b2d1fee62d4f7bb7efbb04fcaa1812436bdc8f4`
- `vineeth/rc-3.0.3` at `f38ff7926dfc9e92d21625c29cc0b84697fda7bc`
- `vineeth/v3.0.4-rc` at `60b5536f960382f88f836c0643552a9f76485cce`
- `vineeth/v3.0.7-release` at `42f94ee414268121219cb0590c17e57c43eee724`
- `vineeth/v3.0.8-rc` at `88ecd4a41462cc60032c913722edee78df52621d`
- `docs/paperclip-integration-refresh` at `8d6f83f170fa2ce53fcdfd531c00b0d9d2c31330`
- `lily/dev-1485-docs-vercel-ai-sdk` at `cceeaadbea54c72890fd29d5be5153f8e1990e6a`

## Resolution

These source branches were merged for ancestry preservation with current `main`
kept as the authoritative tree.

- Release branches for 2.4.2, 2.4.3, 3.0.3, 3.0.4, 3.0.7, and 3.0.8 are
  historical release snapshots. Current `main` is already at 3.0.10 and its
  root changelog plus docs changelog include entries for those historical
  releases.
- `vineeth/docs` only upgraded an older Mintlify package layout. Current `main`
  has the newer `mint` package layout and newer docs dependency versions, so
  applying that branch would regress docs tooling.
- `vineeth/changelog-chore` contains old changelog formatting/content that is
  now included or superseded by the current changelog history.
- `docs/paperclip-integration-refresh` was compared against the live
  `plastic-labs/paperclip-honcho` plugin on 2026-06-25. This PR selectively
  refreshes `docs/v3/guides/integrations/paperclip.mdx` to match the live
  plugin's current setup flow and operator actions while keeping the current
  public config names (`honchoApiKey`, `observe_me`, `observe_others`) and
  action label (`Initialize Honcho memory`). The branch's stale nav/overview
  edits and legacy/camel-case config aliases are intentionally not applied.
- `lily/dev-1485-docs-vercel-ai-sdk` was squash-merged into current `main`
  through the Vercel AI SDK guide work and then extended with a newer Skill
  install section. Applying the branch tree would remove that newer section.

After this receipt PR is merged, these source branches can be deleted only
after Git verifies they are ancestors of `main`.
