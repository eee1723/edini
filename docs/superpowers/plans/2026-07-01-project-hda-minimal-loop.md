# Project HDA — Minimal Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the minimal closed loop of a Project HDA: create a Project HDA node, open an embedded PySide panel bound to it, and chat with the LLM through it — with project state persisted in a hidden parm.

**Architecture:** A custom HDA type `edini::project` carries a hidden string parm `__edini_state` holding the declaration JSON. A Houdini Python Panel (`.pypanel` file, first in this repo) renders a PySide widget that binds to a selected Project HDA node and reuses the **existing singleton** `RpcClient` + `ToolExecutor` (via `edini.ui.windows._main_window`) rather than spawning its own Pi subprocess / HTTP server, multiplexing sessions through Pi's `new_session`/`switch_session` API. Declaration state read/written through pure-Python helpers, fully unit-testable without Houdini.

**Tech Stack:** Python 3.11 (Houdini 21), PySide6, pytest + unittest, mock `hou` (`tests/mock_hou.py`), TypeBox (TS tool schemas), Houdini `.pypanel` XML + `hou.pypanel` API.

**Spec:** `docs/superpowers/specs/2026-07-01-project-hda-design.md` (§13 defines this minimal loop).

---

## File Structure

**Create (pure-Python, fully unit-testable — TDD applies):**
- `python3.11libs/edini/project/__init__.py` — package init, public façade
- `python3.11libs/edini/project/state.py` — declaration JSON ⇄ hidden-parm read/write + schema (NO `hou` at import; takes a node-like object)
- `python3.11libs/edini/project/node.py` — Project HDA creation + node helpers (real `hou`)

**Create (panel — PySide, manual-test in Houdini):**
- `python3.11libs/edini/project/panel/__init__.py` — package init
- `python3.11libs/edini/project/panel/project_pane.py` — the `PythonPanelInterface` subclass + widget
- `python3.11libs/edini/project/panel/project_widget.py` — the `QWidget` (three placeholders + project selector)

**Create (Houdini assets):**
- `python3.11libs/edini/project/edini_project.pypanel` — the Python Panel registration XML
- `scripts/make_project_hda.py` — one-shot script to author `otls/edini_project.hda`
- `otls/edini_project.hda` — the HDA definition (generated, committed like `edini_recipe_manager.hda`)

**Create (tests):**
- `tests/test_project_state.py` — unit tests for `state.py` (mock `hou`)

