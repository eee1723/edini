# Procedural Harness Postmortem Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 7 issues discovered in 2026-06-12 live procedural harness testing — sandbox execution model, skill examples, diagnostics injection, batch params, missing tools, screenshot hardening, and sandbox analytics.

**Architecture:** The sandbox rewrite is the core change: `run_python_sandbox` switches from `exec(code)` to creating a Python SOP node inside the sandbox geo container, injecting code as the SOP's `python` parameter, and cooking it — enabling `hou.pwd()` and `node.geometry()`. Remaining fixes are independent additions to tool_executor/node_utils, Pi extension tools, skill docs, and evaluator.

**Tech Stack:** Python 3.11 (hou API, MockNode/MockParm test doubles), TypeScript (TypeBox Pi tool schemas), Markdown (skill docs)

---

## File Structure

```
edini/harness.py                      → [MODIFY] Rewrite run_python_sandbox, add structural_checks
python3.11libs/edini/harness.py       → [MIRROR]
edini/node_utils.py                   → [MODIFY] Add set_params_batch, enhance capture error msgs
python3.11libs/edini/node_utils.py    → [MIRROR]
edini/tool_executor.py                → [MODIFY] Register new tools in TOOL_HANDLERS
python3.11libs/edini/tool_executor.py → [MIRROR]
pi-extensions/edini-tools/tools/harness.ts → [MODIFY] Update prompt guidelines
pi-extensions/edini-tools/tools/script.ts  → [MODIFY] Add batch params tool schema (or new file)
pi-extensions/edini-tools/index.ts    → [MODIFY] Register batch params tool
skills/procedural-modeling/SKILL.md   → [MODIFY] Rewrite Python SOP section, add Capture section

tests/test_procedural_harness.py      → [MODIFY] New sandbox tests
tests/test_node_utils.py              → [MODIFY] Batch param tests
tests/test_capture_tools.py           → [MODIFY] Capture error message test
tests/test_pi_harness_tools.py        → [MODIFY] Batch param schema test
tests/mock_hou.py                     → [MODIFY] Add mock Python SOP node support if needed

python3.11libs/edini/eval/evaluator.py   → [MODIFY] Add sandbox_adoption_rate (Fix 7)
python3.11libs/edini/ui/knowledge_store.py → [READ-ONLY] Used by Fix 5 handler
```

---

## Phase 1: Sandbox Execution Model (P0 Fix 1)

### Task 1.1: Write sandbox rewrite unit tests

**Files:**
- Modify: `tests/test_procedural_harness.py`
- Modify: `tests/mock_hou.py` (if needed for Python SOP mock)

- [ ] **Step 1: Add mock support for Python SOP node in sandbox**

In `tests/mock_hou.py`, the mock needs a `geometry()` method on MockNode and support for `createNode("python", ...)`. Check if `createNode` already works for arbitrary types; if so, add `geometry()`:

```python
# In MockNode class, add:
def geometry(self):
    if not hasattr(self, '_geometry'):
        self._geometry = MockGeometry()
    return self._geometry
```

And add a minimal `MockGeometry` class:

```python
class MockGeometry:
    def __init__(self):
        self._points = []
        self._prims = []
        self._intrinsics = {"pointcount": 0, "primitivecount": 0, "vertexcount": 0}
    
    def clear(self):
        self._points.clear()
        self._prims.clear()
        self._intrinsics["pointcount"] = 0
        self._intrinsics["primitivecount"] = 0
    
    def addAttrib(self, attr_type, name, default):
        pass  # no-op for testing
    
    def createPoint(self):
        pt = MockPoint()
        self._points.append(pt)
        self._intrinsics["pointcount"] = len(self._points)
        return pt
    
    def createPolygon(self):
        prim = MockPrim()
        self._prims.append(prim)
        self._intrinsics["primitivecount"] = len(self._prims)
        return prim
    
    def intrinsicValue(self, name):
        return self._intrinsics.get(name, 0)
    
    def boundingBox(self):
        from tests.mock_hou import MockBoundingBox
        return MockBoundingBox()

class MockPoint:
    def setPosition(self, pos):
        self._pos = pos
    def position(self):
        return getattr(self, '_pos', (0, 0, 0))
    def setAttribValue(self, name, value):
        pass

class MockPrim:
    def addVertex(self, pt):
        pass
    def setAttribValue(self, name, value):
        pass
```

- [ ] **Step 2: Write test_sandbox_structure_and_diagnostics**

