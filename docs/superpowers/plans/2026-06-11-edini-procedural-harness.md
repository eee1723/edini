# Edini Procedural Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase B of the Edini procedural harness so procedural Houdini assets are generated through sandboxed live-node workflows with diagnostics, structural verification, safe capture, and C-compatible result shapes.

**Architecture:** Keep Phase B inside the current Houdini process, but route procedural generation through a new `edini.harness` helper module and explicit tool handlers. The harness returns `job_id`, `execution_mode`, diagnostics, geometry stats, and artifact-like metadata now, so Phase C can swap live sandbox execution for an external hython/Houdini worker without changing the Pi-facing workflow.

**Tech Stack:** Python 3.11, Houdini `hou` API, PySide6/flipbook for viewport capture, Pi Extensions in TypeScript/TypeBox, pytest/unittest with `tests/mock_hou.py`.

---

## File Structure

| Path | Action | Responsibility |
| --- | --- | --- |
| `tests/mock_hou.py` | Modify | Add mock geometry, bounds, node renaming, display-node helpers, and simple viewer/flipbook fixtures needed by harness tests. |
| `tests/test_node_utils.py` | Modify | Cover fixed `inspect_geometry`, richer `run_python`, and backward-compatible capture behavior. |
| `tests/test_procedural_harness.py` | Create | Unit tests for diagnostics, sandbox execution, verification, commit/discard, and C-shaped result fields. |
| `tests/test_tool_executor_harness.py` | Create | Verify new `TOOL_HANDLERS` entries dispatch expected params without starting the HTTP server. |
| `tests/test_pi_harness_tools.py` | Create | Text-level checks for TypeScript tool registration and prompt guidance. |
| `edini/harness.py` | Create | Source-copy procedural harness helpers. |
| `python3.11libs/edini/harness.py` | Create | Houdini runtime-copy procedural harness helpers. Keep content synchronized with `edini/harness.py`. |
| `edini/node_utils.py` | Modify | Fix geometry stats, improve raw Python diagnostics, add safe capture wrapper, import harness helpers. |
| `python3.11libs/edini/node_utils.py` | Modify | Runtime mirror of `edini/node_utils.py`. |
| `edini/tool_executor.py` | Modify | Register harness tools in source copy. |
| `python3.11libs/edini/tool_executor.py` | Modify | Register harness tools in runtime copy. |
| `pi-extensions/edini-tools/tools/harness.ts` | Create | Pi tool schemas for diagnostics, sandbox execution, verification, commit/discard, and safe capture. |
| `pi-extensions/edini-tools/tools/script.ts` | Modify | Add prompt guidance that raw Python is unsafe for initial procedural modeling. |
| `pi-extensions/edini-tools/tools/scene.ts` | Modify | Point viewport capture guidance to safe capture and remove encouragement to improvise. |
| `pi-extensions/edini-tools/index.ts` | Modify | Register new `harnessTools`. |
| `skills/procedural-modeling/SKILL.md` | Modify | Require harness-first workflow and forbid deleting failed procedural nodes before diagnostics. |
| `wiki/pages/progress.md` | Modify | Add a short Phase B harness progress note after implementation passes. |

**Source/runtime sync rule:** Every Python code change under `edini/` that is loaded by Houdini must be mirrored under `python3.11libs/edini/` in the same task. Tests import from `python3.11libs` to catch runtime behavior first.

---

## Task 1: Extend Mock Houdini Fixtures

**Files:**
- Modify: `tests/mock_hou.py`
- Test: `tests/test_node_utils.py`
- Test: `tests/test_procedural_harness.py`

- [ ] **Step 1: Add mock geometry tests first**

Append these tests to `tests/test_node_utils.py` under `TestInspectGeometry`:

```python
    def test_geometry_counts_and_bounds(self):
        cr = create_node("box", name="geo_with_data")
        _register_created_node(cr)
        node = _mock_hou.node(cr["path"])
        node._geometry = _mock_hou.MockGeometry(
            point_count=8,
            prim_count=6,
            vertex_count=24,
            bounds=(-1.0, 1.0, 0.0, 4.0, -0.5, 0.5),
        )

        r = inspect_geometry(cr["path"])

        self.assertTrue(r["success"])
        self.assertEqual(r["point_count"], 8)
        self.assertEqual(r["prim_count"], 6)
        self.assertEqual(r["vertex_count"], 24)
        self.assertEqual(r["bounds"]["min"], [-1.0, 0.0, -0.5])
        self.assertEqual(r["bounds"]["max"], [1.0, 4.0, 0.5])
        self.assertEqual(r["bounds"]["size"], [2.0, 4.0, 1.0])
```

Create `tests/test_procedural_harness.py` with the shared import harness:

```python
"""Tests for Edini procedural harness helpers."""
import os
import sys
import unittest

from tests.mock_hou import create_mock_hou

_mock_hou = create_mock_hou()
sys.modules["hou"] = _mock_hou
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))

for _mod in list(sys.modules):
    if _mod.startswith("edini"):
        del sys.modules[_mod]

from edini import harness


class TestHarnessImports(unittest.TestCase):
    def test_harness_module_imports(self):
        self.assertTrue(hasattr(harness, "make_job_id"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify failures**

Run:

```powershell
python -m pytest tests/test_node_utils.py::TestInspectGeometry::test_geometry_counts_and_bounds tests/test_procedural_harness.py -q
```

Expected:

```text
FAILED tests/test_node_utils.py::TestInspectGeometry::test_geometry_counts_and_bounds
FAILED tests/test_procedural_harness.py::TestHarnessImports::test_harness_module_imports
```

The first failure should mention missing `MockGeometry` or `None` geometry. The second should mention `No module named 'edini.harness'`.

- [ ] **Step 3: Implement mock geometry support**

In `tests/mock_hou.py`, add these classes before `MockNode`:

```python
class MockAttrib:
    def __init__(self, name: str, data_type: str = "Float"):
        self._name = name
        self._data_type = data_type

    def name(self) -> str:
        return self._name

    def dataType(self) -> str:
        return self._data_type


class MockBoundingBox:
    def __init__(self, bounds: tuple[float, float, float, float, float, float]):
        self._bounds = bounds

    def minvec(self):
        return (self._bounds[0], self._bounds[2], self._bounds[4])

    def maxvec(self):
        return (self._bounds[1], self._bounds[3], self._bounds[5])


class MockGeometry:
    def __init__(
        self,
        point_count: int = 0,
        prim_count: int = 0,
        vertex_count: int = 0,
        bounds: tuple[float, float, float, float, float, float] | None = None,
    ):
        self._point_count = point_count
        self._prim_count = prim_count
        self._vertex_count = vertex_count
        self._bounds = bounds

    def intrinsicValue(self, name: str):
        if name == "pointcount":
            return self._point_count
        if name == "primitivecount":
            return self._prim_count
        if name == "vertexcount":
            return self._vertex_count
        if name == "bounds":
            return self._bounds
        raise KeyError(name)

    def boundingBox(self):
        if self._bounds is None:
            return None
        return MockBoundingBox(self._bounds)

    def pointAttribs(self):
        return [MockAttrib("P")]

    def primAttribs(self):
        return []

    def vertexAttribs(self):
        return []

    def globalAttribs(self):
        return []
