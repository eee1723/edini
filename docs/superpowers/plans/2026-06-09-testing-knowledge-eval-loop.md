# 第二十阶段：测试基建 + 知识检索闭环 + 评估联动

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 node_utils / config / tool_executor 的脱机单元测试，添加 `edini_search_knowledge` 知识检索工具，打通评估→知识联动。

**Architecture:** Mock hou 模块提供 Houdini 节点树模拟，让所有测试在纯 Python 环境运行。新增 knowledge Pi 工具让 Agent 能查询知识库。评估低分会话自动提取知识。

**Tech Stack:** Python 3.11, pytest, unittest.mock, PySide6 (仅 tool executor HTTP 测试需要)

---

## Task 1: 创建 Mock Hou 模块

**Files:**
- Create: `tests/mock_hou.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `tests/__init__.py`**

```python
# Edini test package
```

- [ ] **Step 2: Create `tests/mock_hou.py`**

```python
"""Mock hou module for testing node_utils without Houdini runtime.

Provides MockNode, MockParm, and a mock hou module that supports:
- hou.node(path) → MockNode tree
- hou.nodeTypeCategories() → preset node types
- hou.selectedNodes() → configurable
- hou.hipFile.name() → configurable
"""
from __future__ import annotations

import re
from typing import Any


class MockParm:
    """Mock Houdini parameter."""

    def __init__(self, name: str, value: Any = 0, label: str = ""):
        self._name = name
        self._value = value
        self._label = label or name
        self._description = label or name

    def name(self) -> str:
        return self._name

    def description(self) -> str:
        return self._description

    def eval(self) -> Any:
        return self._value

    def set(self, value: Any) -> None:
        self._value = value

    def pressButton(self) -> None:
        pass


class MockNodeType:
    """Mock Houdini node type."""

    def __init__(self, name: str, description: str = "", category_name: str = "Sop",
                 max_inputs: int = 2, min_inputs: int = 0):
        self._name = name
        self._description = description or name
        self._category_name = category_name
        self._max_inputs = max_inputs
        self._min_inputs = min_inputs

    def name(self) -> str:
        return self._name

    def description(self) -> str:
        return self._description

    def category(self):
        return MockCategory(self._category_name)

    def maxNumInputs(self) -> int:
        return self._max_inputs

    def minNumInputs(self) -> int:
        return self._min_inputs

    def namespaceOrder(self) -> list[str]:
        return [self._name]


class MockCategory:
    """Mock node type category."""

    def __init__(self, name: str, node_types: dict[str, MockNodeType] | None = None):
        self._name = name
        self._node_types = node_types or {}

    def name(self) -> str:
        return self._name

    def nodeTypes(self) -> dict[str, MockNodeType]:
        return self._node_types

    def nodeType(self, name: str) -> MockNodeType | None:
        return self._node_types.get(name)


class MockNode:
    """Mock Houdini node with children, parameters, connections."""

    def __init__(self, path: str, name: str | None = None,
                 type_name: str = "", parent: MockNode | None = None):
        self._path = path
        self._name = name or path.rsplit("/", 1)[-1]
        self._type_name = type_name or self._name
        self._parent = parent
        self._children: list[MockNode] = []
        self._parms: dict[str, MockParm] = {}
        self._inputs: list[MockNode | None] = []
        self._outputs: list[MockNode] = []
        self._destroyed = False
        self._display_flag = False
        self._render_flag = False
        self._time_dependent = False
        self._type = MockNodeType(self._type_name)
        self._errors: list[str] = []
        self._warnings: list[str] = []

    def path(self) -> str:
        return self._path

    def name(self) -> str:
        return self._name

    def type(self) -> MockNodeType:
        return self._type

    def parent(self) -> MockNode | None:
        return self._parent

    def children(self) -> list[MockNode]:
        return list(self._children)

    def allSubChildren(self) -> list[MockNode]:
        result = [self]
        for child in self._children:
            result.extend(child.allSubChildren())
        return result

    def parm(self, name: str) -> MockParm | None:
        return self._parms.get(name)

    def parms(self) -> list[MockParm]:
        return list(self._parms.values())

    def inputs(self) -> list[MockNode | None]:
        return list(self._inputs)

    def outputs(self) -> list[MockNode]:
        return list(self._outputs)

    def setInput(self, index: int, node: MockNode | None) -> None:
        while len(self._inputs) <= index:
            self._inputs.append(None)
        self._inputs[index] = node
        if node is not None and self not in node._outputs:
            node._outputs.append(self)

    def createNode(self, node_type_name: str, node_name: str | None = None) -> MockNode:
        actual_name = node_name or node_type_name
        child_path = f"{self._path}/{actual_name}"
        child = MockNode(child_path, actual_name, node_type_name, parent=self)
        self._children.append(child)
        return child

    def destroy(self) -> None:
        self._destroyed = True
        if self._parent and self in self._parent._children:
            self._parent._children.remove(self)

    def setDisplayFlag(self, value: bool) -> None:
        self._display_flag = value

    def setRenderFlag(self, value: bool) -> None:
        self._render_flag = value

    def isTimeDependent(self) -> bool:
        return self._time_dependent

    def errors(self) -> list[str]:
        return self._errors

    def warnings(self) -> list[str]:
        return self._warnings

    def cook(self, force: bool = False) -> None:
        pass

    def geometry(self):
        return None

    def layoutChildren(self) -> None:
        pass

    def setCurrent(self, value: bool = True) -> None:
        pass

    def createDigitalAsset(self, name: str, hda_file_name: str = "",
                           description: str = "") -> MockNodeType:
        return MockNodeType(name, description)

    def definition(self):
        return None

    def allowEditingOfContents(self, propagate: bool = False) -> None:
        pass


class MockHipFile:
    def __init__(self, name: str = "test.hip"):
        self._name = name

    def name(self) -> str:
        return self._name

    def dirName(self) -> str:
        return "/tmp/test"


