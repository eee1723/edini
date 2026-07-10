# Component Structure Analyzer Implementation Plan (Cut-1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-component structural analyzer (`analyze_component_structure`) that turns node-graph + geometry + declared-intent state into fatal/advisory verdicts, wire its fatal subset into `project_finalize` as an `acknowledge_skip`-immune Gate 4, and require a structural-intent declaration at scaffold time — closing the construction-quality and gate-integrity failures found in the 2026-07-09 two-model session logs.

**Architecture:** A new pure-logic core (`edini/structure.py`: declaration lint + signal evaluator) that is fully unit-testable without `hou`, wrapped by a `hou`-coupled extractor/orchestrator that walks each component subnet. F3 (axis) reuses the existing `verify_orientation` (already reads the baked `edini_world_axis`). `project_finalize` gains a 4th gate whose fatal verdicts cannot be bypassed by `acknowledge_skip` — only by an audited `structure_override`. Cut-1 = F1–F4 + Gate 4 + required declaration. **Cut-1.5 (A3 per-component parametric re-measure) is out of scope** — separate plan.

**Tech Stack:** Python 3.11 (Houdini `hou`), pytest, real-Houdini `hython` e2e tests (subprocess harness pattern from `tests/test_checklayer_e2e_hython.py`), TypeScript tool schemas in `pi-extensions/edini-tools`.

**Spec:** `docs/superpowers/specs/2026-07-10-component-structure-analyzer-design.md`

---

## File Structure

| File | Responsibility | New/Modify |
|---|---|---|
| `python3.11libs/edini/structure.py` | Pure lint + evaluator + hou-coupled extractor + `analyze_component_structure` orchestrator | **Create** |
| `python3.11libs/edini/project/state.py` | `structure` field on component entries + `add_structure_to_component` helper | Modify |
| `python3.11libs/edini/project/builder.py` | Accept+persist `structure`; plan-time lint refusal in `build_project_scaffold` | Modify |
| `python3.11libs/edini/verify.py` | `project_finalize` Gate 4 + `structure_override` semantics | Modify |
| `python3.11libs/edini/tool_executor.py` | `analyze_component_structure` handler in `TOOL_HANDLERS` | Modify |
| `pi-extensions/edini-tools/tools/project.ts` | LLM-facing tool descriptor | Modify |
| `skills/project-modeling/SKILL.md` | Document required `structure` declaration + the new tool | Modify |
| `tests/test_structure_lint.py` | Pure: declaration lint | **Create** |
| `tests/test_structure_rules.py` | Pure: F1/F2/F4 evaluator | **Create** |
| `tests/test_structure_analyzer_e2e_hython.py` | Real-houdini: extraction, orchestrator, acceptance fixtures | **Create** |
| `python3.11libs/edini/harness.py` | (Task 11, low-priority) `_check_modular_structure` delegates to shared classify helpers | Modify |

**Key reuse (no reimplementation):**
- F3 axis → `edini.verify.verify_orientation` (reads baked `edini_world_axis`).
- Component walk → `core.node(cid)` / `subnet.allSubChildren()` / `subnet.node(OUT_GEOMETRY_NODE)` (same as `project_status`).
- Refuse pattern → `project/guards.py` dict shape (`success`/`error`/`suggested_tool`/`schema_hint`).

---

## Task 1: Declaration lint (pure logic)

**Files:**
- Create: `python3.11libs/edini/structure.py`
- Create: `tests/test_structure_lint.py`

- [ ] **Step 1: Write the failing test**

`tests/test_structure_lint.py`:
```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
from edini.structure import lint_structure_decl


def test_missing_structure_is_error():
    errs = lint_structure_decl({"id": "frame"})
    assert [e["code"] for e in errs] == ["structure_missing"]


def test_solid_needs_no_axis():
    errs = lint_structure_decl({"id": "body", "structure": {"kind": "solid"}})
    assert errs == []


def test_radial_requires_axis():
    errs = lint_structure_decl({"id": "wheel", "structure": {"kind": "radial"}})
    assert "missing_axis" in [e["code"] for e in errs]


def test_repeated_requires_repeats():
    errs = lint_structure_decl({"id": "spokes", "structure": {"kind": "repeated"}})
    assert "repeated_without_repeats" in [e["code"] for e in errs]


def test_instancing_repeat_needs_count_ge_2():
    errs = lint_structure_decl({"id": "spokes", "structure": {
        "kind": "repeated", "repeats": [{"part": "spoke", "count": 1, "method": "copytopoints"}]}})
    assert "bad_repeat_count" in [e["code"] for e in errs]


def test_valid_radial_passes():
    errs = lint_structure_decl({"id": "wheel", "structure": {
        "kind": "radial", "expected_axis": "Z",
        "repeats": [{"part": "spoke", "count": 28, "method": "copytopoints"}]}})
    assert errs == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_structure_lint.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'edini.structure'`

- [ ] **Step 3: Write minimal implementation**