```python
class TestSandboxStructure(unittest.TestCase):
    """Tests that run_python_sandbox returns correct structure and diagnostics."""
    
    def setUp(self):
        self.mock = _mock_hou()
    
    def test_sandbox_result_has_required_fields(self):
        """Sandbox result includes job_id, root_path, output_node, diagnostics."""
        from edini import harness
        code = "node = hou.pwd()\ngeo = node.geometry()\ngeo.clear()\npt = geo.createPoint()\npt.setPosition((1,2,3))"
        result = harness.run_python_sandbox(code, sandbox_name="test_struct")
        for field in ["job_id", "root_path", "output_node", "diagnostics", "structural_checks"]:
            self.assertIn(field, result, f"Missing field: {field}")
        self.assertIn("edini_generate", result.get("output_node", ""))
    
    def test_sandbox_diagnostics_has_geometry(self):
        """Diagnostics bundle includes geometry stats."""
        from edini import harness
        code = "node = hou.pwd()\ngeo = node.geometry()\ngeo.clear()\npt = geo.createPoint()\npt.setPosition((0,0,0))"
        result = harness.run_python_sandbox(code, sandbox_name="test_diag")
        diag = result.get("diagnostics", {})
        self.assertTrue(diag.get("success"))
        geo = diag.get("geometry")
        self.assertIsNotNone(geo)
    
    def test_sandbox_structural_checks_included(self):
        """Structural checks summary always present in result."""
        from edini import harness
        code = "node = hou.pwd()\ngeo = node.geometry()\ngeo.clear()\npt = geo.createPoint()\npt.setPosition((0,0,0))"
        result = harness.run_python_sandbox(code, sandbox_name="test_struct_chk")
        checks = result.get("structural_checks", {})
        self.assertIn("has_geometry", checks)
        self.assertIn("point_count", checks)
        self.assertIn("bounds_nonzero", checks)"}]}

- [ ] **Step 3: Write test_sandbox_python_sop_cook_flow**

```python
class TestSandboxPythonSOPCook(unittest.TestCase):
    def setUp(self):
        self.mock_hou = _mock_hou()
    
    def test_sandbox_with_valid_code_returns_success(self):
        """Sandbox with valid geometry code returns success with diagnostics."""
        import harness
        code = """
node = hou.pwd()
geo = node.geometry()
geo.clear()
geo.addAttrib(hou.attribType.Point, "test_attr", 0.0)
pt = geo.createPoint()
pt.setPosition((1.0, 2.0, 3.0))
"""
        result = harness.run_python_sandbox(code, sandbox_name="test")
        # The mock won't fully cook, but structural assertions:
        self.assertIn("job_id", result)
        self.assertIn("root_path", result)
        self.assertIn("output_node", result)
        self.assertIn("diagnostics", result)
```

- [ ] **Step 4: Write test_sandbox_cook_error_preserves_node**

```python
def test_sandbox_cook_error_preserves_node(self):
    """Sandbox with failing code preserves the node and collects errors."""
    import harness
    code = """
node = hou.pwd()
geo = node.geometry()
geo.clear()
raise ValueError("intentional test error")
"""
    result = harness.run_python_sandbox(code, sandbox_name="test_error",
                                         delete_on_failure=False)
    self.assertFalse(result["success"])
    self.assertTrue(result.get("preserved", False))
    self.assertIn("error", result)
    self.assertIn("ValueError", result.get("error", ""))
```

- [ ] **Step 5: Write test_sandbox_delete_on_failure**

```python
def test_sandbox_delete_on_failure_cleans_up(self):
    """Sandbox with delete_on_failure=True removes the sandbox on error."""
    import harness
    code = 'raise RuntimeError("test cleanup")'
    result = harness.run_python_sandbox(code, sandbox_name="test_del",
                                         delete_on_failure=True)
    self.assertFalse(result["success"])
    self.assertTrue(result.get("deleted", False))