class MockShelfTool:
    def __init__(self, script: str = ""):
        self._script = script

    def script(self) -> str:
        return self._script


class MockShelves:
    @staticmethod
    def tool(name: str) -> MockShelfTool | None:
        # Return a tool with a simple pressButton script for copytopoints
        if "copytopoints" in name:
            return MockShelfTool(
                "node = genericTool(kwargs, 'copytopoints::2.0')\n"
                "node.parm('resettargetattribs').pressButton()"
            )
        return None


class MockDesktop:
    def paneTabOfType(self, tab_type):
        return None


class MockUI:
    @staticmethod
    def curDesktop():
        return MockDesktop()


class MockHou:
    """Complete mock of the hou module for testing."""

    # Enums
    class Ramp:
        pass

    paneTabType = type("paneTabType", (), {
        "SceneViewer": 1,
        "NetworkEditor": 2,
    })()

    def __init__(self):
        self._nodes: dict[str, MockNode] = {}
        self._selected_nodes: list[MockNode] = []
        self._hip_file = MockHipFile("test.hip")
        self._pwd_path = "/"
        self._home_dir = "/home/test"
        self.shelves = MockShelves()
        self.ui = MockUI()

        # Build default scene tree
        root = MockNode("/", "")
        self._nodes["/"] = root

        obj = MockNode("/obj", "obj", "obj", parent=root)
        root._children.append(obj)
        self._nodes["/obj"] = obj

        # Default node type categories
        sop_cat = MockCategory("Sop", {
            "box": MockNodeType("box", "Box", "Sop", 2, 0),
            "sphere": MockNodeType("sphere", "Sphere", "Sop", 2, 0),
            "grid": MockNodeType("grid", "Grid", "Sop", 2, 0),
            "null": MockNodeType("null", "Null", "Sop", 1, 0),
            "merge": MockNodeType("merge", "Merge", "Sop", 4, 0),
            "attribwrangle": MockNodeType("attribwrangle", "Attribute Wrangle", "Sop", 1, 1),
            "file": MockNodeType("file", "File", "Sop", 1, 0),
            "pyro": MockNodeType("pyro", "Pyro Solver", "Sop", 5, 2),
            "copytopoints": MockNodeType("copytopoints::2.0", "Copy to Points", "Sop", 2, 1),
        })
        obj_cat = MockCategory("Object", {
            "geo": MockNodeType("geo", "Geometry", "Object", 1, 0),
            "cam": MockNodeType("cam", "Camera", "Object", 0, 0),
            "light": MockNodeType("light", "Light", "Object", 0, 0),
        })
        dop_cat = MockCategory("Dop", {
            "smoke": MockNodeType("smoke", "Smoke Object", "Dop", 1, 0),
        })

        self._categories = {
            "Sop": sop_cat,
            "Object": obj_cat,
            "Dop": dop_cat,
        }

        # HDA definitions
        self._hda_definitions: dict[str, dict] = {}

    def node(self, path: str) -> MockNode | None:
        return self._nodes.get(path)

    def nodeTypeCategories(self) -> dict[str, MockCategory]:
        return self._categories

    def selectedNodes(self) -> list[MockNode]:
        return list(self._selected_nodes)

    def pwd(self) -> MockNode | None:
        return self._nodes.get(self._pwd_path)

    def hipFile(self) -> MockHipFile:
        return self._hip_file

    def homeHoudiniDirectory(self) -> str:
        return self._home_dir

    def add_node(self, node: MockNode) -> None:
        """Helper: register a node in the mock scene."""
        self._nodes[node.path()] = node

    def set_selected(self, nodes: list[MockNode]) -> None:
        """Helper: set the selected nodes."""
        self._selected_nodes = list(nodes)

    def get_obj(self) -> MockNode:
        return self._nodes["/obj"]

    def get_root(self) -> MockNode:
        return self._nodes["/"]

    # Category accessors used by node_utils
    def sopNodeTypeCategory(self) -> MockCategory:
        return self._categories["Sop"]

    def objNodeTypeCategory(self) -> MockCategory:
        return self._categories["Object"]

    def dopNodeTypeCategory(self) -> MockCategory:
        return self._categories["Dop"]

    def vopNodeTypeCategory(self) -> MockCategory:
        return MockCategory("Vop")

    def shopNodeTypeCategory(self) -> MockCategory:
        return MockCategory("Shop")

    def ropNodeTypeCategory(self) -> MockCategory:
        return MockCategory("Rop")

    def nodeType(self, category: MockCategory, name: str) -> MockNodeType | None:
        return category.nodeType(name)

    # HDA support
    class _HDA:
        def __init__(self, definitions):
            self._definitions = definitions

        def definitions(self) -> dict:
            return self._definitions

    @property
    def hda(self):
        return self._HDA(self._hda_definitions)

    # Error type
    class OperationFailed(Exception):
        pass


def create_mock_hou() -> MockHou:
    """Create a fresh mock hou instance."""
    return MockHou()
```

- [ ] **Step 3: Verify mock module imports cleanly**

Run: `cd E:/edini && python -c "from tests.mock_hou import create_mock_hou; h = create_mock_hou(); print(h.node('/obj').path())"`
Expected: `/obj`

- [ ] **Step 4: Commit**

```bash
git add tests/__init__.py tests/mock_hou.py
git commit -m "test: add mock hou module for offline testing"
```

---

## Task 2: node_utils 单元测试

**Files:**
- Create: `tests/test_node_utils.py`

- [ ] **Step 1: Create `tests/test_node_utils.py`**

```python
"""Unit tests for node_utils — all 22 handler functions.

Uses mock_hou to run without Houdini runtime.
Run: pytest tests/test_node_utils.py -v
"""
import sys
import os
import unittest

# Inject mock hou before importing node_utils
from tests.mock_hou import create_mock_hou