`python3.11libs/edini/structure.py` (top of file — pure section, no `hou`):
```python
"""Component structural analyzer: declare→verify closed loop.

Pure-logic core (lint + evaluator) is hou-free and unit-testable; the
hou-coupled extractor/orchestrator is lower in this module and lazy-imports hou.
See docs/superpowers/specs/2026-07-10-component-structure-analyzer-design.md.
"""
from __future__ import annotations
from typing import Any

# ── Declaration schema constants ──────────────────────────────────────────
_VALID_KINDS = {"radial", "planar", "repeated", "solid"}
_AXIS_TOKENS = {"X", "Y", "Z", "-X", "-Y", "-Z"}
_INSTANCING_METHODS = {"copytopoints", "foreach", "stamp", "copy"}
_SURFACING_METHODS = {"sweep", "polywire", "skin", "rails"}

# Node-type taxonomy (canonical home; harness keeps aliases — see Task 11).
MODULAR_NODE_TYPES = {
    "copytopoints", "copytopoints::2.0", "copy", "copystamp",
    "sweep", "sweep::2.0", "skin", "rails",
    "foreach::count", "foreach::piece", "foreach", "foreach_begin",
    "xformpieces", "transformpieces", "instanceto",
    "boolean", "boolean::2.0", "polyextrude", "polyextrude::2.0",
    "pack", "unpack",
}
INSTANCING_NODE_TYPES = {
    "copytopoints", "copytopoints::2.0", "copy", "copystamp",
    "foreach::count", "foreach::piece", "foreach", "foreach_begin",
    "xformpieces", "transformpieces", "instanceto",
}
_CURVE_PRIM_KEYWORDS = ("curve", "polyline", "nurbs", "bez", "span")

# Inferred-repeat heuristic: a Python SOP emitting this many prims with no
# instancing node likely hand-duplicated repeated sub-parts (deepseek wheels).
_INFERRED_REPEAT_MIN_PRIMS = 40


def lint_structure_decl(comp: dict) -> list[dict]:
    """Validate a component's `structure` declaration. Pure (no hou).

    Returns [] if the declaration is acceptable, else a list of
    {code, detail, schema_hint} dicts. Called by build_project_scaffold
    BEFORE any nodes are created — the shift-left refusal point.
    """
    cid = comp.get("id", "?")
    struct = comp.get("structure")
    if struct is None:
        return [{
            "code": "structure_missing",
            "detail": (f"component {cid!r} has no `structure` declaration. "
                       f"Declare kind + (for radial/planar) expected_axis + repeats."),
            "schema_hint": {"kind": "solid | radial | planar | repeated",
                            "expected_axis": "X|Y|Z (required for radial/planar)",
                            "repeats": [{"part": "spoke", "count": 28,
                                         "method": "copytopoints"}]},
        }]
    if not isinstance(struct, dict):
        return [{"code": "structure_not_dict", "detail": f"{cid!r}.structure must be a dict"}]

    errors: list[dict] = []
    kind = struct.get("kind")
    if kind not in _VALID_KINDS:
        errors.append({"code": "bad_kind",
                       "detail": f"{cid!r}.structure.kind={kind!r}; must be one of {sorted(_VALID_KINDS)}"})

    if kind in ("radial", "planar"):
        ax = struct.get("expected_axis")
        if ax not in _AXIS_TOKENS:
            errors.append({"code": "missing_axis",
                           "detail": f"{cid!r} kind={kind} requires expected_axis in {sorted(_AXIS_TOKENS)}"})

    repeats = struct.get("repeats") or []
    if kind == "repeated" and not repeats:
        errors.append({"code": "repeated_without_repeats",
                       "detail": f"{cid!r} kind=repeated requires a non-empty repeats[]"})
    for r in repeats:
        if not isinstance(r, dict):
            errors.append({"code": "bad_repeat_entry", "detail": f"{cid!r} repeat entry not a dict: {r!r}"})
            continue
        m = r.get("method")
        count = r.get("count")
        if m in _INSTANCING_METHODS and (not isinstance(count, int) or count < 2):
            errors.append({"code": "bad_repeat_count",
                           "detail": f"{cid!r} repeat {r.get('part')!r} method={m!r} needs integer count>=2 (got {count!r})"})
    return errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_structure_lint.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/structure.py tests/test_structure_lint.py
git commit -m "feat(structure): declaration lint — pure shift-left validation"
```

---

## Task 2: Fatal/advisory evaluator (pure logic, F1/F2/F4)

**Files:**
- Modify: `python3.11libs/edini/structure.py` (append evaluator)
- Create: `tests/test_structure_rules.py`

- [ ] **Step 1: Write the failing test**

`tests/test_structure_rules.py`:
```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
from edini.structure import evaluate_component_signals


def _sig(**kw):
    base = {"component_id": "c", "prim_types": {}, "instancing_nodes": set(),
            "python_emit_geometry": False, "inferred_repeats": False,
            "ctp_target_has_orient": False}
    base.update(kw)
    return base


def test_F1_bare_curves_at_out_fatal():
    r = evaluate_component_signals(_sig(prim_types={"NURBSCurve": 6}), None)
    assert r["overall"] == "fatal"
    assert r["fatal"][0]["rule"] == "F1_bare_curves_at_out"


def test_F2_declared_instancing_missing_node_fatal():
    declared = {"kind": "repeated",
                "repeats": [{"part": "spoke", "count": 28, "method": "copytopoints"}]}
    r = evaluate_component_signals(_sig(prim_types={"Poly": 500}), declared)
    assert any(f["rule"] == "F2_repeat_no_instancing" and f["confidence"] == "declared"
               for f in r["fatal"])


def test_F2_inferred_repeat_in_python_sop_fatal():
    r = evaluate_component_signals(
        _sig(prim_types={"Poly": 600}, python_emit_geometry=True, inferred_repeats=True), None)
    assert any(f["rule"] == "F2_repeat_no_instancing" and f["confidence"] == "inferred"
               for f in r["fatal"])


def test_F2_passes_when_ctp_present():
    declared = {"kind": "repeated",
                "repeats": [{"part": "spoke", "count": 28, "method": "copytopoints"}]}
    r = evaluate_component_signals(
        _sig(prim_types={"Poly": 500}, instancing_nodes={"copytopoints"}), declared)
    assert not any(f["rule"] == "F2_repeat_no_instancing" for f in r["fatal"])


def test_F4_ctp_without_orient_fatal():
    r = evaluate_component_signals(
        _sig(prim_types={"Poly": 400}, instancing_nodes={"copytopoints"},
              ctp_target_has_orient=False), None)
    assert any(f["rule"] == "F4_ctp_no_orient" for f in r["fatal"])


def test_F4_ctp_with_orient_clean():
    r = evaluate_component_signals(
        _sig(prim_types={"Poly": 400}, instancing_nodes={"copytopoints"},
              ctp_target_has_orient=True), None)
    assert not any(f["rule"] == "F4_ctp_no_orient" for f in r["fatal"])


def test_clean_component():
    r = evaluate_component_signals(
        _sig(prim_types={"Poly": 72}, instancing_nodes={"copytopoints"},
              ctp_target_has_orient=True), {"kind": "repeated",
              "repeats": [{"part": "leg", "count": 4, "method": "copytopoints"}]})
    assert r["overall"] == "clean"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_structure_rules.py -v`
Expected: FAIL — `ImportError: cannot import name 'evaluate_component_signals'`

- [ ] **Step 3: Write minimal implementation**