**Modify (wire-up, minimal diffs):**
- `python3.11libs/edini/__init__.py` — no change needed for panel (it's its own `.pypanel`); keep `createPanel` as-is
- `scripts/install.py` — register the `.pypanel` search path in the edini package JSON (Task 11)
- `pi-extensions/edini-tools/tools/project_hda.ts` — (OPTIONAL, Task 12) one tool to create a Project HDA from the agent side

**Deliberately NOT touched:** `assembly_builder.py`, `vex_strategies.py`, `measure.py`, `ui/main_window.py`, `ui/agent_panel.py`, `rpc_client.py`, `tool_executor.py`. (Reuse via import only.)

---

## Task 1: Project package skeleton + state schema

**Files:**
- Create: `python3.11libs/edini/project/__init__.py`
- Create: `python3.11libs/edini/project/state.py`
- Test: `tests/test_project_state.py`

The `state.py` module holds the declaration schema and the JSON ⇄ hidden-parm bridge. It is **pure Python**: it takes a node-like object (duck-typed: has `parm(name).eval()` and `parm(name).set(value)`), never importing `hou`. This makes it unit-testable with mock nodes.

- [ ] **Step 1: Write the failing test**

Create `tests/test_project_state.py`:

```python
"""Unit tests for edini.project.state — declaration JSON <-> hidden parm.

Uses a tiny fake node (no hou import). Run: pytest tests/test_project_state.py -v
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))


class _FakeParm:
    def __init__(self, value=""):
        self._value = value
    def eval(self):
        return self._value
    def set(self, value):
        self._value = value


class _FakeNode:
    """Duck-typed node: parm(name) -> _FakeParm or None."""
    def __init__(self):
        self._parms = {}
    def parm(self, name):
        return self._parms.get(name)
    def set_parm_value(self, name, value):
        if name not in self._parms:
            self._parms[name] = _FakeParm()
        self._parms[name].set(value)


class TestEmptyDeclaration(unittest.TestCase):
    def test_empty_declaration_has_required_keys(self):
        from edini.project.state import empty_declaration
        d = empty_declaration(project_name="car")
        self.assertEqual(d["version"], 1)
        self.assertEqual(d["project"]["name"], "car")
        self.assertIsNone(d["project"]["goal"])
        self.assertEqual(d["plan"], [])
        self.assertEqual(d["design_params"], [])
        self.assertEqual(d["components"], [])
        self.assertEqual(d["log"], [])
        self.assertEqual(d["drift"], [])
        self.assertIn("created_at", d["project"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_project_state.py -v` (or `pytest tests/test_project_state.py -v`)
Expected: FAIL — `ModuleNotFoundError: No module named 'edini.project.state'`

- [ ] **Step 3: Write minimal implementation**

Create `python3.11libs/edini/project/__init__.py`:

```python
"""Project HDA — a procedural-modeling project agent container.

See docs/superpowers/specs/2026-07-01-project-hda-design.md.
"""
```

Create `python3.11libs/edini/project/state.py`:

```python
"""Project declaration state: schema + JSON <-> hidden-parm bridge.

Pure Python (no `hou` import) so it is unit-testable with a fake node.
The declaration JSON is the knowledge graph (see spec §5). It is persisted
in a hidden string parm `STATE_PARM` on the Project HDA node.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

# Name of the hidden string parm on the Project HDA that holds the JSON.
STATE_PARM = "__edini_state"
SCHEMA_VERSION = 1


def empty_declaration(project_name: str, goal: str | None = None) -> dict:
    """Return a fresh empty declaration (the "empty project" state)."""
    return {
        "version": SCHEMA_VERSION,
        "project": {
            "name": project_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "goal": goal,
        },
        "plan": [],
        "design_params": [],
        "components": [],
        "log": [],
        "drift": [],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_project_state.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/project/__init__.py python3.11libs/edini/project/state.py tests/test_project_state.py
git commit -m "feat(project-hda): declaration schema + empty_declaration (pure python)"
```

---

## Task 2: State read from node (load_declaration)

**Files:**
- Modify: `python3.11libs/edini/project/state.py`
- Test: `tests/test_project_state.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project_state.py` (before the `__main__` block):

```python
class TestLoadDeclaration(unittest.TestCase):
    def test_load_reads_json_from_parm(self):
        from edini.project.state import empty_declaration, load_declaration, STATE_PARM
        node = _FakeNode()
        expected = empty_declaration("car")
        node.set_parm_value(STATE_PARM, json.dumps(expected))
        loaded = load_declaration(node)
        self.assertEqual(loaded["project"]["name"], "car")

    def test_load_missing_parm_returns_empty(self):
        from edini.project.state import load_declaration
        node = _FakeNode()  # no parm set
        loaded = load_declaration(node)
        self.assertIsNone(loaded["project"]["name"])

    def test_load_empty_string_returns_empty(self):
        from edini.project.state import load_declaration, STATE_PARM
        node = _FakeNode()
        node.set_parm_value(STATE_PARM, "")
        loaded = load_declaration(node)
        self.assertEqual(loaded["plan"], [])

    def test_load_corrupt_json_returns_empty(self):
        from edini.project.state import load_declaration, STATE_PARM
        node = _FakeNode()
        node.set_parm_value(STATE_PARM, "{not valid json")
        loaded = load_declaration(node)
        # Must not raise; returns a safe empty skeleton
        self.assertEqual(loaded["version"], 1)
        self.assertEqual(loaded["plan"], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_project_state.py::TestLoadDeclaration -v`
Expected: FAIL — `ImportError: cannot import name 'load_declaration'`

- [ ] **Step 3: Write minimal implementation**

Add to `python3.11libs/edini/project/state.py`:

```python
def load_declaration(node) -> dict:
    """Read the declaration JSON from the node's hidden parm.

    Returns a safe empty skeleton if the parm is absent, empty, or corrupt.
    Never raises.
    """
    parm = node.parm(STATE_PARM)
    raw = parm.eval() if parm is not None else ""
    if not raw:
        return empty_declaration(None)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or "version" not in data:
            return empty_declaration(None)
        return data
    except (json.JSONDecodeError, TypeError):
        return empty_declaration(None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_project_state.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/project/state.py tests/test_project_state.py
git commit -m "feat(project-hda): load_declaration reads JSON from hidden parm (fault-tolerant)"
```

---

## Task 3: State write to node (save_declaration)

**Files:**
- Modify: `python3.11libs/edini/project/state.py`
- Test: `tests/test_project_state.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project_state.py`:

```python
class TestSaveDeclaration(unittest.TestCase):
    def test_save_writes_json_to_parm(self):
        from edini.project.state import save_declaration, load_declaration, STATE_PARM
        node = _FakeNode()
        decl = {"version": 1, "project": {"name": "bike"}, "plan": [],
                "design_params": [], "components": [], "log": [], "drift": []}
        save_declaration(node, decl)
        # The parm now holds the JSON string
        self.assertEqual(node.parm(STATE_PARM).eval(), json.dumps(decl))
        # And round-trips back
        self.assertEqual(load_declaration(node)["project"]["name"], "bike")

    def test_save_then_load_preserves_plan(self):
        from edini.project.state import save_declaration, load_declaration, empty_declaration
        node = _FakeNode()
        decl = empty_declaration("tower")
        decl["plan"] = [{"id": "base", "title": "Base", "parent": None,
                         "status": "pending", "detail": ""}]
        save_declaration(node, decl)
        loaded = load_declaration(node)
        self.assertEqual(len(loaded["plan"]), 1)
        self.assertEqual(loaded["plan"][0]["id"], "base")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_project_state.py::TestSaveDeclaration -v`
Expected: FAIL — `ImportError: cannot import name 'save_declaration'`

- [ ] **Step 3: Write minimal implementation**

Add to `python3.11libs/edini/project/state.py`:

```python
def save_declaration(node, declaration: dict) -> None:
    """Write the declaration JSON to the node's hidden parm."""
    node.parm(STATE_PARM).set(json.dumps(declaration))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_project_state.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/project/state.py tests/test_project_state.py
git commit -m "feat(project-hda): save_declaration writes JSON to hidden parm"
```

---

## Task 4: Plan-step helpers (add_plan_step, set_step_status)

**Files:**
- Modify: `python3.11libs/edini/project/state.py`
- Test: `tests/test_project_state.py`

These helpers operate on the declaration dict in-memory (the caller persists via `save_declaration`). This is the seed of the "plan is a first-class citizen" decision (#8).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project_state.py`:

```python
class TestPlanHelpers(unittest.TestCase):
    def test_add_plan_step_appends(self):
        from edini.project.state import empty_declaration, add_plan_step
        decl = empty_declaration("x")
        add_plan_step(decl, step_id="base", title="Base", parent=None)
        self.assertEqual(len(decl["plan"]), 1)
        self.assertEqual(decl["plan"][0]["id"], "base")
        self.assertEqual(decl["plan"][0]["status"], "pending")

    def test_add_plan_step_rejects_duplicate_id(self):
        from edini.project.state import empty_declaration, add_plan_step
        decl = empty_declaration("x")
        add_plan_step(decl, step_id="base", title="Base")
        with self.assertRaises(ValueError):
            add_plan_step(decl, step_id="base", title="Base again")

    def test_add_plan_step_child_links_parent(self):
        from edini.project.state import empty_declaration, add_plan_step
        decl = empty_declaration("x")
        add_plan_step(decl, step_id="wheels", title="Wheels")
        add_plan_step(decl, step_id="wheel_fr", title="Front-right wheel",
                      parent="wheels")
        self.assertEqual(decl["plan"][1]["parent"], "wheels")

    def test_set_step_status_changes_state(self):
        from edini.project.state import empty_declaration, add_plan_step, set_step_status
        decl = empty_declaration("x")
        add_plan_step(decl, step_id="base", title="Base")
        set_step_status(decl, "base", "done")
        self.assertEqual(decl["plan"][0]["status"], "done")

    def test_set_step_status_rejects_unknown_id(self):
        from edini.project.state import empty_declaration, set_step_status
        decl = empty_declaration("x")
        with self.assertRaises(KeyError):
            set_step_status(decl, "nope", "done")

    def test_set_step_status_rejects_bad_status(self):
        from edini.project.state import empty_declaration, add_plan_step, set_step_status
        decl = empty_declaration("x")
        add_plan_step(decl, step_id="base", title="Base")
        with self.assertRaises(ValueError):
            set_step_status(decl, "base", "banana")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_project_state.py::TestPlanHelpers -v`
Expected: FAIL — `ImportError: cannot import name 'add_plan_step'`

- [ ] **Step 3: Write minimal implementation**

Add to `python3.11libs/edini/project/state.py`:

```python
_STEP_STATUSES = ("pending", "in_progress", "done", "skipped")


def add_plan_step(declaration: dict, step_id: str, title: str,
                  parent: str | None = None, detail: str = "",
                  status: str = "pending") -> dict:
    """Append a plan step to the declaration. Returns the new step.

    Raises ValueError if step_id already exists.
    """
    if any(s["id"] == step_id for s in declaration["plan"]):
        raise ValueError(f"plan step id already exists: {step_id}")
    step = {"id": step_id, "title": title, "parent": parent,
            "status": status, "detail": detail}
    declaration["plan"].append(step)
    return step


def set_step_status(declaration: dict, step_id: str, status: str) -> None:
    """Set a plan step's status. Raises KeyError if step_id unknown,
    ValueError if status not in _STEP_STATUSES."""
    if status not in _STEP_STATUSES:
        raise ValueError(f"bad status: {status}")
    for step in declaration["plan"]:
        if step["id"] == step_id:
            step["status"] = status
            return
    raise KeyError(f"unknown plan step id: {step_id}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_project_state.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/project/state.py tests/test_project_state.py
git commit -m "feat(project-hda): plan-step helpers (add_plan_step, set_step_status)"
```

---

## Task 5: Log-entry helper (append_log)

**Files:**
- Modify: `python3.11libs/edini/project/state.py`
- Test: `tests/test_project_state.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project_state.py`:

```python
class TestAppendLog(unittest.TestCase):
    def test_append_log_adds_entry(self):
        from edini.project.state import empty_declaration, append_log
        decl = empty_declaration("x")
        append_log(decl, kind="atom", summary="created chassis subnet",
                   payload={"node": "/obj/proj/chassis"}, result_ok=True)
        self.assertEqual(len(decl["log"]), 1)
        entry = decl["log"][0]
        self.assertEqual(entry["kind"], "atom")
        self.assertTrue(entry["result_ok"])
        self.assertIn("ts", entry)

    def test_append_log_preserves_order(self):
        from edini.project.state import empty_declaration, append_log
        decl = empty_declaration("x")
        append_log(decl, kind="atom", summary="first", payload={}, result_ok=True)
        append_log(decl, kind="atom", summary="second", payload={}, result_ok=True)
        self.assertEqual(decl["log"][0]["summary"], "first")
        self.assertEqual(decl["log"][1]["summary"], "second")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_project_state.py::TestAppendLog -v`
Expected: FAIL — `ImportError: cannot import name 'append_log'`

- [ ] **Step 3: Write minimal implementation**

Add to `python3.11libs/edini/project/state.py`:

```python
def append_log(declaration: dict, kind: str, summary: str,
               payload: dict | None = None, result_ok: bool = True) -> dict:
    """Append an audit/experience entry to the declaration log."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "summary": summary,
        "payload": payload or {},
        "result_ok": result_ok,
    }
    declaration["log"].append(entry)
    return entry
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_project_state.py -v`
Expected: PASS (15 tests)

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/project/state.py tests/test_project_state.py
git commit -m "feat(project-hda): append_log audit/experience entry helper"
```

---

## Task 6: Project HDA creation — hidden-parm install helper

**Files:**
- Create: `python3.11libs/edini/project/node.py`
- Test: `tests/test_project_state.py` (mock-hou pattern)

`node.py` is the **only** module in this package that touches real `hou`. It installs the hidden `__edini_state` parm onto a node. To keep it testable, we test the parm-template construction with the mock `hou` (the codebase's established pattern — see `tests/test_node_utils.py`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project_state.py`. We use the mock-hou pattern: insert mock `hou` into `sys.modules` before importing the `edini.project.node` module, in a separate test class to avoid polluting earlier tests.

```python
class TestInstallStateParm(unittest.TestCase):
    """Tests that install_state_parm builds a hidden string parm template.
    Uses the repo's mock_hou so no Houdini runtime is needed."""
    @classmethod
    def setUpClass(cls):
        # Fresh mock hou, isolated module import.
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
        from mock_hou import create_mock_hou
        cls._mock = create_mock_hou()
        cls._saved_hou = sys.modules.get("hou")
        sys.modules["hou"] = cls._mock
        # Force reimport of edini.project.node against the mock
        for _m in list(sys.modules):
            if _m.startswith("edini.project.node"):
                del sys.modules[_m]
        from edini.project.node import build_state_parm_template
        cls.build_state_parm_template = staticmethod(build_state_parm_template)

    @classmethod
    def tearDownClass(cls):
        if cls._saved_hou is not None:
            sys.modules["hou"] = cls._saved_hou
        else:
            sys.modules.pop("hou", None)

    def test_template_is_string_type(self):
        import hou
        tmpl = self.build_state_parm_template()
        self.assertEqual(tmpl.dataType(), hou.parmData.String)

    def test_template_is_hidden(self):
        tmpl = self.build_state_parm_template()
        self.assertTrue(tmpl.isHidden())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_project_state.py::TestInstallStateParm -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'edini.project.node'` (or `build_state_parm_template` not found)

- [ ] **Step 3: Write minimal implementation**

Create `python3.11libs/edini/project/node.py`:

```python
"""Project HDA node helpers — the ONLY module here that imports `hou`.

Creation, hidden-parm install, and node lookup. Real hou at runtime;
tested via tests/mock_hou.py for template construction.
"""
from __future__ import annotations

import hou  # noqa: E402  (real hou at runtime)

from .state import STATE_PARM, empty_declaration, save_declaration


def build_state_parm_template() -> hou.StringParmTemplate:
    """Build the hidden string parm template that holds the declaration JSON."""
    tmpl = hou.StringParmTemplate(STATE_PARM, "Edini State", 1)
    tmpl.setHidden(True)
    tmpl.setTags({"editor": "1"})  # multi-line string editor
    return tmpl
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_project_state.py -v`
Expected: PASS (17 tests). If the mock's `StringParmTemplate.isHidden()`/`dataType()` aren't implemented, see Step 4b.

- [ ] **Step 4b: (only if mock lacks methods) extend the mock**

If `mock_hou.py`'s `StringParmTemplate` doesn't track hidden/dataType, check `tests/mock_hou.py` for the class. If absent, add a minimal `_StringParmTemplate` in `mock_hou.py` mirroring the existing float-template mock, supporting `setHidden`/`isHidden`/`dataType`. Re-run the test. (The existing `mock_hou.py` already has parm-template mocks for floats; extend analogously. If it already has a string template with these methods, skip this step.)

- [ ] **Step 5: Commit**

```bash
git add python3.11libs/edini/project/node.py tests/test_project_state.py
git commit -m "feat(project-hda): build_state_parm_template (hidden string parm)"
```

---

## Task 7: Project HDA creation — `create_project_hda`

**Files:**
- Modify: `python3.11libs/edini/project/node.py`
- Test: manual verification (Task 10); this task adds the function + a smoke check.

`create_project_hda` creates a node of type `edini/project`, installs the state parm, and seeds it with an empty declaration. (We author the HDA type itself in Task 8.)

- [ ] **Step 1: Add the function**

Append to `python3.11libs/edini/project/node.py`:

```python
def create_project_hda(name: str = "project", parent_path: str = "/obj",
                       goal: str | None = None) -> "hou.Node":
    """Create a Project HDA node and seed it with an empty declaration.

    The node type `edini::project` must already be registered (via
    HOUDINI_OTLSCAN_PATH pointing at otls/edini_project.hda).
    """
    parent = hou.node(parent_path)
    if parent is None:
        raise ValueError(f"parent not found: {parent_path}")
    node = parent.createNode("edini::project", node_name=name)

    # Install the hidden state parm via the node's spare-parm group,
    # then seed the declaration JSON.
    grp = node.spareParmGroup()
    grp.appendToFolder("Spare", build_state_parm_template())
    node.setSpareParmGroup(grp)

    declaration = empty_declaration(project_name=name, goal=goal)
    save_declaration(node, declaration)
    return node
```

- [ ] **Step 2: Smoke-check the import**

Run: `python -c "import sys; sys.path.insert(0,'python3.11libs'); from tests.mock_hou import create_mock_hou; sys.modules['hou']=create_mock_hou(); import edini.project.node as n; print(hasattr(n,'create_project_hda'))"` from the repo root.
Expected: prints `True` (the function exists and imports cleanly under mock hou). Real-Houdini verification happens in Task 10.

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/project/node.py
git commit -m "feat(project-hda): create_project_hda (create node + seed declaration)"
```

---

## Task 8: Author the `edini::project` HDA definition

**Files:**
- Create: `scripts/make_project_hda.py`
- Create: `otls/edini_project.hda` (generated)

This is a **one-shot authoring script** (modeled on `scripts/rebuild_hda_with_button.py` and `recipe_library.py:1964`). It creates a subnet digital asset named `edini::project`, saves it to `otls/edini_project.hda`. Run once via hython; the `.hda` is committed (like `edini_recipe_manager.hda`) and auto-loaded via `HOUDINI_OTLSCAN_PATH`.

- [ ] **Step 1: Write the authoring script**

Create `scripts/make_project_hda.py`:

```python
"""One-shot: author the edini::project HDA definition.

Run ONCE via hython to (re)generate otls/edini_project.hda:
    hython scripts/make_project_hda.py

The .hda is committed to the repo and auto-loaded by Houdini via
HOUDINI_OTLSCAN_PATH ($EDINI_PATH/otls). Do NOT run at Houdini startup.
"""
import os
import hou


def main() -> None:
    otls_dir = os.path.join(os.path.dirname(__file__), "..", "otls")
    os.makedirs(otls_dir, exist_ok=True)
    hda_file = os.path.join(otls_dir, "edini_project.hda")

    # Clean any pre-existing temp node.
    obj = hou.node("/obj")
    tmp = obj.createNode("subnet", "edini_project_author_tmp")
    try:
        # Create the digital asset from the subnet.
        tmp.createDigitalAsset(
            name="edini::project",
            hda_file_name=hda_file,
            description="Edini Project — a procedural-modeling project agent container",
        )
        d = tmp.type().definition()
        # Minimal default parms: none. The hidden __edini_state parm and
        # design params are added per-instance at runtime by create_project_hda.
        d.save(hda_file)
    finally:
        tmp.destroy()

    print(f"[ok] wrote {hda_file}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it via hython to generate the .hda**

Run: `"D:\houdini\bin\hython.exe" scripts/make_project_hda.py` (adjust path if `EDINI_HYTHON` differs; the test harness uses `D:\houdini`).
Expected: prints `[ok] wrote <repo>/otls/edini_project.hda`. Verify: `ls -la otls/edini_project.hda` shows a non-empty file (typically >1KB).

- [ ] **Step 3: Verify the type loads in a fresh hython**

Run:
```bash
"D:\houdini\bin\hython.exe" -c "import hou; hou.hda.installFile('otls/edini_project.hda'); print([t.name() for t in hou.nodeTypeCategories()['Object'].nodeTypes().values() if 'edini' in t.name()])"
```
Expected: prints a list containing `edini::project` (e.g. `['edini::project', ...]`).

- [ ] **Step 4: Commit**

```bash
git add scripts/make_project_hda.py otls/edini_project.hda
git commit -m "feat(project-hda): edini::project HDA definition + authoring script"
```

---

## Task 9: Panel widget skeleton (PySide QWidget, three placeholders)

**Files:**
- Create: `python3.11libs/edini/project/panel/__init__.py`
- Create: `python3.11libs/edini/project/panel/project_widget.py`

This is the three-column layout from spec §6.2 in its minimal form: a project selector (dropdown) at top, and three placeholder columns (Plan / Chat / State). Real chat wiring is Task 11. This task only builds the static layout, reused from `edini.ui.theme`.

- [ ] **Step 1: Create the panel package init**

Create `python3.11libs/edini/project/panel/__init__.py`:

```python
"""Project HDA embedded PySide panel (Houdini Python Panel)."""
```

- [ ] **Step 2: Write the widget**

Create `python3.11libs/edini/project/panel/project_widget.py`:

```python
"""ProjectPanelWidget — the embedded widget for a Project HDA.

Three-column layout (Plan | Chat | State) per spec §6.2. Minimal-loop
version: project selector + placeholder columns. Reuses edini.ui.theme.
"""
from __future__ import annotations

from PySide2 import QtCore, QtWidgets
# NOTE: Houdini 21 ships PySide2. If your Houdini uses PySide6, swap the import;
# the Qt API used here is identical between PySide2 and PySide6.

from edini.ui.theme import apply_theme, accent_color, fs


class ProjectPanelWidget(QtWidgets.QWidget):
    """The root widget shown inside the Houdini Python Pane tab."""

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._bound_node_path: str | None = None
        self._build_ui()

    # --- UI construction -------------------------------------------------

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # Top bar: project selector + status.
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Project:"))
        self.project_combo = QtWidgets.QComboBox()
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top.addWidget(self.project_combo, 1)
        self.status_label = QtWidgets.QLabel("disconnected")
        top.addWidget(self.status_label)
        root.addLayout(top)

        # Three columns.
        cols = QtWidgets.QHBoxLayout()
        self.plan_column = self._placeholder("Plan Tree\n(plan)")
        self.chat_column = self._placeholder("Chat\n(timeline)")
        self.state_column = self._placeholder("State + Graph\n(statistics)")
        cols.addWidget(self.plan_column, 1)
        cols.addWidget(self.chat_column, 2)
        cols.addWidget(self.state_column, 1)
        root.addLayout(cols, 1)

        apply_theme(self)

    def _placeholder(self, text: str) -> QtWidgets.QFrame:
        f = QtWidgets.QFrame()
        f.setFrameShape(QtWidgets.QFrame.StyledPanel)
        lay = QtWidgets.QVBoxLayout(f)
        lbl = QtWidgets.QLabel(text)
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        lay.addWidget(lbl)
        return f

    # --- Project binding -------------------------------------------------

    def refresh_project_list(self) -> None:
        """Populate the dropdown with all edini::project nodes in the scene."""
        import hou
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        nodes = hou.nodeType("/obj", "edini::project").instances()
        for n in nodes:
            self.project_combo.addItem(n.path(), userData=n.path())
        self.project_combo.blockSignals(False)
        if self.project_combo.count():
            self._bind(self.project_combo.itemData(0))

    def _on_project_changed(self, _idx: int) -> None:
        path = self.project_combo.currentData()
        if path:
            self._bind(path)

    def _bind(self, node_path: str) -> None:
        self._bound_node_path = node_path
        self.status_label.setText(f"bound: {node_path}")

    @property
    def bound_node_path(self) -> str | None:
        return self._bound_node_path
```

> **PySide2 vs PySide6 note:** Houdini 21 ships **PySide2**. The existing `edini.ui` imports `from PySide2 import ...`. Match that. If a future Houdini moves to PySide6, only the import line changes; the `QtWidgets`/`QtCore` API used here is identical.

- [ ] **Step 3: Commit (no automated test — manual verification in Task 10)**

```bash
git add python3.11libs/edini/project/panel/__init__.py python3.11libs/edini/project/panel/project_widget.py
git commit -m "feat(project-hda): ProjectPanelWidget three-column skeleton + project selector"
```

---

## Task 10: Python Panel `.pypanel` registration + end-to-end manual test

**Files:**
- Create: `python3.11libs/edini/project/panel/project_pane.py`
- Create: `python3.11libs/edini/project/edini_project.pypanel`
- Modify: `scripts/install.py` (register the pypanel search path)

The `.pypanel` XML (format per Shotgun `tk-houdini` reference + SideFX docs) defines an `<interface>` whose `<script>` creates a `hou.pypanel.PythonPanelInterface` subclass. That subclass's `createInterface()` returns the `ProjectPanelWidget`.

- [x] **Step 1: Write the PythonPanelInterface subclass** ✅ CORRECTED during verification

> **VERIFICATION CORRECTION (2026-07-02, real-hython):** The original plan below
> assumed `hou.pypanel.PythonPanelInterface` is a base class to subclass, and that
> the `.pypanel` `<script>` must define an `interface` object. **Both are wrong.**
> `hou.pypanel` has no classes (only functions); `hou.PythonPanelInterface` exists
> but is a metadata class, not meant for subclassing. The real pattern (see
> Houdini's shipped `BookmarksEditor.pypanel`): the `<script>` defines (or imports)
> a **module-level function `onCreateInterface()`** that builds and **returns** the
> root QWidget. Houdini calls it per pane-tab. No class, no `createInterface`
> method, no `kwargs`. Also PySide**6** not PySide2 on Houdini 21.

Create `python3.11libs/edini/project/panel/project_pane.py`:

```python
"""PythonPanelInterface for the Project HDA panel.

Houdini's Python Panel system instantiates this and calls createInterface()
to get the widget shown in the pane tab.
"""
from __future__ import annotations

import hou
from PySide2 import QtWidgets

from edini.project.panel.project_widget import ProjectPanelWidget


class ProjectPanelInterface(hou.pypanel.PythonPanelInterface):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._widget: ProjectPanelWidget | None = None

    def createInterface(self) -> QtWidgets.QWidget:
        self._widget = ProjectPanelWidget(self.parent())
        self._widget.refresh_project_list()
        return self._widget
```

- [ ] **Step 2: Write the `.pypanel` XML**

Create `python3.11libs/edini/project/edini_project.pypanel`:

```xml
<?xml version='1.0' encoding='UTF-8'?>
<pythonPanelDocument>
  <interface name="edini_project" label="Edini Project" icon="MISC_python">
    <script><![CDATA[
from edini.project.panel.project_pane import ProjectPanelInterface
interface = ProjectPanelInterface(**kwargs)
]]></script>
  </interface>
  <interfacesMenu type="toolbar"><interfaceItem name="edini_project" /></interfacesMenu>
  <interfacesMenu type="panetab"><interfaceItem name="edini_project" /></interfacesMenu>
</pythonPanelDocument>
```

> The `<script>` is evaluated with `kwargs` in scope (Houdini's convention). It must define `interface` as a `PythonPanelInterface` instance.

- [x] **Step 3: Register the pypanel search path in install.py** ✅ CORRECTED during verification

> **VERIFICATION CORRECTION (2026-07-02, real-hython):** The original plan below
> used a `"python_panels"` key inside the `"houdini"` block of the package JSON.
> **That key does not exist** — Houdini does not read it, so the pane never
> appeared. The correct mechanism is the environment variable
> **`HOUDINI_PYTHON_PANEL_PATH`** set in the package `env` block, pointing at a
> directory containing the `.pypanel` file. Additionally the `.pypanel` file was
> moved from `python3.11libs/edini/project/` to `python_panels/` at the repo
> root (mirroring Houdini's own `HFS/houdini/python_panels/` convention).
> Verified via `hou.pypanel.installFile()` + `interfaceByName()` in hython.

Read `scripts/install.py` first to confirm the exact dict structure (it writes the edini package JSON). The package JSON needs a `python_panels` path entry so Houdini finds the `.pypanel`. Add to the `houdini` section of the written JSON, alongside `python3.11libs`:

Modify `scripts/install.py` — find the `json.dump({...})` call (around line 50) and add a `python_panels` key so the written dict's `"houdini"` section becomes:

```python
"houdini": {
    "python3.11libs": "$EDINI_PATH/python3.11libs",
    "python_panels": "$EDINI_PATH/python3.11libs/edini/project",
},
```

(Use `Edit` to change only the `"houdini"` dict in `install.py`. If the variable name differs, match the existing structure — the goal is that the generated edini package JSON includes `python_panels` pointing at the directory containing `edini_project.pypanel`.)

- [ ] **Step 4: Re-run install.py so Houdini picks up the new path**

Run: `python scripts/install.py` (or `hython scripts/install.py` if it needs hou).
Expected: rewrites `~/houdiniXX/packages/edini.json` with the `python_panels` entry. (User must restart Houdini for the package change to take effect.)

- [ ] **Step 5: Manual end-to-end test in Houdini** (REQUIRES real Houdini — no automation)

After restarting Houdini with the updated package:
1. In the Python Shell, run:
   ```python
   from edini.project.node import create_project_hda
   create_project_hda(name="project_car", goal="a car")
   ```
   → A `edini::project` node appears in `/obj`, with the hidden `__edini_state` parm holding the empty declaration JSON.
2. Verify the state seeded: in the Python Shell:
   ```python
   import hou, json
   n = hou.node("/obj/project_car")
   print(json.loads(n.parm("__edini_state").eval())["project"]["name"])
   ```
   → prints `project_car`.
3. Open a Python Pane (New Pane Tab Type → Edini Project). The panel shows the three-column skeleton.
4. The project dropdown lists `/obj/project_car`; selecting it sets the status label to `bound: /obj/project_car`.

If any step fails, note the exact error; this is the integration point most likely to reveal environment issues (package path, PySide2 vs 6, `.pypanel` syntax).

- [ ] **Step 6: Commit**

```bash
git add python3.11libs/edini/project/panel/project_pane.py python3.11libs/edini/project/edini_project.pypanel scripts/install.py
git commit -m "feat(project-hda): Python Panel registration (.pypanel) + install path"
```

---

## Task 11: Wire chat into the panel (reuse singleton RpcClient)

**Files:**
- Modify: `python3.11libs/edini/project/panel/project_widget.py`

This is the heart of the minimal loop: typing in the panel reaches the LLM and the reply streams back. Per spec §10, **reuse the existing singleton `RpcClient`** (from `edini.ui.windows._main_window._rpc_client`) rather than spawning a new Pi subprocess — spawning per-HDA would collide on port 9876. Each bound project gets its own Pi **session** via `send_new_session`/`send_switch_session`.

- [ ] **Step 1: Replace the chat-column placeholder with a real chat timeline + input**

Read the current `project_widget.py` (from Task 9). Modify `_build_ui` so the chat column is no longer a placeholder but a vertical box containing a timeline (reusing `_TimelineView` from `edini.ui.agent_panel`) and an input box. Use `Edit` to replace `self.chat_column = self._placeholder(...)` with:

```python
        # Chat column: reuse the existing timeline + bubbles from edini.ui.
        from edini.ui.agent_panel import _TimelineView, _AiBubble, _UserBubble
        self.chat_column = QtWidgets.QFrame()
        cl = QtWidgets.QVBoxLayout(self.chat_column)
        cl.setContentsMargins(0, 0, 0, 0)
        self.timeline = _TimelineView()
        cl.addWidget(self.timeline, 1)
        self.input_edit = QtWidgets.QPlainTextEdit()
        self.input_edit.setFixedHeight(56)
        self.input_edit.keyPressEvent = self._on_input_key  # Enter to send
        cl.addWidget(self.input_edit)
```

- [ ] **Step 2: Add the send + stream-back wiring**

Add these methods to `ProjectPanelWidget` (after `_bind`):

```python
    def _get_rpc(self):
        """Return the singleton RpcClient from the main chat window.

        Reuses the already-running Pi subprocess + HTTP server. Never spawns
        a new one (would collide on port 9876). If the main window isn't open
        yet, open it (which bootstraps the agent).
        """
        from edini.ui.windows import open_chat_window
        win = open_chat_window()
        return win._rpc_client

    def _on_input_key(self, event):
        from PySide2 import QtCore, QtGui
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) \
           and not (event.modifiers() & (QtCore.Qt.ShiftModifier | QtCore.Qt.ControlModifier)):
            self._send()
            return
        QtWidgets.QPlainTextEdit.keyPressEvent(self.input_edit, event)

    def _send(self) -> None:
        text = self.input_edit.toPlainText().strip()
        if not text or self._bound_node_path is None:
            return
        self.input_edit.clear()
        # Show the user's message immediately.
        from edini.ui.agent_panel import _UserBubble
        self.timeline.add_widget(_UserBubble(text))
        # Drive the LLM via the shared RpcClient; each project gets its own
        # Pi session, named after the bound node path.
        rpc = self._get_rpc()
        rpc.send_set_session_name(self._bound_node_path)
        # Connect streaming once: route text deltas into a fresh AI bubble.
        if not getattr(self, "_stream_wired", False):
            rpc.text_delta.connect(self._on_stream_delta)
            rpc.agent_finished.connect(self._on_turn_done)
            self._stream_wired = True
        rpc.send_prompt(text)

    def _on_stream_delta(self, chunk: str) -> None:
        # Mirrors edini.ui.agent_panel.AgentPanel.append_stream_chunk:
        # accumulate full text, call update_streaming(full_text). The AiBubble
        # itself has no .text(); read back via get_raw_text().
        from edini.ui.agent_panel import _AiBubble
        if not hasattr(self, "_current_ai") or self._current_ai is None:
            self._current_ai = _AiBubble()
            self.timeline.add_widget(self._current_ai)
        full = self._current_ai.get_raw_text() + chunk
        self._current_ai.update_streaming(full)

    def _on_turn_done(self) -> None:
        if getattr(self, "_current_ai", None) is not None:
            self._current_ai.finalize()
            self._current_ai = None
```

> **Signal-name check:** the existing `RpcClient` emits `text_delta(str)` and `agent_finished` (from the research, `_RpcWorker` dispatches these and `RpcClient` re-emits them). If the actual signal names differ slightly (e.g. `completed` instead of `agent_finished`), match `edini.ui.main_window._bind_events` exactly — read that method's connect lines and use the same names. Confirmed against source: `_AiBubble.update_streaming(full_text)` takes the **accumulated full text** (verified `agent_panel.py:321`), and `_AiBubble.get_raw_text()` reads back the accumulation (`agent_panel.py:328`). The delta handler above mirrors `AgentPanel.append_stream_chunk` (`agent_panel.py:1247`).

- [ ] **Step 3: Manual end-to-end chat test** (REQUIRES real Houdini + configured LLM)

1. Restart Houdini. Open the Edini Project pane.
2. Create a project: `from edini.project.node import create_project_hda; create_project_hda(name="project_test")`.
3. Select it in the panel dropdown.
4. Type "hello" + Enter. Expect: a user bubble appears, then an AI bubble streams a reply.
5. Confirm the main Edini chat window also opened (that's expected — it owns the shared Pi process).

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/project/panel/project_widget.py
git commit -m "feat(project-hda): wire chat via shared singleton RpcClient (per-project session)"
```

---

## Task 12 (OPTIONAL): Agent-side `project_hda_create` tool

**Files:**
- Create: `pi-extensions/edini-tools/tools/project_hda.ts`
- Modify: `pi-extensions/edini-tools/index.ts`
- Modify: `python3.11libs/edini/tool_executor.py`

This lets the LLM create a Project HDA itself. Optional for the minimal loop (the user can create it from the Python Shell), but completes the "agent can spawn projects" path. Skip if you want the loop even leaner.

- [ ] **Step 1: Write the TS tool**

Create `pi-extensions/edini-tools/tools/project_hda.ts`:

```typescript
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

export const projectHdaTools = [
  {
    name: "project_hda_create",
    label: "Create Project HDA",
    description:
      "Create a new Edini Project HDA node — a procedural-modeling project container that " +
      "carries geometry, a knowledge-graph declaration, and a chat panel. Use this to start " +
      "a new procedural-modeling project.",
    promptSnippet: "Start a new procedural-modeling project",
    promptGuidelines: [
      "Use project_hda_create when the user wants to start a new procedural-modeling project.",
      "The returned node path is the project's identity; reference it in subsequent steps.",
    ],
    parameters: Type.Object({
      name: Type.String({ description: "Node name for the Project HDA" }),
      goal: Type.Optional(Type.String({ description: "The project's high-level goal in natural language" })),
    }),
    async execute(_id: string, params: { name: string; goal?: string }) {
      return forwardTool("project_hda_create", params);
    },
  },
];
```

- [ ] **Step 2: Register in index.ts**

Modify `pi-extensions/edini-tools/index.ts`: add `import { projectHdaTools } from "./tools/project_hda";` and add `...projectHdaTools,` to the `allTools` array.

- [ ] **Step 3: Add the Python handler**

Modify `python3.11libs/edini/tool_executor.py` — add to the `TOOL_HANDLERS` dict (around line 139):

```python
    "project_hda_create": lambda **kw: _project_hda_create(**kw),
```

And near the top imports (line 13-44 area), add:

```python
from edini.project.node import create_project_hda as _project_create


def _project_hda_create(name="project", goal=None, **_):
    try:
        node = _project_create(name=name, goal=goal)
        return {"success": True, "path": node.path(),
                "state_parm": "__edini_state"}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

- [ ] **Step 4: Manual test** — in a running Edini chat session, ask the LLM to "create a new project called project_car with goal: a car". Verify the node appears in `/obj`.

- [ ] **Step 5: Commit**

```bash
git add pi-extensions/edini-tools/tools/project_hda.ts pi-extensions/edini-tools/index.ts python3.11libs/edini/tool_executor.py
git commit -m "feat(project-hda): project_hda_create tool (agent-spawned projects)"
```

---

## Self-Review Notes

**Spec coverage (§13 minimal loop):**
- ✅ Create Project HDA with empty subnet + `__edini_state` + empty design params → Tasks 6, 7, 8.
- ✅ Panel registered as Python Pane, opens, shows three columns, project selector → Tasks 9, 10.
- ✅ Chat works: type → RpcClient → Pi → stream back → timeline render, per-project session → Task 11.
- ✅ Declaration JSON read/write, persists across panel close/reopen → Tasks 1–5 (hidden parm survives in the .hip).

**Explicitly out of this plan (per spec §2, future plans):** plan-tree interactivity (checkboxes/advance), drift detection, optimization suggestions, any modeling capability. The `state.py` plan/log helpers (Tasks 4–5) seed those futures but the UI for them is placeholder in Task 9.

**Type/name consistency check:** `STATE_PARM = "__edini_state"`, `SCHEMA_VERSION = 1` used consistently. `load_declaration`/`save_declaration`/`empty_declaration`/`add_plan_step`/`set_step_status`/`append_log`/`build_state_parm_template`/`create_project_hda` — names match across tasks. `_FakeNode` in tests has `parm(name)`/`set_parm_value(name, value)` matching what `state.py` and `node.py` call.

**Known manual-test gates:** Tasks 8, 10 (steps 5), 11 (step 3), 12 (step 4) require real Houdini and cannot be automated by the mock suite. They are flagged explicitly in-step. The pure-Python core (Tasks 1–6) is fully unit-tested.
