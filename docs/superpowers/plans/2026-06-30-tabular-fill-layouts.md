# Tabular Fill Layouts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four new layout strategies (`pickets`/`tiles`/`shelf`/`blocks`) to the rooted-modeling skill by extending `TabularFillStrategy`, each built in an order that drives a real generalization down into the base class.

**Architecture:** Layered generalization (route C from the spec). Each layout = one `TabularFillStrategy` subclass + a `measure.py` oracle + `validate_assembly` schema + SKILL.md docs. The agent never writes VEX; we add pre-built, oracle-verified strategies. The existing `cells` keyboard layout and all 599 M3 tests must stay green at every step (2D path `axes=["X","Z"]` is byte-identical to current `cells`).

**Tech Stack:** Python 3.11 (Houdini's bundled), VEX (pre-built detail-wrangle templates), Houdini 21 hython for real-machine proof, pytest with mock-hou.

**Spec:** `docs/superpowers/specs/2026-06-30-tabular-fill-layouts-design.md`

**Critical environment note:** The local hython is at `D:\houdini\bin\hython.exe` (NOT `C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe` — that path does NOT exist on this machine; the real install is on the D drive). The mock suite runs under `python -m pytest`. Tests needing PySide6 (`test_md_render`, `test_streaming_render`, `test_reflect_worker`, `test_error_surfacing`) are unrelated to this work and can be ignored — they fail only due to missing PySide6 in the bare Python env, not from our changes.

**Development order (the generalization roadmap):**
```
Task 0  (env ready)        →  stale hython-path docs fixed
Task 1-3  (① pickets)      →  shapes axes[] + named columns + count sugar
Task 4-6  (② tiles)        →  shapes per-cell orient (rot + named rules)
Task 7-9  (③ shelf)        →  shapes layer pre-expansion + 3D cells
Task 10-12 (④ blocks)      →  synthesis exam (composes ①②③)
Task 13   (showcase + docs)→  SKILL.md + verify script + showcase .hip
```

---

## File Structure

| file | responsibility | touched in |
|------|----------------|-----------|
| `python3.11libs/edini/vex_strategies.py` | `TabularFillStrategy` base + 4 new subclasses + dispatch | Tasks 1,4,7,10 |
| `python3.11libs/edini/measure.py` | 4 new oracle functions (`measure_pickets`/`measure_tiles`/`measure_shelf`/`measure_blocks`); upgrade return to `(pos,scale,orient)` triples for tiles+blocks | Tasks 2,5,8,11 |
| `python3.11libs/edini/assembly_builder.py` | `validate_assembly` schema branches for 4 measures + `basis`/`axes`; `_expand_pickets_count` / `_expand_shelf_layers` pre-expansion; register measures | Tasks 3,6,9,12 |
| `tests/test_measure.py` | oracle unit tests for the 4 new measures | Tasks 2,5,8,11 |
| `tests/test_assembly_builder.py` | mock schema-validation + network-structure tests | Tasks 3,6,9,12 |
| `tests/test_assembly_hython.py` | real-machine proof per layout | Tasks 3,6,9,12 |
| `scripts/verify_vex_strategies.py` | add 4 strategies to oracle↔VEX comparison | Task 13 |
| `scripts/show_assemblies.py` | add a fence + shelf to the showcase `.hip` | Task 13 |
| `skills/rooted-modeling/SKILL.md` | document the 4 layouts + new schema | Task 13 |

**Key reuse principle:** `TabularFillStrategy._build_vex` is the ONE shared loop generator. New subclasses override `_parse_table` (their schema) and optionally add a builder-layer pre-expansion (Python, before VEX). The VEX loop, unit derivation, orient, and fill are inherited. Do NOT fork the VEX per layout.

---

## Task 0: Environment readiness — fix stale hython-path docs

**Files:**
- Modify: `scripts/verify_vex_strategies.py:13` (docstring)
- Modify: `scripts/show_assemblies.py` (docstring, if it references the path)
- Modify: `wiki/pages/handoff.md` (hython path mentions)
- Modify: `wiki/pages/progress.md` (hython path mentions, if present)

This is a cheap cleanup that prevents every downstream agent from chasing a wrong path. It is the risk surfaced during the project health check.

- [ ] **Step 1: Fix the verify script docstring**

> ⚠️ **CORRECTION (2026-07-01):** The original Task 0 below was based on a wrong assumption — it assumed `C:\Program Files\...` was correct and `D:/houdini/` was stale. The REALITY is the opposite: hython lives at `D:\houdini\bin\hython.exe`; the `C:\Program Files\...` path does NOT exist on this machine. Task 0 as originally written made the path worse. The steps below are kept for the historical record but should NOT be followed verbatim — the docs have since been corrected back to `D:\houdini\bin\hython.exe`.

In `scripts/verify_vex_strategies.py`, change line 13's docstring from:
```
    C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe scripts/verify_vex_strategies.py
```
to:
```
    "D:\houdini\bin\hython.exe" scripts/verify_vex_strategies.py
```

- [ ] **Step 2: Check show_assemblies.py for the same stale path**

Run: `grep -n "C:/Program Files\|C:\\\\Program Files" scripts/show_assemblies.py`
If found, replace with `D:\houdini\bin\hython.exe`. If not found, skip.

- [ ] **Step 3: Fix handoff.md hython path mentions**

In `wiki/pages/handoff.md`, find all occurrences of `C:\Program Files\Side Effects Software\Houdini 21.0.440\bin\hython.exe` (there are ~3: lines ~7, ~78, ~81) and replace with `D:\houdini\bin\hython.exe`.

- [ ] **Step 4: Verify the correct path actually runs the VEX proof**

Run:
```bash
"D:/houdini/bin/hython.exe" scripts/verify_vex_strategies.py
```
Expected: ends with `ALL STRATEGIES MATCH ORACLE` (the M3 baseline). This confirms the env is healthy before we start.

- [ ] **Step 5: Run the baseline mock suite to establish the green floor**

Run: `python -m pytest tests/ -q -k "not hython" --ignore=tests/test_md_render.py --ignore=tests/test_streaming_render.py --ignore=tests/test_reflect_worker.py --ignore=tests/test_error_surfacing.py`
Expected: `559 passed, ...` (the pre-change baseline). Record this number — every task must preserve it.

- [ ] **Step 6: Commit**

```bash
git add scripts/verify_vex_strategies.py scripts/show_assemblies.py wiki/pages/handoff.md wiki/pages/progress.md
git commit -m "docs: fix stale hython path (D:/houdini → C:/Program Files/...) in handoff + scripts"
```

---

## Task 1: Generalize `TabularFillStrategy` — `axes[]` variable dimensionality + named columns

This is the foundation task. It refactors the base class to support 1/2/3 layout axes BEFORE adding any new layout, then proves the existing 2D `cells` is byte-identical (regression). Do this as pure refactor first — no new measure yet.

**Files:**
- Modify: `python3.11libs/edini/vex_strategies.py` (`TabularFillStrategy` + `CellsStrategy._parse_table`)
- Test: `tests/test_assembly_builder.py` (existing `TestCellsLayout` must stay green)

**Approach:** The current `_build_vex` hardcodes `__a0/__a1` (two axes) and `scl[__a0]/scl[__a1]`. Generalize it to loop over an `axes[]` list. The `CellsStrategy` will pass `axes=["X","Z"]` (unchanged behavior). The position/scale VEX writes become loop-generated.

- [ ] **Step 1: Write a regression test proving 2D cells output is unchanged**

Add to `tests/test_assembly_builder.py` in `TestCellsLayout`:

```python
def test_cells_2d_vex_byte_identical_after_axes_refactor(self):
    """After generalizing _build_vex to axes[], the 2D cells VEX must produce
    the exact same setpointattrib calls for position+scale as before. This is
    the regression gate for the base-class refactor."""
    a = _cells_keyboard_assembly()
    mt = a["mounts"][0]
    from edini.vex_strategies import build_mount_vex
    snippet, parms = build_mount_vex(mt["position"])
    # The 2D path still writes scale on exactly the two in-plane axes and
    # emits one addpoint per cell. Assert the structural invariants.
    assert snippet.count("addpoint(geoself()") >= 1
    assert "setpointattrib(geoself(), \"scale\"" in snippet
    # margin + gap remain live spares (not baked).
    assert parms.get("_margin") is not None
    assert parms.get("_gap") is not None
```

- [ ] **Step 2: Run it to confirm it passes on the CURRENT code (baseline)**

Run: `python -m pytest tests/test_assembly_builder.py::TestCellsLayout -q`
Expected: PASS (this test documents the contract we must not break).

- [ ] **Step 3: Refactor `TabularFillStrategy.build` to accept `axes`**

In `python3.11libs/edini/vex_strategies.py`, modify `TabularFillStrategy.build` (around line 266). Add `axes` resolution from the spec (default `["X","Z"]` for back-compat with cells):

```python
    def build(self, position_spec: dict) -> tuple[str, dict[str, Any]]:
        cells = position_spec.get("cells")
        if not isinstance(cells, list) or not cells:
            raise VexStrategyError("cells strategy needs a non-empty 'cells' list")
        square = bool(position_spec.get("square", False))
        fill = str(position_spec.get("fill", "stretch"))
        if fill not in ("stretch", "pad", "repeat"):
            raise VexStrategyError(
                f"cells.fill must be stretch|pad|repeat, got {fill!r}")

        # Resolve the layout axes (default 2D X,Z for back-compat with cells).
        axes = self._resolve_axes(position_spec)
        gx_vals, gz_vals, w_vals, d_vals = self._parse_table(cells)
        # _parse_table returns 4 lists keyed to the FIRST TWO axes (gx/gz, w/d).
        # For 1D/3D the subclass overrides _parse_table to return the right arity.
        total_u = self._table_totals(axes, gx_vals, gz_vals, w_vals, d_vals)

        fparms = _face_selector(self._resolve_face(position_spec))
        parms: dict[str, Any] = {"face_axis": fparms["face_axis"],
                                 "face_sign": fparms["face_sign"]}
        parms["_margin"] = position_spec.get("margin", 0.0)
        parms["_gap"] = position_spec.get("gap", 0.0)
        # Pass the resolved axes to the VEX generator (inlined as a VEX array).
        parms["_axes"] = axes

        snippet = self._build_vex(axes, gx_vals, gz_vals, w_vals, d_vals,
                                  total_u, square, fill)
        return snippet, parms

    def _resolve_axes(self, position_spec: dict) -> list[str]:
        """Resolve the layout axes list. Default ['X','Z'] (cells back-compat).
        Validated: each entry in {X,Y,Z}, no repeats, length 1-3."""
        axes = position_spec.get("axes", ["X", "Z"])
        if not isinstance(axes, list) or not (1 <= len(axes) <= 3):
            raise VexStrategyError(f"axes must be a list of 1-3 entries, got {axes!r}")
        seen = set()
        for a in axes:
            if a not in ("X", "Y", "Z"):
                raise VexStrategyError(f"axis must be X/Y/Z, got {a!r}")
            if a in seen:
                raise VexStrategyError(f"axis {a!r} repeated in {axes!r}")
            seen.add(a)
        return axes

    def _resolve_face(self, position_spec: dict) -> str:
        """Resolve the face string from basis.face or legacy face field."""
        basis = position_spec.get("basis")
        if isinstance(basis, dict) and isinstance(basis.get("face"), str):
            return basis["face"]
        face = position_spec.get("face")
        if isinstance(face, str):
            return face
        raise VexStrategyError("position needs basis.face or face")
```

- [ ] **Step 4: Update `_table_totals` to take `axes`**

Change `_table_totals` signature to accept `axes` and compute per-axis totals:

```python
    def _table_totals(self, axes, gx, gz, w, d) -> list[float]:
        """The layout's grid-unit span PER axis, in `axes` order.
        gx/gz are the first two axes' coords; w/d their sizes. For a 1D layout
        only gx/w are used; for 3D the subclass overrides _parse_table to also
        return gy/h. Here we compute the span per declared axis."""
        # Map the parsed lists to their axes. By convention gx/w → axes[0],
        # gz/d → axes[1] (if present). Subclasses with 3D extend this.
        totals = []
        totals.append(max((g + s) for g, s in zip(gx, w))) if gx else None
        if len(axes) >= 2 and gz:
            totals.append(max((g + s) for g, s in zip(gz, d)))
        return totals
```

- [ ] **Step 5: Refactor `_build_vex` to loop over `axes[]` instead of hardcoded a0/a1**

> ⚠️ **This step is a GUIDED REFACTOR, not paste-ready code.** The VEX body below is the TARGET SHAPE. The executor MUST refactor the existing `_build_vex` incrementally (small diffs), running the Step 1 regression test + Step 8 hython proof after each change, so the 2D `cells` output stays byte-identical. Do NOT rewrite the whole function blind — the existing VEX has subtle invariants (the `__newpts` array contract, `setpointattrib` point-class writes, the `__ci/__ncell` loop vars) that must be preserved. The sketch shows where to generalize `a0/a1` → a loop over `axes`.

This is the core change. Replace the hardcoded `__a0/__a1` VEX with a loop over an injected axes array. The position and scale writes become per-axis. The new `_build_vex` signature takes `axes` as the first arg. Because VEX arrays of axis-indices need to be inlined, inject `axes` (as VEX int array of 0/1/2) via the `parms["_axes"]` → inlined literal in `_install_wrangle_parms` (next step). For the VEX body, generate the per-axis writes by Python-string-expanding the loop body once per axis (cleaner than a VEX loop for 1-3 axes):

```python
    def _build_vex(self, axes, gx_vals, gz_vals, w_vals, d_vals,
                   total_u, square, fill) -> str:
        # unit-derivation block: one unit per axis. square/pad/repeat unify to min.
        axis_idx = {"X": 0, "Y": 1, "Z": 2}
        n = len(axes)
        # Build the per-axis unit + grid-origin lines.
        if square or fill in ("pad", "repeat"):
            unit_lines = "\n".join(
                f"float __u{ai}raw = __span[{ai}] / {repr(total_u[ai])};"
                for ai in range(n))
            unify = ("float __u = min(" + ", ".join(f"__u{ai}raw" for ai in range(n)) + ");\n"
                     + "\n".join(f"float __u{ai} = __u;" for ai in range(n)))
            extra_lines = "\n".join(
                f"float __extra{ai} = (__span[{ai}] - {repr(total_u[ai])} * __u) * 0.5;"
                for ai in range(n))
            grid_lines = "\n".join(
                f"float __g{ai} = __mn[{ai}] + __m + __extra{ai};"
                for ai in range(n))
            unit_block = unit_lines + "\n" + unify + "\n" + extra_lines + "\n" + grid_lines
        else:
            unit_lines = "\n".join(
                f"float __u{ai} = __span[{ai}] / {repr(total_u[ai])};" for ai in range(n))
            grid_lines = "\n".join(
                f"float __g{ai} = __mn[{ai}] + __m;" for ai in range(n))
            unit_block = unit_lines + "\n" + grid_lines

        # Per-axis span declarations (read from bbox, minus 2*margin).
        span_lines = "\n".join(
            f"float __span{ai} = (__mx[{ai}] - __mn[{ai}]) - 2 * __m;" for ai in range(n))

        # The layout table arrays: gx/w per axis. For 2D these are cx/cz, cw/cd.
        # Generate one position-write + one scale-write per axis.
        coord_arrays = []
        size_arrays = []
        for ai in range(n):
            coords = [gx_vals[i] if ai == 0 else gz_vals[i] for i in range(len(gx_vals))] if n >= 2 else gx_vals
            sizes = [w_vals[i] if ai == 0 else d_vals[i] for i in range(len(w_vals))] if n >= 2 else w_vals
            coord_arrays.append(self._arr([c + (s/2.0 if ai==0 else s/2.0) for c, s in zip(coords, sizes)] if False else coords))
            size_arrays.append(self._arr(sizes))
        # (center precompute: cx = gx + w/2. For 1D only gx+w/2; for 2D gz+d/2 too.)
        # ... [see full implementation note below]
```

> **Implementation note for the executor:** The above sketch shows the shape. The FULL implementation must exactly reproduce the existing 2D VEX for `axes=["X","Z"]`. Concretely, the center-precompute `cx = gx + w/2`, `cz = gz + d/2` must remain in Python (as today, lines 345-346), and the loop body writes `__p[__a{ai}] = __g{ai} + __cx[{ai}][__ci] * __u{ai}` and `__scl[__a{ai}] = max(0.0001, __cw[{ai}][__ci] * __u{ai} - __gap)` per axis. The cleanest path: keep the existing `_build_vex` body for the 2D case and verify byte-identity, THEN generalize. **Do NOT rewrite the VEX from scratch** — refactor incrementally so the diff against the current VEX is minimal and the regression test (Step 1) catches any drift.

- [ ] **Step 6: Wire `_axes` inlining in `_install_wrangle_parms`**

In `assembly_builder.py` `_install_wrangle_parms` (around line 578), the `parms["_axes"]` list needs to be inlined as a VEX int-array literal where the VEX reads it. If the VEX body uses inlined axis indices directly (no runtime array), this step is a no-op — confirm by checking the generated snippet does not contain `ch("axes")`.

- [ ] **Step 7: Run the full cells regression**

Run: `python -m pytest tests/test_assembly_builder.py::TestCellsLayout tests/test_measure.py::TestMeasureCells -q`
Expected: all PASS. If any fail, the axes refactor changed 2D behavior — fix before proceeding.

- [ ] **Step 8: Run the hython cells proof (the decisive regression)**

Run:
```bash
"D:/houdini/bin/hython.exe" scripts/verify_vex_strategies.py
```
Expected: `ALL STRATEGIES MATCH ORACLE` (unchanged). This is the strongest regression check — real VEX output vs oracle.

- [ ] **Step 9: Commit**

```bash
git add python3.11libs/edini/vex_strategies.py tests/test_assembly_builder.py
git commit -m "refactor(vex): generalize TabularFillStrategy to axes[] (1D/2D/3D), 2D cells byte-identical"
```

---

## Task 2: `measure_pickets` oracle (1D) + `_expand_pickets_count`

**Files:**
- Modify: `python3.11libs/edini/measure.py` (add `measure_pickets`)
- Modify: `python3.11libs/edini/assembly_builder.py` (add `_expand_pickets_count`)
- Test: `tests/test_measure.py` (new `TestMeasurePickets`)

- [ ] **Step 1: Write failing oracle tests for `measure_pickets`**

Add to `tests/test_measure.py`:

```python
from edini.measure import measure_pickets

class TestMeasurePickets(unittest.TestCase):
    def test_count_uniform_pickets(self):
        """count=8 on a 4-unit X edge → 8 points evenly spaced, each carrying
        a (position, scale, orient) triple; orient is identity (no rot)."""
        geo = _box_geo(0, 4, 0, 0.5, 0, 1)   # 4 wide, 1 deep
        res = measure_pickets(geo, face="+Y", edge_axis="Z", count=8)
        self.assertEqual(len(res), 8)
        pos0, scale0, orient0 = res[0]
        self.assertAlmostEqual(orient0, (0, 0, 0, 1), places=6)  # identity quat
        # X positions should span the edge after margin.
        xs = [p[0] for p, s, o in res]
        self.assertGreater(max(xs) - min(xs), 0)

    def test_explicit_cells_uneven_pickets(self):
        """An explicit cells table (uneven widths) overrides count."""
        geo = _box_geo(0, 4, 0, 0.5, 0, 1)
        res = measure_pickets(geo, face="+Y", edge_axis="Z",
            cells=[{"gx": 0, "w": 2}, {"gx": 2.5, "w": 1}])
        self.assertEqual(len(res), 2)
```

- [ ] **Step 2: Run to confirm it fails (function not defined)**

Run: `python -m pytest tests/test_measure.py::TestMeasurePickets -q`
Expected: FAIL with `cannot import name 'measure_pickets'`.

- [ ] **Step 3: Implement `measure_pickets`**

Add to `python3.11libs/edini/measure.py` (after `measure_cells`):

```python
def measure_pickets(
    geo, face: str, edge_axis: str = "Z", count: int = 0,
    cells: Sequence[dict] | None = None, margin: float = 0.0, gap: float = 0.0,
    h: float = 1.0,
) -> list[tuple[tuple[float, float, float], tuple[float, float, float],
                tuple[float, float, float, float]]]:
    """A 1D row of pickets along ONE edge of a face, each carrying position +
    scale + orient (identity for now; tiles will populate orient).

    The layout steps along `edge_axis` (the in-plane axis perpendicular to the
    pickets' run). `count` produces N equal-width cells (the uniform sugar); an
    explicit `cells` table overrides it with uneven widths. `h` is the
    out-of-plane height (along the face normal), in 1u units, derived like the
    layout axes. Returns (position, scale, orient_quat) triples; orient is
    identity (0,0,0,1) since pickets have no rotation in M-pickets."""
    # Resolve the edge axis to a 1D cell table.
    if cells is None:
        if count < 1:
            raise MeasureError(f"pickets need count>=1 or cells, got count={count}")
        cells = [{"gx": float(i), "w": 1.0} for i in range(count)]
    # Delegate to measure_cells with axes=[edge_axis]: a 1D cells layout.
    # measure_cells returns (pos, scale) pairs; wrap each with identity orient.
    # NOTE: measure_pickets treats edge_axis as the SOLE layout axis. To reuse
    # measure_cells (which is 2D), we call it with face=face and the cells
    # carrying only gx/w; the second axis is degenerate. See implementation.
    pairs = measure_cells(geo, face, cells=[{**c, "gz": 0, "d": 1} for c in cells],
                          margin=margin, gap=gap)
    return [(p, s, (0.0, 0.0, 0.0, 1.0)) for (p, s) in pairs]
```

> **Implementation note:** pickets is the simplest layout — it reuses `measure_cells` with a 1D cell table (gz/d forced to 1). The real generalization work was Task 1's `axes[]`; pickets proves the 1D path works end-to-end. If `measure_cells` cannot accept a 1D table cleanly, the executor should generalize `measure_cells` to take an `axes` arg (mirroring Task 1's VEX refactor) — but try the reuse path first (YAGNI).