Append to `python3.11libs/edini/structure.py`:
```python
def _is_curve_prim_type(type_name: str) -> bool:
    t = (type_name or "").lower()
    return any(k in t for k in _CURVE_PRIM_KEYWORDS)


def evaluate_component_signals(signals: dict, declared: dict | None) -> dict:
    """Pure: map extracted signals + declared intent to fatal/advisory verdicts.

    F3 (axis) is NOT computed here — it needs cooked geometry math and is
    delegated to verify_orientation by the orchestrator. This function handles
    the node-graph/prim-type/CTP structure rules F1/F2/F4.

    signals keys: component_id, prim_types(dict name->count),
        instancing_nodes(set of method names present in subnet),
        python_emit_geometry(bool), inferred_repeats(bool),
        ctp_target_has_orient(bool).
    Returns {fatal:[...], advisory:[...], overall: 'fatal'|'advisory'|'clean'}.
    """
    cid = signals.get("component_id", "?")
    fatal: list[dict] = []
    advisory: list[dict] = []
    prim_types = signals.get("prim_types", {}) or {}
    instancing = set(signals.get("instancing_nodes", set()) or set())

    # ── F1: bare curve/surface prims at the component's out_geometry ──
    curve_types = sorted({t for t in prim_types if _is_curve_prim_type(t)})
    if curve_types:
        fatal.append({"rule": "F1_bare_curves_at_out", "component": cid,
            "detail": (f"out_geometry has curve prims {curve_types} — skeleton not "
                       f"surfaced, or OUT is wired to the curve instead of PolyWire/Sweep"),
            "fix": "Wire out_geometry through PolyWire/Sweep to thicken curves, "
                   "or Blast the construction curves.",
            "suggested_tool": "houdini_connect_nodes"})

    # ── F2: repeated part declared with instancing but no such node ──
    declared_repeats = ((declared or {}).get("repeats")) or []
    declared_instancing = {r.get("method") for r in declared_repeats
                           if isinstance(r, dict) and r.get("method") in _INSTANCING_METHODS}
    if declared_instancing and not (declared_instancing & instancing):
        fatal.append({"rule": "F2_repeat_no_instancing", "component": cid, "confidence": "declared",
            "detail": (f"declared instancing method(s) {sorted(declared_instancing)} but no such "
                       f"node in the component subnet — repeated sub-parts must be instanced, not "
                       f"hand-duplicated (even 2 instances)"),
            "fix": "Add a Copy-to-Points node: one template + target point cloud.",
            "suggested_tool": "houdini_create_node"})
    elif signals.get("inferred_repeats") and not instancing:
        # No declaration (legacy) — infer. False-positive risk ⇒ override-able.
        fatal.append({"rule": "F2_repeat_no_instancing", "component": cid, "confidence": "inferred",
            "detail": "repeated/radial sub-geometry detected with no instancing node — likely "
                      "hand-duplicated inside a Python SOP",
            "fix": "Add a Copy-to-Points node for the repeated sub-parts.",
            "suggested_tool": "houdini_create_node"})

    # ── F4: Copy-to-Points present but target points lack orient/N/up ──
    if instancing and not signals.get("ctp_target_has_orient"):
        fatal.append({"rule": "F4_ctp_no_orient", "component": cid,
            "detail": "Copy-to-Points target points have none of orient/N/up — copies inherit "
                      "identity orientation (candles/wheels pointing the wrong way)",
            "fix": "Set @orient (quaternion) or @N + @up on the target points "
                   "(attribwrangle or Scatter orient handle).",
            "suggested_tool": "houdini_set_param"})

    overall = "fatal" if fatal else ("advisory" if advisory else "clean")
    return {"fatal": fatal, "advisory": advisory, "overall": overall}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_structure_rules.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/structure.py tests/test_structure_rules.py
git commit -m "feat(structure): F1/F2/F4 signal evaluator (pure logic)"
```

---

## Task 3: Classify helpers + signal extractor (hou-coupled)

**Files:**
- Modify: `python3.11libs/edini/structure.py` (append extractor)
- Create: `tests/test_structure_analyzer_e2e_hython.py` (first test: extractor on a python-SOP wheel)

- [ ] **Step 1: Write the failing e2e test**

`tests/test_structure_analyzer_e2e_hython.py`:
```python
"""Real-Houdini (hython) tests for edini.structure. Auto-discovers hython
via tests/_hython.py; skips when not found.
Run: py -3 -m pytest tests/test_structure_analyzer_e2e_hython.py -v
"""
import json, os, subprocess, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
from _hython import HYTHON  # noqa: E402
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _run(harness_py: str) -> dict:
    proc = subprocess.run([HYTHON, "-c", harness_py % (_REPO, _REPO)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"hython failed (rc={proc.returncode}):\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


# Build a 1-component project whose wheel is a Python SOP (no CTP) — the
# deepseek-bike failure shape. _extract_component_signals must report
# instancing_nodes empty + python_emit_geometry True + inferred_repeats True.
_EXTRACT_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda): hou.hda.installFile(_hda)
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.project.state import empty_declaration
from edini.project.ports import OUT_GEOMETRY_NODE
from edini.structure import _extract_component_signals

core = create_project_hda(name="proj_struct_extract")
decl = empty_declaration("proj_struct_extract")
decl["components"] = [{"id": "wheel", "structure": {"kind": "radial", "expected_axis": "Z",
    "repeats": [{"part": "spoke", "count": 28, "method": "copytopoints"}]}}]
build_project_scaffold(core, declaration=decl)
wheel = core.node("wheel")
# A python SOP that emits many prims, wired into out_geometry — no CTP.
py = wheel.createNode("python", "wheel_gen")
py.parm("python").set(
    "geo = hou.pwd().geometry()\n"
    "for i in range(60):\n"
    "    geo.createPolygon()\n")
outg = wheel.node(OUT_GEOMETRY_NODE)
outg.setInput(0, py)
outg.cook(force=True)
sig = _extract_component_signals(wheel, "wheel")
print(json.dumps({"prim_types": sig["prim_types"],
                  "instancing_nodes": sorted(sig["instancing_nodes"]),
                  "python_emit_geometry": sig["python_emit_geometry"],
                  "inferred_repeats": sig["inferred_repeats"]}))
"""


class TestExtractSignals(unittest.TestCase):
    @unittest.skipUnless(HYTHON, "hython not installed — run under real Houdini")
    def test_python_sop_wheel_signals(self):
        r = _run(_EXTRACT_HARNESS)
        self.assertGreater(r["prim_types"].get("Poly", 0), 0)
        self.assertEqual(r["instancing_nodes"], [])
        self.assertTrue(r["python_emit_geometry"])
        self.assertTrue(r["inferred_repeats"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_structure_analyzer_e2e_hython.py -v`
Expected: FAIL — `ImportError: cannot import name '_extract_component_signals'`

- [ ] **Step 3: Write minimal implementation**

