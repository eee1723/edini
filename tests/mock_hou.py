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

    def definition(self):
        return None


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


class MockAttrib:
    def __init__(self, name: str, data_type: str = "Float"):
        self._name = name
        self._data_type = data_type

    def name(self) -> str:
        return self._name

    def dataType(self) -> str:
        return self._data_type


class MockPoint:
    """Mock Houdini point for builder-mode geometry."""

    def __init__(self):
        self._pos = (0.0, 0.0, 0.0)
        self._attribs: dict[str, Any] = {}

    def setPosition(self, pos):
        self._pos = (float(pos[0]), float(pos[1]), float(pos[2]))

    def position(self):
        return self._pos

    def setAttribValue(self, name: str, value: Any) -> None:
        self._attribs[name] = value

    def attribValue(self, name: str) -> Any:
        return self._attribs.get(name)


class MockPrim:
    """Mock Houdini primitive for builder-mode geometry."""

    def __init__(self):
        self._vertices: list[MockPoint] = []
        self._attribs: dict[str, Any] = {}

    def addVertex(self, pt: MockPoint) -> None:
        self._vertices.append(pt)

    def vertices(self) -> list[MockPoint]:
        return list(self._vertices)

    def setAttribValue(self, name: str, value: Any) -> None:
        self._attribs[name] = value

    def attribValue(self, name: str) -> Any:
        return self._attribs.get(name)


class MockBoundingBox:
    def __init__(self, bounds: tuple[float, float, float, float, float, float]):
        self._bounds = bounds

    def minvec(self):
        return (self._bounds[0], self._bounds[2], self._bounds[4])

    def maxvec(self):
        return (self._bounds[1], self._bounds[3], self._bounds[5])


class MockGeometry:
    """Mock Houdini geometry supporting both stats-mode and builder-mode.

    Stats-mode (constructor): pass fixed point_count/prim_count/bounds.
    Builder-mode (createPoint/createPolygon): mutable geometry built incrementally.
    """

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
        self._builder_mode = False
        self._points: list[MockPoint] = []
        self._prims: list[MockPrim] = []
        self._builder_attribs: dict[str, Any] = {}

    def clear(self) -> None:
        """Clear geometry and switch to builder mode."""
        self._builder_mode = True
        self._points.clear()
        self._prims.clear()
        self._point_count = 0
        self._prim_count = 0
        self._vertex_count = 0

    def addAttrib(self, attrib_type, name: str, default_value: Any) -> None:
        """Add an attribute (no-op in mock but tracked)."""
        self._builder_attribs[name] = default_value

    def createPoint(self) -> MockPoint:
        """Create a point in builder mode."""
        self._builder_mode = True
        pt = MockPoint()
        self._points.append(pt)
        self._point_count = len(self._points)
        return pt

    def createPolygon(self) -> MockPrim:
        """Create a polygon in builder mode."""
        self._builder_mode = True
        prim = MockPrim()
        self._prims.append(prim)
        self._prim_count = len(self._prims)
        return prim

    def points(self) -> list[MockPoint]:
        return list(self._points)

    def prims(self) -> list[MockPrim]:
        return list(self._prims)

    def intrinsicValue(self, name: str):
        if name == "pointcount":
            return self._point_count
        if name == "primitivecount":
            return self._prim_count
        if name == "vertexcount":
            return self._vertex_count
        if name == "bounds":
            if self._builder_mode and self._points:
                # Compute bounds from builder points
                xs = [p.position()[0] for p in self._points]
                ys = [p.position()[1] for p in self._points]
                zs = [p.position()[2] for p in self._points]
                return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))
            return self._bounds
        raise KeyError(name)

    def boundingBox(self):
        b = self.intrinsicValue("bounds")
        if b is None:
            return None
        return MockBoundingBox(b)

    def pointAttribs(self):
        return [MockAttrib("P")]

    def primAttribs(self):
        return []

    def vertexAttribs(self):
        return []

    def globalAttribs(self):
        return []