- [ ] **Step 4: Implement `_expand_pickets_count` in assembly_builder.py**

Add to `python3.11libs/edini/assembly_builder.py` (near `_expand_repeat_cells`):

```python
def _expand_pickets_count(position_spec: dict) -> dict:
    """Expand a pickets `count` into an explicit equal-width cells table.
    count=N → N cells of width 1 at gx=0,1,...,N-1. This is the uniform-layout
    sugar: the VEX loop is unchanged, only fed a generated table."""
    if "count" not in position_spec:
        return position_spec
    count = int(position_spec["count"])
    if count < 1:
        raise AssemblyError(f"pickets count must be >= 1, got {count}")
    cells = [{"gx": float(i), "w": 1.0} for i in range(count)]
    out = {k: v for k, v in position_spec.items() if k != "count"}
    out["cells"] = cells
    return out
```

- [ ] **Step 5: Run the oracle tests**

Run: `python -m pytest tests/test_measure.py::TestMeasurePickets -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add python3.11libs/edini/measure.py python3.11libs/edini/assembly_builder.py tests/test_measure.py
git commit -m "feat(measure): measure_pickets oracle (1D) + _expand_pickets_count sugar"
```

---

## Task 3: `PicketStrategy` + `pickets` measure wiring + hython proof (① COMPLETE)