Append to `python3.11libs/edini/structure.py`:
```python
# ── hou-coupled section (lazy import) ─────────────────────────────────────
def _bare_type_name(node) -> str:
    try:
        return node.type().name()
    except Exception:
        return ""


def _classify_instancing(type_name: str) -> bool:
    t = (type_name or "").lower()
    return any(t == n or t.startswith(n + "::") for n in INSTANCING_NODE_TYPES)


def _ctp_target_has_orient(ctp_node) -> bool:
    """True if any input geometry of a Copy-to-Points node carries point-level
    orient / N / up (the target-point orientation attributes). Checks all inputs
    so CTP 1.0 (target=input1) and 2.0 (target=input0) both work."""
    try:
        for inp in ctp_node.inputs():
            if inp is None:
                continue
            geo = inp.geometry()
            if geo is None:
                continue
            for nm in ("orient", "N", "up"):
                if geo.findPointAttrib(nm) is not None:
                    return True
    except Exception:
        pass
    return False


def _extract_component_signals(subnet, component_id: str) -> dict:
    """Walk a component subnet + its out_geometry, build the signal dict that
    evaluate_component_signals consumes. hou-coupled."""
    from edini.project.ports import OUT_GEOMETRY_NODE

    instancing_nodes: set[str] = set()
    python_emit_geometry = False
    ctp_target_has_orient = False
    try:
        children = list(subnet.allSubChildren())
    except Exception:
        children = []
    for child in children:
        tname = _bare_type_name(child)
        if _classify_instancing(tname):
            instancing_nodes.add(tname.split("::")[0])
            if "copy" in tname and "points" in tname or tname.startswith("copytopoints"):
                if _ctp_target_has_orient(child):
                    ctp_target_has_orient = True
        if tname == "python":
            try:
                if child.geometry() is not None and len(child.geometry().prims()) > 0:
                    python_emit_geometry = True
            except Exception:
                pass

    # prim_types from the component's out_geometry (agent's raw output, pre-bake).
    prim_types: dict[str, int] = {}
    out_geo = subnet.node(OUT_GEOMETRY_NODE)
    out_prim_count = 0
    if out_geo is not None:
        try:
            geo = out_geo.geometry()
            if geo is not None:
                for prim in geo.prims():
                    tn = prim.type().name()
                    prim_types[tn] = prim_types.get(tn, 0) + 1
                out_prim_count = len(geo.prims())
        except Exception:
            pass

    inferred_repeats = (
        python_emit_geometry and not instancing_nodes
        and out_prim_count >= _INFERRED_REPEAT_MIN_PRIMS
    )
    return {"component_id": component_id, "prim_types": prim_types,
            "instancing_nodes": instancing_nodes,
            "python_emit_geometry": python_emit_geometry,
            "inferred_repeats": inferred_repeats,
            "ctp_target_has_orient": ctp_target_has_orient}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_structure_analyzer_e2e_hython.py -v`
Expected: PASS (1 test, when hython available; SKIP otherwise — correct)

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/structure.py tests/test_structure_analyzer_e2e_hython.py
git commit -m "feat(structure): hou-coupled signal extractor + classify helpers"
```

---

## Task 4: Orchestrator `analyze_component_structure` (F3 via verify_orientation)

**Files:**
- Modify: `python3.11libs/edini/structure.py` (append orchestrator)
- Modify: `tests/test_structure_analyzer_e2e_hython.py` (add orchestrator test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_structure_analyzer_e2e_hython.py`:
```python
# analyze_component_structure on the python-SOP wheel must verdict FATAL with
# F2_repeat_no_instancing (declared copytopoints but no CTP node).
_ANALYZE_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda): hou.hda.installFile(_hda)
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.project.state import empty_declaration
from edini.project.ports import OUT_GEOMETRY_NODE
from edini.structure import analyze_component_structure

core = create_project_hda(name="proj_struct_analyze")
decl = empty_declaration("proj_struct_analyze")
decl["components"] = [{"id": "wheel", "structure": {"kind": "radial", "expected_axis": "Z",
    "repeats": [{"part": "spoke", "count": 28, "method": "copytopoints"}]}}]
build_project_scaffold(core, declaration=decl)
wheel = core.node("wheel")
py = wheel.createNode("python", "wheel_gen")
py.parm("python").set("geo=hou.pwd().geometry()\n[geo.createPolygon() for _ in range(60)]\n")
wheel.node(OUT_GEOMETRY_NODE).setInput(0, py)
res = analyze_component_structure(core.path(), component_id="wheel")
print(json.dumps({"overall": res["overall"],
                  "rules": [f["rule"] for f in res["fatal"]]}))
"""


class TestAnalyze(unittest.TestCase):
    @unittest.skipUnless(HYTHON, "hython not installed — run under real Houdini")
    def test_python_wheel_is_fatal(self):
        r = _run(_ANALYZE_HARNESS)
        self.assertEqual(r["overall"], "fatal")
        self.assertIn("F2_repeat_no_instancing", r["rules"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_structure_analyzer_e2e_hython.py::TestAnalyze -v`
Expected: FAIL — `ImportError: cannot import name 'analyze_component_structure'`

- [ ] **Step 3: Write minimal implementation**