class MockNode:
    """Mock Houdini node with children, parameters, connections."""

    # Class-level reference to the MockHou instance, set during create_mock_hou()
    _hou_ref: "MockHou | None" = None

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
        self._geometry = None

    def path(self) -> str:
        return self._path

    def name(self) -> str:
        return self._name

    def setName(self, name: str, unique_name: bool = False) -> None:
        old_paths = {node: node._path for node in self.allSubChildren()}
        self._name = name

        def refresh_path(node: MockNode) -> None:
            parent_path = node._parent.path() if node._parent else ""
            if parent_path and parent_path != "/":
                node._path = f"{parent_path}/{node._name}"
            else:
                node._path = f"/{node._name}"
            for child in node._children:
                refresh_path(child)

        refresh_path(self)
        if MockNode._hou_ref is not None:
            for old_path in old_paths.values():
                MockNode._hou_ref._nodes.pop(old_path, None)
            for node in self.allSubChildren():
                MockNode._hou_ref._nodes[node._path] = node

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
        # Auto-create known parms for specific node types
        if node_type_name == "attribwrangle":
            child._parms["snippet"] = MockParm("snippet", "")
            child._parms["snippet_attribname"] = MockParm("snippet_attribname", "result")
        self._children.append(child)
        if MockNode._hou_ref is not None:
            MockNode._hou_ref._nodes[child.path()] = child
        return child

    def destroy(self) -> None:
        self._destroyed = True
        for child in list(self._children):
            child.destroy()
        self._children.clear()
        if self._parent and self in self._parent._children:
            self._parent._children.remove(self)
        # Remove from the global node registry if available
        if MockNode._hou_ref is not None:
            MockNode._hou_ref._nodes.pop(self._path, None)

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
        return self._geometry

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
        if "copytopoints" in name:
            return MockShelfTool(
                "node = genericTool(kwargs, 'copytopoints::2.0')\n"
                "node.parm('resettargetattribs').pressButton()"
            )
        return None


class MockViewport:
    def __init__(self):
        self.home_all_called = False

    def homeAll(self) -> None:
        self.home_all_called = True


class MockFlipbookSettings:
    def __init__(self):
        self.output_path: str | None = None
        self.output_to_mplay: bool | None = None
        self.frame_range: tuple[int, int] | None = None
        self.stash_called = False
        self.stashed_settings: list[MockFlipbookSettings] = []
        self.stashed_from: MockFlipbookSettings | None = None

    def stash(self) -> MockFlipbookSettings:
        self.stash_called = True
        settings = MockFlipbookSettings()
        settings.stashed_from = self
        self.stashed_settings.append(settings)
        return settings

    def output(self, filepath: str) -> None:
        self.output_path = filepath

    def outputToMPlay(self, value: bool) -> None:
        self.output_to_mplay = value

    def frameRange(self, frame_range: tuple[int, int]) -> None:
        self.frame_range = frame_range


class MockSceneViewer:
    def __init__(self):
        self.viewport = MockViewport()
        self.base_settings = MockFlipbookSettings()
        self.flipbook_calls: list[tuple[MockViewport, MockFlipbookSettings]] = []

    def curViewport(self) -> MockViewport:
        return self.viewport

    def flipbookSettings(self) -> MockFlipbookSettings:
        return self.base_settings

    def flipbook(
        self,
        viewport: MockViewport,
        settings: MockFlipbookSettings,
    ) -> None:
        self.flipbook_calls.append((viewport, settings))
        if settings.output_path:
            with open(settings.output_path, "wb") as output:
                output.write(b"mock flipbook")


class MockDesktop:
    def __init__(self, scene_viewer=None, network_editor=None):
        self.scene_viewer = scene_viewer
        self.network_editor = network_editor

    def paneTabOfType(self, tab_type):
        if tab_type == MockHou.paneTabType.SceneViewer:
            return self.scene_viewer
        if tab_type == MockHou.paneTabType.NetworkEditor:
            return self.network_editor
        return None


class MockUI:
    def __init__(self):
        self.desktop = MockDesktop()

    def curDesktop(self):
        return self.desktop

    def set_scene_viewer(self, viewer) -> None:
        self.desktop.scene_viewer = viewer


class MockHou:
    """Complete mock of the hou module for testing."""

    paneTabType = type("paneTabType", (), {
        "SceneViewer": 1,
        "NetworkEditor": 2,
    })()

    class Ramp:
        pass

    MockGeometry = MockGeometry

    def __init__(self):
        self._nodes: dict[str, MockNode] = {}
        self._selected_nodes: list[MockNode] = []
        self._hip_file = MockHipFile("test.hip")
        self._pwd_path = "/"
        self._home_dir = "/home/test"
        self.shelves = MockShelves()
        self.ui = MockUI()

        root = MockNode("/", "")
        self._nodes["/"] = root

        obj = MockNode("/obj", "obj", "obj", parent=root)
        root._children.append(obj)
        self._nodes["/obj"] = obj

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

        self._hda_definitions: dict[str, dict] = {}

    def node(self, path: str) -> MockNode | None:
        return self._nodes.get(path)

    def nodeTypeCategories(self) -> dict[str, MockCategory]:
        return self._categories

    def selectedNodes(self) -> list[MockNode]:
        return list(self._selected_nodes)

    def pwd(self) -> MockNode | None:
        return self._nodes.get(self._pwd_path)

    @property
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

    class _HDA:
        def __init__(self, definitions):
            self._definitions = definitions

        def definitions(self) -> dict:
            return self._definitions

    @property
    def hda(self):
        return self._HDA(self._hda_definitions)

    class OperationFailed(Exception):
        pass


def create_mock_hou() -> MockHou:
    """Create a fresh mock hou instance."""
    hou = MockHou()
    MockNode._hou_ref = hou
    return hou