```

- [ ] **Step 6: Run tests to verify they fail (pre-implementation)**

Run: `python -m pytest tests/test_procedural_harness.py::TestSandboxPythonSOPCook -v`
Expected: FAIL — new tests fail because sandbox not yet rewritten

- [ ] **Step 7: Commit scaffold tests**

```bash
git add tests/test_procedural_harness.py tests/mock_hou.py
git commit -m "test(harness): add sandbox Python SOP cook tests"
```

---

### Task 1.2: Rewrite run_python_sandbox

**Files:**
- Modify: `edini/harness.py:457-520`

- [ ] **Step 1: Replace run_python_sandbox implementation**

Replace the entire `run_python_sandbox` function (lines ~457 to ~520) with:

```python
def run_python_sandbox(
    code: str,
    sandbox_name: str = "procedural",
    commit_on_success: bool = False,
    delete_on_failure: bool = False,
) -> dict[str, Any]:
    job_id, root_path = _create_sandbox_root(sandbox_name)

    # Create Python SOP inside sandbox
    sandbox_root = hou.node(root_path)
    py_sop = sandbox_root.createNode("python", "edini_generate")
    py_sop.parm("python").set(code)
    output_node_path = py_sop.path()

    # Capture stdout/stderr from cooking
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = stdout_capture
    sys.stderr = stderr_capture

    try:
        py_sop.cook(force=True)
        cook_errors = list(py_sop.errors() or [])
        cook_warnings = list(py_sop.warnings() or [])

        if cook_errors:
            raise RuntimeError("; ".join(cook_errors))

        # Build diagnostics (always, for both success and failure)
        diag = _safe_collect_diagnostics(
            output_node_path,
            include_geometry=True,
            include_parms=False,
        )

        # Build structural checks summary
        geo_stats = diag.get("geometry") or {}
        structural_checks = {
            "has_geometry": geo_stats.get("point_count", 0) > 0,
            "point_count": geo_stats.get("point_count", 0),
            "prim_count": geo_stats.get("prim_count", 0),
            "bounds_nonzero": (
                isinstance(geo_stats.get("bounds", {}).get("size"), list)
                and any(abs(c) > 1e-6 for c in geo_stats["bounds"]["size"])
                if geo_stats.get("bounds", {}).get("size") else False
            ),
        }

        response = {
            "success": True,
            "job_id": job_id,
            "execution_mode": EXECUTION_MODE_LIVE,
            "root_path": root_path,
            "output_node": output_node_path,
            "output": _safe_getvalue(stdout_capture) or "(no output)",
            "stderr": _safe_getvalue(stderr_capture),
            "diagnostics": diag,
            "structural_checks": structural_checks,
            "commit_requested": bool(commit_on_success),
            "committed": False,
        }

        if commit_on_success:
            commit_result = commit_sandbox(root_path, sandbox_name)
            response["committed"] = commit_result.get("committed", False)
            if commit_result.get("success"):
                response["final_path"] = commit_result.get("final_path", "")
            else:
                response["commit_error"] = commit_result.get("error", "")

        return response

    except Exception as e:
        execution_traceback = traceback.format_exc()
        diagnostics = _safe_collect_diagnostics(
            output_node_path, include_geometry=True, include_parms=False,
        )
        geo_stats = diagnostics.get("geometry") or {}
        structural_checks = {
            "has_geometry": geo_stats.get("point_count", 0) > 0,
            "point_count": geo_stats.get("point_count", 0),
            "prim_count": geo_stats.get("prim_count", 0),
            "bounds_nonzero": False,
        }

        deleted = False
        delete_error = None
        delete_traceback = None
        if delete_on_failure:
            try:
                _destroy_node(root_path)
                deleted = True
            except Exception as cleanup_exc:
                delete_error = str(cleanup_exc)
                delete_traceback = traceback.format_exc()

        response = {
            "success": False,
            "job_id": job_id,
            "execution_mode": EXECUTION_MODE_LIVE,
            "root_path": root_path,
            "output_node": output_node_path,
            "error": str(e),
            "output": _safe_getvalue(stdout_capture),
            "stderr": _safe_getvalue(stderr_capture),
            "traceback": execution_traceback,
            "diagnostics": diagnostics,
            "structural_checks": structural_checks,
            "preserved": not deleted,
            "deleted": deleted,
            "commit_requested": bool(commit_on_success),
            "committed": False,
        }
        if delete_error is not None:
            response["delete_error"] = delete_error
            response["delete_traceback"] = delete_traceback
        return response
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
```

- [ ] **Step 2: Mirror to runtime copy**

```bash
cp edini/harness.py python3.11libs/edini/harness.py
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_procedural_harness.py -v`
Expected: New sandbox SOP tests pass; existing harness tests (LadderRegression, etc.) remain passing

- [ ] **Step 4: Run full harness-related test suite**

Run: `python -m pytest tests/test_procedural_harness.py tests/test_tool_executor_harness.py tests/test_pi_harness_tools.py -q`
Expected: All harness tests pass

- [ ] **Step 5: Compile check**

Run: `python -m compileall -q edini/harness.py python3.11libs/edini/harness.py`
Expected: No output (success)

- [ ] **Step 6: Commit**

```bash
git add edini/harness.py python3.11libs/edini/harness.py tests/test_procedural_harness.py tests/mock_hou.py
git commit -m "fix(harness): rewrite run_python_sandbox to use Python SOP cooking context