Append to `python3.11libs/edini/structure.py`:
```python
def analyze_component_structure(core_path: str, component_id: str | None = None) -> dict:
    """Analyze one or all components of a project core. hou-coupled.

    Returns {success, core_path, component_id, overall, fatal[], advisory[],
    signals_per_component}. F3 (axis) is computed here via verify_orientation
    (reuses the baked edini_world_axis ground truth).
    """
    try:
        import hou
        from edini.project.state import load_declaration
        from edini.verify import verify_orientation
    except ImportError:
        return {"success": False, "error": "hou not available"}

    core = hou.node(core_path)
    if core is None:
        return {"success": False, "error": f"Core not found: {core_path}"}
    decl = load_declaration(core)
    components = decl.get("components", []) or []
    if component_id is not None:
        components = [c for c in components if c.get("id") == component_id]
        if not components:
            return {"success": False, "error": f"component {component_id!r} not declared"}

    out_node = core.node("OUT")
    out_path = out_node.path() if out_node is not None else None

    all_fatal: list[dict] = []
    all_advisory: list[dict] = []
    signals_per: dict[str, dict] = {}

    for comp in components:
        cid = comp.get("id", "?")
        subnet = core.node(cid)
        if subnet is None:
            all_fatal.append({"rule": "missing_component_subnet", "component": cid,
                              "detail": f"component subnet {cid!r} not found on the core"})
            continue
        declared = comp.get("structure")
        signals = _extract_component_signals(subnet, cid)

        # ── F3: declared radial/planar axis vs baked edini_world_axis ──
        kind = (declared or {}).get("kind")
        expected_axis = (declared or {}).get("expected_axis")
        if kind in ("radial", "planar") and expected_axis and out_path is not None:
            vr = verify_orientation(out_path, [{"component_id": cid,
                                                "kind": kind,
                                                "expected_axis": expected_axis,
                                                "tolerance_deg": 15}])
            if vr.get("success") and vr.get("failed", 0) > 0:
                det = (vr.get("checks") or [{}])[0].get("detected_axis", "?")
                signals["baked_axis"] = det
                all_fatal.append({"rule": "F3_axis_mismatch", "component": cid,
                    "detail": f"declared axis {expected_axis!r} != baked/detected axis {det!r}",
                    "fix": "Rebuild the part so its construction axis matches, "
                           "or correct the declared expected_axis.",
                    "suggested_tool": "verify_orientation"})

        verdict = evaluate_component_signals(signals, declared)
        all_fatal.extend(verdict["fatal"])
        all_advisory.extend(verdict["advisory"])
        signals_per[cid] = signals

    overall = "fatal" if all_fatal else ("advisory" if all_advisory else "clean")
    return {"success": True, "core_path": core_path,
            "component_id": component_id, "overall": overall,
            "fatal": all_fatal, "advisory": all_advisory,
            "signals_per_component": signals_per}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_structure_analyzer_e2e_hython.py -v`
Expected: PASS (2 tests when hython available)

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/structure.py tests/test_structure_analyzer_e2e_hython.py
git commit -m "feat(structure): analyze_component_structure orchestrator (F3 via verify_orientation)"
```

---

## Task 5: `structure` field in component schema (state.py)

**Files:**
- Modify: `python3.11libs/edini/project/state.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_structure_lint.py`:
```python
from edini.project.state import empty_declaration, add_structure_to_component


def test_add_structure_to_component_persists():
    decl = empty_declaration("p")
    decl["components"].append({"id": "wheel"})
    add_structure_to_component(decl, "wheel",
                               {"kind": "radial", "expected_axis": "Z"})
    c = decl["components"][0]
    assert c["structure"]["kind"] == "radial"
    assert c["structure"]["expected_axis"] == "Z"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_structure_lint.py::test_add_structure_to_component_persists -v`
Expected: FAIL — `ImportError: cannot import name 'add_structure_to_component'`

- [ ] **Step 3: Write minimal implementation**

Append to `python3.11libs/edini/project/state.py`:
```python
def add_structure_to_component(declaration: dict, component_id: str,
                               structure: dict) -> dict:
    """Attach a validated structural-intent block to a declared component.

    Pure (no hou). Raises KeyError if the component isn't declared. The
    structure dict is validated by edini.structure.lint_structure_decl at
    scaffold time; this helper only attaches it.
    """
    for c in declaration["components"]:
        if c.get("id") == component_id:
            c["structure"] = structure
            return c
    raise KeyError(f"component not declared: {component_id!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_structure_lint.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/project/state.py tests/test_structure_lint.py
git commit -m "feat(state): add_structure_to_component — structure field on components"
```

---

## Task 6: Wire lint into `build_project_scaffold` (shift-left refusal)

**Files:**
- Modify: `python3.11libs/edini/project/builder.py` — `build_project_scaffold` / the component-validation entry

- [ ] **Step 1: Write the failing test**

Append to `tests/test_structure_analyzer_e2e_hython.py`:
```python
# build_project_scaffold must REFUSE a component whose structure fails lint,
# before creating any nodes.
_LINT_REFUSE_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda): hou.hda.installFile(_hda)
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.project.state import empty_declaration
core = create_project_hda(name="proj_lint_refuse")
decl = empty_declaration("proj_lint_refuse")
decl["components"] = [{"id": "wheel", "structure": {"kind": "radial"}}]  # no axis
res = build_project_scaffold(core, declaration=decl)
print(json.dumps({"refused": not res.get("success", False),
                  "code": (res.get("lint_errors") or [{}])[0].get("code")}))
"""


class TestScaffoldLint(unittest.TestCase):
    @unittest.skipUnless(HYTHON, "hython not installed — run under real Houdini")
    def test_scaffold_refuses_bad_structure(self):
        r = _run(_LINT_REFUSE_HARNESS)
        self.assertTrue(r["refused"])
        self.assertEqual(r["code"], "missing_axis")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_structure_analyzer_e2e_hython.py::TestScaffoldLint -v`
Expected: FAIL — scaffold does not yet lint (builds anyway).

- [ ] **Step 3: Write minimal implementation**

In `python3.11libs/edini/project/builder.py`, find the component-validation entry of `build_project_scaffold` (the loop around `for i, comp in enumerate(components):` near line 57, where `cid = comp.get("id", ...)`). Insert the lint at the TOP of the function, before any `_ensure_component_subnet` calls:

```python
# At the top of build_project_scaffold, after `components` is resolved:
from edini.structure import lint_structure_decl
lint_errors: list[dict] = []
for comp in components:
    lint_errors.extend(lint_structure_decl(comp))
if lint_errors:
    return {"success": False,
            "error": ("structural-intent declaration failed lint (refused before any "
                      "nodes were created). Fix the declaration and re-run "
                      "project_build_scaffold."),
            "lint_errors": lint_errors,
            "suggested_fix": lint_errors[0].get("detail", "")}
```

If `build_project_scaffold` currently returns the core/subnet rather than a dict, wrap the lint refusal to match the existing return convention (return `None`/raise is also acceptable if that is the function's error convention — check the existing return and mirror it; the test asserts on the dict shape so prefer returning the dict).

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_structure_analyzer_e2e_hython.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/project/builder.py tests/test_structure_analyzer_e2e_hython.py
git commit -m "feat(builder): plan-time structural-intent lint refusal (shift-left)"
```

---

## Task 7: `project_finalize` Gate 4 + `structure_override`

**Files:**
- Modify: `python3.11libs/edini/verify.py` — `project_finalize`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_structure_analyzer_e2e_hython.py`:
```python
# A project with a fatal structure verdict must NOT finalize even with
# acknowledge_skip=True (skip does not bypass Gate 4). Only structure_override
# + structure_reason passes.
_FINALIZE_GATE4_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda): hou.hda.installFile(_hda)
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.project.state import empty_declaration
from edini.project.ports import OUT_GEOMETRY_NODE
from edini.verify import project_finalize

core = create_project_hda(name="proj_gate4")
decl = empty_declaration("proj_gate4")
decl["components"] = [{"id": "wheel", "structure": {"kind": "radial", "expected_axis": "Z",
    "repeats": [{"part": "spoke", "count": 28, "method": "copytopoints"}]}}]
build_project_scaffold(core, declaration=decl)
wheel = core.node("wheel")
py = wheel.createNode("python", "wheel_gen")
py.parm("python").set("geo=hou.pwd().geometry()\n[geo.createPolygon() for _ in range(60)]\n")
wheel.node(OUT_GEOMETRY_NODE).setInput(0, py)
skip = project_finalize(core.path(), acknowledge_skip=True, skip_reason="try to skip")
over = project_finalize(core.path(), structure_override=True, structure_reason="test override")
print(json.dumps({"skip_finalized": skip.get("finalized"),
                  "skip_structure_blocked": skip.get("structure_blocked"),
                  "override_finalized": over.get("finalized")}))
"""