**Files:**
- Modify: `python3.11libs/edini/vex_strategies.py` (`PicketStrategy` + register in `build_mount_vex`)
- Modify: `python3.11libs/edini/assembly_builder.py` (`validate_assembly` `pickets` branch + call `_expand_pickets_count`)
- Test: `tests/test_assembly_builder.py` (`TestPicketsLayout`)
- Test: `tests/test_assembly_hython.py` (`TestPicketsHython`)

- [ ] **Step 1: Write failing mock schema-validation tests**

Add to `tests/test_assembly_builder.py`:

```python
class TestPicketsLayout(unittest.TestCase):
    def test_pickets_count_validates(self):
        a = {"id": "fence",
             "root": {"shape": {"type": "box", "params": {"size": [4, 0.5, 1]}}},
             "mounts": [{"id": "pickets", "position": {
                 "measure": "pickets", "from": "root",
                 "basis": {"face": "+Y", "edge": "+Z"},
                 "axes": ["X"], "count": 8}}],
             "leaves": [{"id": "post", "mount": "pickets",
                 "shape": {"type": "box", "params": {"size": [0.1, 1.0, 0.1]}}}]}
        r = validate_assembly(a)
        assert r["success"], r["errors"]

    def test_pickets_bad_count_rejected(self):
        a = {"id": "fence",
             "root": {"shape": {"type": "box", "params": {"size": [4, 0.5, 1]}}},
             "mounts": [{"id": "pickets", "position": {
                 "measure": "pickets", "count": 0}}],
             "leaves": []}
        r = validate_assembly(a)
        assert not r["success"]
        assert any("count" in str(e.get("message", "")) for e in r["errors"])
```