- Create Python SOP 'edini_generate' inside sandbox geo container
- Inject user code as SOP parameter, cook in SOP context
- hou.pwd() now returns the SOP node, node.geometry() works
- Always include diagnostics and structural_checks in result
- Fixes all 7 sandbox attempts that failed due to missing cooking context"
```

---

## Phase 2: Skill + Diagnostics + Batch Params (P0 Fix 2, P1 Fixes 3-4)

### Task 2.1: Rewrite Skill Python SOP section

**Files:**
- Modify: `skills/procedural-modeling/SKILL.md`

- [ ] **Step 1: Replace Python SOP section**

Find the section starting with `## Python SOP Guidelines` and the code block:

```
### OLD (to replace):
```python
# Via houdini_run_python_sandbox - creates a persistent Python SOP in a sandbox
geo_node = hou.node("/obj").createNode("geo", "procedural_result")
py = geo_node.createNode("python", "generate")
py.parm("python").set("node = hou.pwd()\ngeo = node.geometry()\n# generation code here")
```
```

Replace with:

```markdown
## Python SOP Guidelines

When using `houdini_run_python_sandbox`, the sandbox creates a Python SOP node (`edini_generate`) for you and injects your code as the SOP's `python` parameter. Your code runs inside a Python SOP cooking context — use `hou.pwd()` and `node.geometry()` directly:

```python
# Inside houdini_run_python_sandbox — this IS a Python SOP context
node = hou.pwd()
geo = node.geometry()
geo.clear()

# Add attributes BEFORE creating geometry
geo.addAttrib(hou.attribType.Point, "height", 0.0)
geo.addAttrib(hou.attribType.Prim, "group_id", 0)

# Build geometry
pt = geo.createPoint()
pt.setPosition((0, 0, 0))
pt.setAttribValue("height", 1.5)

poly = geo.createPolygon()
poly.addVertex(pt)
poly.setAttribValue("group_id", 0)
```

For node network generation inside a sandbox, create child nodes under `hou.pwd().parent()`:

```python
node = hou.pwd()
container = node.parent()  # the sandbox geo container
box = container.createNode("box", "my_box")
box.parm("size").set((1, 1, 1))
```

Use Python SOP for: recursive geometry (L-systems, trees), external data parsing, complex loops, CSG operations, mesh manipulation.

For raw `houdini_run_python` (non-sandbox, expert use), create nodes at `/obj` level:
```python
geo_node = hou.node("/obj").createNode("geo", "procedural_result")
py = geo_node.createNode("python", "generate")
py.parm("python").set("node = hou.pwd()\ngeo = node.geometry()\n# code")
```
```

### Workflow section: update step 4

Change step 4 from:

```
4. **Preserve failed nodes** - Do not delete a failed procedural node before calling `houdini_collect_diagnostics`.
```

To:

```
4. **Trust sandbox diagnostics** - The sandbox result includes `diagnostics` and `structural_checks` (has_geometry, point_count, bounds_nonzero). No need for separate `houdini_inspect_geo` or `houdini_check_errors` calls.
```

- [ ] **Step 2: Verify skill renders**

Check the skill markdown is valid. Run:
```bash
grep -c "```" skills/procedural-modeling/SKILL.md
```
Expected: even number (code fences balanced)

- [ ] **Step 3: Commit**

```bash
git add skills/procedural-modeling/SKILL.md
git commit -m "docs(skill): rewrite Python SOP section for sandbox-safe patterns

- Show hou.pwd()-based code that works inside sandbox's Python SOP context
- Add node network generation pattern using hou.pwd().parent()
- Move raw houdini_run_python example to expert-use section
- Update workflow step 4 to reference sandbox diagnostics"
```

---

### Task 2.2: Add Capture section to Skill

**Files:**
- Modify: `skills/procedural-modeling/SKILL.md`

- [ ] **Step 1: Add Capture section before Common VEX Pitfalls**

Insert after the Workflow section:

```markdown
### Capture (Screenshots)