```

Inside `MockNode.__init__`, add:

```python
        self._geometry = None
```

Replace `MockNode.geometry()` with:

```python
    def geometry(self):
        return self._geometry
```

Inside `MockHou`, expose the geometry class for tests:

```python
    MockGeometry = MockGeometry
```

- [ ] **Step 4: Run tests again**

Run:

```powershell
python -m pytest tests/test_node_utils.py::TestInspectGeometry::test_geometry_counts_and_bounds -q
```

Expected:

```text
FAILED ... 'BoundingBox' object has no attribute 'size'
```

This confirms the test now reaches the real `inspect_geometry` bug.

- [ ] **Step 5: Commit mock fixture change**

```powershell
git add tests/mock_hou.py tests/test_node_utils.py tests/test_procedural_harness.py
git commit -m "test(harness): add mock geometry fixtures"
```

---

## Task 2: Fix Geometry Stats and Raw Python Diagnostics

**Files:**
- Modify: `python3.11libs/edini/node_utils.py`
- Modify: `edini/node_utils.py`
- Test: `tests/test_node_utils.py`

- [ ] **Step 1: Add failing `run_python` diagnostics tests**

Append to `TestRunPython` in `tests/test_node_utils.py`:

```python
    def test_failure_includes_traceback_and_partial_output(self):
        r = run_python("print('before boom')\nraise RuntimeError('boom')")

        self.assertFalse(r["success"])
        self.assertIn("boom", r["error"])
        self.assertIn("before boom", r["output"])
        self.assertIn("RuntimeError", r["traceback"])
        self.assertIn("not sandboxed", r["warning"])

    def test_stderr_is_captured(self):
        r = run_python("import sys\nprint('warn text', file=sys.stderr)")

        self.assertTrue(r["success"])
        self.assertIn("warn text", r["stderr"])
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
python -m pytest tests/test_node_utils.py::TestInspectGeometry::test_geometry_counts_and_bounds tests/test_node_utils.py::TestRunPython::test_failure_includes_traceback_and_partial_output tests/test_node_utils.py::TestRunPython::test_stderr_is_captured -q
```

Expected: failures for missing bounds shape, missing traceback, and missing stderr.

- [ ] **Step 3: Add shared geometry helper to both node_utils copies**

In both `python3.11libs/edini/node_utils.py` and `edini/node_utils.py`, add this helper above `inspect_geometry`:

```python
def _vector_to_list(value) -> list[float]:
    try:
        return [float(value[0]), float(value[1]), float(value[2])]
    except Exception:
        return [float(value.x()), float(value.y()), float(value.z())]


def _geometry_bounds(geo) -> dict[str, list[float]] | None:
    try:
        raw = geo.intrinsicValue("bounds")
        if raw is not None and len(raw) == 6:
            mn = [float(raw[0]), float(raw[2]), float(raw[4])]
            mx = [float(raw[1]), float(raw[3]), float(raw[5])]
            return {
                "min": mn,
                "max": mx,
                "size": [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]],
            }
    except Exception:
        pass

    try:
        bbox = geo.boundingBox()
        if bbox is None:
            return None
        mn = _vector_to_list(bbox.minvec())
        mx = _vector_to_list(bbox.maxvec())
        return {
            "min": mn,
            "max": mx,
            "size": [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]],
        }
    except Exception:
        return None
```

Replace the `bounds` line in `inspect_geometry` with:

```python
            "bounds": _geometry_bounds(geo),
```

- [ ] **Step 4: Improve `run_python` in both node_utils copies**

Replace `run_python()` with:

```python
def run_python(code: str) -> dict[str, Any]:
    """Execute arbitrary Python code in Houdini context.

    This is intentionally raw execution. Procedural asset generation should
    prefer harness sandbox tools so failed cooks preserve diagnostics.
    """
    import io
    import sys
    import traceback

    namespace = {"hou": hou, "__builtins__": __builtins__}
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture

    try:
        exec(code, namespace)
        return {
            "success": True,
            "output": stdout_capture.getvalue() or "(no output)",
            "stderr": stderr_capture.getvalue(),
            "warning": "Raw houdini_run_python is not sandboxed; use harness tools for procedural assets.",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "output": stdout_capture.getvalue(),
            "stderr": stderr_capture.getvalue(),
            "traceback": traceback.format_exc(),
            "warning": "Raw houdini_run_python is not sandboxed; failed code may have changed the live scene.",
        }
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
python -m pytest tests/test_node_utils.py::TestInspectGeometry tests/test_node_utils.py::TestRunPython -q
```

Expected:

```text
8 passed
```

The exact count may be higher if additional tests were added earlier; all tests in those two classes must pass.

- [ ] **Step 6: Commit**

```powershell
git add python3.11libs/edini/node_utils.py edini/node_utils.py tests/test_node_utils.py
git commit -m "fix(houdini): return geometry bounds and python tracebacks"
```

---

## Task 3: Add Harness Diagnostics Module

**Files:**
- Create: `python3.11libs/edini/harness.py`
- Create: `edini/harness.py`
- Modify: `tests/test_procedural_harness.py`

- [ ] **Step 1: Add failing diagnostics tests**

Extend `tests/test_procedural_harness.py`:

```python
class TestCollectDiagnostics(unittest.TestCase):
    def test_missing_node(self):
        r = harness.collect_diagnostics("/obj/missing")

        self.assertFalse(r["success"])
        self.assertEqual(r["node_path"], "/obj/missing")
        self.assertIn("not found", r["error"].lower())

    def test_node_with_errors_warnings_and_geometry(self):
        obj = _mock_hou.node("/obj")
        node = obj.createNode("box", "diag_box")
        _mock_hou.add_node(node)
        node._errors = ["bad cook"]
        node._warnings = ["low confidence"]
        node._geometry = _mock_hou.MockGeometry(
            point_count=4,
            prim_count=1,
            vertex_count=4,
            bounds=(0.0, 1.0, 0.0, 2.0, 0.0, 3.0),
        )

        r = harness.collect_diagnostics(node.path(), include_geometry=True, include_parms=True)

        self.assertTrue(r["success"])
        self.assertEqual(r["node_path"], node.path())
        self.assertEqual(r["node_errors"], ["bad cook"])
        self.assertEqual(r["node_warnings"], ["low confidence"])
        self.assertEqual(r["geometry"]["point_count"], 4)
        self.assertEqual(r["geometry"]["bounds"]["size"], [1.0, 2.0, 3.0])
        self.assertIn("parameters", r)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_procedural_harness.py::TestCollectDiagnostics -q
```

Expected: failure because `collect_diagnostics` is not defined.

- [ ] **Step 3: Create harness module in both Python copies**

Create `python3.11libs/edini/harness.py` and copy the same content to `edini/harness.py`:

```python
"""Procedural harness helpers for safer Houdini generation."""
from __future__ import annotations

import datetime as _dt
import io
import json
import re
import sys
import traceback
from typing import Any

import hou


EXECUTION_MODE_LIVE = "live_sandbox"


def make_job_id(label: str = "job") -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", label).strip("_").lower() or "job"
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{safe}"