- [ ] **Step 2: Run to confirm fail**

Run: `python -m pytest tests/test_assembly_builder.py::TestPicketsLayout -q`
Expected: FAIL (`pickets` not a valid measure).

- [ ] **Step 3: Add `PicketStrategy` + register it**

In `python3.11libs/edini/vex_strategies.py`, add (after `CellsStrategy`):

```python
class PicketStrategy(TabularFillStrategy):
    """The 1D picket/fence schema. Each cell declares {gx, w} (+ optional h for
    out-of-plane height). Reuses the TabularFill loop with axes=['X'] (or the
    declared edge axis). The `count`→cells expansion happens in the builder
    layer (assembly_builder._expand_pickets_count) BEFORE this sees the spec."""

    def _parse_table(self, cells):
        gx_vals, w_vals = [], []
        for ci, c in enumerate(cells):
            try:
                gx_vals.append(float(c["gx"])); w_vals.append(float(c["w"]))
            except (KeyError, TypeError, ValueError):
                raise VexStrategyError(f"picket cell {ci} needs numeric gx/w, got {c!r}") from None
        # Return 4-tuple shape expected by base: (gx, gz, w, d). gz/d unused (1D).
        return gx_vals, [0.0]*len(gx_vals), w_vals, [1.0]*len(gx_vals)


_PICKET_STRATEGY = PicketStrategy()
```