class TestFinalizeGate4(unittest.TestCase):
    @unittest.skipUnless(HYTHON, "hython not installed — run under real Houdini")
    def test_skip_does_not_bypass_gate4(self):
        r = _run(_FINALIZE_GATE4_HARNESS)
        self.assertFalse(r["skip_finalized"], "acknowledge_skip must NOT bypass fatal structure verdicts")
        self.assertTrue(r["skip_structure_blocked"])
        self.assertTrue(r["override_finalized"], "structure_override+reason must pass")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m pytest tests/test_structure_analyzer_e2e_hython.py::TestFinalizeGate4 -v`
Expected: FAIL — today `acknowledge_skip=True` finalizes regardless.

- [ ] **Step 3: Write minimal implementation**

In `python3.11libs/edini/verify.py`, modify `project_finalize` (signature + skip block + Gate 4):

1. Add params to the signature:
```python
def project_finalize(
    core_path: str,
    acknowledge_skip: bool = False,
    skip_reason: str | None = None,
    samples: str = "min_default_max",
    structure_override: bool = False,
    structure_reason: str | None = None,
) -> dict[str, Any]:
```

2. Replace the SKIP path (the `if acknowledge_skip:` block ~line 1132) so it runs Gate 4 first and cannot bypass a fatal structure verdict:
```python
        # ── Gate 4: structure (FATAL verdicts immune to acknowledge_skip) ──
        from edini.structure import analyze_component_structure
        struct = analyze_component_structure(core_path)
        fatal_struct = struct.get("fatal", []) if struct.get("success") else []
        if fatal_struct and not structure_override:
            if acknowledge_skip:
                # Skip does NOT bypass structural defects. Report + refuse.
                return {"success": False, "finalized": False, "core_path": core_path,
                        "skipped": False, "structure_blocked": True,
                        "checks": {"structure": struct},
                        "failures": [f"Gate 4 (structure) fatal — not bypassable by "
                                     f"acknowledge_skip: {[f.get('rule') for f in fatal_struct]}"],
                        "structure_fatal": fatal_struct}
            _add_failure("structure",
                         f"Gate 4 structure fatal: {[f.get('rule') for f in fatal_struct]}",
                         components=[f.get("component") for f in fatal_struct])
        elif fatal_struct and structure_override:
            if not (structure_reason and structure_reason.strip()):
                return {"success": False, "error": (
                    "structure_override=True requires a non-empty structure_reason "
                    "(state WHY the structural fatal is being overridden).")}
            append_log(decl, kind="structure_override",
                       summary=f"structure fatal overridden: {structure_reason.strip()}",
                       payload={"fatal": [f.get("rule") for f in fatal_struct],
                                "reason": structure_reason.strip()}, result_ok=True)
            save_declaration(core, decl)
        checks["structure"] = struct

        # ── SKIP path: bypasses ONLY Gate 1–3 (status/robust/parametric) ──
        if acknowledge_skip:
            if not (skip_reason and skip_reason.strip()):
                return {"success": False,
                        "error": ("acknowledge_skip=True requires a non-empty skip_reason.")}
            append_log(decl, kind="finalize_skip",
                       summary=f"finalized (Gates 1-3 skipped, Gate 4 passed): {skip_reason.strip()}",
                       payload={"skip_reason": skip_reason.strip()}, result_ok=True)
            save_declaration(core, decl)
            return {"success": True, "finalized": True, "skipped": True,
                    "skip_reason": skip_reason.strip(), "core_path": core_path,
                    "checks": checks, "failures": [], "drafts_created": 0,
                    "failure_records": []}
```

Place the Gate 4 block AFTER `decl = load_declaration(core)` is available and BEFORE the existing `if acknowledge_skip:` block. `decl` is loaded at line ~1200 in the current code — ensure Gate 4 reads run after that. The non-skip path already appends failures via `_add_failure` and the existing `if failures:` block at the end will then refuse finalize.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m pytest tests/test_structure_analyzer_e2e_hython.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/verify.py tests/test_structure_analyzer_e2e_hython.py
git commit -m "feat(finalize): Gate 4 structure — fatal immune to acknowledge_skip + structure_override"
```

---

## Task 8: Tool registration (Python handler + TS schema)

**Files:**
- Modify: `python3.11libs/edini/tool_executor.py` — `TOOL_HANDLERS`
- Modify: `pi-extensions/edini-tools/tools/project.ts`

- [ ] **Step 1: Python handler**

In `python3.11libs/edini/tool_executor.py`, add to the imports near the top (where `verify_parametric` etc. are imported, ~line 26-32):
```python
from edini.structure import analyze_component_structure
```
Add to `TOOL_HANDLERS` (e.g. after the `project_status` entry ~line 656):
```python
    # Per-component structural verdicts (fatal/advisory). Its fatal subset is
    # also enforced as Gate 4 in project_finalize (immune to acknowledge_skip).
    "analyze_component_structure": lambda **kw: analyze_component_structure(
        kw["core_path"],
        component_id=kw.get("component_id"),
    ),
```

- [ ] **Step 2: TS schema**