def _vector_to_list(value) -> list[float]:
    try:
        return [float(value[0]), float(value[1]), float(value[2])]
    except Exception:
        return [float(value.x()), float(value.y()), float(value.z())]


def geometry_bounds(geo) -> dict[str, list[float]] | None:
    try:
        raw = geo.intrinsicValue("bounds")
        if raw is not None and len(raw) == 6:
            mn = [float(raw[0]), float(raw[2]), float(raw[4])]
            mx = [float(raw[1]), float(raw[3]), float(raw[5])]
            return {"min": mn, "max": mx, "size": [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]]}
    except Exception:
        pass

    try:
        bbox = geo.boundingBox()
        if bbox is None:
            return None
        mn = _vector_to_list(bbox.minvec())
        mx = _vector_to_list(bbox.maxvec())
        return {"min": mn, "max": mx, "size": [mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]]}
    except Exception:
        return None


def geometry_stats(node_path: str) -> dict[str, Any] | None:
    node = hou.node(node_path)
    if node is None:
        return None
    geo = node.geometry()
    if geo is None:
        return None
    return {
        "point_count": geo.intrinsicValue("pointcount"),
        "prim_count": geo.intrinsicValue("primitivecount"),
        "vertex_count": geo.intrinsicValue("vertexcount"),
        "bounds": geometry_bounds(geo),
    }


def collect_diagnostics(
    node_path: str,
    include_geometry: bool = True,
    include_parms: bool = False,
) -> dict[str, Any]:
    node = hou.node(node_path)
    if node is None:
        return {
            "success": False,
            "node_path": node_path,
            "error": f"Node not found: {node_path}",
        }

    result: dict[str, Any] = {
        "success": True,
        "node_path": node_path,
        "node_type": node.type().name(),
        "node_errors": list(node.errors() or []),
        "node_warnings": list(node.warnings() or []),
    }

    if include_geometry:
        result["geometry"] = geometry_stats(node_path)

    if include_parms:
        result["parameters"] = [
            {"name": p.name(), "label": p.description(), "value": p.eval()}
            for p in node.parms()
        ]

    return result
```

- [ ] **Step 4: Run diagnostics tests**

Run:

```powershell
python -m pytest tests/test_procedural_harness.py::TestHarnessImports tests/test_procedural_harness.py::TestCollectDiagnostics -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

```powershell
git add python3.11libs/edini/harness.py edini/harness.py tests/test_procedural_harness.py
git commit -m "feat(harness): collect procedural diagnostics"
```

---

## Task 4: Add Live Sandbox Execution

**Files:**
- Modify: `python3.11libs/edini/harness.py`
- Modify: `edini/harness.py`
- Modify: `tests/mock_hou.py`
- Modify: `tests/test_procedural_harness.py`

- [ ] **Step 1: Add failing sandbox tests**

Append to `tests/test_procedural_harness.py`:

```python
class TestRunPythonSandbox(unittest.TestCase):
    def test_success_creates_sandbox_and_returns_job_shape(self):
        code = """
root = hou.node(sandbox_root_path)
child = root.createNode("null", "OUT")
hou.add_node(child)
result["output_node"] = child.path()
result["components"] = {"rungs": 8}
"""
        r = harness.run_python_sandbox(code, sandbox_name="ladder", commit_on_success=False)

        self.assertTrue(r["success"])
        self.assertEqual(r["execution_mode"], "live_sandbox")
        self.assertIn("job_id", r)
        self.assertTrue(r["root_path"].startswith("/obj/edini_sandbox_"))
        self.assertEqual(r["result"]["components"]["rungs"], 8)
        self.assertIsNotNone(_mock_hou.node(r["root_path"]))

    def test_failure_preserves_sandbox_and_returns_traceback(self):
        r = harness.run_python_sandbox(
            "print('before failure')\nraise RuntimeError('sandbox boom')",
            sandbox_name="fail_case",
            delete_on_failure=False,
        )

        self.assertFalse(r["success"])
        self.assertEqual(r["execution_mode"], "live_sandbox")
        self.assertIn("sandbox boom", r["error"])
        self.assertIn("before failure", r["output"])
        self.assertIn("RuntimeError", r["traceback"])
        self.assertIsNotNone(_mock_hou.node(r["root_path"]))
```

- [ ] **Step 2: Run failing sandbox tests**

Run:

```powershell
python -m pytest tests/test_procedural_harness.py::TestRunPythonSandbox -q
```

Expected: failure because `run_python_sandbox` is not defined.

- [ ] **Step 3: Update mock node creation to register child paths**

In `tests/mock_hou.py`, at the end of `MockNode.createNode`, before `return child`, add:

```python
        if MockNode._hou_ref is not None:
            MockNode._hou_ref._nodes[child.path()] = child
```

Existing `_register_created_node()` remains harmless and can stay.

- [ ] **Step 4: Implement sandbox execution in both harness copies**

Append to both `python3.11libs/edini/harness.py` and `edini/harness.py`:

```python
def _create_sandbox_root(sandbox_name: str) -> tuple[str, str]:
    job_id = make_job_id(sandbox_name)
    root_name = f"edini_sandbox_{job_id}"
    obj = hou.node("/obj")
    if obj is None:
        raise RuntimeError("No /obj context")
    root = obj.createNode("geo", root_name)
    return job_id, root.path()


def _destroy_node(path: str) -> None:
    node = hou.node(path)
    if node is not None:
        node.destroy()


def run_python_sandbox(
    code: str,
    sandbox_name: str = "procedural",
    commit_on_success: bool = False,
    delete_on_failure: bool = False,
) -> dict[str, Any]:
    job_id, root_path = _create_sandbox_root(sandbox_name)
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    result_payload: dict[str, Any] = {}
    namespace = {
        "hou": hou,
        "__builtins__": __builtins__,
        "sandbox_root_path": root_path,
        "result": result_payload,
    }

    sys.stdout = stdout_capture
    sys.stderr = stderr_capture
    try:
        exec(code, namespace)
        response = {
            "success": True,
            "job_id": job_id,
            "execution_mode": EXECUTION_MODE_LIVE,
            "root_path": root_path,
            "output": stdout_capture.getvalue() or "(no output)",
            "stderr": stderr_capture.getvalue(),
            "result": result_payload,
            "diagnostics": collect_diagnostics(
                result_payload.get("output_node", root_path),
                include_geometry=True,
                include_parms=False,
            ),
        }
        response["committed"] = bool(commit_on_success)
        return response
    except Exception as e:
        if delete_on_failure:
            _destroy_node(root_path)
        return {
            "success": False,
            "job_id": job_id,
            "execution_mode": EXECUTION_MODE_LIVE,
            "root_path": root_path,
            "error": str(e),
            "output": stdout_capture.getvalue(),
            "stderr": stderr_capture.getvalue(),
            "traceback": traceback.format_exc(),
            "diagnostics": collect_diagnostics(root_path, include_geometry=True, include_parms=False),
            "preserved": not delete_on_failure,
        }
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
```

- [ ] **Step 5: Run sandbox tests**

Run:

```powershell
python -m pytest tests/test_procedural_harness.py::TestRunPythonSandbox -q
```

Expected:

```text
2 passed
```

- [ ] **Step 6: Commit**

```powershell
git add python3.11libs/edini/harness.py edini/harness.py tests/mock_hou.py tests/test_procedural_harness.py
git commit -m "feat(harness): execute python in live sandboxes"
```

---

## Task 5: Add Verification, Commit, and Discard

**Files:**
- Modify: `python3.11libs/edini/harness.py`
- Modify: `edini/harness.py`
- Modify: `tests/mock_hou.py`
- Modify: `tests/test_procedural_harness.py`

- [ ] **Step 1: Add failing verification and lifecycle tests**

Append to `tests/test_procedural_harness.py`:

```python
class TestVerifyAsset(unittest.TestCase):
    def _make_geo_node(self, name="verify_geo", points=12, prims=6):
        obj = _mock_hou.node("/obj")
        node = obj.createNode("null", name)
        _mock_hou.add_node(node)
        node._geometry = _mock_hou.MockGeometry(
            point_count=points,
            prim_count=prims,
            vertex_count=24,
            bounds=(0.0, 1.0, 0.0, 2.0, 0.0, 0.5),
        )
        return node

    def test_verify_passes_non_empty_geometry(self):
        node = self._make_geo_node()

        r = harness.verify_asset(node.path(), {"min_points": 1, "min_prims": 1, "bounds_nonzero": True})

        self.assertTrue(r["success"])
        self.assertTrue(all(check["passed"] for check in r["checks"]))

    def test_verify_fails_min_points(self):
        node = self._make_geo_node(points=0, prims=0)

        r = harness.verify_asset(node.path(), {"min_points": 1, "min_prims": 1})

        self.assertFalse(r["success"])
        failed = [check["name"] for check in r["checks"] if not check["passed"]]
        self.assertIn("min_points", failed)
        self.assertIn("min_prims", failed)


class TestSandboxLifecycle(unittest.TestCase):
    def test_discard_sandbox_deletes_root(self):
        r = harness.run_python_sandbox("result['output_node'] = sandbox_root_path", sandbox_name="discard_me")
        root_path = r["root_path"]

        d = harness.discard_sandbox(root_path)

        self.assertTrue(d["success"])
        self.assertIsNone(_mock_hou.node(root_path))

    def test_commit_sandbox_renames_root(self):
        r = harness.run_python_sandbox("result['output_node'] = sandbox_root_path", sandbox_name="commit_me")

        c = harness.commit_sandbox(r["root_path"], "committed_asset", replace_existing=False)

        self.assertTrue(c["success"])
        self.assertEqual(c["final_path"], "/obj/committed_asset")
        self.assertIsNotNone(_mock_hou.node("/obj/committed_asset"))
```

- [ ] **Step 2: Run failing lifecycle tests**

Run:

```powershell
python -m pytest tests/test_procedural_harness.py::TestVerifyAsset tests/test_procedural_harness.py::TestSandboxLifecycle -q
```

Expected: failures because `verify_asset`, `discard_sandbox`, and `commit_sandbox` are not defined.

- [ ] **Step 3: Add `setName` support to mock nodes**

In `tests/mock_hou.py`, add this method to `MockNode`:

```python
    def setName(self, name: str, unique_name: bool = False) -> None:
        old_path = self._path
        self._name = name
        parent_path = self._parent.path() if self._parent else ""
        self._path = f"{parent_path}/{name}" if parent_path and parent_path != "/" else f"/{name}"
        if MockNode._hou_ref is not None:
            MockNode._hou_ref._nodes.pop(old_path, None)
            MockNode._hou_ref._nodes[self._path] = self
```

- [ ] **Step 4: Implement verification and lifecycle in both harness copies**

Append to both harness files:

```python
def _check(name: str, passed: bool, actual: Any, expected: Any = None) -> dict[str, Any]:
    item = {"name": name, "passed": bool(passed), "actual": actual}
    if expected is not None:
        item["expected"] = expected
    return item


def verify_asset(node_path: str, expected: dict[str, Any] | None = None) -> dict[str, Any]:
    expected = expected or {}
    stats = geometry_stats(node_path)
    checks: list[dict[str, Any]] = []

    if stats is None:
        checks.append(_check("geometry_exists", False, None, True))
        return {"success": False, "node_path": node_path, "geometry": None, "checks": checks}

    if "min_points" in expected:
        checks.append(_check("min_points", stats["point_count"] >= expected["min_points"], stats["point_count"], expected["min_points"]))
    if "min_prims" in expected:
        checks.append(_check("min_prims", stats["prim_count"] >= expected["min_prims"], stats["prim_count"], expected["min_prims"]))
    if expected.get("bounds_nonzero"):
        size = (stats.get("bounds") or {}).get("size")
        checks.append(_check("bounds_nonzero", bool(size and any(abs(v) > 1e-6 for v in size)), size, True))

    diag = collect_diagnostics(node_path, include_geometry=False, include_parms=False)
    node_errors = diag.get("node_errors", []) if diag.get("success") else [diag.get("error")]
    checks.append(_check("node_errors", len(node_errors) == 0, node_errors, []))

    return {
        "success": all(c["passed"] for c in checks),
        "node_path": node_path,
        "geometry": stats,
        "checks": checks,
    }


def discard_sandbox(sandbox_root_path: str) -> dict[str, Any]:
    node = hou.node(sandbox_root_path)
    if node is None:
        return {"success": False, "error": f"Sandbox not found: {sandbox_root_path}"}
    node.destroy()
    return {"success": True, "sandbox_root_path": sandbox_root_path, "discarded": True}


def commit_sandbox(
    sandbox_root_path: str,
    final_name: str,
    replace_existing: bool = False,
) -> dict[str, Any]:
    node = hou.node(sandbox_root_path)
    if node is None:
        return {"success": False, "error": f"Sandbox not found: {sandbox_root_path}"}
    final_path = f"/obj/{final_name}"
    existing = hou.node(final_path)
    if existing is not None and not replace_existing:
        return {"success": False, "error": f"Target already exists: {final_path}", "final_path": final_path}
    if existing is not None:
        existing.destroy()
    node.setName(final_name, unique_name=False)
    node.setDisplayFlag(True)
    return {
        "success": True,
        "sandbox_root_path": sandbox_root_path,
        "final_path": node.path(),
        "committed": True,
    }
```

- [ ] **Step 5: Run lifecycle tests**

Run:

```powershell
python -m pytest tests/test_procedural_harness.py::TestVerifyAsset tests/test_procedural_harness.py::TestSandboxLifecycle -q
```

Expected:

```text
4 passed
```

- [ ] **Step 6: Commit**

```powershell
git add python3.11libs/edini/harness.py edini/harness.py tests/mock_hou.py tests/test_procedural_harness.py
git commit -m "feat(harness): verify and manage sandboxes"
```

---

## Task 6: Register Harness Tool Handlers

**Files:**
- Modify: `python3.11libs/edini/tool_executor.py`
- Modify: `edini/tool_executor.py`
- Create: `tests/test_tool_executor_harness.py`

- [ ] **Step 1: Add dispatcher tests**

Create `tests/test_tool_executor_harness.py`:

```python
"""Tests for procedural harness tool executor registrations."""
import os
import sys
import unittest

from tests.mock_hou import create_mock_hou

_mock_hou = create_mock_hou()
sys.modules["hou"] = _mock_hou
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))

for _mod in list(sys.modules):
    if _mod.startswith("edini"):
        del sys.modules[_mod]

from edini.tool_executor import TOOL_HANDLERS


class TestHarnessToolHandlers(unittest.TestCase):
    def test_harness_handlers_registered(self):
        expected = {
            "houdini_collect_diagnostics",
            "houdini_run_python_sandbox",
            "houdini_verify_asset",
            "houdini_commit_sandbox",
            "houdini_discard_sandbox",
            "houdini_capture_viewport_safe",
        }
        self.assertTrue(expected.issubset(set(TOOL_HANDLERS)))

    def test_collect_diagnostics_dispatches(self):
        r = TOOL_HANDLERS["houdini_collect_diagnostics"](node_path="/obj")

        self.assertTrue(r["success"])
        self.assertEqual(r["node_path"], "/obj")

    def test_verify_asset_dispatches_expected(self):
        r = TOOL_HANDLERS["houdini_verify_asset"](
            node_path="/obj",
            expected={"min_points": 1},
        )

        self.assertFalse(r["success"])
        self.assertEqual(r["node_path"], "/obj")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run dispatcher tests to verify failure**

Run:

```powershell
python -m pytest tests/test_tool_executor_harness.py -q
```

Expected: failure because handlers are missing.

- [ ] **Step 3: Import harness functions in both tool_executor copies**

In both `python3.11libs/edini/tool_executor.py` and `edini/tool_executor.py`, add:

```python
from edini.harness import (
    collect_diagnostics, run_python_sandbox, verify_asset,
    commit_sandbox, discard_sandbox,
)
```

- [ ] **Step 4: Register handler lambdas in both tool_executor copies**

Add entries to `TOOL_HANDLERS`:

```python
    "houdini_collect_diagnostics": lambda **kw: collect_diagnostics(
        kw["node_path"],
        include_geometry=kw.get("include_geometry", True),
        include_parms=kw.get("include_parms", False),
    ),
    "houdini_run_python_sandbox": lambda **kw: run_python_sandbox(
        kw["code"],
        sandbox_name=kw.get("sandbox_name", "procedural"),
        commit_on_success=kw.get("commit_on_success", False),
        delete_on_failure=kw.get("delete_on_failure", False),
    ),
    "houdini_verify_asset": lambda **kw: verify_asset(
        kw["node_path"],
        expected=kw.get("expected", {}),
    ),
    "houdini_commit_sandbox": lambda **kw: commit_sandbox(
        kw["sandbox_root_path"],
        kw["final_name"],
        replace_existing=kw.get("replace_existing", False),
    ),
    "houdini_discard_sandbox": lambda **kw: discard_sandbox(
        kw["sandbox_root_path"],
    ),
```

Leave `houdini_capture_viewport_safe` out until Task 7 implements the function. The failing registration test from Step 1 will still fail for this one entry until Task 7. This task should temporarily change the first test to expect only the five implemented handlers, then Task 7 expands it to six.

Use this expected set for this task:

```python
        expected = {
            "houdini_collect_diagnostics",
            "houdini_run_python_sandbox",
            "houdini_verify_asset",
            "houdini_commit_sandbox",
            "houdini_discard_sandbox",
        }
```

- [ ] **Step 5: Run dispatcher tests**

Run:

```powershell
python -m pytest tests/test_tool_executor_harness.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 6: Commit**

```powershell
git add python3.11libs/edini/tool_executor.py edini/tool_executor.py tests/test_tool_executor_harness.py
git commit -m "feat(harness): register procedural tool handlers"
```

---

## Task 7: Add Safe Viewport Capture

**Files:**
- Modify: `python3.11libs/edini/node_utils.py`
- Modify: `edini/node_utils.py`
- Modify: `python3.11libs/edini/tool_executor.py`
- Modify: `edini/tool_executor.py`
- Modify: `tests/test_tool_executor_harness.py`
- Modify: `tests/test_capture_tools.py`

- [ ] **Step 1: Add safe capture contract tests**

In `tests/test_capture_tools.py`, add safe capture to `TOOL_HANDLERS_SIGNATURES`:

```python
    "houdini_capture_viewport_safe": {
        "required": ["filepath"],
        "optional": ["frame", "home_viewport"],
    },
```

Append tests:

```python
    def test_capture_viewport_safe_has_filepath_and_options(self):
        sig = TOOL_HANDLERS_SIGNATURES["houdini_capture_viewport_safe"]
        self.assertIn("filepath", sig["required"])
        self.assertIn("frame", sig["optional"])
        self.assertIn("home_viewport", sig["optional"])
```

In `tests/test_tool_executor_harness.py`, restore the six-handler expected set:

```python
        expected = {
            "houdini_collect_diagnostics",
            "houdini_run_python_sandbox",
            "houdini_verify_asset",
            "houdini_commit_sandbox",
            "houdini_discard_sandbox",
            "houdini_capture_viewport_safe",
        }
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
python -m pytest tests/test_capture_tools.py::TestToolSignatureMatches::test_capture_viewport_safe_has_filepath_and_options tests/test_tool_executor_harness.py::TestHarnessToolHandlers::test_harness_handlers_registered -q
```

Expected: failure because safe capture is not registered.

- [ ] **Step 3: Implement safe capture in both node_utils copies**

Add this function below `capture_viewport` in both `python3.11libs/edini/node_utils.py` and `edini/node_utils.py`:

```python
def capture_viewport_safe(
    filepath: str,
    frame: int = 1,
    home_viewport: bool = True,
) -> dict[str, Any]:
    """Capture viewport through Houdini flipbook without Qt widget probing."""
    try:
        import os

        desktop = hou.ui.curDesktop()
        viewer = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
        if viewer is None:
            return {"success": False, "error": "No Scene Viewer pane found"}

        viewport = viewer.curViewport()
        if home_viewport and hasattr(viewport, "homeAll"):
            viewport.homeAll()

        os.makedirs(os.path.dirname(os.path.abspath(filepath)) or ".", exist_ok=True)
        settings = viewer.flipbookSettings()
        settings.output(filepath)
        settings.outputToMPlay(False)
        settings.frameRange((frame, frame))
        viewer.flipbook(viewport, settings)

        if os.path.exists(filepath):
            return {
                "success": True,
                "path": filepath,
                "size_kb": round(os.path.getsize(filepath) / 1024, 1),
                "method": "scene_viewer_flipbook",
            }
        return {
            "success": False,
            "error": f"Flipbook completed but file was not created: {filepath}",
            "method": "scene_viewer_flipbook",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "method": "scene_viewer_flipbook",
            "note": "Safe capture does not fall back to direct Qt widget probing.",
        }
```

Change existing `capture_viewport(filepath)` to call the safe function:

```python
def capture_viewport(filepath: str) -> dict[str, Any]:
    """Backward-compatible viewport capture wrapper."""
    return capture_viewport_safe(filepath)
```

- [ ] **Step 4: Register safe capture handler**

In both `tool_executor.py` copies, import `capture_viewport_safe` from `edini.node_utils` and add:

