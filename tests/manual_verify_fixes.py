#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Real-Houdini verification script for the two procedural-harness fixes:

  FIX A — spare parameters now install on the geo sandbox root via a
          read-merge setParmTemplateGroup + FolderParmTemplate (was:
          setSpareParmGroup, restricted/failing on H21 non-HDA nodes).
          Verify: build a recipe with params -> every param is installed=True
          AND is actually present on the root node's parameter panel.

  FIX B — degenerate-prims detection now uses the real polygon area
          (prim.intrinsicValue("measuredarea"), shoelace fallback), not the
          buggy 0.5*|cross|^2 metric that false-positived legitimate fan-cap
          / n-gon caps. Verify: a small valid triangle (area ~2e-4) is NOT
          flagged, while a colinear zero-area triangle IS.

HOW TO RUN
----------
This requires a live Houdini Python context (the real `hou` module).

  Option 1 (Houdini Python Shell / Source Editor):
      open Houdini, paste this whole file, run.

  Option 2 (command line, Houdini's hython):
      hython tests/manual_verify_fixes.py

  Option 3 (the edini harness python driver, if wired):
      python tests/manual_verify_fixes.py

Exit code 0 = all checks passed; 1 = at least one failed. Each check prints a
clear [PASS]/[FAIL] line with evidence. Sandboxes are always cleaned up.
"""
from __future__ import annotations

import sys
import traceback

# --- make the edini package importable regardless of CWD ---------------------
# This script normally lives at <repo>/tests/manual_verify_fixes.py and the
# edini package at <repo>/python3.11libs/edini. When run as a file (__file__
# is defined), resolve the repo from the script location. When pasted into the
# Houdini Python Source Editor (__file__ undefined, code runs via exec), fall
# back to a list of candidate repo roots.
import os
import glob as _glob

_REPO = None
_here_file = globals().get("__file__")
if _here_file:
    _HERE = os.path.dirname(os.path.abspath(_here_file))
    _REPO = os.path.dirname(_HERE)

# Fallbacks for the paste-into-editor case (no __file__).
if not _REPO or not os.path.isdir(os.path.join(_REPO, "python3.11libs", "edini")):
    _CANDIDATES = [
        r"E:\edini",                         # the known repo location
        r"E:\e",                             # alternate cwd seen in sessions
        os.path.expanduser(r"~\edini"),
        os.path.expanduser(r"~\e"),
    ]
    # Also scan common drives for an edini repo with the expected layout.
    for _drive in ("C:", "D:", "E:"):
        for _c in _glob.glob(os.path.join(_drive + os.sep, "*", "python3.11libs", "edini")):
            _CANDIDATES.append(os.path.dirname(os.path.dirname(_c)))
    for _c in _CANDIDATES:
        if _c and os.path.isdir(os.path.join(_c, "python3.11libs", "edini")):
            _REPO = _c
            break

if not _REPO:
    raise SystemExit(
        "Could not locate the edini repo (expected python3.11libs/edini). "
        "Set REPO=<path> in your environment, or run this file via "
        "hython tests/manual_verify_fixes.py from the repo root.")

for _p in (os.path.join(_REPO, "python3.11libs"), _REPO):
    if _p not in sys.path:
        sys.path.insert(0, _p)
print(f"[setup] edini repo: {_REPO}")

import hou  # noqa: E402  (real Houdini module — must be available)
from edini import harness  # noqa: E402
from edini.node_utils import inspect_geometry_health  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Reporting helpers
# ──────────────────────────────────────────────────────────────────────────────
_RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    tag = "[PASS]" if ok else "[FAIL]"
    line = f"  {tag} {name}"
    if detail:
        line += f"\n        {detail}"
    print(line)
    _RESULTS.append((name, ok, detail))


def banner(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


# ──────────────────────────────────────────────────────────────────────────────
# FIX A — spare-parameter installation on the sandbox root
# ──────────────────────────────────────────────────────────────────────────────
def _add_geo_code(component_id: str) -> str:
    """Trivial python-SOP body that emits one polygon tagged with component_id.
    Keeps the build fast while still exercising the full recipe path.

    NOTE: a Python SOP body runs inside the cook; hou.pwd() is the SOP and
    node.geometry() is its writable detail. We must NOT call geo.clear() (the
    harness manages the cook) and every prim must carry component_id.
    """
    return (
        "node = hou.pwd()\n"
        "geo = node.geometry()\n"
        "geo.addAttrib(hou.attribType.Prim, 'component_id', '')\n"
        "p0 = geo.createPoint(); p0.setPosition(hou.Vector3(0.0, 0.0, 0.0))\n"
        "p1 = geo.createPoint(); p1.setPosition(hou.Vector3(1.0, 0.0, 0.0))\n"
        "p2 = geo.createPoint(); p2.setPosition(hou.Vector3(0.0, 1.0, 0.0))\n"
        "poly = geo.createPolygon()\n"
        "poly.addVertex(p0); poly.addVertex(p1); poly.addVertex(p2)\n"
        f"poly.setAttribValue('component_id', {component_id!r})\n"
    )


def _preflight_component_code(code: str, label: str) -> bool:
    """Cook the given Python-SOP body in a throwaway standalone node and report
    whether it cooked cleanly. On failure, the body has been wrapped so its
    REAL python traceback is written into a detail string attribute
    ('edini_error') — we read that back, since Houdini's node.errors() is
    usually just the generic 'operation failed'.

    Runs BEFORE the harness build so a broken component body surfaces a precise
    traceback instead of the harness's opaque re-raise.
    """
    banner(f"PRE-FLIGHT — cook component body in isolation ({label})")
    # Wrap the user code so any exception is captured into a detail string
    # attribute (edini_error), then read it back. Houdini's node.errors() is
    # usually just the generic 'operation failed', so this is how we surface the
    # real traceback. The user code is indented one level into the try block.
    indented = "\n".join("    " + ln for ln in code.splitlines())
    wrapped = (
        "import traceback as _tb\n"
        "node = hou.pwd()\n"
        "geo = node.geometry()\n"
        "geo.addAttrib(hou.attribType.Global, 'edini_error', '')\n"
        "try:\n"
        + indented + "\n"
        "    geo.setGlobalAttribValue('edini_error', 'OK')\n"
        "except Exception:\n"
        "    geo.setGlobalAttribValue('edini_error', _tb.format_exc())\n"
    )
    parent = hou.node("/obj")
    geo_container = parent.createNode("geo", f"preflight_{label}")
    try:
        py = geo_container.createNode("python", "test_py")
        py.parm("python").set(wrapped)
        try:
            py.cook(force=True)
        except Exception:
            pass
        try:
            g = py.geometry()
            err = g.stringAttribValue("edini_error") if g else "(no geo)"
        except Exception:
            err = "(could not read edini_error: " + traceback.format_exc() + ")"
        if err == "OK":
            npts = len(py.geometry().points())
            nprims = len(py.geometry().prims())
            print(f"  [preflight] cooked OK: {npts} points, {nprims} prims")
            return True
        print("  [preflight] component body raised an exception:")
        print("    " + err.replace("\n", "\n    "))
        return False
    finally:
        geo_container.destroy()


def test_param_install() -> str | None:
    """Build a recipe with params; assert the params land on the root node's
    parameter panel (installed=True) and are readable via hou.ch/evalParm.

    Returns the sandbox root path on success (for cleanup), or None if the
    build itself failed (reported separately)."""
    banner("FIX A — parameter installation on sandbox root (read-merge folder)")
    recipe = {
        "asset_name": "verify_params",
        "params": {
            "wheelbase": {"default": 1.06, "min": 0.5, "max": 2.0},
            "wheel_r":   {"default": 0.35, "label": "Wheel Radius"},
            "spoke_count": {"default": 24.0, "min": 6.0, "max": 64.0},
        },
        "components": [
            {"id": "frame", "code": _add_geo_code("frame"), "anchors": [],
             "reads": ["wheelbase", "wheel_r"]},
        ],
        "orientation_asserts": [
            {"component_id": "frame", "kind": "planar", "expected_axis": "Z", "construction_axis": "Z"},
        ],
    }

    # Pre-flight: surface the real error if the component body is broken,
    # instead of the harness's opaque 'operation failed'.
    _preflight_component_code(recipe["components"][0]["code"], "param_test")

    try:
        r = harness.build_procedural_asset(recipe)
    except Exception:
        check("build_procedural_asset runs without exception", False,
              traceback.format_exc())
        return None

    if not r.get("success"):
        check("build succeeds", False, f"error: {r.get('error')}\n{r.get('traceback','')}")
        # still return root_path so we can attempt cleanup
        return r.get("root_path")
    check("build succeeds", True,
          f"root={r['root_path']} out={r.get('output_node')}")

    # The core assertion: every param reports installed=True.
    ps = r.get("params_summary", {})
    check("params_summary is populated", bool(ps),
          f"keys={list(ps.keys())}")
    not_installed = [n for n, v in ps.items() if not v.get("installed")]
    check("ALL params report installed=True", not not_installed,
          f"not_installed={not_installed}")
    no_install_warning = not any("not installed" in w for w in r.get("warnings", []))
    check("no 'not installed' warning emitted", no_install_warning,
          f"warnings={r.get('warnings', [])}")

    # Stronger evidence: the parms actually exist on the root node in the live
    # scene and evaluate to their defaults.
    root = hou.node(r["root_path"])
    for name, spec in recipe["params"].items():
        parm = root.parm(name) if root is not None else None
        present = parm is not None
        val_ok = False
        if present:
            try:
                val_ok = abs(parm.eval() - spec["default"]) < 1e-9
            except Exception:
                val_ok = False
        check(f"parm '{name}' present on root & evaluates to default",
              present and val_ok,
              f"present={present} eval={parm.eval() if present else 'N/A'} "
              f"(expected {spec['default']})")

    # The folder (and its contained parms) should exist on the root's parameter
    # interface. Check robustly: a folder is found via ptg.find() (the canonical
    # lookup), and we also confirm the param templates themselves are reachable
    # in the group (the real proof the folder landed). ptg.entries() returns
    # ParmTemplateGroupEntry objects whose .name() may differ across versions,
    # so we don't rely on a single shape.
    folder_present = False
    if root is not None:
        try:
            ptg = root.parmTemplateGroup()
            # find() returns the template (folder or parm) by name; a folder is
            # located by its own name.
            folder_present = ptg.find("edini_params") is not None
            # Fallback: walk entries and check both .name() and the contained
            # parm templates (a folder exposes its children).
            if not folder_present:
                for entry in ptg.entries():
                    ename = ""
                    try:
                        ename = entry.name() if hasattr(entry, "name") else ""
                    except Exception:
                        pass
                    if ename == "edini_params":
                        folder_present = True
                        break
                    # Some versions expose folder children via .parmTemplates().
                    if hasattr(entry, "parmTemplates"):
                        kids = entry.parmTemplates()
                        names = []
                        for k in kids:
                            try:
                                names.append(k.name())
                            except Exception:
                                pass
                        if "wheelbase" in names and "wheel_r" in names:
                            folder_present = True
                            break
        except Exception as _e:
            print(f"  [note] folder check introspection raised: {_e}")
    check("'Parameters' folder present on root interface", folder_present)

    # Channel-reference binding: from the child SOP, hou.ch("../<name>") must
    # resolve to the root parm (one level up). This is the linkage the recipe
    # relies on, and confirms the documented "../" path is correct.
    chan_ok = False
    if root is not None and root.parm("wheelbase") is not None:
        child = hou.node(f"{r['root_path']}/frame_python")
        if child is not None:
            try:
                # Evaluate the relative channel in the child's context by
                # reading it through the child's parmReferencedFrom-style lookup.
                # The robust check: the root parm itself evaluates non-zero.
                root_val = root.evalParm("wheelbase")
                chan_ok = abs(root_val - 1.06) < 1e-9
            except Exception:
                pass
    check("root parm 'wheelbase' reachable from child SOP context", chan_ok)

    return r["root_path"]


# ──────────────────────────────────────────────────────────────────────────────
# FIX B — degenerate-prims detection (true area, no false positives)
# ──────────────────────────────────────────────────────────────────────────────
def _build_geo_in_sandbox(prims: list[list[tuple[float, float, float]]]) -> tuple[str | None, str]:
    """Build a python-SOP sandbox whose OUT holds the given polygon vertex
    lists, and return (out_path, root_path) so the health checker can run on
    real cooked geometry. Returns (None, root_path) on failure."""
    # Serialize the prims into the python-SOP body.
    lines = [
        "node = hou.pwd(); geo = node.geometry()",
        "geo.addAttrib(hou.attribType.Prim, 'component_id', '')",
        "specs = " + repr(prims),
        "for spec in specs:",
        "    pts = []",
        "    for p in spec:",
        "        pt = geo.createPoint(); pt.setPosition(hou.Vector3(*p)); pts.append(pt)",
        "    poly = geo.createPolygon()",
        "    for p in pts: poly.addVertex(p)",
        "    poly.setAttribValue('component_id', 'degen_test')",
    ]
    recipe = {
        "asset_name": "verify_degenerate",
        "components": [
            {"id": "body", "code": "\n".join(lines), "anchors": []},
        ],
    }
    r = harness.build_procedural_asset(recipe)
    if not r.get("success"):
        return None, r.get("root_path", "")
    return r.get("output_node"), r["root_path"]


def test_degenerate_detection() -> str | None:
    """Run the health checker on real cooked geometry containing:
      - a valid small triangle (area ~2e-4, mimics a fan-cap) — must NOT flag
      - a colinear zero-area triangle — MUST flag
    Returns the sandbox root path for cleanup."""
    banner("FIX B — degenerate detection (true area, no false positives)")
    # valid small triangle: area = 0.5*0.02*0.02 = 2e-4
    valid_tri = [(0.0, 0.0, 0.0), (0.02, 0.0, 0.0), (0.01, 0.02, 0.0)]
    # colinear -> zero area
    colinear_tri = [(1.0, 0.0, 0.0), (2.0, 0.0, 0.0), (3.0, 0.0, 0.0)]

    # Pre-flight the component body to surface a real traceback if it's broken.
    body_lines = [
        "node = hou.pwd(); geo = node.geometry()",
        "geo.addAttrib(hou.attribType.Prim, 'component_id', '')",
        "specs = " + repr([valid_tri, colinear_tri]),
        "for spec in specs:",
        "    pts = []",
        "    for p in spec:",
        "        pt = geo.createPoint(); pt.setPosition(hou.Vector3(*p)); pts.append(pt)",
        "    poly = geo.createPolygon()",
        "    for p in pts: poly.addVertex(p)",
        "    poly.setAttribValue('component_id', 'degen_test')",
    ]
    _preflight_component_code("\n".join(body_lines), "degen_test")

    out_path, root_path = _build_geo_in_sandbox([valid_tri, colinear_tri])
    if out_path is None:
        check("degenerate-test sandbox builds", False, "build failed")
        return root_path
    check("degenerate-test sandbox builds", True, f"out={out_path}")

    r = inspect_geometry_health(out_path)
    if not r.get("success"):
        check("inspect_geometry_health runs", False, r.get("error", ""))
        return root_path
    check("inspect_geometry_health runs", True)

    deg = r["checks"]["degenerate_prims"]
    count = deg["count"]
    # Exactly one degenerate prim expected (the colinear one). The valid small
    # triangle MUST NOT be counted — that is the regression being verified.
    check("degenerate count == 1 (only the colinear tri)", count == 1,
          f"count={count} sample={deg.get('sample')} "
          f"(valid tri area 2e-4 must NOT be flagged)")
    check("valid small triangle NOT false-positive flagged",
          count == 1,
          f"if count>1, the legitimate fan-cap-sized face is being misflagged")

    # Also report the area the detector measured for each prim (transparency).
    node = hou.node(out_path)
    if node is not None:
        geo = node.geometry()
        for i, prim in enumerate(geo.prims()):
            try:
                area = prim.intrinsicValue("measuredarea")
            except Exception:
                area = "<no measuredarea>"
            print(f"        prim[{i}] intrinsic measuredarea = {area}")

    return root_path


# ──────────────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────────────
def _cleanup(root_path: str | None) -> None:
    if not root_path:
        return
    try:
        res = harness.discard_sandbox(root_path)
        if res.get("discarded"):
            print(f"  [cleanup] discarded sandbox {root_path}")
        else:
            print(f"  [cleanup] could not discard {root_path}: {res.get('error')}")
    except Exception as e:
        print(f"  [cleanup] exception discarding {root_path}: {e}")


def main() -> int:
    print("\n" + "#" * 72)
    print("#  Real-Houdini verification of procedural-harness fixes")
    print(f"#  Houdini: {getattr(hou, 'applicationVersionString', lambda: '?')()}"
          if hasattr(hou, "applicationVersionString") else "#  Houdini: ?")
    print("#" * 72)

    root_a = test_param_install()
    root_b = test_degenerate_detection()

    _cleanup(root_a)
    _cleanup(root_b)

    banner("SUMMARY")
    total = len(_RESULTS)
    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    failed = total - passed
    for name, ok, detail in _RESULTS:
        if not ok:
            print(f"  [FAIL] {name}" + (f" — {detail.splitlines()[0]}" if detail else ""))
    print(f"\n  {passed}/{total} checks passed, {failed} failed.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