In `pi-extensions/edini-tools/tools/project.ts`, add a descriptor alongside the sibling project tools (mirror an existing entry's shape — see `project_status` / `verify_parametric` in that file):
```typescript
{
  name: "analyze_component_structure",
  description: (
    "Per-component structural verdicts for an edini::project core. Reads the " +
    "node graph + cooked geometry + declared structural intent, returns fatal/" +
    "advisory findings: F1 bare curves at out_geometry, F2 repeated parts not " +
    "instanced via Copy-to-Points, F3 radial/planar axis mismatch vs baked " +
    "edini_world_axis, F4 Copy-to-Points target points missing orient/N/up. " +
    "The fatal subset is also enforced as Gate 4 in project_finalize and " +
    "cannot be bypassed by acknowledge_skip. Call this during the build to " +
    "self-check before finalizing."
  ),
  inputSchema: {
    type: "object",
    properties: {
      core_path: { type: "string", description: "edini::project SOP HDA instance path" },
      component_id: {
        type: "string",
        description: "Optional: analyze one component. Omit to analyze all components.",
      },
    },
    required: ["core_path"],
  },
}
```

- [ ] **Step 3: Verify dispatch wires up**

Run: `py -3 -c "import sys; sys.path.insert(0,'python3.11libs'); from edini.tool_executor import TOOL_HANDLERS; assert 'analyze_component_structure' in TOOL_HANDLERS; print('registered')"`
Expected output: `registered`

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/tool_executor.py pi-extensions/edini-tools/tools/project.ts
git commit -m "feat(tools): register analyze_component_structure (handler + TS schema)"
```

---

## Task 9: SKILL.md — document required `structure` declaration + the tool

**Files:**
- Modify: `skills/project-modeling/SKILL.md`

- [ ] **Step 1: Add the declaration requirement**

In `skills/project-modeling/SKILL.md`, add a section under the component-declaration guidance (near where components are introduced). Content:

```markdown
## Structural intent (REQUIRED on every component)

When you declare a component for `project_build_scaffold`, include a `structure`
block. The scaffold REFUSES to build a component whose `structure` fails lint —
this catches structural mistakes before any geometry is created.

```jsonc
{"id": "front_wheel",
 "structure": {
    "kind": "radial",              // radial | planar | repeated | solid
    "expected_axis": "Z",          // required for radial | planar (X|Y|Z|-X|-Y|-Z)
    "repeats": [                   // repeated sub-parts + how they're instanced
      {"part": "spoke", "count": 28, "method": "copytopoints"}
    ]
 }}
```

Rules this declares (and that `analyze_component_structure` + `project_finalize`
Gate 4 enforce as fatal, un-skippable):

- **Repeated parts must be instanced via Copy-to-Points** (even 2 instances) —
  declare each in `repeats` with `method: "copytopoints"`. Two wheels, four
  legs, N spokes: ONE template + Copy-to-Points, never hand-duplicated subnets
  or Python-SOP loops emitting each copy.
- **Radial parts (wheels, gears) declare their axle axis** (`expected_axis`).
  The analyzer compares it to the baked `edini_world_axis`.
- **Copy-to-Points target points need `orient`/`N`/`up`** or copies inherit
  identity orientation (candles/wheels pointing the wrong way).

Wheels, gears, tires → `radial`. Tabletops, plates → `planar`. Spokes, legs,
candles, rivets → `repeated`. A single box body → `solid`.

Self-check anytime with `analyze_component_structure(core_path)`; finalize runs
the same check as Gate 4 (fatal verdicts are not bypassable by
`acknowledge_skip` — use `structure_override` + reason only for a genuinely
atypical structure).
```

- [ ] **Step 2: Commit**

```bash
git add skills/project-modeling/SKILL.md
git commit -m "docs(skill): required structural-intent declaration + analyze tool"
```

---

## Task 10: Acceptance fixtures — 4 crashed → fatal, 2 clean → clean

**Files:**
- Modify: `tests/test_structure_analyzer_e2e_hython.py`

- [ ] **Step 1: Add the acceptance test class**

Append to `tests/test_structure_analyzer_e2e_hython.py`. These replay the four logged failure shapes and the two clean ones. (Full reproduction of glm's bare-curve miswire and deepseek's candle-no-orient requires a few nodes each — built inline in the harness.)

```python
# Replays of the 2026-07-09 logged failures + clean cases.
_ACCEPTANCE_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda): hou.hda.installFile(_hda)
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.project.state import empty_declaration
from edini.project.ports import OUT_GEOMETRY_NODE
from edini.structure import analyze_component_structure

def fresh(name, comps):
    core = create_project_hda(name=name)
    decl = empty_declaration(name)
    decl["components"] = comps
    build_project_scaffold(core, declaration=decl)
    return core

# 1. deepseek wheel: python SOP, no CTP, declared radial+Z
c = fresh("acc_wheel", [{"id":"wheel","structure":{"kind":"radial","expected_axis":"Z",
    "repeats":[{"part":"spoke","count":28,"method":"copytopoints"}]}}])
w = c.node("wheel"); py = w.createNode("python","wg")
py.parm("python").set("g=hou.pwd().geometry()\n[g.createPolygon() for _ in range(60)]\n")
w.node(OUT_GEOMETRY_NODE).setInput(0, py)

# 2. glm frame: bare curve wired to out_geometry
c2 = fresh("acc_frame", [{"id":"frame","structure":{"kind":"solid"}}])
f = c2.node("frame"); cv = f.createNode("curve","skel")
cv.parm("type").set("nurbs"); cv.parm("coords").set("0,0,0 1,1,1 2,0,0")
f.node(OUT_GEOMETRY_NODE).setInput(0, cv)

# 3. deepseek candles: CTP present but target has no orient
c3 = fresh("acc_candle", [{"id":"candles","structure":{"kind":"repeated",
    "repeats":[{"part":"candle","count":6,"method":"copytopoints"}]}}])
cd = c3.node("candles")
tmpl = cd.createNode("tube","candle_body"); scatter = cd.createNode("scatter","pts")
ctp = cd.createNode("copytopoints::2.0","copy")
ctp.setInput(0, tmpl); ctp.setInput(1, scatter)
cd.node(OUT_GEOMETRY_NODE).setInput(0, ctp)

# 4. clean table legs: CTP + (declared) — clean
c4 = fresh("acc_legs", [{"id":"legs","structure":{"kind":"repeated",
    "repeats":[{"part":"leg","count":4,"method":"copytopoints"}]}}])
lg = c4.node("legs"); leg = lg.createNode("tube","leg_t"); sc = lg.createNode("scatter","lp")
# give target points an orient so F4 passes
wr = lg.createNode("attribwrangle","ori"); wr.parm("snippet").set("p@orient={0,0,0,1};")
wr.setInput(0, sc); cp = lg.createNode("copytopoints::2.0","cp")
cp.setInput(0, leg); cp.setInput(1, wr); lg.node(OUT_GEOMETRY_NODE).setInput(0, cp)