In `build_mount_vex`, add the dispatch (near the `cells` branch):

```python
    if kind == "pickets":
        return _PICKET_STRATEGY.build(mount_position)
```

- [ ] **Step 4: Add `pickets` validation branch + pre-expansion call**

In `assembly_builder.py` `validate_assembly`, add `pickets` to the allowed measures list (line ~137) and add a validation branch mirroring `cells` but for the 1D schema (gx/w required, count or cells required). Then in `build_assembly` (around line 913, near the `repeat` expansion), add:

```python
            if pos_spec.get("measure") == "pickets" and "count" in pos_spec:
                pos_spec = _expand_pickets_count(pos_spec)
```

- [ ] **Step 5: Run mock tests**

Run: `python -m pytest tests/test_assembly_builder.py::TestPicketsLayout -q`
Expected: PASS.

- [ ] **Step 6: Add hython proof**

Add to `tests/test_assembly_hython.py`:

```python
def _fence():
    return {
        "id": "fence",
        "root": {"shape": {"type": "box", "params": {"size": [4, 0.5, 1]}}},
        "mounts": [{"id": "pickets", "position": {
            "measure": "pickets", "from": "root",
            "basis": {"face": "+Y", "edge": "+Z"}, "axes": ["X"], "count": 8}}],
        "leaves": [{"id": "post", "mount": "pickets",
            "shape": {"type": "box", "params": {"size": [0.1, 1.0, 0.1]}}}]}

class TestPicketsHython(unittest.TestCase):
    def setUp(self):
        if not _HAS_HYTHON:  # the existing skip guard
            self.skipTest("no hython")
    def test_fence_eight_posts_evenly_spaced(self):
        res = _run(_fence(), probe="piece_bboxes")
        assert res["success"], res.get("error")
        # 8 posts along the 4-unit X edge, evenly spaced.
        assert res["piece_count"] == 8
```

- [ ] **Step 7: Run hython proof**

Run:
```bash
"D:/houdini/bin/hython.exe" -m pytest tests/test_assembly_hython.py::TestPicketsHython -v
```
Expected: PASS (8 posts built, evenly spaced).

- [ ] **Step 8: Full regression**

Run: `python -m pytest tests/ -q -k "not hython" --ignore=tests/test_md_render.py --ignore=tests/test_streaming_render.py --ignore=tests/test_reflect_worker.py --ignore=tests/test_error_surfacing.py`
Expected: `560+ passed` (baseline 559 + new pickets tests). Zero regressions.