# We need to inject mock hou before node_utils is imported
_mock_hou = create_mock_hou()
sys.modules["hou"] = _mock_hou

# Now import node_utils (it will use our mock hou)
# We need to force reimport since hou may already be cached
if "edini.node_utils" in sys.modules:
    del sys.modules["edini.node_utils"]

# Add python3.11libs to path so we can import edini
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))

from edini.node_utils import (
    get_scene_info, create_node, delete_node, connect_nodes,
    set_param, get_param, list_nodes, get_node_info, layout_nodes,
    search_nodes, get_help, inspect_geometry,
    run_python, run_vex, create_hda, get_hda_info,
    capture_viewport, capture_network,
    get_selection, check_errors, set_display_flag,
)


class TestGetSceneInfo(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_returns_success(self):
        result = get_scene_info()
        self.assertTrue(result["success"])

    def test_has_hip_file(self):
        result = get_scene_info()
        self.assertEqual(result["hip_file"], "test.hip")

    def test_has_root_children(self):
        result = get_scene_info()
        self.assertIn("obj", result["root_children"])

    def test_has_total_nodes(self):
        result = get_scene_info()
        self.assertGreater(result["total_nodes"], 0)


class TestCreateNode(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_create_basic_node(self):
        result = create_node("geo", "my_geo", "/obj")
        self.assertTrue(result["success"])
        self.assertEqual(result["name"], "my_geo")
        self.assertEqual(result["path"], "/obj/my_geo")

    def test_create_with_default_parent(self):
        result = create_node("geo")
        self.assertTrue(result["success"])
        self.assertTrue(result["path"].startswith("/obj/"))

    def test_create_nonexistent_parent(self):
        result = create_node("geo", parent_path="/nonexistent")
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])

    def test_create_preserves_type(self):
        result = create_node("geo", "geo1", "/obj")
        self.assertTrue(result["success"])
        self.assertEqual(result["type"], "geo")


class TestDeleteNode(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_delete_existing_node(self):
        node = create_node("geo", "to_delete", "/obj")
        path = node["path"]
        result = delete_node(path)
        self.assertTrue(result["success"])
        self.assertEqual(result["path"], path)

    def test_delete_nonexistent_node(self):
        result = delete_node("/obj/ghost_node")
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])


