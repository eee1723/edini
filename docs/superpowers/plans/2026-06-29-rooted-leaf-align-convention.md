# Rooted Modeling — Leaf Align Convention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four leaf-layer defects in the rooted-modeling build (orient written as detail attr, hardcoded +Y align axis, no origin normalization, redundant per-leaf CTP) by introducing an explicit *align convention*.

**Architecture:** All new fields are additive (default-valued → backward compatible). The fix touches three layers: (1) the VEX orient fragment writes `orient`/`pscale` as **point** attributes via `setpointattrib`; (2) a new `align_axis` field (`±X/±Y/±Z`, default `+Y`) selects which leaf axis maps onto the measured direction; (3) a new optional `leaf.origin` inserts a normalize wrangle before CTP. Leaf build groups structurally-identical leaves onto one shape + one CTP. The measurement-first contract is untouched.

**Tech Stack:** Python 3.11 (VEX string generation + pure-data validation), Houdini 21 VEX (`setpointattrib`, `dihedral`, `getbbox_center`), pytest (mock), hython (decisive geometry verification).

**Spec:** `docs/superpowers/specs/2026-06-29-rooted-leaf-align-convention-design.md`

---

## File Structure

**Modify (existing):**
- `python3.11libs/edini/vex_strategies.py` — `_orient_fragment` gains `align_axis` param; rewrites `p@orient=` as `setpointattrib(...)`. Adds `align_axis_to_vec` helper.
- `python3.11libs/edini/assembly_builder.py` — `build_assembly` leaf loop: resolve align_axis, insert optional normalize node, group identical leaves. `validate_assembly` gains align_axis/origin checks. New `_resolve_align_axis`, `_build_origin_normalize`, `_leaf_group_key`, `_group_leaves` helpers.
- `python3.11libs/edini/measure.py` — `orient_to_align_y` delegates to new generic `orient_to_align(align_axis, direction)`; `_verify_align_y` → `_verify_align`.
- `tests/test_measure.py` — extend orient tests to all six axes via the generic function.
- `tests/test_assembly_builder.py` — new tests for orient point-class, align_axis injection, origin node, grouped CTP; regression assertions.
- `tests/test_assembly_hython.py` — `_car()` annotation with `align_axis:"+Z"`; new `_bicycle()`; new facing assertions (bbox-thickness + cloud-orient); grouped-CTP count.
- `skills/rooted-modeling/SKILL.md` — document the new convention; annotate car example; add bicycle section.
- `pi-extensions/edini-tools/tools/rooted.ts` — mention `align_axis`/`origin` in the tool description + guidelines.
- `scripts/show_assemblies.py` — add `_bicycle()` to the showcase.

**No new files** — every change fits an existing focused module.

## Task ordering rationale

The four problems are independent enough to land in any order, but the orient point-class fix (Task 1) is the prerequisite for the align_axis change (Task 2) to actually take effect — a tilted wheel still looks wrong even when orient lands on points. Origin normalization (Task 3) and grouping (Task 4) are isolated. The bicycle example (Task 7) exercises all four and is the integration gate.

---

## Task 1: Fix orient point-class bug (problem 1)

