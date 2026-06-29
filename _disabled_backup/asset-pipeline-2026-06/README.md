# Disabled: Declarative Asset Pipeline (asset-authoring skill)

**Archived**: 2026-06-29
**Reason**: Replaced by a new "rooted-modeling" skill (Root → Measure → Mount → Shape).
This pipeline's core premise — positions derived from a param/skeleton expression DAG —
worked for tube structures (bike frame) but could NOT express "measure the real geometry
of a root component to derive where leaves attach" (keyboard key grid on a tray, doors on
a building wall, wheels on an already-built hub). That gap is the whole reason the new
skill exists.

## What is in here

```
python3.11libs/edini/
  asset_model.py       # params + skeleton DAG: validate_asset / resolve_skeleton
  asset_builder.py     # build_asset: native_chain + python backends, from-to, instances, orient
  data/                # bicycle/chair/table.asset.json sample assets
pi-extensions/edini-tools/tools/asset.ts   # validateAsset + buildAsset TS schemas
skills/asset-authoring/SKILL.md            # the agent-facing skill doc
tests/                                    # 6 test files (model, builder, hython, commit, skeleton, tool_executor)
```

## What was NOT moved (kept live — shared infrastructure)

- `python3.11libs/edini/exprs.py` — safe arithmetic expression engine. Reused by the
  new skill for small derived numbers (e.g. `pscale = bbox/10`). Its test
  `tests/test_exprs.py` also stays live.
- `python3.11libs/edini/harness.py` — sandbox lifecycle / commit_sandbox / geometry
  health. The new skill reuses this. (The `edini_asset_source` stamp-recognition branch
  in commit_sandbox was left in place; it is now dormant code — harmless, and re-enabled
  if ever needed.)
- `mock_hou.py` — the mock Houdini used by tests. Shared.

## What was severed from live code

- `tool_executor.py`: removed the `validate_asset` / `build_asset` handlers + the
  `_validate_asset_data` / `_build_asset_network` / `_resolve_skeleton_data` /
  `_load_asset_file` imports + the `build_asset` wrapper. The TOOL_HANDLERS entries
  `validate_asset` / `build_asset` were removed.
- `pi-extensions/edini-tools/index.ts`: removed `assetTools` import + spread.

## How to restore (if ever needed)

1. Move every file above back to its original path (the layout mirrors the repo).
2. Re-add the `tool_executor.py` handler/imports and the `index.ts` registration
   (see the diff in the commit that archived this — search for "asset-pipeline-2026-06").
3. Re-add the `_validate_skeleton_graph` import of `skeleton_resolver` etc.
4. `exprs.py` and `harness.py` were never moved — nothing to restore there.
```