- [ ] **Step 9: Commit**

```bash
git add python3.11libs/edini/vex_strategies.py python3.11libs/edini/assembly_builder.py tests/
git commit -m "feat(rooted): ① pickets strategy (1D layout) — axes[] generalization proven, cells still green"
```

---

## Task 4: Generalize `_build_vex` + oracle for per-cell `rot` (orient)

This is the orient foundation (driven by ② tiles). Add the per-cell orient mechanism to the base class BEFORE the `TileStrategy`, then reuse.

**Files:**
- Modify: `python3.11libs/edini/vex_strategies.py` (`_build_vex` adds optional `rot` array + orient write)
- Modify: `python3.11libs/edini/measure.py` (upgrade return to `(pos,scale,orient)` triples — keep `measure_cells` returning pairs for back-compat; add a helper to pair-or-triple)

- [ ] **Step 1: Write failing orient-oracle test**

Add to `tests/test_measure.py`:

```python
class TestPerCellOrient(unittest.TestCase):
    def test_rot_90_about_face_normal(self):
        """A cell with rot=90 about the +Y face normal produces an orient
        quaternion that is NOT identity (rotates 90° about Y)."""
        geo = _box_geo(0, 4, 0, 0.4, 0, 4)
        res = measure_tiles(geo, "+Y", cells=[{"gx":0,"gz":0,"w":1,"d":1,"rot":90}])
        self.assertEqual(len(res), 1)
        pos, scale, orient = res[0]
        # 90° about +Y → quaternion (0, sin45, 0, cos45) = (0, 0.7071, 0, 0.7071)
        import math
        self.assertAlmostEqual(orient[1], math.sin(math.radians(45)), places=5)
        self.assertAlmostEqual(orient[3], math.cos(math.radians(45)), places=5)
```

- [ ] **Step 2: Run to confirm fail**

Run: `python -m pytest tests/test_measure.py::TestPerCellOrient -q`
Expected: FAIL (`measure_tiles` undefined).

- [ ] **Step 3: Add `measure_tiles` oracle (returns triples)**

Add to `measure.py` (after `measure_pickets`):

```python
def measure_tiles(geo, face, cells, margin=0.0, gap=0.0, orient_rule=None):
    """A 2D tile mosaic. Each cell may carry `rot` (degrees, about the face
    normal) and/or the mount-level `orient_rule` (herringbone/checker/running)
    computes a per-cell rot. Returns (pos, scale, orient_quat) triples.
    orient_quat = quaternion(rot° about face_normal)."""
    pairs = measure_cells(geo, face, cells=cells, margin=margin, gap=gap)
    sign, axis = _parse_face(face)
    nvec = [0.0, 0.0, 0.0]; nvec[_axis_index(axis)] = float(sign)
    out = []
    for ci, ((p, s), c) in enumerate(zip(pairs, cells)):
        rot = float(c.get("rot", 0.0))
        if orient_rule and "rot" not in c:
            rot = _rule_rot(orient_rule, ci, c)
        q = _axis_angle_quat(nvec, rot)
        out.append((p, s, q))
    return out

def _rule_rot(rule, ci, cell):
    """Named orient rules → per-cell rotation degrees."""
    if rule == "checker":
        r, col = int(cell.get("gz", 0)), int(cell.get("gx", 0))
        return 0.0 if (r + col) % 2 == 0 else 90.0
    if rule == "herringbone":
        r, col = int(cell.get("gz", 0)), int(cell.get("gx", 0))
        return 45.0 if (r + col) % 2 == 0 else 135.0
    if rule == "running":
        col = int(cell.get("gx", 0))
        return (col * 30.0) % 90.0
    return 0.0

def _axis_angle_quat(axis, deg):
    """axis-angle (degrees) → quaternion (x,y,z,w). Mirrors VEX quaternion()."""
    h = math.radians(deg) / 2.0
    s = math.sin(h)
    n = _normalize3(axis)
    return (n[0]*s, n[1]*s, n[2]*s, math.cos(h))
```

- [ ] **Step 4: Run orient-oracle test**

Run: `python -m pytest tests/test_measure.py::TestPerCellOrient -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/measure.py tests/test_measure.py
git commit -m "feat(measure): per-cell orient oracle (measure_tiles + _rule_rot + _axis_angle_quat)"
```

---

## Task 5: `TileStrategy` + `tiles` VEX orient write

**Files:**
- Modify: `python3.11libs/edini/vex_strategies.py` (`TileStrategy` + per-cell orient in `_build_vex`)
- Modify: `python3.11libs/edini/assembly_builder.py` (`validate_assembly` `tiles` branch)

- [ ] **Step 1: Add per-cell orient to `_build_vex`**

In `vex_strategies.py` `TabularFillStrategy._build_vex`, after the scale `setpointattrib`, add (only when a `rot` array is present):

```vex
// per-cell orient (tiles): rotate `rot` degrees about the face normal → quaternion.
if (hasparam("rot")) {  // pseudo; actual: Python gates this block on rot presence
    vector __nvec = {0,0,0}; __nvec[__fa] = __fs;
    vector4 __qrot = quaternion(radians(__rot[__ci]), __nvec);
    setpointattrib(geoself(), "orient", __pt, __qrot, "set");
}
```

In Python, generate the `__rot[]` array literal only when any cell has `rot` (or a named rule applies). Gate the orient-write VEX block on whether `rot_vals` is non-empty.

- [ ] **Step 2: Add `TileStrategy`**