out = {}
for name, core in [("wheel", c), ("frame", c2), ("candle", c3), ("legs", c4)]:
    r = analyze_component_structure(core.path())
    out[name] = {"overall": r["overall"], "rules": [f["rule"] for f in r["fatal"]]}
print(json.dumps(out))
"""


class TestAcceptance(unittest.TestCase):
    @unittest.skipUnless(HYTHON, "hython not installed — run under real Houdini")
    def test_logged_failures_are_fatal_and_clean_is_clean(self):
        r = _run(_ACCEPTANCE_HARNESS)
        self.assertEqual(r["wheel"]["overall"], "fatal")
        self.assertIn("F2_repeat_no_instancing", r["wheel"]["rules"])
        self.assertEqual(r["frame"]["overall"], "fatal")
        self.assertIn("F1_bare_curves_at_out", r["frame"]["rules"])
        self.assertEqual(r["candle"]["overall"], "fatal")
        self.assertIn("F4_ctp_no_orient", r["candle"]["rules"])
        self.assertEqual(r["legs"]["overall"], "clean")
```

- [ ] **Step 2: Run the full suite**

Run: `py -3 -m pytest tests/test_structure_lint.py tests/test_structure_rules.py tests/test_structure_analyzer_e2e_hython.py -v`
Expected: all pure tests PASS; all e2e tests PASS (when hython available) or SKIP (correct when not).

- [ ] **Step 3: Commit**

```bash
git add tests/test_structure_analyzer_e2e_hython.py
git commit -m "test(structure): acceptance fixtures — logged failures fatal, clean legs clean"
```

---

## Task 11 (low-priority): Consolidate harness classify helpers

**Files:**
- Modify: `python3.11libs/edini/harness.py`

Defer unless the DRY duplication bites. Goal: make `_check_modular_structure` import `MODULAR_NODE_TYPES` / `POSTPROCESS_NODE_TYPES` + the classify helpers from `edini.structure` instead of carrying its own copies. **Safety net:** the existing sandbox tests (`test_*sandbox*`, `test_*commit*`) must remain green.

- [ ] **Step 1:** In `harness.py`, replace the local `_MODULAR_NODE_TYPES` / `_POSTPROCESS_NODE_TYPES` / `_node_type_name` / `_node_type_components` / `_python_sop_code_line_count` / `_geometry_component_ids` definitions (lines ~892–960) with imports:
```python
from edini.structure import (MODULAR_NODE_TYPES as _MODULAR_NODE_TYPES,
                             POSTPROCESS_NODE_TYPES as _POSTPROCESS_NODE_TYPES)
from edini.structure import _bare_type_name as _node_type_name
# keep harness's _node_type_components / _python_sop_code_line_count /
# _geometry_component_ids as thin wrappers over structure.py equivalents if
# their signatures differ; otherwise import directly.
```
Verify `_node_type_components` in structure.py matches harness's usage (`tcomp == m or tcomp.startswith(m+"::")` expects a lowercased name with version suffix). Add a `_node_type_components` to structure.py if not already present.

- [ ] **Step 2:** Run the full sandbox/commit test suite:
Run: `py -3 -m pytest tests/ -k "sandbox or commit or modular" -v`
Expected: PASS (no behavior change).

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/harness.py python3.11libs/edini/structure.py
git commit -m "refactor(harness): delegate _check_modular_structure helpers to edini.structure"
```

---

## Self-Review

**Spec coverage (spec § → task):**
- §4 structural-intent declaration → Task 1 (lint) + Task 5 (state field) + Task 6 (scaffold refusal) + Task 9 (SKILL). ✓
- §5 signals read → Task 3 (extraction). ✓
- §6.1 F1/F2/F4 → Task 2; F3 → Task 4 (verify_orientation reuse). ✓
- §6.2 declared vs inferred → Task 2 (`confidence` field). ✓
- §6.3 A1/A2 advisory → **DEFERRED**: A1/A2 are advisory-only (non-blocking) and lower-value than the fatal set; they are not in cut-1. Add a follow-up task if desired. (A3 = cut-1.5, out of scope per spec §13.)
- §7 Gate 4 + skip immunity + structure_override → Task 7. ✓
- §8 tool surface (handler + return + TS) → Task 4 (return) + Task 8 (handler + TS). ✓
- §9 rejected alternatives → reflected in design choices (F3 reuse, no inspect_health folding). ✓
- §10 acceptance fixtures → Task 10. ✓
- §12 implementation surface → Tasks 1–11 cover every listed file. ✓

**Placeholder scan:** Task 6 Step 3 and Task 11 Step 1 say "check the existing return/signature and mirror it" — these are genuine adaptation points where the implementer must read the adjacent code rather than copy a fixed snippet (because `build_project_scaffold`'s return convention and harness's exact helper bodies weren't fully captured). Both name the exact file+line region to consult. Acceptable; not "TBD."

**Type consistency:** `evaluate_component_signals` keys (`prim_types`, `instancing_nodes`, `python_emit_geometry`, `inferred_repeats`, `ctp_target_has_orient`, `component_id`) match between Task 2 (consumer) and Task 3 (producer). `analyze_component_structure` return keys match Task 4 + the spec §8.3 + Task 7's Gate 4 consumer (`struct.get("fatal")`). `lint_structure_decl` error codes (`structure_missing`, `missing_axis`, `repeated_without_repeats`, `bad_repeat_count`) match Task 1 tests and Task 6's assertion (`missing_axis`). ✓

**One known gap to flag:** the `ctp` detection in Task 3 uses `tname.startswith("copytopoints")` to decide which instancing node to probe for orient — copy/foreach/instance variants are counted as instancing but not probed for orient (only Copy-to-Points takes target-point orient). This matches F4's intent (orient matters for CTP). Documented inline.

---

## Out of Scope (separate plan)

- **Cut-1.5 — A3:** per-component parametric re-measure in `project_finalize` (auto-target `verify_parametric` at the component a param drives, when OUT-level fails). Fixes the `frosting_overhang` / `top_radius` / `tube_radius` bbox false-negatives. Highest-value advisory item; sequenced next.
- **L2 part-helpers** (`make_radial_part`, `make_tube_from_curves`, `array_on_anchors`) — the "make wrong states unconstructable" layer.
- **Visual/gestalt render complement** — optional, lowest priority.
- **A1/A2 advisory rules** (sibling hand-built detection, monolithic-python project-scoped) — advisory-only, can be added post-cut-1.