```python
    "houdini_capture_viewport_safe": lambda **kw: capture_viewport_safe(
        kw["filepath"],
        frame=kw.get("frame", 1),
        home_viewport=kw.get("home_viewport", True),
    ),
```

- [ ] **Step 5: Run safe capture contract tests**

Run:

```powershell
python -m pytest tests/test_capture_tools.py tests/test_tool_executor_harness.py -q
```

Expected: all tests in these files pass.

- [ ] **Step 6: Commit**

```powershell
git add python3.11libs/edini/node_utils.py edini/node_utils.py python3.11libs/edini/tool_executor.py edini/tool_executor.py tests/test_capture_tools.py tests/test_tool_executor_harness.py
git commit -m "fix(houdini): add safe viewport capture"
```

---

## Task 8: Add Pi Harness Tool Schemas

**Files:**
- Create: `pi-extensions/edini-tools/tools/harness.ts`
- Modify: `pi-extensions/edini-tools/index.ts`
- Modify: `pi-extensions/edini-tools/tools/script.ts`
- Modify: `pi-extensions/edini-tools/tools/scene.ts`
- Create: `tests/test_pi_harness_tools.py`

- [ ] **Step 1: Add text-level Pi tool tests**

Create `tests/test_pi_harness_tools.py`:

```python
"""Text-level tests for Pi harness tool registration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_harness_tools_file_contains_all_tool_names():
    text = read("pi-extensions/edini-tools/tools/harness.ts")
    for name in [
        "houdini_collect_diagnostics",
        "houdini_run_python_sandbox",
        "houdini_verify_asset",
        "houdini_commit_sandbox",
        "houdini_discard_sandbox",
        "houdini_capture_viewport_safe",
    ]:
        assert name in text


def test_index_registers_harness_tools():
    text = read("pi-extensions/edini-tools/index.ts")
    assert 'import { harnessTools } from "./tools/harness";' in text
    assert "...harnessTools" in text


def test_raw_python_guidance_mentions_sandbox():
    text = read("pi-extensions/edini-tools/tools/script.ts")
    assert "not sandboxed" in text
    assert "houdini_run_python_sandbox" in text


def test_viewport_guidance_mentions_safe_capture():
    text = read("pi-extensions/edini-tools/tools/scene.ts")
    assert "houdini_capture_viewport_safe" in text
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_pi_harness_tools.py -q
```

Expected: failure because `harness.ts` does not exist and guidance is not updated.

- [ ] **Step 3: Create `harness.ts`**

Create `pi-extensions/edini-tools/tools/harness.ts`:

```typescript
// pi-extensions/edini-tools/tools/harness.ts
// Safer procedural modeling harness tool definitions.

import { Type } from "typebox";

const TOOL_PORT = parseInt(process.env.EDINI_TOOL_PORT || "9876", 10);
const TOOL_URL = `http://127.0.0.1:${TOOL_PORT}/execute`;

async function forwardTool(toolName: string, params: Record<string, unknown>) {
  const response = await fetch(TOOL_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool: toolName, params }),
  });
  const result = await response.json();
  return {
    content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
    details: result,
  };
}

export const houdiniCollectDiagnostics = {
  name: "houdini_collect_diagnostics",
  label: "Collect Houdini Diagnostics",
  description:
    "Collect node diagnostics, errors, warnings, parameters, and optional geometry stats without changing the scene.",
  promptSnippet: "Collect diagnostics for a Houdini node",
  promptGuidelines: [
    "Use this after any failed cook, blank output, or unexpected procedural result before changing strategy or deleting nodes.",
  ],
  parameters: Type.Object({
    node_path: Type.String({ description: "Node path to inspect" }),
    include_geometry: Type.Optional(Type.Boolean({ description: "Include geometry stats, default true" })),
    include_parms: Type.Optional(Type.Boolean({ description: "Include parameter values, default false" })),
  }),
  async execute(_toolCallId: string, params: { node_path: string; include_geometry?: boolean; include_parms?: boolean }) {
    return forwardTool("houdini_collect_diagnostics", params);
  },
};

export const houdiniRunPythonSandbox = {
  name: "houdini_run_python_sandbox",
  label: "Run Python In Procedural Sandbox",
  description:
    "Execute Houdini Python inside /obj/edini_sandbox_<job_id>. Use this instead of raw houdini_run_python for initial procedural asset generation.",
  promptSnippet: "Run Houdini Python in a procedural sandbox",
  promptGuidelines: [
    "For procedural modeling, create assets in a sandbox first, verify them, then commit the sandbox.",
    "Do not delete a failed sandbox before calling houdini_collect_diagnostics.",
  ],
  parameters: Type.Object({
    code: Type.String({ description: "Python code. The namespace includes hou, sandbox_root_path, and result." }),
    sandbox_name: Type.Optional(Type.String({ description: "Human-readable sandbox label" })),
    commit_on_success: Type.Optional(Type.Boolean({ description: "Reserved for explicit commit behavior, default false" })),
    delete_on_failure: Type.Optional(Type.Boolean({ description: "Delete failed sandbox, default false" })),
  }),
  async execute(_toolCallId: string, params: { code: string; sandbox_name?: string; commit_on_success?: boolean; delete_on_failure?: boolean }) {
    return forwardTool("houdini_run_python_sandbox", params);
  },
};

export const houdiniVerifyAsset = {
  name: "houdini_verify_asset",
  label: "Verify Procedural Asset",
  description: "Verify a generated Houdini asset using geometry counts, bounds, and node errors.",
  promptSnippet: "Verify procedural asset structure",
  parameters: Type.Object({
    node_path: Type.String({ description: "Node path to verify" }),
    expected: Type.Optional(Type.Record(Type.String(), Type.Unknown())),
  }),
  async execute(_toolCallId: string, params: { node_path: string; expected?: Record<string, unknown> }) {
    return forwardTool("houdini_verify_asset", params);
  },
};

export const houdiniCommitSandbox = {
  name: "houdini_commit_sandbox",
  label: "Commit Procedural Sandbox",
  description: "Rename a verified sandbox root into its final /obj asset name.",
  promptSnippet: "Commit verified procedural sandbox",
  parameters: Type.Object({
    sandbox_root_path: Type.String({ description: "Sandbox root path" }),
    final_name: Type.String({ description: "Final /obj node name" }),
    replace_existing: Type.Optional(Type.Boolean({ description: "Replace existing node with same name, default false" })),
  }),
  async execute(_toolCallId: string, params: { sandbox_root_path: string; final_name: string; replace_existing?: boolean }) {
    return forwardTool("houdini_commit_sandbox", params);
  },
};

export const houdiniDiscardSandbox = {
  name: "houdini_discard_sandbox",
  label: "Discard Procedural Sandbox",
  description: "Delete a procedural sandbox root after the user or agent no longer needs it.",
  promptSnippet: "Discard procedural sandbox",
  parameters: Type.Object({
    sandbox_root_path: Type.String({ description: "Sandbox root path to delete" }),
  }),
  async execute(_toolCallId: string, params: { sandbox_root_path: string }) {
    return forwardTool("houdini_discard_sandbox", params);
  },
};