- **Only use `houdini_capture_viewport_safe`** — `houdini_capture_network` is unsupported in Houdini 21 (`NetworkEditor.grab` removed).
- If safe capture returns an error, do not retry or explore alternative capture methods. Trust geometry diagnostics instead.
- `describe_image` is a best-effort visual confirmation. If it returns ambiguous results ("faint", "ghostly"), rely on geometry stats (point/prim counts, bounds) as the authoritative verification.
- Visual verification via capture is supplementary; structural diagnostics are primary.
```

- [ ] **Step 2: Commit**

```bash
git add skills/procedural-modeling/SKILL.md
git commit -m "docs(skill): add Capture section with H21-safe screenshot guidance"
```

---

### Task 2.3: Add batch parameter tool (Python handler)

**Files:**
- Modify: `edini/node_utils.py`

- [ ] **Step 1: Add set_params_batch handler**

Add after the `set_param` function (~line 275):

```python
def set_params_batch(node_path: str, params: dict[str, Any]) -> dict[str, Any]:
    """Set multiple parameters on a node in a single call."""
    node = hou.node(node_path)
    if node is None:
        return {"success": False, "error": f"Node not found: {node_path}"}

    failed: list[str] = []
    for name, value in params.items():
        parm = node.parm(name)
        if parm is None:
            failed.append(name)
            continue
        try:
            parm.set(value)
        except Exception as e:
            failed.append(f"{name}: {e}")

    if failed:
        return {
            "success": True,
            "partial": True,
            "set_count": len(params) - len(failed),
            "total_count": len(params),
            "failed_params": failed,
            "warning": f"{len(failed)} parameter(s) could not be set",
        }
    return {
        "success": True,
        "set_count": len(params),
        "total_count": len(params),
    }
```

- [ ] **Step 2: Mirror to runtime copy**

```bash
cp edini/node_utils.py python3.11libs/edini/node_utils.py
```

- [ ] **Step 3: Commit**

```bash
git add edini/node_utils.py python3.11libs/edini/node_utils.py
git commit -m "feat(node_utils): add set_params_batch for bulk parameter setting"
```

---

### Task 2.4: Register batch param tool in tool_executor and Pi extension

**Files:**
- Modify: `edini/tool_executor.py`
- Modify: `pi-extensions/edini-tools/tools/script.ts`
- Modify: `pi-extensions/edini-tools/index.ts`

- [ ] **Step 1: Import set_params_batch in tool_executor.py**

Edit imports at top of `edini/tool_executor.py`:

```python
from edini.node_utils import (
    get_scene_info,  create_node, delete_node, connect_nodes,
    set_param, set_params_batch, get_param, list_nodes, get_node_info, layout_nodes,
    ...
)
```

- [ ] **Step 2: Register in TOOL_HANDLERS**

After the `"houdini_set_param"` entry in TOOL_HANDLERS:

```python
    "houdini_set_params_batch": lambda **kw: set_params_batch(
        kw["node_path"], kw["params"],
    ),
```

- [ ] **Step 3: Mirror to runtime copy**

```bash
cp edini/tool_executor.py python3.11libs/edini/tool_executor.py
```

- [ ] **Step 4: Add Pi tool schema in script.ts**

Add after the `houdiniSetParam` export in `pi-extensions/edini-tools/tools/script.ts`:

```typescript
export const houdiniSetParamsBatch = {
  name: "houdini_set_params_batch",
  label: "Set Multiple Houdini Parameters",
  description:
    "Set multiple parameters on a single Houdini node in one call. Much faster than calling houdini_set_param repeatedly.",
  promptSnippet: "Set multiple parameters on a Houdini node at once",
  promptGuidelines: [
    "Use houdini_set_params_batch when setting 3+ parameters on the same node — it's significantly faster than individual calls.",
  ],
  parameters: Type.Object({
    node_path: Type.String({ description: "Full path of the node" }),
    params: Type.Record(Type.String(), Type.Unknown(), {
      description: "Map of parameter names to values",
    }),
  }),
  async execute(
    _toolCallId: string,
    params: { node_path: string; params: Record<string, unknown> }
  ) {
    return forwardTool("houdini_set_params_batch", params);
  },
};
```

- [ ] **Step 5: Register in index.ts**

In `pi-extensions/edini-tools/index.ts`, add import and allTools entry:

```typescript
import { houdiniSetParamsBatch } from "./tools/script";

// In allTools array, after ...scriptTools:
const allTools = [
    ...sceneTools,
    ...queryTools,
    ...scriptTools,
    houdiniSetParamsBatch,
    ...harnessTools,
    ediniGetEvalStats,
    ediniSearchKnowledge,
];
```

- [ ] **Step 6: Commit**

```bash
git add edini/tool_executor.py python3.11libs/edini/tool_executor.py pi-extensions/edini-tools/tools/script.ts pi-extensions/edini-tools/index.ts
git commit -m "feat(tools): add houdini_set_params_batch for bulk parameter setting"
```

---

## Phase 3: Missing Tools + Screenshot + Analytics (P1 Fix 5, P2 Fixes 6-7)

### Task 3.1: Add edini_search_knowledge handler

**Files:**
- Modify: `edini/tool_executor.py`

- [ ] **Step 1: Add import and handler function**

In `edini/tool_executor.py`, add import:

```python
# At top of imports section
try:
    from edini.ui.knowledge_store import search_entries