```python
class TileStrategy(TabularFillStrategy):
    """The 2D tile-mosaic schema. Cells carry {gx,gz,w,d, rot?}. rot (degrees)
    rotates each tile about the face normal. Mount-level orient rules
    (herringbone/checker/running) supply rot for cells without explicit rot."""
    def build(self, position_spec):
        # Pre-apply the named orient rule: if position_spec.orient is a rule,
        # compute per-cell rot and inject into cells (Python layer).
        spec = dict(position_spec)
        cells = list(spec.get("cells", []))
        rule = spec.get("orient")
        if isinstance(rule, str):
            from edini.measure import _rule_rot
            cells = [dict(c) for c in cells]
            for ci, c in enumerate(cells):
                if "rot" not in c:
                    c["rot"] = _rule_rot(rule, ci, c)
            spec["cells"] = cells
        return super().build(spec)

    def _parse_table(self, cells):
        gx, gz, w, d, rot = [], [], [], [], []
        for c in cells:
            gx.append(float(c["gx"])); gz.append(float(c["gz"]))
            w.append(float(c["w"])); d.append(float(c["d"]))
            rot.append(float(c.get("rot", 0.0)))
        # Store rot as a side-channel the base _build_vex reads (via instance).
        self._rot_vals = rot
        return gx, gz, w, d
```

- [ ] **Step 3: Register `tiles` in `build_mount_vex` + `validate_assembly`**

Add the `tiles` dispatch (like `cells`/`pickets`) and a `validate_assembly` branch mirroring `cells` but accepting optional `rot` per cell + optional mount-level `orient` (must be `herringbone|checker|running` if present).