export const houdiniCaptureViewportSafe = {
  name: "houdini_capture_viewport_safe",
  label: "Safely Capture Houdini Viewport",
  description:
    "Capture the Houdini viewport through the supported flipbook path. This tool does not probe Qt widgets if capture fails.",
  promptSnippet: "Safely capture Houdini viewport screenshot",
  promptGuidelines: [
    "Use this for visual verification. If it fails, report the failure and diagnostics instead of trying Qt widget or viewport internals through Python.",
  ],
  parameters: Type.Object({
    filepath: Type.String({ description: "Output image file path" }),
    frame: Type.Optional(Type.Number({ description: "Frame to capture, default 1" })),
    home_viewport: Type.Optional(Type.Boolean({ description: "Home viewport before capture, default true" })),
  }),
  async execute(_toolCallId: string, params: { filepath: string; frame?: number; home_viewport?: boolean }) {
    return forwardTool("houdini_capture_viewport_safe", params);
  },
};

export const harnessTools = [
  houdiniCollectDiagnostics,
  houdiniRunPythonSandbox,
  houdiniVerifyAsset,
  houdiniCommitSandbox,
  houdiniDiscardSandbox,
  houdiniCaptureViewportSafe,
];
```

- [ ] **Step 4: Register tools in `index.ts`**

Add:

```typescript
import { harnessTools } from "./tools/harness";
```

Update `allTools`:

```typescript
const allTools = [
  ...sceneTools,
  ...queryTools,
  ...scriptTools,
  ...harnessTools,
  ediniGetEvalStats,
  ediniSearchKnowledge,
];
```

- [ ] **Step 5: Update raw Python and viewport guidance**

In `pi-extensions/edini-tools/tools/script.ts`, change `houdiniRunPython.description` to include:

```typescript
"Execute arbitrary Python code in the Houdini environment. This is not sandboxed; for procedural asset generation use houdini_run_python_sandbox first."
```

Update `promptGuidelines`:

```typescript
promptGuidelines: [
  "Use houdini_run_python only when dedicated tools and houdini_run_python_sandbox cannot accomplish the task.",
  "For procedural modeling, prefer houdini_run_python_sandbox so failed cooks preserve diagnostics and do not overwrite live scene nodes.",
],
```

In `pi-extensions/edini-tools/tools/scene.ts`, update `houdiniCaptureViewport.promptGuidelines`:

```typescript
promptGuidelines: [
  "Prefer houdini_capture_viewport_safe for visual verification. Use this backward-compatible tool only when safe capture is unavailable.",
],
```

- [ ] **Step 6: Run Pi text tests**

Run:

```powershell
python -m pytest tests/test_pi_harness_tools.py -q
```

Expected:

```text
4 passed
```

Also run syntax read check:

```powershell
node -e "const fs=require('fs'); for (const f of ['pi-extensions/edini-tools/tools/harness.ts','pi-extensions/edini-tools/index.ts']) { fs.readFileSync(f,'utf8'); } console.log('TS files readable')"
```

Expected:

```text
TS files readable
```

- [ ] **Step 7: Commit**

```powershell
git add pi-extensions/edini-tools/tools/harness.ts pi-extensions/edini-tools/index.ts pi-extensions/edini-tools/tools/script.ts pi-extensions/edini-tools/tools/scene.ts tests/test_pi_harness_tools.py
git commit -m "feat(pi): expose procedural harness tools"
```

---

## Task 9: Update Procedural Modeling Skill

**Files:**
- Modify: `skills/procedural-modeling/SKILL.md`
- Modify: `skills/procedural-modeling/preview.html` if this generated preview is meant to stay in sync
- Test: `tests/test_pi_harness_tools.py`

- [ ] **Step 1: Add skill guidance test**

Append to `tests/test_pi_harness_tools.py`:

```python
def test_procedural_modeling_skill_requires_harness():
    text = read("skills/procedural-modeling/SKILL.md")
    assert "houdini_run_python_sandbox" in text
    assert "houdini_collect_diagnostics" in text
    assert "houdini_verify_asset" in text
    assert "Do not delete a failed procedural node" in text
    assert "Do not explore Qt widgets" in text
```

- [ ] **Step 2: Run failing skill test**

Run:

```powershell
python -m pytest tests/test_pi_harness_tools.py::test_procedural_modeling_skill_requires_harness -q
```

Expected: failure because the skill has not been updated.

- [ ] **Step 3: Update skill workflow**

In `skills/procedural-modeling/SKILL.md`, replace the `## Workflow` section with:

```markdown
## Workflow

1. **Create a recipe first** — State asset type, backend, parameters, and expected structural checks.
2. **Choose backend** — `python_sop` for algorithmic mesh generation, `vex_wrangle` for per-element math, `node_network` for native SOP composition.
3. **Use the harness first** — For procedural assets, use `houdini_run_python_sandbox` or future harness tools instead of raw `houdini_run_python`.
4. **Preserve failed nodes** — Do not delete a failed procedural node before calling `houdini_collect_diagnostics`.
5. **Diagnose before switching strategy** — For Python SOP cook errors, inspect node errors, warnings, parameters, traceback, and generated code before falling back to another backend.
6. **Verify structurally** — Use `houdini_verify_asset` and/or `houdini_inspect_geo` to check point counts, primitive counts, bounds, and expected components.
7. **Capture safely** — Use `houdini_capture_viewport_safe` for visual verification. Do not explore Qt widgets or unsupported viewport internals during normal modeling.
8. **Commit only after verification** — Use `houdini_commit_sandbox` only after structural checks pass. Use `houdini_discard_sandbox` only when the sandbox is no longer useful.
```

Add a short section after Python SOP Guidelines:

```markdown
## Harness Rules

- Do not use raw `houdini_run_python` for initial procedural asset generation when `houdini_run_python_sandbox` is available.
- Do not delete a failed procedural node before `houdini_collect_diagnostics`.
- Do not explore Qt widgets, main windows, viewport internals, or unsupported HOM APIs to capture images. Use `houdini_capture_viewport_safe` and report clean failure if capture is unavailable.
- If a generated Python SOP fails to cook, diagnose that SOP first. Switching to manual node-network generation is allowed only after diagnostics identify why the code-first path is unsuitable.
```

- [ ] **Step 4: Update preview if it is maintained manually**

If `skills/procedural-modeling/preview.html` is a generated artifact, regenerate it using the existing local preview workflow. If there is no generator, update the relevant visible workflow text by hand so the preview does not contradict `SKILL.md`.

Run:

```powershell
Select-String -LiteralPath skills/procedural-modeling/preview.html -Pattern "houdini_run_python_sandbox","Do not explore Qt widgets"
```

Expected: both strings are present if `preview.html` remains tracked.

- [ ] **Step 5: Run skill test**

Run:

```powershell
python -m pytest tests/test_pi_harness_tools.py::test_procedural_modeling_skill_requires_harness -q
```

Expected:

```text
1 passed
```

- [ ] **Step 6: Commit**

```powershell
git add skills/procedural-modeling/SKILL.md skills/procedural-modeling/preview.html tests/test_pi_harness_tools.py
git commit -m "docs(skill): require procedural harness workflow"
```