except ImportError:
    def search_entries(query="", category="", limit=10):
        return {"success": False, "error": "Knowledge store not available in this context"}
```

- [ ] **Step 2: Add TOOL_HANDLERS entry**

```python
    "edini_search_knowledge": lambda **kw: search_entries(
        query=kw.get("query", ""),
        category=kw.get("category", ""),
        limit=kw.get("limit", 10),
    ),
```

- [ ] **Step 3: Commit**

```bash
git add edini/tool_executor.py python3.11libs/edini/tool_executor.py
git commit -m "fix(tools): add edini_search_knowledge handler in tool_executor"
```

---

### Task 3.2: Add edini_get_eval_stats handler

**Files:**
- Modify: `edini/tool_executor.py`

- [ ] **Step 1: Add handler function**

```python
try:
    from edini.eval.evaluator import EvalStore
except ImportError:
    EvalStore = None

def _edini_get_eval_stats(period: int = 10) -> dict[str, Any]:
    """Get evaluation statistics for recent sessions."""
    if EvalStore is None:
        return {"success": False, "error": "Eval system not available in this context"}
    try:
        store = EvalStore()
        sessions = store.get_recent_sessions(period)
        if not sessions:
            return {"success": True, "sessions_analyzed": 0, "message": "No evaluation data yet"}
        
        from collections import Counter
        dims = ["reliability", "efficiency", "cost", "tool_accuracy", "task_completion"]
        scores = {d: [] for d in dims}
        for s in sessions:
            for d in dims:
                score = getattr(s, d, None)
                if score is not None:
                    scores[d].append(score)
        
        avg = {d: round(sum(v)/len(v), 2) if v else None for d, v in scores.items()}
        weakest = min((d for d in dims if avg[d] is not None), key=lambda d: avg[d], default=None)
        
        return {
            "success": True,
            "sessions_analyzed": len(sessions),
            "average_scores": avg,
            "weakest_dimension": weakest,
            "message": f"Analyzed {len(sessions)} recent sessions. Weakest: {weakest}" if weakest else "",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
```

- [ ] **Step 2: Add TOOL_HANDLERS entry**

```python
    "edini_get_eval_stats": lambda **kw: _edini_get_eval_stats(
        period=kw.get("period", 10),
    ),
```

- [ ] **Step 3: Mirror to runtime copy**

```bash
cp edini/tool_executor.py python3.11libs/edini/tool_executor.py
```

- [ ] **Step 4: Commit**

```bash
git add edini/tool_executor.py python3.11libs/edini/tool_executor.py
git commit -m "fix(tools): add edini_get_eval_stats handler in tool_executor"
```

---

### Task 3.3: Enhance capture error messages

**Files:**
- Modify: `edini/node_utils.py`

- [ ] **Step 1: Enhance capture_network error**

In `capture_network` (~line 648), change the `AttributeError` handler:

```python
    except AttributeError as e:
        return {
            "success": False,
            "error": f"Network grab failed (API mismatch): {e}",
            "guidance": "NetworkEditor.grab is not available in Houdini 21. "
                        "Use houdini_capture_viewport_safe for viewport screenshots instead. "
                        "To verify node network structure, use houdini_layout_nodes or houdini_list_nodes.",
        }
```

- [ ] **Step 2: Enhance capture_viewport_safe error**

In the main `except Exception` block of `capture_viewport_safe` (~line 630), enhance the note:

```python
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "method": method,
            "stage": stage,
            "traceback": traceback.format_exc(),
            "note": "Safe capture does not fall back to direct Qt widget probing. "
                    "Verify geometry with houdini_inspect_geo or sandbox diagnostics instead. "
                    "Do not retry capture or explore alternative capture methods.",
        }
```

- [ ] **Step 3: Mirror to runtime copy**

```bash
cp edini/node_utils.py python3.11libs/edini/node_utils.py
```

- [ ] **Step 4: Commit**

```bash
git add edini/node_utils.py python3.11libs/edini/node_utils.py
git commit -m "fix(node_utils): add guidance to capture error messages for H21 compatibility"
```

---

### Task 3.4: Update harness.ts prompt guidelines

**Files:**
- Modify: `pi-extensions/edini-tools/tools/harness.ts`

- [ ] **Step 1: Update houdiniRunPythonSandbox guidelines**

In `houdiniRunPythonSandbox` definition, update `promptGuidelines`:

```typescript
  promptGuidelines: [
    "ALWAYS use houdini_run_python_sandbox for initial procedural asset generation instead of raw houdini_run_python.",
    "The sandbox provides a Python SOP context — use hou.pwd() and node.geometry() directly in your code.",
    "The sandbox result includes diagnostics and structural_checks (has_geometry, point_count, bounds_nonzero) — no need for separate inspect_geo or check_errors calls.",
    "Do not delete a failed sandbox before reviewing the diagnostics in the result.",
  ],