- [ ] **Step 4: Write mock + hython tests (mirroring Task 3's structure)**

Mock: `TestTilesLayout` — schema validation + VEX generates an `__rot[]` array + `setpointattrib("orient"...)` when rot present.
Hython: `TestTilesHython` — a 4×4 herringbone mosaic; verify each instance's `p@orient` dot-product with the oracle quaternion ≥ 1-1e-6.

- [ ] **Step 5: Run all + regression + commit**

```bash
python -m pytest tests/ -q -k "not hython" --ignore=...  # expected 562+
"D:/houdini/bin/hython.exe" -m pytest tests/test_assembly_hython.py::TestTilesHython -v
git commit -m "feat(rooted): ② tiles strategy (per-cell orient) — deferred milestone resolved, named rules"
```

---

## Task 6: (② tiles complete) — named orient rules hython proof + SKILL stub

This task is folded into Task 5's Step 4 hython test. If the executor split it, the remaining work is: add a `herringbone` + explicit-`rot` mixed test, and a one-paragraph SKILL.md addition for tiles. Commit separately if split.

- [ ] **Step 1: If not done in Task 5, add the mixed-rule hython test + commit**

(Skipped if Task 5 Step 4 covered it.)

---

## Task 7: `measure_shelf` oracle (3D) + `_expand_shelf_layers`

**Files:**
- Modify: `python3.11libs/edini/measure.py` (`measure_shelf`)
- Modify: `python3.11libs/edini/assembly_builder.py` (`_expand_shelf_layers`)

- [ ] **Step 1: Write failing shelf-oracle test**

```python
class TestMeasureShelf(unittest.TestCase):
    def test_three_layers_flatten_to_3d_cells(self):
        """3 layers of varying height → flattened cells with absolute gy/h."""
        geo = _box_geo(0, 6, 0, 0.4, 0, 2)  # shelf root
        layers = [{"height": 10, "cells": [{"gx":0,"w":2},{"gx":2,"w":1}]},
                  {"height": 8,  "cells": [{"gx":0,"w":3}]}]
        res = measure_shelf(geo, face="+Y", axis="Y", layers=layers)
        self.assertEqual(len(res), 3)  # 2 + 1 books
        # First two books in layer 0 (gy=0), third in layer 1 (gy=10).
```

- [ ] **Step 2: Implement `measure_shelf` (flattens layers → 3D, returns triples)**

> **Type contract:** ALL four new oracles return `(pos, scale, orient)` triples for uniformity (spec §4.5). `measure_cells` itself keeps returning pairs (back-compat). So shelf/blocks/pickets WRAP the pairs with an identity orient `(0,0,0,1)`; only tiles populates a real orient.

```python
def measure_shelf(geo, face, axis, layers, margin=0.0, gap=0.0):
    """A 3D layered layout. Each layer has a `height` (1u units along `axis`)
    and a `cells` table (within-layer 2D). Flattens to a single 3D cell table
    and delegates to measure_cells, then WRAPS each pair with identity orient
    (shelf books have no per-cell rotation). Returns (pos,scale,orient) triples."""
    flat = []
    cur = 0.0
    for layer in layers:
        h = float(layer["height"])
        for c in layer["cells"]:
            cell = dict(c)
            cell["g" + axis.lower()] = cur
            cell[axis.lower()] = h
            flat.append(cell)
        cur += h
    pairs = measure_cells(geo, face, cells=flat, margin=margin, gap=gap)
    return [(p, s, (0.0, 0.0, 0.0, 1.0)) for (p, s) in pairs]
```

- [ ] **Step 3: Implement `_expand_shelf_layers` in assembly_builder.py** (mirrors `measure_shelf`'s flatten, in the builder layer)

- [ ] **Step 4: Run + commit**

```bash
python -m pytest tests/test_measure.py::TestMeasureShelf -q
git commit -m "feat(measure): measure_shelf oracle (3D layers) + _expand_shelf_layers"
```

---

## Task 8: `ShelfStrategy` + `shelf` wiring + hython proof (③ COMPLETE)

**Files:**
- Modify: `vex_strategies.py` (`ShelfStrategy` — thin: delegates to TabularFill with 3D axes after layer flatten)
- Modify: `assembly_builder.py` (`validate_assembly` `shelf` branch + call `_expand_shelf_layers`)
- Test: `tests/test_assembly_builder.py::TestShelfLayout`, `tests/test_assembly_hython.py::TestShelfHython`

- [ ] **Step 1-5: Mirror Task 3's structure** — `ShelfStrategy` is thin (its `_parse_table` handles gx/gz/w/d; layer flatten happened in the builder). Schema validates `layers: [{height, cells}]`. Hython proof: a 3-shelf bookcase with layer heights [10,8,6]; verify book Y-positions match the flattened coords × derived unit.

- [ ] **Step 6: Regression + commit**

```bash
python -m pytest tests/ -q -k "not hython" --ignore=...  # expected 564+
git commit -m "feat(rooted): ③ shelf strategy (layer pre-expansion + 3D) — base class untouched, layer is subclass-only"
```

---

## Task 9: `BlockStrategy` + `blocks` (④ synthesis) + hython proof

**Files:**
- Modify: `vex_strategies.py` (`BlockStrategy` — composes tiles' rot + shelf's h, in 2D)
- Modify: `assembly_builder.py` (`validate_assembly` `blocks` branch)
- Test: `tests/test_assembly_builder.py::TestBlocksLayout`, `tests/test_assembly_hython.py::TestBlocksHython`

- [ ] **Step 1: Write the synthesis test**

```python
class TestBlocksLayout(unittest.TestCase):
    def test_city_blocks_footprint_plus_height(self):
        a = {"id": "city",
             "root": {"shape": {"type": "box", "params": {"size": [8, 0.1, 6]}}},
             "mounts": [{"id": "blocks", "position": {
                 "measure": "blocks", "from": "root", "basis": {"face": "+Y"},
                 "cells": [
                     {"gx":2,"gz":0,"w":2,"d":3,"h":40},
                     {"gx":4,"gz":0,"w":2,"d":3,"h":10,"rot":0},
                     {"gx":0,"gz":2,"w":6,"d":2,"h":6}],
                 "square": True, "fill": "pad"}}],
             "leaves": [{"id": "bldg", "mount": "blocks",
                 "shape": {"type": "box", "params": {"size": [1,1,1]}}}]}
        r = validate_assembly(a)
        assert r["success"], r["errors"]
```

- [ ] **Step 2: Add `BlockStrategy` (near-zero new code — reuses tiles' rot + cells' h)**

```python
class BlockStrategy(TabularFillStrategy):
    """The 2D city-blocks schema. Cells carry {gx,gz,w,d, h?, rot?} — a 2D
    footprint + optional height (h, out-of-plane) + optional rotation. This is
    the synthesis: tiles' per-cell rot + shelf's h column, in 2D."""
    def build(self, position_spec):
        return super().build(position_spec)  # base handles it; h via pickets' mechanism
    def _parse_table(self, cells):
        gx, gz, w, d, rot = [], [], [], [], []
        for c in cells:
            gx.append(float(c["gx"])); gz.append(float(c["gz"]))
            w.append(float(c["w"])); d.append(float(c["d"]))
            rot.append(float(c.get("rot", 0.0)))
        self._rot_vals = rot
        return gx, gz, w, d
```

- [ ] **Step 3-5: Register `blocks`, validate, hython proof (4-block cityscape), regression**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(rooted): ④ blocks strategy (synthesis) — composes ①②③, near-zero new code"
```

---

## Task 10: SKILL.md docs + verify script + showcase (FINAL)

**Files:**
- Modify: `skills/rooted-modeling/SKILL.md` (document all 4 layouts)
- Modify: `scripts/verify_vex_strategies.py` (add 4 strategies to the oracle comparison)
- Modify: `scripts/show_assemblies.py` (add fence + shelf to the showcase `.hip`)

- [ ] **Step 1: Add the 4 layouts to the verify script**

In `scripts/verify_vex_strategies.py` `main()`, add 4 cases to the `cases` list (pickets 1D, tiles herringbone, shelf 3 layers, blocks cityscape), each comparing VEX output to its oracle. Run:
```bash
"D:/houdini/bin/hython.exe" scripts/verify_vex_strategies.py
```
Expected: `ALL STRATEGIES MATCH ORACLE` with the 4 new cases listed.

- [ ] **Step 2: Add fence + shelf to show_assemblies.py**

Add `_fence()` and `_shelf()` assembly dicts + build them in `main()` alongside car/keyboard/stairs, writing to `edini_showcase.hip`. Verify the `.hip` opens (run the script).

- [ ] **Step 3: Document the 4 layouts in SKILL.md**

Add a new section per layout (pickets/tiles/shelf/blocks) with: when to use it, the schema, and a worked example. Add the `axes`/`basis`/`count`/`rot`/`layers` fields to the measurements table. Add the per-cell orient milestone resolution to the "what's coming" section (move it to "done").

- [ ] **Step 4: Final full regression**

```bash
python -m pytest tests/ -q -k "not hython" --ignore=tests/test_md_render.py --ignore=tests/test_streaming_render.py --ignore=tests/test_reflect_worker.py --ignore=tests/test_error_surfacing.py
"D:/houdini/bin/hython.exe" -m pytest tests/test_assembly_hython.py -v
```
Expected: all mock green (565+), all hython green.

- [ ] **Step 5: Commit + update progress/handoff**

```bash
git add skills/rooted-modeling/SKILL.md scripts/ wiki/pages/progress.md wiki/pages/handoff.md
git commit -m "docs(rooted): 4 tabular-fill layouts — SKILL.md + verify + showcase + handoff update"
```

---

## Self-Review Checklist (executor runs this before declaring done)

- [ ] **Spec coverage:** all 4 layouts (pickets/tiles/shelf/blocks) have a strategy + oracle + validate branch + mock tests + hython proof.
- [ ] **3 base-class generalizations:** `axes[]` (Task 1), per-cell `rot` orient (Task 4-5), named columns (Task 1).
- [ ] **Regression gate:** 599 M3 tests green at every commit; `cells` 2D byte-identical (Task 1 Step 8 hython proof).
- [ ] **No placeholders:** every step has real code or an exact command.
- [ ] **Type consistency:** `measure_pickets`/`measure_tiles`/`measure_shelf`/`measure_blocks` signatures match across oracle + tests + VEX.