If `preview.html` is not updated because it is intentionally ignored or regenerated elsewhere, omit it from `git add` and mention that in the task completion note.

---

## Task 10: Add Ladder Regression Fixture

**Files:**
- Modify: `tests/test_procedural_harness.py`
- Create: `docs/harness_ladder_regression.md`

- [ ] **Step 1: Add regression test using sandbox code**

Append to `tests/test_procedural_harness.py`:

```python
class TestLadderRegression(unittest.TestCase):
    def test_ladder_sandbox_preserves_components_and_verifies(self):
        code = """
root = hou.node(sandbox_root_path)
out = root.createNode("null", "OUT")
hou.add_node(out)
out._geometry = hou.MockGeometry(
    point_count=240,
    prim_count=160,
    vertex_count=640,
    bounds=(-0.54, 0.54, 0.0, 4.0, -0.04, 0.04),
)
result["output_node"] = out.path()
result["asset_type"] = "ladder"
result["components"] = {"rails": 2, "rungs": 8}
"""

        run = harness.run_python_sandbox(code, sandbox_name="ladder")
        verify = harness.verify_asset(
            run["result"]["output_node"],
            {"min_points": 1, "min_prims": 1, "bounds_nonzero": True},
        )

        self.assertTrue(run["success"])
        self.assertEqual(run["result"]["components"], {"rails": 2, "rungs": 8})
        self.assertTrue(verify["success"])
        self.assertEqual(verify["geometry"]["point_count"], 240)
```

- [ ] **Step 2: Run regression test**

Run:

```powershell
python -m pytest tests/test_procedural_harness.py::TestLadderRegression -q
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Create human-readable regression note**

Create `docs/harness_ladder_regression.md`:

```markdown
# Procedural Harness Ladder Regression

This note captures the 2026-06-11 ladder incident as a regression target for Edini's procedural harness.

Expected behavior after Phase B:

- The agent creates a ladder in a live sandbox first.
- Failed Python SOP or node-network attempts are preserved until diagnostics are collected.
- Diagnostics include node path, node errors, node warnings, traceback when available, geometry stats, and bounds.
- Verification checks non-empty geometry and non-zero bounds before commit.
- Visual capture uses `houdini_capture_viewport_safe`.
- The agent does not explore Qt widgets or unsupported viewport internals when capture fails.

The unit regression in `tests/test_procedural_harness.py::TestLadderRegression` verifies the structural part of this workflow without requiring Houdini.
```

- [ ] **Step 4: Commit**

```powershell
git add tests/test_procedural_harness.py docs/harness_ladder_regression.md
git commit -m "test(harness): capture ladder regression"
```

---

## Task 11: Update Progress Docs and Run Final Verification

**Files:**
- Modify: `wiki/pages/progress.md`
- Optional Modify: `wiki/pages/tools.md`
- Verify: all files touched in Tasks 1-10

- [ ] **Step 1: Update progress page**

Add a short entry to `wiki/pages/progress.md` near the latest progress section:

```markdown
### Procedural Harness Phase B

- Added live sandbox workflow for procedural generation.
- Added diagnostics before retry/delete, structural asset verification, sandbox commit/discard, and safe viewport capture.
- Updated procedural-modeling skill so agents use harness tools before raw Houdini Python.
- Preserved Phase C path through `job_id`, `execution_mode`, diagnostics bundles, and artifact-shaped result fields.
```

If `wiki/pages/tools.md` has a tool list that users rely on, add entries for:

- `houdini_collect_diagnostics`
- `houdini_run_python_sandbox`
- `houdini_verify_asset`
- `houdini_commit_sandbox`
- `houdini_discard_sandbox`
- `houdini_capture_viewport_safe`

- [ ] **Step 2: Run focused test suite**

Run:

```powershell
python -m pytest tests/test_node_utils.py tests/test_procedural_harness.py tests/test_tool_executor_harness.py tests/test_capture_tools.py tests/test_pi_harness_tools.py -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run broader ordinary test suite**

Run:

```powershell
python -m pytest tests -q
```

Expected: ordinary `tests/` pass. If failures occur in unrelated pre-existing dirty files, capture exact failing test names and do not rewrite unrelated modules as part of this task.

- [ ] **Step 4: Python compile check**

Run:

```powershell
python -m py_compile `
  python3.11libs\edini\harness.py `
  edini\harness.py `
  python3.11libs\edini\node_utils.py `
  edini\node_utils.py `
  python3.11libs\edini\tool_executor.py `
  edini\tool_executor.py
```

Expected: command exits with code 0 and no output.

- [ ] **Step 5: Pi TypeScript text/syntax check**

Run:

```powershell
node -e "const fs=require('fs'); ['pi-extensions/edini-tools/tools/harness.ts','pi-extensions/edini-tools/index.ts','pi-extensions/edini-tools/tools/script.ts','pi-extensions/edini-tools/tools/scene.ts'].forEach(f=>fs.readFileSync(f,'utf8')); console.log('Pi harness tool files readable')"
```

Expected:

```text
Pi harness tool files readable
```

- [ ] **Step 6: Commit docs and verification notes**

```powershell
git add wiki/pages/progress.md wiki/pages/tools.md
git commit -m "docs: record procedural harness phase b"
```

If `wiki/pages/tools.md` was not changed, omit it from `git add`.

---

## Phase C Prep Checklist

Phase B implementation should leave these hooks intact for Phase C:

- `run_python_sandbox` returns `job_id`.
- Harness results include `execution_mode: "live_sandbox"`.
- Diagnostics are JSON-serializable.
- Verification result shape does not depend on live-only objects.
- Pi tool names describe workflow concepts, not the live-process implementation detail.
- No tool requires the agent to know whether execution happened in a live sandbox or an external worker.

Phase C should begin with a separate design and plan when two or more trigger conditions from the spec are met. The first Phase C plan should create `edini/harness/job_models.py`, `edini/harness/job_queue.py`, `edini/harness/worker_runner.py`, and `scripts/edini_harness_worker.py`, then add an `execution_mode: "external_worker"` path behind the same Pi workflow.

---

## Self-Review

Spec coverage:

- Existing tool bugs: Tasks 2 and 7.
- Diagnostics before retry/delete: Tasks 3, 6, 8, 9.
- Sandbox execution: Task 4.
- Verification: Task 5.
- Commit/discard lifecycle: Task 5.
- Pi tool surface: Task 8.
- Skill update: Task 9.
- Ladder regression: Task 10.
- Phase C evolution path: Phase C Prep Checklist and C-shaped result requirements in Tasks 4 and 5.

Deferred marker scan:

- This plan contains no deferred-work markers or incomplete implementation notes.
- Each test task includes concrete code and a command with expected outcome.

Type consistency:

- Python helper names: `collect_diagnostics`, `run_python_sandbox`, `verify_asset`, `commit_sandbox`, `discard_sandbox`, `capture_viewport_safe`.
- Pi tool names: `houdini_collect_diagnostics`, `houdini_run_python_sandbox`, `houdini_verify_asset`, `houdini_commit_sandbox`, `houdini_discard_sandbox`, `houdini_capture_viewport_safe`.
- Handler names match the Pi tool names and map to Python helper names.