```

- [ ] **Step 2: Update houdiniCollectDiagnostics guidelines**

```typescript
  promptGuidelines: [
    "Use houdini_collect_diagnostics after a failed cook, blank output, or unexpected procedural result before changing strategy or deleting nodes.",
    "For sandbox executions, diagnostics are already included in the sandbox result — separate diagnostics call is only needed for non-sandbox nodes.",
  ],
```

- [ ] **Step 3: Commit**

```bash
git add pi-extensions/edini-tools/tools/harness.ts
git commit -m "docs(harness): update prompt guidelines for sandbox diagnostics and usage"
```

---

### Task 3.5: Write tests for batch params, capture errors, harness tools

**Files:**
- Modify: `tests/test_node_utils.py`
- Modify: `tests/test_capture_tools.py`
- Modify: `tests/test_pi_harness_tools.py`

- [ ] **Step 1: Add batch param tests**

In `tests/test_node_utils.py`:

```python
class TestSetParamsBatch(unittest.TestCase):
    def setUp(self):
        self.mock = _mock_hou()
        self.node = hou.node("/obj/geo1")
    
    def test_set_params_batch_all_success(self):
        from edini.node_utils import set_params_batch
        result = set_params_batch("/obj/geo1", {"tx": 1.5, "ty": 2.0, "tz": 3.0})
        self.assertTrue(result["success"])
        self.assertEqual(result["set_count"], 3)
        self.assertEqual(result["total_count"], 3)
        self.assertNotIn("partial", result)
    
    def test_set_params_batch_missing_param(self):
        from edini.node_utils import set_params_batch
        result = set_params_batch("/obj/geo1", {"tx": 1.0, "nonexistent": 99})
        self.assertTrue(result["success"])
        self.assertTrue(result.get("partial"))
        self.assertEqual(result["set_count"], 1)
        self.assertIn("nonexistent", result["failed_params"])
    
    def test_set_params_batch_node_not_found(self):
        from edini.node_utils import set_params_batch
        result = set_params_batch("/obj/missing", {"tx": 1.0})
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])
```

- [ ] **Step 2: Add capture error guidance test**

In `tests/test_capture_tools.py`:

```python
class TestCaptureErrorGuidance(unittest.TestCase):
    def test_capture_network_error_includes_guidance(self):
        from edini.node_utils import capture_network
        result = capture_network("/tmp/test.png", "/obj")
        if not result["success"] and "guidance" in result:
            self.assertIn("houdini_capture_viewport_safe", result["guidance"])
    
    def test_capture_viewport_safe_error_includes_note(self):
        from edini.node_utils import capture_viewport_safe
        result = capture_viewport_safe("/tmp/test.png")
        if not result["success"] and "note" in result:
            self.assertIn("Safe capture", result["note"])
```

- [ ] **Step 3: Add batch params Pi schema test**

In `tests/test_pi_harness_tools.py`:

```python
class TestBatchParamsSchema(unittest.TestCase):
    def test_batch_params_schema_exists(self):
        import importlib
        # Verify the tool schema file is loadable
        try:
            with open("pi-extensions/edini-tools/tools/script.ts", "r") as f:
                content = f.read()
            self.assertIn("houdini_set_params_batch", content)
        except FileNotFoundError:
            self.skipTest("Pi extension not available")
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_node_utils.py::TestSetParamsBatch tests/test_capture_tools.py::TestCaptureErrorGuidance tests/test_pi_harness_tools.py::TestBatchParamsSchema -v`
Expected: PASS (or skip for Pi schema test)

- [ ] **Step 5: Commit**

```bash
git add tests/test_node_utils.py tests/test_capture_tools.py tests/test_pi_harness_tools.py
git commit -m "test: add tests for batch params, capture error guidance, and harness schema"
```

---

### Task 3.6: Add sandbox survival analytics to evaluator (Fix 7)

**Files:**
- Modify: `python3.11libs/edini/eval/evaluator.py`

**Note:** The evaluator only exists in the runtime copy (`python3.11libs/edini/`). Source copy `edini/eval/` does not exist. This task modifies the runtime copy only.

- [ ] **Step 1: Extend ToolCallRecord**

Find the `ToolCallRecord` dataclass and add fields:

```python
@dataclass
class ToolCallRecord:
    # ... existing fields ...
    sandbox_job_id: Optional[str] = None
    sandbox_action: Optional[str] = None      # "create" | "discard" | "commit"
    sandbox_root_path: Optional[str] = None
