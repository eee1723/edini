# Edini Procedural Harness — 实测后修复设计

> Status: Draft for user review · 2026-06-12
> Background: Phase B harness landed 2026-06-11. Three procedural tasks run 2026-06-12 exposed critical gaps. This design addresses them.

## Summary

Three live procedural tasks (bicycle, sports car, mechanical keyboard) ran through the Phase B harness on 2026-06-12. All three produced working assets, but the harness sandbox workflow failed completely: 7 sandbox attempts, 7 discards, 0 commits. The agent fell back to raw `houdini_run_python` and manual node creation for every task.

This design fixes the sandbox execution model (the root cause), improves efficiency, registers missing tools, hardens screenshot paths, and adds sandbox survival analytics.

## Fixes Overview

| # | Priority | Area | Root Cause |
|---|----------|------|------------|
| 1 | P0 | Sandbox execution model | `exec(code)` provides no Python SOP cooking context → `hou.pwd()` returns None |
| 2 | P0 | Skill example code | Example shows creating new geo at `/obj`, not operating inside existing sandbox geo |
| 3 | P1 | Diagnostics auto-injection | Agent calls `inspect_geo` + `check_errors` separately when sandbox result already has the data |
| 4 | P1 | Batch parameter setting | 120 individual `set_param` calls in one task (60% of all tool calls) |
| 5 | P1 | Missing tool registration | `edini_search_knowledge` and `edini_get_eval_stats` not in Pi tool index |
| 6 | P2 | Screenshot path hardening | `NetworkEditor.grab` API missing in H21; `describe_image` gives unreliable feedback |
| 7 | P2 | Sandbox survival analytics | No metrics track whether the harness is actually being used |

## Fix 1: Sandbox Execution Model (P0)

### Problem

`run_python_sandbox` currently does:

```python
root = obj.createNode("geo", root_name)   # creates /obj/edini_sandbox_<id>
exec(code, {"hou": hou, "sandbox_root_path": root.path(), ...})
```

Agent code uses `hou.pwd()` → returns `None` (not in SOP cooking context) → `node.geometry()` → `AttributeError`. This caused all 7 sandbox attempts to fail identically.

### Solution

Instead of `exec(code)`, the sandbox automatically creates a Python SOP node inside the geo container, injects user code as that SOP's `python` parameter, and cooks it:

```python
def run_python_sandbox(code, sandbox_name, ...):
    job_id, root_path = _create_sandbox_root(sandbox_name)
    
    # Create Python SOP inside sandbox
    py_sop = hou.node(root_path).createNode("python", "edini_generate")
    py_sop.parm("python").set(code)
    
    # Cook in SOP context
    try:
        py_sop.cook(force=True)
    except hou.OperationFailed:
        pass  # errors captured via diagnostics
    
    # Collect results
    errors = list(py_sop.errors())
    geo = py_sop.geometry()
    ...
```

**Key behaviors:**

- `hou.pwd()` inside user code now returns the `edini_generate` Python SOP node
- `node.geometry()` returns the SOP's output geometry (with `geo.clear()` available)
- `node.createNode(...)` creates children inside the sandbox geo container
- If cook fails, the SOP node is preserved with errors intact
- `output_node` in result payload defaults to `edini_generate` path

**Backward compatibility:**

- `sandbox_root_path` still returned in result
- Same `job_id`, `execution_mode`, `commit_on_success`, `delete_on_failure` parameters
- Return schema unchanged except diagnostics now always present
- Raw `houdini_run_python` unaffected

### Files changed

- `edini/harness.py` — rewrite `run_python_sandbox` function (~50 lines changed)
- `python3.11libs/edini/harness.py` — mirror

### Testing

- Unit test: create sandbox, verify Python SOP node exists, verify `hou.pwd()` returns the SOP inside sandbox code, verify geometry populates
- Unit test: sandbox with cook error preserves node and errors
- Unit test: sandbox with `delete_on_failure=True` cleans up
- Unit test: sandbox with `commit_on_success=True` auto-commits
- Existing `TestLadderRegression` must still pass

---

## Fix 2: Skill Example Code (P0)

### Problem

`skills/procedural-modeling/SKILL.md` Python SOP section shows:

```python
geo_node = hou.node("/obj").createNode("geo", "procedural_result")
py = geo_node.createNode("python", "generate")
py.parm("python").set("...")
```

This is correct for raw `houdini_run_python` usage but misleading for sandbox usage. Agent copied this pattern inside sandbox code, creating a nested geo → "Invalid node type name" error.

### Solution

Rewrite the Python SOP section to show sandbox-safe code:

```markdown
## Python SOP Guidelines

When using `houdini_run_python_sandbox`, the sandbox already provides a sanitized Python SOP context. Use `hou.pwd()` directly:

```python
node = hou.pwd()
geo = node.geometry()
geo.clear()