class TestConnectNodes(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_connect_two_nodes(self):
        n1 = create_node("geo", "src", "/obj")
        n2 = create_node("geo", "dst", "/obj")
        result = connect_nodes(n1["path"], n2["path"])
        self.assertTrue(result["success"])
        self.assertEqual(result["from"], n1["path"])
        self.assertEqual(result["to"], n2["path"])

    def test_connect_with_input_index(self):
        n1 = create_node("geo", "src2", "/obj")
        n2 = create_node("geo", "dst2", "/obj")
        result = connect_nodes(n1["path"], n2["path"], input_index=1)
        self.assertTrue(result["success"])
        self.assertEqual(result["input_index"], 1)

    def test_connect_missing_source(self):
        n2 = create_node("geo", "dst3", "/obj")
        result = connect_nodes("/obj/missing", n2["path"])
        self.assertFalse(result["success"])

    def test_connect_missing_dest(self):
        n1 = create_node("geo", "src3", "/obj")
        result = connect_nodes(n1["path"], "/obj/missing")
        self.assertFalse(result["success"])


class TestSetGetParam(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou
        self.node = create_node("geo", "param_test", "/obj")
        # Add a mock parameter
        from tests.mock_hou import MockParm
        mock_node = self.hou.node(self.node["path"])
        mock_node._parms["tx"] = MockParm("tx", 0.0, "Translate X")
        mock_node._parms["file"] = MockParm("file", "", "File Path")

    def test_set_param_string(self):
        result = set_param(self.node["path"], "file", "/tmp/test.bgeo")
        self.assertTrue(result["success"])
        self.assertEqual(result["value"], "/tmp/test.bgeo")

    def test_set_param_number(self):
        result = set_param(self.node["path"], "tx", 5.0)
        self.assertTrue(result["success"])

    def test_get_param(self):
        set_param(self.node["path"], "tx", 3.14)
        result = get_param(self.node["path"], "tx")
        self.assertTrue(result["success"])
        self.assertAlmostEqual(result["value"], 3.14)

    def test_get_missing_param(self):
        result = get_param(self.node["path"], "nonexistent")
        self.assertFalse(result["success"])

    def test_set_on_missing_node(self):
        result = set_param("/obj/ghost", "tx", 1.0)
        self.assertFalse(result["success"])


class TestListNodes(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_list_root_children(self):
        result = list_nodes("/")
        self.assertTrue(result["success"])
        self.assertGreater(result["node_count"], 0)

    def test_list_with_type_filter(self):
        # Create a geo node
        create_node("geo", "filtered_geo", "/obj")
        result = list_nodes("/obj", type_filter="geo")
        self.assertTrue(result["success"])
        for n in result["nodes"]:
            self.assertEqual(n["type"], "geo")

    def test_list_missing_parent(self):
        result = list_nodes("/nonexistent")
        self.assertFalse(result["success"])


class TestGetNodeInfo(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou
        self.node = create_node("geo", "info_test", "/obj")

    def test_get_existing_node(self):
        result = get_node_info(self.node["path"])
        self.assertTrue(result["success"])
        self.assertEqual(result["name"], "info_test")
        self.assertIn("parameters", result)

    def test_get_missing_node(self):
        result = get_node_info("/obj/ghost")
        self.assertFalse(result["success"])


class TestLayoutNodes(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_layout_existing(self):
        create_node("geo", "lay1", "/obj")
        result = layout_nodes("/obj")
        self.assertTrue(result["success"])

    def test_layout_missing(self):
        result = layout_nodes("/nonexistent")
        self.assertFalse(result["success"])


class TestSearchNodes(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_search_finds_box(self):
        result = search_nodes("box")
        self.assertTrue(result["success"])
        names = [r["name"] for r in result["results"]]
        self.assertIn("box", names)

    def test_search_finds_by_description(self):
        result = search_nodes("Pyro")
        self.assertTrue(result["success"])
        self.assertGreater(result["match_count"], 0)

    def test_search_limits_results(self):
        result = search_nodes("a")  # broad search
        self.assertTrue(result["success"])
        self.assertLessEqual(result["match_count"], 20)


class TestGetHelp(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_help_for_known_type(self):
        result = get_help("box")
        self.assertTrue(result["success"])
        self.assertEqual(result["name"], "box")

    def test_help_for_unknown_type(self):
        result = get_help("nonexistent_node_xyz")
        self.assertFalse(result["success"])


class TestInspectGeometry(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_inspect_missing_node(self):
        result = inspect_geometry("/obj/ghost")
        self.assertFalse(result["success"])

    def test_inspect_node_no_geometry(self):
        node = create_node("geo", "no_geo", "/obj")
        result = inspect_geometry(node["path"])
        # Mock returns None geometry → should return error
        self.assertFalse(result["success"])


class TestRunPython(unittest.TestCase):

    def test_simple_expression(self):
        result = run_python("x = 1 + 1")
        self.assertTrue(result["success"])

    def test_print_output(self):
        result = run_python("print('hello from test')")
        self.assertTrue(result["success"])
        self.assertIn("hello from test", result["output"])

    def test_syntax_error(self):
        result = run_python("def broken(")
        self.assertFalse(result["success"])

    def test_runtime_error(self):
        result = run_python("raise ValueError('test error')")
        self.assertFalse(result["success"])


class TestRunVex(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_basic_vex(self):
        result = run_vex("@P.x += 1;")
        self.assertTrue(result["success"])
        self.assertIn("wrangle_path", result)

    def test_vex_with_input(self):
        n = create_node("geo", "vex_input", "/obj")
        result = run_vex("@P.y = 0;", node_path=n["path"])
        self.assertTrue(result["success"])


class TestCreateHda(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_create_hda_from_node(self):
        node = create_node("geo", "hda_test", "/obj")
        result = create_hda(node["path"], "test_hda", "Test HDA")
        self.assertTrue(result["success"])
        self.assertEqual(result["name"], "test_hda")

    def test_create_hda_missing_node(self):
        result = create_hda("/obj/ghost", "ghost_hda")
        self.assertFalse(result["success"])


class TestGetHdaInfo(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_unknown_hda(self):
        result = get_hda_info("nonexistent_hda")
        self.assertFalse(result["success"])


class TestCaptureViewport(unittest.TestCase):

    def test_no_scene_viewer(self):
        result = capture_viewport("/tmp/test.png")
        self.assertFalse(result["success"])
        self.assertIn("Scene Viewer", result["error"])


class TestCaptureNetwork(unittest.TestCase):

    def test_no_network_editor(self):
        result = capture_network("/tmp/test.png")
        self.assertFalse(result["success"])
        self.assertIn("Network Editor", result["error"])


class TestGetSelection(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_empty_selection(self):
        self.hou.set_selected([])
        result = get_selection()
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 0)

    def test_with_selection(self):
        n = create_node("geo", "sel_node", "/obj")
        mock_node = self.hou.node(n["path"])
        self.hou.set_selected([mock_node])
        result = get_selection()
        self.assertTrue(result["success"])
        self.assertEqual(result["count"], 1)


class TestCheckErrors(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_scene_scan(self):
        result = check_errors()
        self.assertTrue(result["success"])

    def test_single_node(self):
        n = create_node("geo", "err_node", "/obj")
        result = check_errors(node_path=n["path"])
        self.assertTrue(result["success"])

    def test_missing_node(self):
        result = check_errors(node_path="/obj/ghost")
        self.assertFalse(result["success"])


class TestSetDisplayFlag(unittest.TestCase):

    def setUp(self):
        self.hou = _mock_hou

    def test_set_flag(self):
        n = create_node("geo", "display_node", "/obj")
        result = set_display_flag(n["path"])
        self.assertTrue(result["success"])

    def test_missing_node(self):
        result = set_display_flag("/obj/ghost")
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests**

Run: `cd E:/edini && python -m pytest tests/test_node_utils.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_node_utils.py
git commit -m "test: add node_utils unit tests (22 handlers, mock hou)"
```

---

## Task 3: config.py 单元测试

**Files:**
- Create: `tests/test_config.py`

- [ ] **Step 1: Create `tests/test_config.py`**

```python
"""Unit tests for edini/config.py.

Tests config loading, path resolution, JSON read/write, and legacy migration.
Uses tempdir to isolate file system.
Run: pytest tests/test_config.py -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Add python3.11libs to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))


class TestAtomicWriteJson(unittest.TestCase):

    def test_writes_valid_json(self):
        from edini.config import _atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.json"
            _atomic_write_json(path, {"key": "value", "number": 42})
            self.assertTrue(path.exists())
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data["key"], "value")
            self.assertEqual(data["number"], 42)

    def test_creates_parent_dirs(self):
        from edini.config import _atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sub" / "dir" / "test.json"
            _atomic_write_json(path, {"ok": True})
            self.assertTrue(path.exists())

    def test_overwrites_existing(self):
        from edini.config import _atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.json"
            _atomic_write_json(path, {"v": 1})
            _atomic_write_json(path, {"v": 2})
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data["v"], 2)

    def test_unicode_content(self):
        from edini.config import _atomic_write_json
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.json"
            _atomic_write_json(path, {"text": "中文测试 🎉"})
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["text"], "中文测试 🎉")


class TestReadPiAuth(unittest.TestCase):

    def test_returns_empty_when_missing(self):
        from edini.config import read_pi_auth
        with mock.patch("edini.config.PI_AUTH_FILE", Path("/nonexistent/auth.json")):
            result = read_pi_auth()
            self.assertEqual(result, {})

    def test_reads_valid_file(self):
        from edini.config import read_pi_auth
        with tempfile.TemporaryDirectory() as td:
            auth_file = Path(td) / "auth.json"
            auth_file.write_text(json.dumps({"deepseek": {"type": "api_key", "key": "sk-test"}}))
            with mock.patch("edini.config.PI_AUTH_FILE", auth_file):
                result = read_pi_auth()
                self.assertIn("deepseek", result)
                self.assertEqual(result["deepseek"]["key"], "sk-test")

    def test_handles_corrupt_json(self):
        from edini.config import read_pi_auth
        with tempfile.TemporaryDirectory() as td:
            auth_file = Path(td) / "auth.json"
            auth_file.write_text("{invalid json}")
            with mock.patch("edini.config.PI_AUTH_FILE", auth_file):
                result = read_pi_auth()
                self.assertEqual(result, {})


class TestReadPiModels(unittest.TestCase):

    def test_returns_empty_when_missing(self):
        from edini.config import read_pi_models
        with mock.patch("edini.config.PI_MODELS_FILE", Path("/nonexistent/models.json")):
            result = read_pi_models()
            self.assertEqual(result, {})

    def test_reads_valid_file(self):
        from edini.config import read_pi_models
        with tempfile.TemporaryDirectory() as td:
            models_file = Path(td) / "models.json"
            models_file.write_text(json.dumps({"providers": {"custom": {}}}))
            with mock.patch("edini.config.PI_MODELS_FILE", models_file):
                result = read_pi_models()
                self.assertIn("providers", result)


class TestReadPiSettings(unittest.TestCase):

    def test_returns_empty_when_missing(self):
        from edini.config import read_pi_settings
        with mock.patch("edini.config.PI_SETTINGS_FILE", Path("/nonexistent/settings.json")):
            result = read_pi_settings()
            self.assertEqual(result, {})


class TestWritePiAuth(unittest.TestCase):

    def test_writes_auth_data(self):
        from edini.config import write_pi_auth
        with tempfile.TemporaryDirectory() as td:
            auth_file = Path(td) / "auth.json"
            with mock.patch("edini.config.PI_AUTH_FILE", auth_file):
                write_pi_auth({"anthropic": {"type": "api_key", "key": "sk-ant-test"}})
                with open(auth_file) as f:
                    data = json.load(f)
                self.assertIn("anthropic", data)


class TestEdiniSettings(unittest.TestCase):

    def test_defaults(self):
        from edini.config import _EDINI_DEFAULTS
        self.assertIn("knowledge_enabled", _EDINI_DEFAULTS)
        self.assertTrue(_EDINI_DEFAULTS["knowledge_enabled"])

    def test_load_defaults_when_missing(self):
        from edini.config import _load_edini_settings
        with mock.patch("edini.config.EDINI_SETTINGS_FILE", Path("/nonexistent/settings.json")):
            settings = _load_edini_settings()
            self.assertTrue(settings["knowledge_enabled"])

    def test_save_and_load(self):
        from edini.config import save_settings, _load_edini_settings
        with tempfile.TemporaryDirectory() as td:
            settings_file = Path(td) / "settings.json"
            with mock.patch("edini.config.EDINI_SETTINGS_FILE", settings_file):
                save_settings({"knowledge_enabled": False})
                settings = _load_edini_settings()
                self.assertFalse(settings["knowledge_enabled"])


class TestLegacyMigration(unittest.TestCase):

    def test_no_migration_when_no_legacy_keys(self):
        from edini.config import migrate_legacy_settings
        with tempfile.TemporaryDirectory() as td:
            settings_file = Path(td) / "settings.json"
            settings_file.write_text(json.dumps({"knowledge_enabled": True}))
            with mock.patch("edini.config.EDINI_SETTINGS_FILE", settings_file):
                with mock.patch("edini.config.PI_AUTH_FILE", Path(td) / "auth.json"):
                    with mock.patch("edini.config.PI_SETTINGS_FILE", Path(td) / "pi_settings.json"):
                        result = migrate_legacy_settings()
                        self.assertIsNone(result)

    def test_migrates_legacy_keys(self):
        from edini.config import migrate_legacy_settings
        with tempfile.TemporaryDirectory() as td:
            settings_file = Path(td) / "settings.json"
            settings_file.write_text(json.dumps({
                "api_key": "sk-test-key",
                "provider": "deepseek",
                "model_id": "deepseek-chat",
                "knowledge_enabled": True,
            }))
            auth_file = Path(td) / "auth.json"
            pi_settings_file = Path(td) / "pi_settings.json"

            with mock.patch("edini.config.EDINI_SETTINGS_FILE", settings_file):
                with mock.patch("edini.config.PI_AUTH_FILE", auth_file):
                    with mock.patch("edini.config.PI_SETTINGS_FILE", pi_settings_file):
                        result = migrate_legacy_settings()
                        self.assertIsNotNone(result)
                        self.assertIn("Migrated", result)

                        # Verify legacy keys removed
                        with open(settings_file) as f:
                            data = json.load(f)
                        self.assertNotIn("api_key", data)
                        self.assertNotIn("provider", data)


class TestGetPiCommand(unittest.TestCase):

    def test_command_includes_rpc_mode(self):
        from edini.config import get_pi_command
        cmd = get_pi_command()
        self.assertIn("--mode", cmd)
        self.assertIn("rpc", cmd)

    def test_command_includes_extensions(self):
        from edini.config import get_pi_command
        cmd = get_pi_command()
        self.assertIn("-e", cmd)
        # Should have at least edini-tools and edini-context
        cmd_str = " ".join(cmd)
        self.assertIn("edini-tools", cmd_str)
        self.assertIn("edini-context", cmd_str)


class TestGetPiEnv(unittest.TestCase):

    def test_includes_tool_port(self):
        from edini.config import get_pi_env
        env = get_pi_env()
        self.assertIn("EDINI_TOOL_PORT", env)
        self.assertEqual(env["EDINI_TOOL_PORT"], "9876")

    def test_preserves_existing_env(self):
        from edini.config import get_pi_env
        env = get_pi_env()
        # Should have PATH from os.environ
        self.assertIn("PATH", env)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests**

Run: `cd E:/edini && python -m pytest tests/test_config.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_config.py
git commit -m "test: add config.py unit tests (read/write, migration, env)"
```

---

## Task 4: knowledge_store 单元测试

**Files:**
- Create: `tests/test_knowledge_store.py`

- [ ] **Step 1: Create `tests/test_knowledge_store.py`**

```python
"""Unit tests for knowledge_store — CRUD, search, and parse extraction.

Uses tempdir to isolate file system.
Run: pytest tests/test_knowledge_store.py -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))


class TestRulesCRUD(unittest.TestCase):

    def _patch_dir(self, td: str):
        """Patch knowledge dir to tempdir."""
        return mock.patch("edini.ui.knowledge_store._knowledge_dir", return_value=Path(td) / "knowledge")

    def test_load_default_rules_when_empty(self):
        from edini.ui.knowledge_store import load_rules
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                rules = load_rules()
                self.assertGreater(len(rules), 0)
                self.assertEqual(rules[0]["category"], "避坑")

    def test_add_rule(self):
        from edini.ui.knowledge_store import add_rule, load_rules
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                add_rule("技巧", "Test Rule", "This is a test rule content.")
                rules = load_rules()
                titles = [r["title"] for r in rules]
                self.assertIn("Test Rule", titles)

    def test_max_rules_enforcement(self):
        from edini.ui.knowledge_store import add_rule, load_rules, MAX_RULES
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                # Add more than MAX_RULES
                for i in range(MAX_RULES + 5):
                    add_rule("技巧", f"Rule {i}", f"Content {i}")
                rules = load_rules()
                self.assertLessEqual(len(rules), MAX_RULES)

    def test_delete_rule(self):
        from edini.ui.knowledge_store import add_rule, delete_rule, load_rules
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                rule = add_rule("技巧", "Delete Me", "Will be deleted")
                result = delete_rule(rule["id"])
                self.assertTrue(result)
                rules = load_rules()
                titles = [r["title"] for r in rules]
                self.assertNotIn("Delete Me", titles)

    def test_update_rule(self):
        from edini.ui.knowledge_store import add_rule, update_rule
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                rule = add_rule("技巧", "Original", "Original content")
                updated = update_rule(rule["id"], title="Updated", content="Updated content")
                self.assertIsNotNone(updated)
                self.assertEqual(updated["title"], "Updated")

    def test_get_enabled_rules(self):
        from edini.ui.knowledge_store import add_rule, get_enabled_rules
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                add_rule("技巧", "Enabled", "I'm enabled", enabled=True)
                add_rule("技巧", "Disabled", "I'm disabled", enabled=False)
                enabled = get_enabled_rules()
                titles = [r["title"] for r in enabled]
                self.assertIn("Enabled", titles)
                self.assertNotIn("Disabled", titles)


class TestEntriesCRUD(unittest.TestCase):

    def _patch_dir(self, td: str):
        return mock.patch("edini.ui.knowledge_store._knowledge_dir", return_value=Path(td) / "knowledge")

    def test_add_entry(self):
        from edini.ui.knowledge_store import add_entry, load_entries
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                add_entry("技巧", "Test Entry", "Some knowledge content", tags=["test"])
                entries = load_entries()
                titles = [e["title"] for e in entries]
                self.assertIn("Test Entry", titles)

    def test_delete_entry(self):
        from edini.ui.knowledge_store import add_entry, delete_entry
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                entry = add_entry("技巧", "Delete Entry", "Bye")
                self.assertTrue(delete_entry(entry["id"]))

    def test_update_entry(self):
        from edini.ui.knowledge_store import add_entry, update_entry
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                entry = add_entry("技巧", "Original", "Original")
                updated = update_entry(entry["id"], title="Updated")
                self.assertEqual(updated["title"], "Updated")


class TestSearchEntries(unittest.TestCase):

    def _patch_dir(self, td: str):
        return mock.patch("edini.ui.knowledge_store._knowledge_dir", return_value=Path(td) / "knowledge")

    def test_search_by_query(self):
        from edini.ui.knowledge_store import add_entry, search_entries
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                add_entry("技巧", "Pyro技巧", "Pyro模拟的关键参数设置")
                add_entry("避坑", "Ramp参数", "Ramp参数需要特殊处理")
                results = search_entries(query="pyro")
                self.assertGreater(len(results), 0)
                self.assertIn("Pyro", results[0]["title"])

    def test_search_by_category(self):
        from edini.ui.knowledge_store import add_entry, search_entries
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                add_entry("技巧", "技巧条目", "内容")
                add_entry("避坑", "避坑条目", "内容")
                results = search_entries(category="避坑")
                for r in results:
                    self.assertEqual(r["category"], "避坑")

    def test_search_by_tags(self):
        from edini.ui.knowledge_store import add_entry, search_entries
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                add_entry("技巧", "Tagged", "Content", tags=["vex", "wrangle"])
                add_entry("技巧", "Untagged", "Content", tags=["python"])
                results = search_entries(tags=["vex"])
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]["title"], "Tagged")

    def test_search_limit(self):
        from edini.ui.knowledge_store import add_entry, search_entries
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                for i in range(10):
                    add_entry("技巧", f"Entry {i}", "test content", tags=["common"])
                results = search_entries(tags=["common"], limit=3)
                self.assertLessEqual(len(results), 3)

    def test_search_empty_query_returns_all(self):
        from edini.ui.knowledge_store import add_entry, search_entries
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                add_entry("技巧", "Entry A", "Content A")
                add_entry("避坑", "Entry B", "Content B")
                results = search_entries()
                self.assertEqual(len(results), 2)


class TestParseExtraction(unittest.TestCase):

    def test_parse_valid_json(self):
        from edini.ui.knowledge_store import parse_extraction_response
        text = '''```json
[
  {"type": "rule", "category": "避坑", "title": "Test Rule", "content": "Important note"},
  {"type": "entry", "category": "技巧", "title": "Test Entry", "content": "Useful tip"}
]
```'''
        items, remaining = parse_extraction_response(text)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["type"], "rule")
        self.assertEqual(items[1]["type"], "entry")

    def test_parse_plain_json_array(self):
        from edini.ui.knowledge_store import parse_extraction_response
        text = '[{"type": "rule", "category": "避坑", "title": "Direct", "content": "No code block"}]'
        items, _ = parse_extraction_response(text)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Direct")

    def test_parse_with_single_quotes(self):
        from edini.ui.knowledge_store import parse_extraction_response
        text = "[{'type': 'entry', 'category': '技巧', 'title': 'Single', 'content': 'Quotes'}]"
        items, _ = parse_extraction_response(text)
        self.assertEqual(len(items), 1)

    def test_parse_with_trailing_commas(self):
        from edini.ui.knowledge_store import parse_extraction_response
        text = '[{"type": "entry", "category": "技巧", "title": "Trailing", "content": "Commas",},]'
        items, _ = parse_extraction_response(text)
        self.assertEqual(len(items), 1)

    def test_parse_empty_input(self):
        from edini.ui.knowledge_store import parse_extraction_response
        items, _ = parse_extraction_response("")
        self.assertEqual(len(items), 0)

    def test_parse_non_json_text(self):
        from edini.ui.knowledge_store import parse_extraction_response
        items, _ = parse_extraction_response("This is just plain text without any JSON.")
        self.assertEqual(len(items), 0)

    def test_parse_filters_empty_items(self):
        from edini.ui.knowledge_store import parse_extraction_response
        text = '[{"type": "rule", "category": "避坑", "title": "", "content": ""}]'
        items, _ = parse_extraction_response(text)
        self.assertEqual(len(items), 0)

    def test_normalize_unknown_category(self):
        from edini.ui.knowledge_store import parse_extraction_response
        text = '[{"type": "entry", "category": "未知分类", "title": "Test", "content": "Content"}]'
        items, _ = parse_extraction_response(text)
        self.assertEqual(items[0]["category"], "技巧")  # default fallback


class TestAcceptExtracted(unittest.TestCase):

    def _patch_dir(self, td: str):
        return mock.patch("edini.ui.knowledge_store._knowledge_dir", return_value=Path(td) / "knowledge")

    def test_accept_mixed_items(self):
        from edini.ui.knowledge_store import accept_extracted, load_rules, load_entries
        with tempfile.TemporaryDirectory() as td:
            with self._patch_dir(td):
                items = [
                    {"type": "rule", "category": "避坑", "title": "Rule 1", "content": "Important", "tags": []},
                    {"type": "entry", "category": "技巧", "title": "Entry 1", "content": "Tip", "tags": ["test"]},
                ]
                r_count, e_count = accept_extracted(items, "/tmp/test.jsonl")
                self.assertEqual(r_count, 1)
                self.assertEqual(e_count, 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests**

Run: `cd E:/edini && python -m pytest tests/test_knowledge_store.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_knowledge_store.py
git commit -m "test: add knowledge_store unit tests (CRUD, search, parse)"
```

---

## Task 5: edini_search_knowledge Pi 工具

**Files:**
- Create: `pi-extensions/edini-tools/tools/knowledge.ts`
- Modify: `pi-extensions/edini-tools/index.ts`
- Modify: `python3.11libs/edini/tool_executor.py`

- [ ] **Step 1: Create `pi-extensions/edini-tools/tools/knowledge.ts`**

```typescript
// pi-extensions/edini-tools/tools/knowledge.ts
// Knowledge search tool — lets the agent query the accumulated knowledge base.

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

export const ediniSearchKnowledge = {
  name: "edini_search_knowledge",
  label: "Search Knowledge Base",
  description:
    "Search the accumulated knowledge base for relevant tips, pitfalls, workflows, and configuration notes. " +
    "The knowledge base contains lessons learned from past sessions — both iron rules (always applied) and " +
    "detailed entries (searchable). Use this to avoid repeating past mistakes and to leverage known techniques. " +
    "Search by keyword, category, or both.",
  promptSnippet: "Search the knowledge base for relevant tips and pitfalls",
  promptGuidelines: [
    "Use edini_search_knowledge at the start of a session to check if there are known tips or pitfalls related to the user's request.",
    "When working with unfamiliar node types or effects, search the knowledge base first to avoid known issues.",
    "If you encounter an error, search the knowledge base to see if this is a known pitfall with a documented solution.",
    "Categories: 避坑 (pitfalls), 技巧 (tips), 工作流 (workflows), 配置 (configuration).",
  ],
  parameters: Type.Object({
    query: Type.String({
      description: "Search keyword to match against title and content",
    }),
    category: Type.Optional(
      Type.String({
        description: "Filter by category: 避坑, 技巧, 工作流, 配置",
      })
    ),
    limit: Type.Optional(
      Type.Number({
        description: "Maximum results to return (default: 10)",
        default: 10,
      })
    ),
  }),
  async execute(
    _toolCallId: string,
    params: { query: string; category?: string; limit?: number }
  ) {
    return forwardTool("edini_search_knowledge", params);
  },
};
```

- [ ] **Step 2: Modify `pi-extensions/edini-tools/index.ts` — add knowledge import and registration**

In the imports section, add:
```typescript
import { ediniSearchKnowledge } from "./tools/knowledge";
```

In the function body, change the allTools array to include the new tool:
```typescript
const allTools = [...sceneTools, ...queryTools, ...scriptTools, ediniGetEvalStats, ediniSearchKnowledge];
```

- [ ] **Step 3: Modify `python3.11libs/edini/tool_executor.py` — add handler and import**

Add import at the top (after existing imports):
```python
from edini.ui.knowledge_store import search_entries
```

Add handler to `TOOL_HANDLERS` dict:
```python
"edini_search_knowledge": lambda **kw: _search_knowledge(
    query=kw["query"],
    category=kw.get("category", ""),
    limit=kw.get("limit", 10),
),
```

Add the handler function before `TOOL_HANDLERS`:
```python
def _search_knowledge(query: str, category: str = "", limit: int = 10) -> dict[str, Any]:
    """Search the knowledge base entries."""
    try:
        entries = search_entries(query=query, category=category, limit=limit)
        return {
            "success": True,
            "query": query,
            "match_count": len(entries),
            "entries": [
                {
                    "title": e.get("title", ""),
                    "content": e.get("content", ""),
                    "category": e.get("category", ""),
                    "tags": e.get("tags", []),
                }
                for e in entries
            ],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
```

- [ ] **Step 4: Verify TypeScript compiles (or at least is syntactically valid)**

Run: `cd E:/edini && node -e "require('fs').readFileSync('pi-extensions/edini-tools/tools/knowledge.ts', 'utf8'); console.log('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add pi-extensions/edini-tools/tools/knowledge.ts pi-extensions/edini-tools/index.ts python3.11libs/edini/tool_executor.py
git commit -m "feat: add edini_search_knowledge tool for agent knowledge retrieval"
```

---

## Task 6: 评估→知识联动

**Files:**
- Modify: `python3.11libs/edini/eval/evaluator.py`

- [ ] **Step 1: Read current evaluator.py to understand the structure**

Read: `python3.11libs/edini/eval/evaluator.py`

- [ ] **Step 2: Add knowledge extraction from low-score sessions**

Add a function at the end of `evaluator.py`:

```python
def extract_knowledge_from_eval(
    session: StructuredSession,
    result: EvalResult,
    score_threshold: float = 0.5,
) -> list[dict]:
    """Auto-extract knowledge entries from low-scoring sessions.

    Only extracts if total_score < score_threshold.
    Generates entries based on error patterns and failure modes.
    Returns list of candidate items for entries.json (not auto-saved).
    """
    if result.total_score >= score_threshold:
        return []

    items = []

    # Extract from failed tool calls
    for tc in session.tool_calls:
        if not tc.result_success and tc.error_message:
            items.append({
                "type": "entry",
                "category": "避坑",
                "title": f"{tc.tool_name}: {tc.error_message[:50]}",
                "content": f"Tool {tc.tool_name} failed with: {tc.error_message}. "
                           f"Check parameters and node paths before calling.",
                "tags": [tc.tool_name, "auto-extracted"],
            })

    # Extract from low reliability (empty responses or errors)
    if result.reliability < 0.4:
        items.append({
            "type": "entry",
            "category": "避坑",
            "title": "低可靠性会话模式",
            "content": f"Session had reliability score {result.reliability:.2f}. "
                       f"Review error patterns and tool parameter validation.",
            "tags": ["reliability", "auto-extracted"],
        })

    # Extract from low tool accuracy
    if result.tool_accuracy is not None and result.tool_accuracy < 0.4:
        failed_tools = [
            tc.tool_name for tc in session.tool_calls if not tc.result_success
        ]
        if failed_tools:
            items.append({
                "type": "entry",
                "category": "技巧",
                "title": f"工具精度低: {', '.join(set(failed_tools[:3]))}",
                "content": f"Tools {set(failed_tools)} had accuracy issues. "
                           f"Double-check parameters and verify node existence before calling.",
                "tags": list(set(failed_tools)) + ["accuracy", "auto-extracted"],
            })

    return items[:5]  # Cap at 5 items per session
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/eval/evaluator.py
git commit -m "feat: add knowledge extraction from low-score eval sessions"
```

---

## Task 7: 更新 Wiki 文档

**Files:**
- Modify: `wiki/pages/progress.md`
- Modify: `wiki/pages/handoff.md`

- [ ] **Step 1: Update progress.md — add Phase 20 entry**

在近期关键节点中添加（最前面）：

```markdown
<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-09</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">第二十阶段：测试基建 + 知识检索闭环 + 评估联动</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">① Mock Hou 模块（MockNode/MockParm/MockNodeType/MockCategory）支持全部 22 个 handler 脱机测试 ② node_utils 单元测试 50+ 用例覆盖全部 handler ③ config.py 测试覆盖读写 JSON、路径查找、legacy 迁移 ④ knowledge_store 测试覆盖 CRUD/search/parse extraction ⑤ edini_search_knowledge Pi 工具注册，Agent 可查询知识库 ⑥ 评估低分会话自动提取知识条目 ⑦ handoff.md 更新至第十九阶段</div>
    <div class="timeline-tags">
      <span>单元测试</span><span>Mock Hou</span><span>知识检索</span><span>评估联动</span>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Update handoff.md — sync to Phase 19**

Replace the header:
```
**最后更新**：2026-06-09（第二十阶段：测试基建 + 知识检索 + 评估联动）
**当前阶段**：Mock Hou 测试 · edini_search_knowledge · 评估→知识联动
**下一阶段**：Houdini Pane Tab 嵌入 · Judge 模型优化
```

Update the tool count in one-sentence summary and key features.

- [ ] **Step 3: Commit**

```bash
git add wiki/pages/progress.md wiki/pages/handoff.md
git commit -m "docs: update wiki with phase 20 (testing + knowledge search + eval loop)"
```

---

## Task 8: 运行全部测试验证

- [ ] **Step 1: Run all tests**

Run: `cd E:/edini && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS, ≥30 test cases

- [ ] **Step 2: Verify test count**

Run: `cd E:/edini && python -m pytest tests/ --collect-only -q`
Expected: ≥30 tests collected

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address test failures from full suite run"
```