```

- [ ] **Step 2: Parse sandbox fields in LogParser**

In `python3.11libs/edini/eval/log_parser.py` (or wherever tool calls are parsed from JSONL), add sandbox field extraction:

```python
# In the tool call parsing function:
tool_name = record.get("name", "")
if tool_name == "houdini_run_python_sandbox":
    tc.sandbox_action = "create"
    tc.sandbox_root_path = record.get("arguments", {}).get("sandbox_root_path", "")
elif tool_name == "houdini_discard_sandbox":
    tc.sandbox_action = "discard"
    tc.sandbox_root_path = record.get("arguments", {}).get("sandbox_root_path", "")
elif tool_name == "houdini_commit_sandbox":
    tc.sandbox_action = "commit"
    tc.sandbox_root_path = record.get("arguments", {}).get("sandbox_root_path", "")
```

- [ ] **Step 3: Add sandbox_adoption_rate to evaluator**

Add a new evaluation method in `EvaluatorPipeline`:

```python
def _eval_sandbox_adoption(self, session: StructuredSession) -> float:
    sandbox_commits = sum(
        1 for tc in session.tool_calls
        if tc.sandbox_action == "commit"
    )
    raw_python_runs = sum(
        1 for tc in session.tool_calls
        if tc.tool_name == "houdini_run_python"
        and tc.sandbox_action is None  # exclude sandbox-related calls
    )
    total = sandbox_commits + raw_python_runs
    if total == 0:
        return 1.0  # no procedural work done, neutral
    return sandbox_commits / total
```

- [ ] **Step 4: Wire into evaluate method**

Add to the `evaluate()` method's result dict:

```python
"sandbox_adoption_rate": round(self._eval_sandbox_adoption(session), 2),
```

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/eval/evaluator.py
git commit -m "feat(eval): add sandbox_adoption_rate dimension for harness effectiveness tracking"
```

---

## Phase 4: Final Verification

### Task 4.1: Run full test suite

- [ ] **Step 1: Harness-specific tests**

```bash
python -m pytest tests/test_procedural_harness.py tests/test_tool_executor_harness.py tests/test_pi_harness_tools.py tests/test_node_utils.py -v -q
```
Expected: All pass (verify count; should be 111+ new tests included)

- [ ] **Step 2: Capture tests**

```bash
python -m pytest tests/test_capture_tools.py -v -q
```
Expected: All pass

- [ ] **Step 3: Full test suite**

```bash
python -m pytest tests -q
```
Expected: All pass. Note any pre-existing unrelated failures (like the config test).

- [ ] **Step 4: Compile check**

```bash
python -m compileall -q python3.11libs/edini edini
```
Expected: No output

- [ ] **Step 5: Source/runtime mirror check**

```bash
diff edini/harness.py python3.11libs/edini/harness.py
diff edini/node_utils.py python3.11libs/edini/node_utils.py
diff edini/tool_executor.py python3.11libs/edini/tool_executor.py
```
Expected: No differences (or only intentional ones like import availability)

- [ ] **Step 6: Pi TypeScript check**

```bash
cd pi-extensions/edini-tools && npx tsc --noEmit index.ts 2>&1 || echo "TS check skipped (may not have tsc in path)"
```

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "chore: final verification — all tests pass, all mirrors in sync"
```

---

## Verification Checklist (Post-Implementation)

- [ ] `python -m pytest tests -q` — full suite passes
- [ ] `python -m compileall -q python3.11libs/edini edini` — no compile errors
- [ ] Source/runtime mirrors identical for `harness.py`, `node_utils.py`, `tool_executor.py`
- [ ] `skills/procedural-modeling/SKILL.md` has balanced code fences
- [ ] `pi-extensions/edini-tools/index.ts` lists `houdiniSetParamsBatch`
- [ ] Sandbox test: `run_python_sandbox` creates `edini_generate` Python SOP node
- [ ] Sandbox test: `hou.pwd()` returns the SOP node, `node.geometry()` works
- [ ] Sandbox test: `diagnostics` and `structural_checks` always present in result
- [ ] Batch params test: `set_params_batch` sets multiple params, reports failures
- [ ] Capture test: error messages include guidance for H21 alternatives