# Build geometry here
geo.addAttrib(hou.attribType.Point, "height", 0.0)
pt = geo.createPoint()
pt.setPosition((0, 0, 0))
```

For advanced node network creation inside a sandbox, create child nodes under `hou.pwd().parent()`.
```

Also update the Workflow section (#4) to clarify that sandbox code runs as a Python SOP, not a plain script.

### Files changed

- `skills/procedural-modeling/SKILL.md` — rewrite Python SOP section, update workflow step 4

---

## Fix 3: Diagnostics Auto-Injection (P1)

### Problem

Agent consistently calls `houdini_inspect_geo` + `houdini_check_errors` after sandbox execution, even though `run_python_sandbox` already collects this data (in its `diagnostics` field). Each task wastes 3-5 extra tool calls.

### Solution

`run_python_sandbox` already includes `diagnostics` in its return. No code change needed in harness — the diagnostics are there. But we should:

1. Ensure diagnostics are **always populated** (currently on error path only — fix to always include)
2. Add `structural_checks` summary at top level: `has_geometry`, `bounds_nonzero`, `point_count > 0`
3. Add prompt guidelines in `harness.ts` telling Agent: "diagnostics and geometry stats are included in the sandbox result — no need for separate inspect_geo or check_errors"

### Return schema (enhanced)

```json
{
  "success": true,
  "job_id": "...",
  "root_path": "/obj/edini_sandbox_...",
  "output_node": "/obj/edini_sandbox_.../edini_generate",
  "output": "...",
  "diagnostics": {
    "node_errors": [],
    "node_warnings": [],
    "geometry": {
      "point_count": 2672,
      "prim_count": 2494,
      "bounds": {"min": [...], "max": [...], "size": [...]}
    }
  },
  "structural_checks": {
    "has_geometry": true,
    "point_count": 2672,
    "bounds_nonzero": true
  }
}
```

### Files changed

- `edini/harness.py` — always include diagnostics + structural_checks in success path
- `pi-extensions/edini-tools/tools/harness.ts` — update `houdiniRunPythonSandbox` prompt guidelines

---

## Fix 4: Batch Parameter Setting (P1)

### Problem

Task 2 (sports car) used 120 individual `houdini_set_param` calls, one per parameter, at ~100ms HTTP round-trip each. This is 60% of all tool calls for that task.

### Solution

New tool: `houdini_set_params_batch`

**Pi schema:**
```typescript
parameters: Type.Object({
  node_path: Type.String({ description: "Full path of the node" }),
  params: Type.Record(Type.String(), Type.Unknown(), {
    description: "Map of parameter names to values"
  }),
})
```

**Python handler:**
```python
def set_params_batch(node_path, params):
    node = hou.node(node_path)
    for name, value in params.items():
        parm = node.parm(name)
        if parm is None:
            return {"success": False, "error": f"Parameter '{name}' not found on {node_path}"}
        parm.set(value)
    return {"success": True, "set_count": len(params)}
```

### Files changed

- `edini/node_utils.py` — add `set_params_batch` handler
- `python3.11libs/edini/node_utils.py` — mirror
- `edini/tool_executor.py` — register `houdini_set_params_batch` in TOOL_HANDLERS
- `python3.11libs/edini/tool_executor.py` — mirror
- `pi-extensions/edini-tools/tools/` — new file or add to existing params tool file
- `pi-extensions/edini-tools/index.ts` — register in allTools

---

## Fix 5: Missing Tool Registration (P1)

### Problem

Agent called `edini_search_knowledge` and `edini_get_eval_stats` in all 3 tasks. Both returned "Unknown tool". The tool schemas exist in the Pi extension but are not exported in `index.ts`'s `allTools` array.

### Solution

Add both tools to `allTools` array in `pi-extensions/edini-tools/index.ts`.

Verify by searching the extension directory for existing schema definitions.

### Files changed

- `pi-extensions/edini-tools/index.ts` — add entries to `allTools`

---

## Fix 6: Screenshot Path Hardening (P2)

### Problem

Three screenshot failure modes observed:
1. `houdini_capture_network` → `NetworkEditor.grab` doesn't exist in H21 (4 calls, all failed)
2. `setRotation` → wrong argument type for `HOM_Matrix3` (1 call)
3. `describe_image` → returns "faint" / "ghostly" descriptions even for valid geometry (5+ calls)

### Solution

**6a.** `houdini_capture_network` handler: when it fails with API mismatch, add guidance to error message: "Network grab not available in Houdini 21. Use houdini_capture_viewport_safe instead."

**6b.** `houdini_capture_viewport_safe` handler: when flipbook capture fails, add to error: "Viewport capture unavailable. Verify geometry with houdini_inspect_geo or sandbox diagnostics instead."

**6c.** Update procedural-modeling Skill: add "Capture" section under workflow explaining:
- Use `houdini_capture_viewport_safe` only — `houdini_capture_network` is unsupported in H21
- If safe capture fails, trust geometry stats (point/prim/bounds) over visual verification
- `describe_image` is a best-effort visual check; geometry diagnostics are authoritative

### Files changed

- `edini/node_utils.py` — enhance error messages in `capture_network` and `capture_viewport_safe` handlers
- `skills/procedural-modeling/SKILL.md` — add Capture section

---

## Fix 7: Sandbox Survival Analytics (P2)

### Problem

No metrics track whether harness sandbox workflow is actually being used. Need visibility into sandbox adoption rate.

### Solution

Extend `ToolCallRecord` in the evaluation data model with optional sandbox fields:

```python
@dataclass
class ToolCallRecord:
    # ... existing fields ...
    sandbox_job_id: Optional[str] = None
    sandbox_action: Optional[str] = None  # "create" | "discard" | "commit"
    sandbox_root_path: Optional[str] = None
```

Parse these from tool call arguments and results in `LogParser`:
- `houdini_run_python_sandbox` → `sandbox_action = "create"`
- `houdini_discard_sandbox` → `sandbox_action = "discard"`
- `houdini_commit_sandbox` → `sandbox_action = "commit"`

Add evaluation dimension: `sandbox_adoption_rate`
- Formula: `sandbox_committed / (raw_python_runs + sandbox_committed)`
- `raw_python_runs` = count of `houdini_run_python` calls
- Score: 0% → 0pts, 100% → 100pts (linear)

Display in EvalDashboard:
- Add `sandbox_adoption` trend line to existing trend chart
- Add sandbox stats row in session detail view

### Files changed

- `edini/evaluator.py` — extend ToolCallRecord, add sandbox_adoption_rate dimension
- `edini/log_parser.py` — parse sandbox action/job_id from tool calls
- `edini/ui/eval_dashboard.py` — display sandbox adoption in trend chart + session detail
- Mirror copies in `python3.11libs/edini/`

---

## Verification Plan

### Unit tests (new)

```
tests/test_procedural_harness.py:
  - test_sandbox_creates_python_sop       # verify edini_generate exists
  - test_sandbox_hou_pwd_works            # verify hou.pwd() returns the SOP
  - test_sandbox_geometry_populates       # verify points/prims after cook
  - test_sandbox_cook_error_preserves     # verify errors preserved on failure
  - test_sandbox_delete_on_failure        # verify cleanup
  - test_sandbox_auto_commit              # verify commit_on_success

tests/test_node_utils.py:
  - test_set_params_batch                 # batch param setting
  - test_set_params_batch_missing_param   # error on missing parm

tests/test_capture_tools.py:
  - test_capture_network_error_guidance   # error message mentions _safe alternative

tests/test_pi_harness_tools.py:
  - test_batch_params_schema              # Pi schema validation
```

### Integration verification

```bash
python -m pytest tests/test_procedural_harness.py tests/test_node_utils.py \
  tests/test_tool_executor_harness.py tests/test_capture_tools.py \
  tests/test_pi_harness_tools.py -q
```

### Compile check

```bash
python -m compileall -q python3.11libs/edini edini
```

### Source/runtime mirror check

Verify `edini/` and `python3.11libs/edini/` copies are identical for all changed files.

### Skill preview

Open `skills/procedural-modeling/preview.html` to verify updated content renders correctly.

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `edini/harness.py` | Rewrite `run_python_sandbox`, always-include diagnostics on success |
| `python3.11libs/edini/harness.py` | Mirror |
| `edini/node_utils.py` | Add `set_params_batch`, enhance capture error messages |
| `python3.11libs/edini/node_utils.py` | Mirror |
| `edini/tool_executor.py` | Register `houdini_set_params_batch` in TOOL_HANDLERS |
| `python3.11libs/edini/tool_executor.py` | Mirror |
| `pi-extensions/edini-tools/tools/harness.ts` | Update prompt guidelines for sandbox + diagnostics |
| `pi-extensions/edini-tools/index.ts` | Register `edini_search_knowledge`, `edini_get_eval_stats`, batch params |
| `skills/procedural-modeling/SKILL.md` | Rewrite Python SOP section, add Capture section, update workflow |
| `edini/evaluator.py` | Extend ToolCallRecord, add sandbox_adoption_rate |
| `edini/log_parser.py` | Parse sandbox fields from tool calls |
| `edini/ui/eval_dashboard.py` | Display sandbox adoption metrics |
| `tests/test_procedural_harness.py` | New sandbox execution tests |
| `tests/test_node_utils.py` | Batch param tests |
| `tests/test_capture_tools.py` | Capture error message test |
| `tests/test_pi_harness_tools.py` | Batch param schema test |

---

## Non-Goals (explicitly excluded)

- No external Houdini worker process (Phase C)
- No semantic understanding of asset types (e.g., "bicycle has wheels")
- No changes to the VEX wrangle path (unaffected by sandbox changes)
- No changes to Copernicus workflow
- No UI changes to Edini panel