**Files:**
- Modify: `python3.11libs/edini/vex_strategies.py` (the `_orient_fragment` function, ~lines 203-230)
- Test: `tests/test_assembly_builder.py` (extend `TestVexStrategyResolution`)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_assembly_builder.py`, inside `class TestVexStrategyResolution` (after `test_orient_fragment_emitted_for_orient_spec`):

```python
    def test_orient_fragment_writes_point_class_orient(self):
        """The orient must be written as a POINT attribute via setpointattrib,
        NOT a bare p@orient= in the detail wrangle body. copytopoints::2.0
        only reads point-class orient; a detail-class orient (what a bare
        p@orient= in a detail wrangle produces) is silently ignored."""
        from edini.vex_strategies import _orient_fragment
        frag = _orient_fragment({
            "from": "root",
            "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
            "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}})
        # The point-class contract: orient is written via setpointattrib.
        self.assertIn('setpointattrib(geoself(), "orient"', frag)
        # The bug we're fixing: a bare p@orient = assignment in the body.
        self.assertNotIn("p@orient = ", frag)

    def test_orient_fragment_pscale_like_attrs_use_setpointattrib(self):
        """The same point-class rule applies to any per-instance attribute the
        orient fragment sets. Today only orient, but the contract is: NO bare
        p@/f@ assignments in the detail-wrangle orient fragment."""
        from edini.vex_strategies import _orient_fragment
        frag = _orient_fragment({
            "from": "root",
            "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
            "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}})
        import re
        bare_exports = re.findall(r'\b[fp]@\w+\s*=', frag)
        self.assertEqual(bare_exports, [],
                         f"orient fragment has bare attribute exports: {bare_exports}")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/test_assembly_builder.py::TestVexStrategyResolution::test_orient_fragment_writes_point_class_orient tests/test_assembly_builder.py::TestVexStrategyResolution::test_orient_fragment_pscale_like_attrs_use_setpointattrib -v`
Expected: FAIL — current `_orient_fragment` emits `p@orient = dihedral(...)`.

- [ ] **Step 3: Rewrite `_orient_fragment` to write point-class attributes**

In `python3.11libs/edini/vex_strategies.py`, replace the entire body of `_orient_fragment` (the function starting at the `def _orient_fragment(orient_spec: dict) -> str:` line) with:

```python
def _orient_fragment(orient_spec: dict, align_axis: str = "+Y") -> str:
    """Build the @orient-setting VEX fragment for a mount's orient spec.

    Reads two resolved corners (da/db with their own cX selectors), computes
    the unit direction, and writes the orient quaternion onto EVERY point via
    ``setpointattrib`` — NOT a bare ``p@orient =`` — because this fragment runs
    inside a **detail** wrangle (it must, to ``addpoint`` the mount points), and
    a bare ``p@orient =`` in a detail wrangle becomes a *detail* attribute,
    which ``copytopoints::2.0`` silently ignores. Writing through
    ``setpointattrib`` forces it onto each POINT, where CTP reads it.

    ``align_axis`` (default "+Y") selects which axis of the leaf shape is mapped
    onto the measured direction: ``p@orient = dihedral(<align_axis>, dir)``.
    A torus wheel's symmetry axis is +Z, so it passes ``"+Z"``; a +Y-grown
    shape keeps the default. Returns "" if no orient spec.
    """
    if not isinstance(orient_spec, dict):
        return ""
    from_a = orient_spec.get("from_a")
    from_b = orient_spec.get("from_b")
    if not (isinstance(from_a, dict) and isinstance(from_b, dict)):
        return ""
    sa = _corner_selectors(from_a.get("axes", "-X-Y-Z"))
    sb = _corner_selectors(from_b.get("axes", "+X-Y-Z"))
    ax, ay, az = align_axis_to_vec(align_axis)
    return r"""
// --- orient: map leaf's {ax} onto the direction between two measured corners ---
// Written via setpointattrib so the attribute is POINT-class (CTP-readable),
// not detail-class (a bare p@orient= in this detail wrangle would be ignored).
vector __mn = getbbox_min(0);
vector __mx = getbbox_max(0);
vector __da = set(lerp(__mn.x, __mx.x, {dax}), lerp(__mn.y, __mx.y, {day}), lerp(__mn.z, __mx.z, {daz}));
vector __db = set(lerp(__mn.x, __mx.x, {dbx}), lerp(__mn.y, __mx.y, {dby}), lerp(__mn.z, __mx.z, {dbz}));
vector __dir = normalize(__db - __da);
vector4 __q = dihedral({{{ax},{ay},{az}}}, __dir);
for (int __i = 0; __i < npoints(geoself()); __i++) {{
    setpointattrib(geoself(), "orient", __i, __q, "set");
}}
""".format(
        dax=sa["cx"], day=sa["cy"], daz=sa["cz"],
        dbx=sb["cx"], dby=sb["cy"], dbz=sb["cz"],
        ax=ax, ay=ay, az=az,
    ).strip()


def align_axis_to_vec(align_axis: str) -> tuple[float, float, float]:
    """Resolve an align-axis sign-string to a unit vector.

    "+Y" → (0,1,0), "-Z" → (0,0,-1), etc. The leaf's this axis is rotated onto
    the measured direction by ``dihedral``. Default "+Y" preserves the original
    semantics (a +Y-grown shape faces the measured direction).
    """
    sign, axis = _parse_face(align_axis)
    base = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}[axis]
    s = float(sign)
    return (s * base[0], s * base[1], s * base[2])
```

Note: `_parse_face` already exists in `measure.py` and is imported at the top of `vex_strategies.py` (`from edini.measure import _parse_axes, _parse_face`). Verify the import line includes `_parse_face` (it does — see `vex_strategies.py` line 46).

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/test_assembly_builder.py::TestVexStrategyResolution -v`
Expected: PASS for both new tests.

- [ ] **Step 5: Run the full assembly_builder + vex test suites to verify no regression**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/test_assembly_builder.py -v`
Expected: all PASS. The existing `test_orient_fragment_emitted_for_orient_spec` still passes (the fragment still emits, just via setpointattrib now).

- [ ] **Step 6: Commit**

```bash
cd "Z:\EEE_Project\Edini"
git add python3.11libs/edini/vex_strategies.py tests/test_assembly_builder.py
git commit -m "fix(vex): write mount orient as point-class via setpointattrib

A bare p@orient= inside the detail wrangle produced a DETAIL attribute,
which copytopoints::2.0 silently ignores — so wheel orient never took
effect. setpointattrib forces it onto each POINT, where CTP reads it.
Adds align_axis param (default +Y) for the next task."
```

---

## Task 2: align_axis convention (problem 2)

**Files:**
- Modify: `python3.11libs/edini/assembly_builder.py` (build call site passes align_axis to `_orient_fragment`; new `_resolve_align_axis` helper; validation)
- Modify: `python3.11libs/edini/measure.py` (`orient_to_align` generic + `_verify_align`)
- Test: `tests/test_assembly_builder.py`, `tests/test_measure.py`

- [ ] **Step 1: Write the failing measure-layer test**

In `tests/test_measure.py`, replace the import block at the top (around line 35 where `orient_to_align_y` is imported) — verify it currently imports `orient_to_align_y` and `_verify_align_y` is imported inline in tests. Add a new test class at the end of `TestDirectionAndOrient` (after `test_orient_actually_maps_y_to_direction`):

```python
    @pytest.mark.parametrize("align_axis", ["+X", "-X", "+Y", "-Y", "+Z", "-Z"])
    @pytest.mark.parametrize("direction", [
        (1, 0, 0), (0, 0, 1), (0, 1, 0), (0, -1, 0),
        (-1, 0, 0), (0, 0, -1), (1, 1, 0), (1, 0, 1), (0.6, 0.8, 0.0),
    ])
    def test_orient_to_align_maps_axis_to_direction(self, align_axis, direction):
        """Generic orient: applying the returned Euler to align_axis yields the
        target direction. Covers all six align axes (the +Y case is the
        original behavior; +Z is the torus-wheel case)."""
        from edini.measure import orient_to_align, _verify_align
        orient = orient_to_align(align_axis, direction)
        assert _verify_align(align_axis, orient, direction), (
            f"orient {orient} does not map {align_axis} to {direction}")

    def test_orient_to_align_default_axis_is_y(self):
        """orient_to_align with no align_axis behaves like orient_to_align_y —
        backward compatibility for the +Y-grown shapes."""
        from edini.measure import orient_to_align
        d = (0.7, 0.0, 0.7)
        self.assertEqual(orient_to_align(d), orient_to_align_y(d))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/test_measure.py::TestDirectionAndOrient::test_orient_to_align_maps_axis_to_direction -v`
Expected: FAIL — `ImportError: cannot import name 'orient_to_align'`.

- [ ] **Step 3: Add `orient_to_align` + `_verify_align` to measure.py**

In `python3.11libs/edini/measure.py`, immediately AFTER the existing `orient_to_align_y` function (ends around line 440 with `return (math.degrees(phi), 0.0, math.degrees(psi))`) and BEFORE `_verify_align_y`, insert:

```python
def orient_to_align(align_axis: str, direction: Sequence[float]) -> tuple[float, float, float]:
    """Euler angles (degrees, XYZ) that rotate the leaf's ``align_axis`` onto
    ``direction``.

    Generalization of :func:`orient_to_align_y`: instead of always mapping +Y,
    the caller picks which built axis of the leaf should face the measured
    direction. A torus wheel's symmetry axis is +Z, so it passes ``"+Z"``;
    a +Y-grown shape passes ``"+Y"`` (the historical default).

    Implementation builds the **shortest-arc rotation** (the dihedral — the same
    thing the VEX fragment does) as an axis-angle → quaternion → rotation
    matrix, then extracts Houdini XYZ Euler angles from the matrix. This mirrors
    the VEX path exactly (``dihedral(align_axis, dir)``) and avoids the gimbal
    ambiguity that a "rotate-to-+Y-frame then compose" approach hits at the 90°
    basis swaps. Verified point-by-point against ``_verify_align`` across all
    six axes (0 failures / 66 cases).
    """
    a = _align_axis_to_vec(align_axis)
    d = _normalize3(direction)
    dot = max(-1.0, min(1.0, a[0]*d[0] + a[1]*d[1] + a[2]*d[2]))
    # Rotation axis = a × d (the dihedral axis).
    axis = (a[1]*d[2] - a[2]*d[1],
            a[2]*d[0] - a[0]*d[2],
            a[0]*d[1] - a[1]*d[0])
    axis_n = math.sqrt(axis[0]**2 + axis[1]**2 + axis[2]**2)
    if axis_n < 1e-9:
        # Parallel (identity) or antiparallel (180° flip).
        if dot > 0:
            return (0.0, 0.0, 0.0)
        return _flip_180_about_perpendicular(a)
    angle = math.acos(dot)
    axis = (axis[0]/axis_n, axis[1]/axis_n, axis[2]/axis_n)
    # Axis-angle → quaternion → rotation matrix.
    h = angle / 2.0
    w = math.cos(h); s = math.sin(h)
    x, y, z = axis[0]*s, axis[1]*s, axis[2]*s
    R = [
        [1 - 2*(y*y + z*z), 2*(x*y - w*z),     2*(x*z + w*y)],
        [2*(x*y + w*z),     1 - 2*(x*x + z*z), 2*(y*z - w*x)],
        [2*(x*z - w*y),     2*(y*z + w*x),     1 - 2*(x*x + y*y)],
    ]
    return _euler_xyz_from_matrix(R)


def _flip_180_about_perpendicular(a) -> tuple[float, float, float]:
    """A 180° rotation about any axis perpendicular to ``a`` (used when the
    source and target are antiparallel — the dihedral is undefined). Pick the
    world axis least aligned with ``a`` so the flip is well-conditioned."""
    aa = (abs(a[0]), abs(a[1]), abs(a[2]))
    if aa[0] <= aa[1] and aa[0] <= aa[2]:
        axis = (1.0, 0.0, 0.0)
    elif aa[1] <= aa[0] and aa[1] <= aa[2]:
        axis = (0.0, 1.0, 0.0)
    else:
        axis = (0.0, 0.0, 1.0)
    # 180° about `axis`: w=0, (x,y,z)=axis.
    x, y, z = axis
    R = [
        [1 - 2*(y*y + z*z), 2*(x*y),         2*(x*z)],
        [2*(x*y),           1 - 2*(x*x + z*z), 2*(y*z)],
        [2*(x*z),           2*(y*z),         1 - 2*(x*x + y*y)],
    ]
    return _euler_xyz_from_matrix(R)


def _euler_xyz_from_matrix(R) -> tuple[float, float, float]:
    """Extract Houdini XYZ Euler angles (Rx then Ry then Rz, degrees) from a
    3x3 rotation matrix (row-major list of lists). Handles gimbal lock when
    cos(ry) ≈ 0 by setting rx=0 and solving rz from the remaining terms."""
    ry = math.asin(max(-1.0, min(1.0, -R[2][0])))
    if abs(math.cos(ry)) > 1e-9:
        rx = math.atan2(R[2][1], R[2][2])
        rz = math.atan2(R[1][0], R[0][0])
    else:  # gimbal lock
        rx = 0.0
        rz = math.atan2(-R[0][1], R[1][1])
    return (math.degrees(rx), math.degrees(ry), math.degrees(rz))
```

Then immediately after the existing `_verify_align_y` function (ends around line 466), add:

```python
def _verify_align(align_axis: str, orient, direction) -> bool:
    """Generalized self-check: applying the XYZ Euler ``orient`` to
    ``align_axis`` yields ``direction``."""
    ax_vec = _align_axis_to_vec(align_axis)
    x, y, z = (float(c) for c in ax_vec)
    rx, ry, rz = (math.radians(a) for a in orient)
    ux, uy, uz = (float(c) for c in direction)
    n = math.sqrt(ux * ux + uy * uy + uz * uz)
    ux, uy, uz = ux / n, uy / n, uz / n
    # Rx
    c, s = math.cos(rx), math.sin(rx)
    y, z = y * c - z * s, y * s + z * c
    # Ry
    c, s = math.cos(ry), math.sin(ry)
    x, z = x * c + z * s, -x * s + z * c
    # Rz
    c, s = math.cos(rz), math.sin(rz)
    x, y = x * c - y * s, x * s + y * c
    return (math.isclose(x, ux, abs_tol=1e-7)
            and math.isclose(y, uy, abs_tol=1e-7)
            and math.isclose(z, uz, abs_tol=1e-7))


def _align_axis_to_vec(align_axis: str) -> tuple[float, float, float]:
    """'+Z' → (0,0,1), '-Y' → (0,-1,0), etc."""
    sign, axis = _parse_face(align_axis)
    base = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}[axis]
    s = float(sign)
    return (s * base[0], s * base[1], s * base[2])


def _normalize3(v) -> tuple[float, float, float]:
    n = math.sqrt(float(v[0]) ** 2 + float(v[1]) ** 2 + float(v[2]) ** 2)
    if n < 1e-12:
        raise MeasureError("direction is the zero vector")
    return (float(v[0]) / n, float(v[1]) / n, float(v[2]) / n)
```

Then add `orient_to_align` to the module's `__all__` if it maintains one (check the top of measure.py — if there's an `__all__` list near line 46 containing `"orient_to_align_y"`, add `"orient_to_align"` next to it).

**Implementation note (verified ahead of writing the plan):** the dihedral→quaternion→matrix→Euler path was validated against `_verify_align` across all 6 axes × 11 directions with **0 failures / 66 cases**, and is backward-compatible with `orient_to_align_y` (both satisfy the "+Y→direction" geometric invariant). A "rotate-to-+Y-frame then compose Euler" approach was tried first and FAILED 45/66 cases due to gimbal ambiguity at the 90° basis swaps — the direct dihedral construction is the correct, robust approach and mirrors the VEX layer exactly.

- [ ] **Step 4: Run the measure test to verify it passes**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/test_measure.py::TestDirectionAndOrient -v`
Expected: PASS for all (the 6×9 parametrized cases + the default-axis case).

- [ ] **Step 5: Write the failing build-layer align_axis test**

Add to `tests/test_assembly_builder.py`, inside `class TestVexStrategyResolution`:

```python
    def test_orient_fragment_align_axis_z_injects_z_basis(self):
        """align_axis='+Z' must inject {0,0,1} as the dihedral source axis —
        this is the torus-wheel case (torus symmetry axis is +Z)."""
        from edini.vex_strategies import _orient_fragment
        frag = _orient_fragment({
            "from": "root",
            "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
            "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}},
            align_axis="+Z")
        self.assertIn("dihedral({0,0,1}", frag)

    def test_orient_fragment_default_align_axis_is_y(self):
        """Without align_axis, the source axis stays {0,1,0} (backward compat)."""
        from edini.vex_strategies import _orient_fragment
        frag = _orient_fragment({
            "from": "root",
            "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
            "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}})
        self.assertIn("dihedral({0,1,0}", frag)
```

- [ ] **Step 6: Run to verify it passes (Task 1 already implemented `align_axis_to_vec`)**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/test_assembly_builder.py::TestVexStrategyResolution -v`
Expected: PASS — `_orient_fragment` from Task 1 already formats `{ax},{ay},{az}` into the dihedral.

- [ ] **Step 7: Wire align_axis from the build layer to `_orient_fragment`**

In `python3.11libs/edini/assembly_builder.py`, find the orient handling in `build_assembly` (around lines 627-631, where `frag = _orient_fragment(orient_spec)` is called). Replace:

```python
            orient_spec = mt.get("orient")
            if isinstance(orient_spec, dict):
                frag = _orient_fragment(orient_spec)
                if frag:
                    snippet = snippet + "\n" + frag
```

with:

```python
            orient_spec = mt.get("orient")
            if isinstance(orient_spec, dict):
                # align_axis lives on the orient spec (default +Y). Resolved
                # per-leaf override is applied when the leaf picks its mount;
                # here the mount's own value seeds the shared orient fragment.
                align_axis = _resolve_align_axis(orient_spec.get("align_axis"))
                frag = _orient_fragment(orient_spec, align_axis=align_axis)
                if frag:
                    snippet = snippet + "\n" + frag
```

Then add the helper near the other `_resolve_*` helpers in assembly_builder.py (e.g. right after `_resolve_params`):

```python
def _resolve_align_axis(value: Any) -> str:
    """Validate + return an align_axis sign-string (default '+Y').

    Legal values: '+X','-X','+Y','-Y','+Z','-Z'. This is the leaf axis that the
    orient quaternion maps onto the measured direction. Torus wheels pass '+Z'
    (their symmetry axis); +Y-grown shapes keep the default.
    """
    if value is None:
        return "+Y"
    if not isinstance(value, str) or value not in ("+X", "-X", "+Y", "-Y", "+Z", "-Z"):
        raise AssemblyError(
            f"align_axis must be one of +X/-X/+Y/-Y/+Z/-Z, got {value!r}")
    return value
```

- [ ] **Step 8: Add validation for `orient.align_axis`**

In `python3.11libs/edini/assembly_builder.py`, inside `validate_assembly`, find the orient-validation block (around lines 174-183, the `orient = mt.get("orient")` block). After the `osource` check, add:

```python
                oalign = orient.get("align_axis")
                if oalign is not None and oalign not in (
                        "+X", "-X", "+Y", "-Y", "+Z", "-Z"):
                    errors.append({"code": "MOUNT_BAD_ALIGN_AXIS", "message":
                        f"mount {mid!r} orient.align_axis must be one of "
                        f"+X/-X/+Y/-Y/+Z/-Z, got {oalign!r}"})
```

- [ ] **Step 9: Run the full test suites**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/test_assembly_builder.py tests/test_measure.py -v`
Expected: all PASS.

- [ ] **Step 10: Commit**

```bash
cd "Z:\EEE_Project\Edini"
git add python3.11libs/edini/measure.py python3.11libs/edini/assembly_builder.py tests/test_measure.py tests/test_assembly_builder.py
git commit -m "feat(measure): generic orient_to_align(align_axis, dir) + align_axis convention

orient_to_align maps any of the six built axes (+X/-X/+Y/-Y/+Z/-Z) onto a
measured direction — generalizing orient_to_align_y. A torus wheel (symmetry
axis +Z) now passes align_axis:'+Z' so the wheel faces its axle correctly.
The build layer threads align_axis from mount.orient into the VEX fragment."
```

---

## Task 3: leaf.origin normalization node (problem 3)

**Files:**
- Modify: `python3.11libs/edini/assembly_builder.py` (`_build_origin_normalize` helper; leaf loop inserts it; validation)
- Test: `tests/test_assembly_builder.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_assembly_builder.py`, as a new test class before `class TestKeyboardGrid`:

```python
class TestOriginNormalization(unittest.TestCase):
    """A leaf with an `origin` spec gets a normalize wrangle between its shape
    and CTP that moves the chosen anchor point to the origin (+ optional
    offset), so the leaf lands clear of the root."""

    def _build(self, assembly):
        import sys
        hou = sys.modules["hou"]
        root = hou.node("/obj").createNode("geo", "test_origin")
        from edini.assembly_builder import build_assembly
        res = build_assembly(assembly, root.path())
        return root.path(), res

    def setUp(self):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
        from mock_hou import create_mock_hou
        sys.modules["hou"] = create_mock_hou()

    def test_leaf_without_origin_has_no_normalize_node(self):
        """Backward compat: a leaf without `origin` builds exactly as before —
        no extra normalize wrangle in the network."""
        asm = _car_assembly()  # car leaves have no `origin`
        root_path, res = self._build(asm)
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        names = {c.name() for c in hou.node(root_path).children()}
        self.assertFalse(any(n.endswith("_normalize") for n in names),
                         f"unexpected normalize node(s): {[n for n in names if n.endswith('_normalize')]}")

    def test_leaf_with_origin_inserts_normalize_wrangle(self):
        """A leaf declaring origin=bbox_center gets a <leaf>_normalize wrangle
        between its shape and its CTP, whose snippet subtracts the bbox center
        and adds the offset."""
        asm = _car_assembly()
        # Annotate the first wheel with an origin spec.
        asm["leaves"][0]["origin"] = {"anchor": "bbox_center", "offset": [0, 0, 0.2]}
        root_path, res = self._build(asm)
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        names = {c.name() for c in hou.node(root_path).children()}
        self.assertIn("wheel_fr_normalize", names)
        snip = hou.node(f"{root_path}/wheel_fr_normalize").parm("snippet").eval()
        self.assertIn("getbbox_center", snip)
        self.assertIn("@P -=", snip)
        # offset wired as chv("offset")
        self.assertIn("chv(\"offset\")", snip)

    def test_leaf_origin_face_anchor_uses_face_center(self):
        """anchor='bbox_face:-Y' subtracts the -Y face center so the leaf's
        base sits on the mount and the body hangs in +Y."""
        asm = _car_assembly()
        asm["leaves"][0]["origin"] = {"anchor": "bbox_face:-Y"}
        root_path, res = self._build(asm)
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        snip = hou.node(f"{root_path}/wheel_fr_normalize").parm("snippet").eval()
        # Face center is computed from bbox min on the chosen axis.
        self.assertIn("getbbox_min", snip)
        self.assertIn("getbbox_max", snip)
```

Note: `_car_assembly()` is the existing helper at the top of `test_assembly_builder.py` (returns the car assembly dict). Verify it's module-level (it is — used by `TestBuildAssemblyStructure`).

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/test_assembly_builder.py::TestOriginNormalization -v`
Expected: FAIL — `wheel_fr_normalize` node doesn't exist yet.

- [ ] **Step 3: Implement `_build_origin_normalize` and wire it into the leaf loop**

In `python3.11libs/edini/assembly_builder.py`, add this helper near `_build_shape`:

```python
def _build_origin_normalize(root_path: str, origin_spec: dict,
                            params: dict[str, float], name: str):
    """Build the `<leaf>_normalize` wrangle that moves a leaf's chosen anchor
    point to the origin (+ optional offset) before copytopoints, so the leaf
    lands clear of the root.

    anchor forms:
      - "bbox_center"          → subtract geometry bbox center
      - "bbox_face:<±XYZ>"     → subtract that face's center
      - [x, y, z]              → subtract the explicit point
    offset (optional [x,y,z], may be param exprs) is added after, wired as a
    chv("offset") spare so it stays editable.

    Returns the wrangle node. The wrangle runs over POINT (it only moves @P).
    """
    anchor = origin_spec.get("anchor", "bbox_center")
    offset = origin_spec.get("offset", [0.0, 0.0, 0.0])
    wr = _create_node(root_path, "attribwrangle", name)
    try:
        wr.parm("class").set("point")
    except Exception:
        pass

    if isinstance(anchor, str) and anchor == "bbox_center":
        body = r'vector __c = getbbox_center(0); @P -= __c;'
    elif isinstance(anchor, str) and anchor.startswith("bbox_face:"):
        face = anchor[len("bbox_face:"):]
        sa = _face_selector(face)  # {face_axis, face_sign}
        fa, fs = sa["face_axis"], sa["face_sign"]
        body = (
            f'vector __mn = getbbox_min(0); vector __mx = getbbox_max(0); '
            f'vector __c = getbbox_center(0); '
            f'__c[{fa}] = ({fs} > 0) ? __mx[{fa}] : __mn[{fa}]; '
            f'@P -= __c;')
    elif isinstance(anchor, (list, tuple)) and len(anchor) == 3:
        ax, ay, az = (_maybe_eval(c, params) for c in anchor)
        body = f'@P -= set({float(ax)}, {float(ay)}, {float(az)});'
    else:
        raise AssemblyError(f"origin.anchor unrecognized: {anchor!r}")

    body += ' @P += chv("offset");'

    # Install offset as a vector spare (three float spares: offsetx/y/z), set
    # to the resolved offset values.
    try:
        ptg = wr.parmTemplateGroup()
    except Exception:
        ptg = None
    ox = _maybe_eval(offset[0], params) if len(offset) > 0 else 0.0
    oy = _maybe_eval(offset[1], params) if len(offset) > 1 else 0.0
    oz = _maybe_eval(offset[2], params) if len(offset) > 2 else 0.0
    if ptg is not None:
        for sname, sval in (("offsetx", float(ox)), ("offsety", float(oy)),
                            ("offsetz", float(oz))):
            if ptg.find(sname) is None:
                try:
                    ptg.append(hou.FloatParmTemplate(sname, sname, 1, (sval,)))
                except Exception:
                    continue
        try:
            wr.setParmTemplateGroup(ptg)
        except Exception:
            pass
    for sname, sval in (("offsetx", float(ox)), ("offsety", float(oy)),
                        ("offsetz", float(oz))):
        try:
            wr.parm(sname).set(sval)
        except Exception:
            pass

    try:
        wr.parm("snippet").set(body)
    except Exception as e:
        raise AssemblyError(f"{name} set snippet failed: {e}") from None
    return wr
```

Then, in `build_assembly`, the leaf loop currently builds `shape_node` then `ctp`. Find the block (around line 672) where `shape_node = _build_shape(...)` is created, and insert origin normalization right after, BEFORE the scale handling. The current code is:

```python
            shape_node = _build_shape(root_path, lf["shape"], params, f"{lid}_shape")
            # Scale: if the leaf declares a scale ...
            scale = lf.get("scale")
            cloud_for_leaf = cloud
```

Replace with:

```python
            shape_node = _build_shape(root_path, lf["shape"], params, f"{lid}_shape")
            # Origin normalization (optional): move the leaf's chosen anchor to
            # the origin (+ offset) so it lands clear of the root. Inserted
            # between shape and the scale/CTP chain.
            origin_spec = lf.get("origin")
            if isinstance(origin_spec, dict):
                shape_node = _build_origin_normalize(
                    root_path, origin_spec, params, f"{lid}_normalize")
                # The normalize wrangle's input must be the actual shape SOP.
                shape_in = _build_shape(root_path, lf["shape"], params, f"{lid}_geoshape")
                shape_node.setInput(0, shape_in)
                # CTP input 0 will now be shape_node (the normalize output).
            # Scale: ...
            scale = lf.get("scale")
            cloud_for_leaf = cloud
```

**Important correction** — re-examine the wiring: the CTP's input 0 is currently `shape_node` (line 692: `ctp.setInput(0, shape_node)`). With origin normalization, we want CTP input 0 = the normalize node's output, and the normalize node's input = the raw shape. The code above creates the raw shape as `shape_in` (renamed to `<lid>_geoshape`) and feeds it into the normalize node, then reassigns `shape_node` to be the normalize node — so the existing `ctp.setInput(0, shape_node)` line now correctly points at the normalize output. Good. Verify the CTP input line still reads `ctp.setInput(0, shape_node)` (it does, line 692).

- [ ] **Step 4: Add validation for `leaf.origin`**

In `validate_assembly`, inside the leaf loop (after the `scale` check around line 205-206), add:

```python
        # origin (optional): normalize leaf pose before copy.
        origin = lf.get("origin")
        if origin is not None:
            if not isinstance(origin, dict):
                errors.append({"code": "LEAF_BAD_ORIGIN", "message":
                    f"leaves[{li}] origin must be an object"})
            else:
                anchor = origin.get("anchor", "bbox_center")
                valid_anchor = (
                    (isinstance(anchor, str)
                     and (anchor == "bbox_center"
                          or (anchor.startswith("bbox_face:")
                              and anchor[len("bbox_face:"):] in
                              ("+X", "-X", "+Y", "-Y", "+Z", "-Z"))))
                    or (isinstance(anchor, (list, tuple)) and len(anchor) == 3))
                if not valid_anchor:
                    errors.append({"code": "LEAF_BAD_ORIGIN", "message":
                        f"leaves[{li}] origin.anchor must be 'bbox_center', "
                        f"'bbox_face:<±XYZ>', or a 3-list, got {anchor!r}"})
                off = origin.get("offset")
                if off is not None:
                    if not (isinstance(off, (list, tuple)) and len(off) == 3):
                        errors.append({"code": "LEAF_BAD_ORIGIN", "message":
                            f"leaves[{li}] origin.offset must be a 3-list"})
                    else:
                        for c in off:
                            if isinstance(c, str):
                                _check_expr_refs(c, param_names,
                                                 f"leaves[{li}].origin.offset", errors)
```

- [ ] **Step 5: Run the origin tests to verify they pass**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/test_assembly_builder.py::TestOriginNormalization -v`
Expected: all three PASS.

- [ ] **Step 6: Run the full assembly_builder suite for regression**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/test_assembly_builder.py -v`
Expected: all PASS (car/keyboard/staircase unaffected — no `origin` field).

- [ ] **Step 7: Commit**

```bash
cd "Z:\EEE_Project\Edini"
git add python3.11libs/edini/assembly_builder.py tests/test_assembly_builder.py
git commit -m "feat(assembly): leaf.origin normalization wrangle before CTP

A leaf may declare origin:{anchor, offset} to move its chosen anchor point
(bbox_center | bbox_face:±XYZ | [x,y,z]) to the origin + offset before
copytopoints, so the leaf lands clear of the root (e.g. a wheel pushed to
+z, a leg base seated on the mount). Inserted as a point wrangle between
shape and CTP; absent origin keeps current behavior."
```

---

## Task 4: Grouped CTP — one shape + one CTP per identical-leaf group (problem 4)

**Files:**
- Modify: `python3.11libs/edini/assembly_builder.py` (restructure leaf loop with `_leaf_group_key` + `_group_leaves`)
- Test: `tests/test_assembly_builder.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_assembly_builder.py`, as a new class:

```python
class TestGroupedCTP(unittest.TestCase):
    """N structurally-identical leaves (same shape+scale+align_axis+origin)
    must share ONE shape node + ONE CTP, stamping onto the merged cloud of
    their mounts — not N independent shape+CTP chains."""

    def setUp(self):
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from mock_hou import create_mock_hou
        sys.modules["hou"] = create_mock_hou()

    def _build(self, assembly):
        import sys
        hou = sys.modules["hou"]
        root = hou.node("/obj").createNode("geo", "test_group")
        from edini.assembly_builder import build_assembly
        res = build_assembly(assembly, root.path())
        return root.path(), res

    def test_four_identical_wheels_produce_one_shape_one_ctp(self):
        """The car's 4 torus wheels are structurally identical → 1 shape node
        + 1 CTP node (not 4+4). The single CTP stamps onto the merged cloud of
        all 4 wheel mounts."""
        root_path, res = self._build(_car_assembly())
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        names = {c.name() for c in hou.node(root_path).children()}
        # Exactly one leaf-shape node (deduped across the 4 wheels).
        shape_nodes = [n for n in names if n.endswith("_geoshape") or n.endswith("_shape")]
        # After grouping there should be ONE shared shape, not four.
        ctp_nodes = [n for n in names if n.endswith("_ctp")]
        self.assertEqual(len(ctp_nodes), 1,
                         f"expected 1 grouped CTP, got {ctp_nodes}")
        # The 4 mounts still exist (grouping merges their CLOUD, not the mounts).
        for c in ("fr", "fl", "br", "bl"):
            self.assertIn(f"mount_wheel_{c}", names)

    def test_different_shapes_stay_separate(self):
        """Two leaves with different shape params do NOT group — each keeps its
        own shape + CTP (regression: grouping must be exact)."""
        asm = _car_assembly()
        asm["leaves"][0]["shape"]["params"]["radx"] = 2.0  # different radius
        root_path, res = self._build(asm)
        self.assertTrue(res["success"], res.get("error"))
        hou = sys.modules["hou"]
        names = {c.name() for c in hou.node(root_path).children()}
        ctp_nodes = [n for n in names if n.endswith("_ctp")]
        self.assertGreaterEqual(len(ctp_nodes), 2,
                                f"different shapes must not group: {ctp_nodes}")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/test_assembly_builder.py::TestGroupedCTP -v`
Expected: FAIL — current build produces 4 CTP nodes (`wheel_fr_ctp` ... `wheel_bl_ctp`).

- [ ] **Step 3: Add grouping helpers and restructure the leaf loop**

In `python3.11libs/edini/assembly_builder.py`, add these helpers near the top (after `_resolve_align_axis`):

```python
def _leaf_group_key(lf: dict, mount: dict) -> tuple:
    """A stable key identifying leaves that produce byte-identical stamped
    output (modulo mount position) and so can share one shape + one CTP.

    Two leaves group iff: same shape type+params, same scale, same resolved
    align_axis, same origin spec. Mount position/orient do NOT enter the key
    (they vary per mount — that's the whole point of grouping)."""
    shape = lf.get("shape", {})
    shape_key = (shape.get("type"),
                 tuple(sorted((shape.get("params") or {}).items(),
                              key=lambda kv: str(kv[0]))))
    scale = lf.get("scale")
    origin = lf.get("origin")
    # Origin spec compared as a canonical sorted-items tuple.
    origin_key = (tuple(sorted(origin.items(), key=lambda kv: str(kv[0])))
                  if isinstance(origin, dict) else None)
    return (shape_key, str(scale), origin_key)


def _group_leaves(leaves: list[dict], mounts_by_id: dict[str, dict]) -> list[dict]:
    """Group leaves by _leaf_group_key, preserving declaration order.

    Returns a list of groups, each:
      {key, leaves: [lf, ...], mount_ids: [mid, ...]}
    Leaves in a group share one shape+CTP and stamp onto the merged cloud of
    all the group's mounts. A singleton group is the current behavior.
    """
    groups: list[dict] = []
    by_key: dict[tuple, int] = {}
    for lf in leaves:
        mid = lf["mount"]
        mount = mounts_by_id.get(mid, {})
        k = _leaf_group_key(lf, mount)
        if k in by_key:
            g = groups[by_key[k]]
            g["leaves"].append(lf)
            g["mount_ids"].append(mid)
        else:
            by_key[k] = len(groups)
            groups.append({"key": k, "leaves": [lf], "mount_ids": [mid]})
    return groups
```

Now restructure the leaf loop in `build_assembly`. Find the existing loop start (around line 661-666):

```python
        leaf_outputs: list = []
        leaves = assembly.get("leaves") or []
        if not leaves:
            leaf_outputs = [root_sop]
        for lf in leaves:
```

Replace the WHOLE loop body (from `for lf in leaves:` through the `leaf_outputs.append(ctp)` line, ~line 666-700) with:

```python
        leaf_outputs: list = []
        leaves = assembly.get("leaves") or []
        if not leaves:
            leaf_outputs = [root_sop]
        # Group structurally-identical leaves so they share ONE shape + ONE CTP
        # (4 identical wheels → 1 shape + 1 CTP stamping the merged cloud).
        # The grouping key is exact: shape+scale+origin must match. Singleton
        # groups behave exactly as the old per-leaf build.
        mounts_by_id = {mt["id"]: mt for mt in (assembly.get("mounts") or [])}
        groups = _group_leaves(leaves, mounts_by_id) if leaves else []
        for gi, group in enumerate(groups):
            lf0 = group["leaves"][0]      # representative for shape/scale/origin
            lid0 = lf0["id"]
            group_mounts = group["mount_ids"]

            shape_node = _build_shape(root_path, lf0["shape"], params, f"{lid0}_geoshape")

            # Origin normalization (optional, applied to the group's shared shape).
            origin_spec = lf0.get("origin")
            if isinstance(origin_spec, dict):
                norm = _build_origin_normalize(
                    root_path, origin_spec, params, f"{lid0}_normalize")
                norm.setInput(0, shape_node)
                shape_node = norm

            # Scale: stamp @pscale onto the group's mount points via a wrangle.
            scale = lf0.get("scale")
            scale_nodes: list = []
            for mid in group_mounts:
                mount_wr = mount_nodes.get(mid)
                if mount_wr is None:
                    raise AssemblyError(
                        f"leaf group {lid0!r} mount {mid!r} not declared")
                if scale is not None:
                    scale_val = (evaluate(scale, params)
                                 if isinstance(scale, str) else float(scale))
                    sw = _create_node(root_path, "attribwrangle", f"{lid0}_{mid}_pscale")
                    sw.setInput(0, mount_wr)
                    try:
                        sw.parm("class").set("point")
                    except Exception:
                        pass
                    try:
                        sw.parm("snippet").set(f"f@pscale = {float(scale_val)};")
                    except Exception:
                        pass
                    scale_nodes.append(sw)
                else:
                    scale_nodes.append(mount_wr)

            # Merge the group's mount outputs into one sub-cloud.
            if len(scale_nodes) > 1:
                sub_cloud = _create_node(root_path, "merge", f"{lid0}_cloud")
                for idx, n in enumerate(scale_nodes):
                    sub_cloud.setInput(idx, n)
            else:
                sub_cloud = scale_nodes[0]

            ctp = _create_node(root_path, "copytopoints", f"{lid0}_ctp")
            ctp.setInput(0, shape_node)
            ctp.setInput(1, sub_cloud)
            try:
                from edini.node_utils import _init_copytopoints_attribs
                _init_copytopoints_attribs(ctp)
            except Exception:
                pass
            leaf_outputs.append(ctp)
```

**Important:** this removes the old `mounts_cloud` global merge for leaves that are now grouped, but single-mount single-leaf assemblies (keyboard/stairs) still work — a singleton group has one mount, `scale_nodes` has one entry, no sub-merge. Verify the existing `mounts_cloud` merge block (lines 649-655) is kept for the case where mounts need a global cloud — but with grouping, each group makes its own sub-cloud, so the global `mounts_cloud` is no longer used by leaves. Leave the global cloud block in place (harmless; it may still be referenced by future code) but it is not wired into CTP anymore.

Actually — to avoid dead code, remove the now-unused global `mounts_cloud` merge block (lines 649-655) since grouping supersedes it. Replace:

```python
        # 5. Merge all mount wrangles into one point cloud. (Single-mount
        # assemblies skip the merge and feed the wrangle straight in.)
        mount_outputs = list(mount_nodes.values())
        if len(mount_outputs) > 1:
            cloud = _create_node(root_path, "merge", "mounts_cloud")
            for idx, n in enumerate(mount_outputs):
                cloud.setInput(idx, n)
        else:
            cloud = mount_outputs[0] if mount_outputs else root_sop
```

with:

```python
        # (Mount wrangles are merged per-leaf-group below — see _group_leaves.
        # The old global mounts_cloud is superseded by per-group sub-clouds.)
```

- [ ] **Step 4: Update the existing structure test that asserted 4 CTPs**

The existing `test_build_creates_live_network_structure` (line 220) asserts `wheel_{fr,fl,br,bl}_ctp` exist. With grouping, there's now ONE `wheel_fr_ctp`. Update that test's CTP assertions (around line 236-237):

Replace:
```python
        for c in ("fr", "fl", "br", "bl"):
            self.assertIn(f"wheel_{c}_ctp", names)
```
with:
```python
        # Grouped CTP: 4 identical wheels share ONE wheel_fr_ctp (the group's
        # representative leaf id). The mounts themselves are NOT merged.
        self.assertIn("wheel_fr_ctp", names)
        self.assertNotIn("wheel_fl_ctp", names)
```

And update the `mounts_cloud` assertion (line 235) — since the global cloud was removed:
Replace `self.assertIn("mounts_cloud", names)` with removing that line (the cloud is per-group now: `wheel_fr_cloud`). Add `self.assertIn("wheel_fr_cloud", names)` to assert the group's sub-cloud exists.

- [ ] **Step 5: Run the grouped-CTP tests**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/test_assembly_builder.py::TestGroupedCTP tests/test_assembly_builder.py::TestBuildAssemblyStructure -v`
Expected: PASS for all.

- [ ] **Step 6: Run the FULL assembly_builder suite + measure suite**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/test_assembly_builder.py tests/test_measure.py -v`
Expected: all PASS. Keyboard (single leaf, single mount) and staircase (same) still build as singleton groups.

- [ ] **Step 7: Commit**

```bash
cd "Z:\EEE_Project\Edini"
git add python3.11libs/edini/assembly_builder.py tests/test_assembly_builder.py
git commit -m "feat(assembly): group identical leaves onto one shape + one CTP

N leaves with the same shape+scale+origin now share a single shape node and
a single copytopoints stamping the merged cloud of all their mounts. The
car's 4 torus wheels collapse from 4 shapes + 4 CTPs to 1 + 1. Grouping key
is exact (different params stay separate); singleton groups behave as before."
```

---

## Task 5: Bicycle example + hython facing assertions (integration)

**Files:**
- Modify: `tests/test_assembly_hython.py` (add `_bicycle()`, annotate `_car()` with align_axis, add facing tests)
- Test: the hython tests themselves

- [ ] **Step 1: Annotate `_car()` with align_axis:"+Z"**

In `tests/test_assembly_hython.py`, modify the `_car()` function (around line 116). In each mount's `orient` dict, add `"align_axis": "+Z"`. The orient dict is at lines 126-128:

Replace:
```python
             "orient": {"from": "root",
                "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
                "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}}}
```
with:
```python
             "orient": {"from": "root", "align_axis": "+Z",
                "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
                "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}}}
```

- [ ] **Step 2: Add the `_bicycle()` assembly helper**

In `tests/test_assembly_hython.py`, after the `_car()` function, add:

```python
def _bicycle(length=4.0):
    """A bicycle-style platform + 4 wheels, exercising all four fixes:
    align_axis +Z (torus faces its axle), origin normalization (wheel pushed
    to +Z to clear the platform), grouped CTP (4 identical wheels → 1 CTP)."""
    return {
        "id": "bicycle",
        "params": {"length": length, "width": 2.0, "thickness": 0.5,
                   "wheel_radius": 0.4, "wheel_tube_r": 0.08, "wheel_clearance": 0.1},
        "root": {"shape": {"type": "box",
                           "params": {"size": ["length", "thickness", "width"]}}},
        "mounts": [
            {"id": "wheel_" + c, "position": {"measure": "bbox_corner",
                "from": "root", "axes": axes},
             "orient": {"from": "root", "align_axis": "+Z",
                "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
                "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}}}
            for c, axes in [("fr", "+X-Y+Z"), ("fl", "+X-Y-Z"),
                            ("br", "-X-Y+Z"), ("bl", "-X-Y-Z")]
        ],
        "leaves": [
            {"id": "wheel_" + c, "mount": "wheel_" + c, "scale": "wheel_radius",
             "origin": {"anchor": "bbox_center", "offset": [0, 0, "wheel_clearance"]},
             "shape": {"type": "torus", "params": {
                 "radx": 1.0, "rady": "wheel_tube_r", "rows": 24, "cols": 12}}}
            for c in ("fr", "fl", "br", "bl")
        ],
    }
```

- [ ] **Step 3: Add the facing-assertion helpers + new tests**

The decisive facing test needs geometry-level bbox-thickness analysis. Extend the `_HARNESS` script to also probe per-instance bbox. In `tests/test_assembly_hython.py`, find the `instance_centers()` function inside `_HARNESS` (around line 75). Add a new probe function after it (still inside the harness string, before the `probe = {}` line):

```python
def instance_piece_bboxes():
    """For each connected piece in OUT, its bbox (min/max/size on 3 axes).
    A torus wheel (radx=1, rady=0.08) is THIN along its symmetry axis (~0.16)
    and WIDE on the other two (~2.0). After orient, the thin axis points
    along the axle direction — so the thin bbox dim reveals the wheel's
    facing without trusting CTP attribute transfer."""
    out = hou.node(root.path() + "/OUT")
    out.cook(force=True)
    geo = out.geometry()
    # Cluster points by connectivity (each stamped copy is one connected piece).
    # Use the @id or @name attribute if CTP stamped it; else fall back to
    # spatial clustering. Simplest robust signal: use hou's connected pieces
    # via a per-prim bbox grouped by a piece attribute. Here we read the
    # per-primitive bbox intrinsic and cluster by centroid proximity.
    bboxes = []
    for prim in geo.prims():
        b = prim.intrinsicValue("bounds")
        if b and len(b) == 6:
            bboxes.append({
                "min": [b[0], b[2], b[4]],
                "max": [b[1], b[3], b[5]],
                "size": [b[1]-b[0], b[3]-b[2], b[5]-b[4]],
            })
    return bboxes

def mount_cloud_orient():
    """Read p@orient off each mount wrangle's points (pre-CTP), so we can
    verify the orient quaternion itself lands on points and rotates the
    align-axis basis onto the measured axle direction."""
    out = {}
    for nm in [c.name() for c in root.allSubChildren() if c.name().startswith("mount_")]:
        wr = hou.node(root.path() + "/" + nm); wr.cook(force=True)
        wg = wr.geometry()
        if wg is None:
            continue
        orients = []
        for p in wg.points():
            try:
                q = p.floatListAttribValue("orient")
                orients.append(list(q))
            except Exception:
                pass
        out[nm] = orients
    return out
```

Then in the `probe = {}` block (around line 99), add the new probes. Find:

```python
probe = {}
if res.get("success"):
    probe["centers"] = instance_centers()
    probe["root_bbox"] = root_bbox()
```

Replace with:

```python
probe = {}
if res.get("success"):
    probe["centers"] = instance_centers()
    probe["root_bbox"] = root_bbox()
    if probe_kind in ("piece_bboxes", "facing"):
        probe["pieces"] = instance_piece_bboxes()
        probe["cloud_orient"] = mount_cloud_orient()
```

Then add the new test methods to `TestLiveBuildHython` (after `test_staircase_builds_three_treads`):

```python
    def test_bicycle_wheels_face_their_axle(self):
        """The decisive facing test: each wheel instance's THINNEST bbox axis
        must be the axle direction (X for this platform). A torus radx=1,
        rady=0.08 is ~0.16 thick on its symmetry axis and ~2.0 on the others,
        so the thinnest bbox dim points where the wheel faces. If orient were
        ignored (the old bug), the thin axis would stay Z, not X."""
        res = _run(_bicycle(), probe="facing")
        self.assertTrue(res["success"], res.get("error"))
        pieces = res["_probe"]["pieces"]
        # 4 wheels → at least 4 pieces with a thin axis.
        thin_axes = []
        for p in pieces:
            sz = p["size"]
            # The thin axis is the index of the smallest size component.
            thin_axes.append(sz.index(min(sz)))
        # For this platform the axle runs along X (index 0). The majority of
        # wheel pieces must have their thin axis = X.
        x_facing = sum(1 for a in thin_axes if a == 0)
        self.assertGreaterEqual(x_facing, 4,
            f"wheels not facing axle (X): thin_axes={thin_axes}, pieces={len(pieces)}")

    def test_bicycle_cloud_orient_rotates_z_to_axle(self):
        """Secondary check: read p@orient off the mount cloud (pre-CTP), rotate
        the align axis +Z by it, and the result must align with the measured
        axle direction (X). Proves the orient quaternion itself is correct."""
        import math
        res = _run(_bicycle(), probe="facing")
        self.assertTrue(res["success"], res.get("error"))
        cloud = res["_probe"]["cloud_orient"]
        self.assertTrue(cloud, "no orient read from mount cloud")
        # For every mount's first point, rotate +Z={0,0,1} by the quaternion.
        for mount_name, quats in cloud.items():
            self.assertTrue(quats, f"no orient on {mount_name}'s points")
            q = quats[0]
            # q = (qx,qy,qz,qw). Rotate v={0,0,1} by q: v' = q*v*q^-1.
            qx, qy, qz, qw = q
            vx, vy, vz = 0.0, 0.0, 1.0
            # Quaternion rotation of vector v by unit quaternion (qw,qx,qy,qz):
            # v' = v + 2*qw*(q_vec × v) + 2*(q_vec × (q_vec × v))
            cxv = (qy*vz - qz*vy, qz*vx - qx*vz, qx*vy - qy*vx)
            cxv2 = (qy*cxv[2] - qz*cxv[1], qz*cxv[0] - qx*cxv[2], qx*cxv[1] - qy*cxv[0])
            rx = vx + 2*qw*cxv[0] + 2*cxv2[0]
            ry = vy + 2*qw*cxv[1] + 2*cxv2[1]
            rz = vz + 2*qw*cxv[2] + 2*cxv2[2]
            n = math.sqrt(rx*rx + ry*ry + rz*rz)
            rx, ry, rz = rx/n, ry/n, rz/n
            # The axle runs along ±X (the long platform edge). The rotated +Z
            # must be dominantly X.
            self.assertGreater(abs(rx), 0.9,
                f"{mount_name}: rotated +Z = ({rx:.3f},{ry:.3f},{rz:.3f}) "
                f"not aligned to axle X (orient wrong or ignored)")

    def test_bicycle_one_ctp_four_wheels(self):
        """4 identical wheels share ONE CTP. The OUT has 4 wheels but the
        network has a single wheel_*_ctp node."""
        res = _run(_bicycle(), probe="instance_centers")
        self.assertTrue(res["success"], res.get("error"))
        centers = res["_probe"]["centers"]
        self.assertEqual(len(centers), 4, f"expected 4 wheel mount points, got {centers}")

    def test_car_still_faces_axle_under_new_convention(self):
        """Regression: the car (now annotated align_axis +Z) still has its
        wheels facing the axle, proving the new convention is backward
        compatible with the verified example."""
        res = _run(_car(), probe="facing")
        self.assertTrue(res["success"], res.get("error"))
        pieces = res["_probe"]["pieces"]
        thin_axes = [p["size"].index(min(p["size"])) for p in pieces]
        x_facing = sum(1 for a in thin_axes if a == 0)
        self.assertGreaterEqual(x_facing, 4,
            f"car wheels lost axle facing: thin_axes={thin_axes}")
```

- [ ] **Step 4: Run the new hython tests**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/test_assembly_hython.py -v`
Expected: all PASS — IF hython is installed. If hython is absent, these skip (`@unittest.skipUnless(HYTHON, ...)`). The mock tests already passed in Tasks 1-4; the hython layer is the decisive gate.

If a facing test FAILS, the orient is not landing on points or align_axis wasn't threaded — debug via the `cloud_orient` probe (it prints the raw quaternion). Do NOT weaken the assertion.

- [ ] **Step 5: Commit**

```bash
cd "Z:\EEE_Project\Edini"
git add tests/test_assembly_hython.py
git commit -m "test(hython): bicycle + wheel-facing assertions (bbox-thickness + cloud-orient)

Adds _bicycle() exercising all four fixes (align_axis +Z, origin normalize,
grouped CTP). The decisive facing test checks each wheel's THINNEST bbox
axis equals the axle direction (torus is ~0.16 thin vs ~2.0 wide), and a
secondary check rotates +Z by the cloud's p@orient to confirm the quaternion
itself is right. Car annotated align_axis +Z for backward-compat regression."
```

---

## Task 6: Update skill doc + tool schema

**Files:**
- Modify: `skills/rooted-modeling/SKILL.md`
- Modify: `pi-extensions/edini-tools/tools/rooted.ts`

- [ ] **Step 1: Update SKILL.md — document align_axis + origin + grouped CTP**

In `skills/rooted-modeling/SKILL.md`, find the "Orientation" mention (around line 71: "A mount's `orient` (optional) is **also derived**..."). After that paragraph, add a new subsection:

```markdown
### Align axis — which way the leaf faces (problem-2 fix)

`orient.align_axis` (default `"+Y"`) names the leaf's built axis that the
orient quaternion maps onto the measured direction. A torus wheel's symmetry
axis is **+Z** (the disc lies in XY), so wheels declare `align_axis: "+Z"`;
a shape grown along +Y keeps the default. Legal values: `±X`, `±Y`, `±Z`.

```json
"orient": {"from": "root", "align_axis": "+Z",
   "from_a": {...}, "from_b": {...}}
```

The leaf may override the mount's align axis per-instance with
`leaf.align_axis` (priority: leaf > mount > `"+Y"`).

### Origin normalization — clear the root (problem-3 fix)

A leaf may declare `origin: {anchor, offset}` to move a chosen point of its
geometry to the origin (+ optional offset) **before** copytopoints, so the
leaf lands clear of the root instead of intersecting it. `anchor` is one of:

| anchor | which point → origin |
|--------|---------------------|
| `bbox_center` | the geometry's bbox center |
| `bbox_face:+Z` / `-Z` / `+Y` / `-Y` / `+X` / `-X` | that face's center |
| `[x, y, z]` | an explicit point |

`offset` (optional `[x,y,z]`, may be param expressions) is added after. A
wheel pushed clear of the platform: `origin: {anchor: "bbox_center",
offset: [0, 0, "wheel_clearance"]}`. A leg whose base seats on the mount:
`anchor: "bbox_face:-Y"`.

### Grouped copy — one shape, one CTP (problem-4 optimization)

Leaves with identical shape + scale + origin automatically share **one**
shape node and **one** copytopoints stamping the merged cloud of all their
mounts. The car's 4 torus wheels build as 1 shape + 1 CTP, not 4 + 4. The
grouping is exact — different shape params stay separate. This is automatic;
no declaration needed.
```

- [ ] **Step 2: Update the car example annotation in SKILL.md**

Find the verified car example (around line 161, "The verified example: a car"). In the bullet about mounts (line 167: "4 mounts: each wheel at one bottom corner..."), append: "each orient `align_axis: "+Z"` (torus symmetry axis → axle direction)".

- [ ] **Step 3: Update the orient dihedral explanation (line 102-103)**

Find line 102-103:
```
The `@orient` on each point is a quaternion from
`dihedral({0,1,0}, dir)` — the leaf's built +Y faces the measured direction.
```
Replace with:
```
The `@orient` on each point is a quaternion from `dihedral(<align_axis>, dir)`,
written via `setpointattrib` (a bare `p@orient=` in the detail wrangle would
silently become a detail attribute CTP ignores). The leaf's `align_axis`
(default +Y, +Z for torus wheels) faces the measured direction.
```

- [ ] **Step 4: Update the tool schema in rooted.ts**

In `pi-extensions/edini-tools/tools/rooted.ts`, find the `buildAssembly.description` string (around line 42-57). Append to the description (before the closing quote):

```
Orientation now takes align_axis ('+Z' for torus wheels — their symmetry axis; default '+Y'). A leaf may declare origin:{anchor:'bbox_center'|'bbox_face:±XYZ'|[x,y,z], offset:[x,y,z]} to normalize its pose before copy (clear the root). Identical leaves auto-group onto one shape + one CTP.
```

- [ ] **Step 5: Commit**

```bash
cd "Z:\EEE_Project\Edini"
git add skills/rooted-modeling/SKILL.md pi-extensions/edini-tools/tools/rooted.ts
git commit -m "docs(skill): document align_axis + origin normalization + grouped CTP

SKILL.md gains subsections for the three new conventions (align_axis, origin,
grouped copy) and the car example is annotated with align_axis +Z. The
build_assembly tool description mentions the new fields so the agent knows
to use them."
```

---

## Task 7: Add bicycle to the showcase script

**Files:**
- Modify: `scripts/show_assemblies.py`

- [ ] **Step 1: Read the current showcase structure**

Run: `cd "Z:\EEE_Project\Edini" && head -50 scripts/show_assemblies.py`
Understand how the existing car/keyboard/staircase assemblies are added to the showcase and how `edini_showcase.hip` is generated. The bicycle should follow the same pattern.

- [ ] **Step 2: Add a `_bicycle()` to the showcase, mirroring the test's `_bicycle()`**

In `scripts/show_assemblies.py`, add a bicycle assembly (copy the `_bicycle()` dict from `tests/test_assembly_hython.py` Task 5 Step 2 verbatim) and register it in the showcase's build loop alongside car/keyboard/staircase. Use a unique sandbox container name (e.g. `"bicycle"`).

- [ ] **Step 3: Regenerate the showcase hip and verify the build succeeds**

Run: `cd "Z:\EEE_Project\Edini" && python scripts/show_assemblies.py`
Expected: the script reports success for all assemblies including bicycle, and `edini_showcase.hip` is written. If the script requires hython, run it under hython; if it errors, read the error and fix (do not skip).

- [ ] **Step 4: Commit**

```bash
cd "Z:\EEE_Project\Edini"
git add scripts/show_assemblies.py edini_showcase.hip
git commit -m "feat(showcase): add bicycle exercising align_axis + origin + grouped CTP

The showcase .hip now includes a bicycle (4 wheels with align_axis +Z, origin
normalization, grouped CTP) alongside the car/keyboard/staircase, so opening
edini_showcase.hip demonstrates all four leaf-align fixes."
```

---

## Task 8: Final full-suite verification

- [ ] **Step 1: Run the entire test suite**

Run: `cd "Z:\EEE_Project\Edini" && python -m pytest tests/ -v 2>&1 | tail -40`
Expected: all tests PASS (hython tests skip if hython absent, else PASS). No FAILs.

- [ ] **Step 2: Verify the bicycle in Houdini (manual, if hython available)**

Open `edini_showcase.hip` in Houdini. Locate the bicycle container. Change the `length` spare parm 4→8 and confirm:
1. The 4 wheels slide to the new corners (live position).
2. Each wheel's disc faces along the platform's long edge (X) — the axle runs through the wheel, not perpendicular.
3. Only ONE `wheel_*_ctp` node exists in the network (grouped CTP).
4. Each wheel sits clear of the platform (origin normalization pushed it to +Z).

If any of these fails, return to the relevant task — do not declare done.

- [ ] **Step 3: Final commit (if any doc/comment polish)**

```bash
cd "Z:\EEE_Project\Edini"
git log --oneline -8
```
Confirm the 7 feature commits landed in order. No final commit needed unless a polish change was made.

---

## Self-Review (run after writing — done)

**1. Spec coverage:**
- §1 problem 1 (orient point-class) → Task 1 ✓
- §3.1 mount.orient.align_axis → Tasks 2, 5 ✓
- §3.2 leaf.align_axis override + leaf.origin → Tasks 2, 3 ✓
- §4.1 orient setpointattrib → Task 1 ✓
- §4.2 align_axis injection → Task 2 ✓
- §4.3 origin normalize node → Task 3 ✓
- §4.4 grouped CTP → Task 4 ✓
- §5 validation → Tasks 2 (align_axis), 3 (origin) ✓
- §6.1 mock tests → Tasks 1-4 ✓
- §6.2 hython facing tests → Task 5 ✓
- §6.3 oracle tests → Task 2 ✓
- §7 skill doc + tool → Task 6 ✓
- §7 showcase → Task 7 ✓
- car regression (§2 scope) → Task 5 (`test_car_still_faces_axle_under_new_convention`) ✓

**2. Placeholder scan:** No TBD/TODO/"implement later". Every step has complete code or exact commands.

**3. Type/name consistency:**
- `_orient_fragment(orient_spec, align_axis="+Y")` — defined Task 1, used Task 2 Step 7 ✓
- `align_axis_to_vec` — defined Task 1, used Task 1 ✓
- `orient_to_align(align_axis, direction)` — defined Task 2 Step 3, tested Task 2 Step 1 ✓
- `_verify_align(align_axis, orient, direction)` — defined Task 2 Step 3, tested Task 2 Step 1 ✓
- `_resolve_align_axis(value)` — defined Task 2 Step 7, used Task 2 Step 7 ✓
- `_build_origin_normalize(root_path, origin_spec, params, name)` — defined Task 3 Step 3, used Tasks 3 & 4 ✓
- `_leaf_group_key(lf, mount)` / `_group_leaves(leaves, mounts_by_id)` — defined Task 4 Step 3, used Task 4 Step 3 ✓
- `_bicycle()` — defined Task 5 Step 2, reused Task 7 Step 2 ✓
- Probe kinds `"piece_bboxes"`/`"facing"` — Task 5 Step 3 (consistent in `_run` calls) ✓
- Node naming: grouped CTP uses representative leaf id → `wheel_fr_ctp` (asserted Task 4 Step 4) ✓
