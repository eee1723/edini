"""Mock hou module for testing node_utils without Houdini runtime.

Provides MockNode, MockParm, and a mock hou module that supports:
- hou.node(path) → MockNode tree
- hou.nodeTypeCategories() → preset node types
- hou.selectedNodes() → configurable
- hou.hipFile.name() → configurable
"""
from __future__ import annotations

import re
import traceback as _traceback_module
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

    def setExpression(self, expr: str, language: Any = None) -> None:
        """Mock of hou.Parm.setExpression — records the expression string.

        Real Houdini evaluates the expression on cook; the mock just stores it
        so unit tests can verify a channel reference (e.g. ch("../wheel_r"))
        was wired. Many builder paths call setExpression inside try/except,
        so without this the unit tests would pass even when the expression
        fails to install."""
        self._expression = expr

    def expression(self) -> str:
        return getattr(self, "_expression", "")

    def hasExpression(self) -> bool:
        """Mock of hou.Parm.hasExpression — True if setExpression was called."""
        return bool(getattr(self, "_expression", ""))

    def pressButton(self) -> None:
        pass


class MockParmTemplate:
    """Mock base for a Houdini ParmTemplate — stores name/label/default.

    Also carries a type tag (matching hou.parmTemplateType enum names like
    "Float"/"Int"/"Menu"/"Toggle"/"String") so the node-params manifest
    generator can categorize parms. Subclasses (MockIntParmTemplate,
    MockMenuParmTemplate) override the type and add type-specific accessors."""

    def __init__(self, name: str = "", label: str = "", components: int = 1):
        self.name = name
        self.label = label
        self.components = components
        self.default = 0.0
        self.min_val = 0.0
        self.max_val = 10.0
        self._type_name = "Float"

    def name(self) -> str:
        return self.name

    def label(self) -> str:
        return self.label

    # hou.parmTemplateType parity: type() returns an object whose .name() is the
    # enum member name (e.g. "Float", "Menu").
    def type(self):
        return _MockTypeEnum(self._type_name)

    def setMin(self, v: float) -> None:
        self.min_val = float(v)

    def setMax(self, v: float) -> None:
        self.max_val = float(v)

    def setMinValueStr(self, s: str) -> None:
        pass

    def setMaxValueStr(self, s: str) -> None:
        pass

    def defaultValue(self):
        return self.default

    def minValue(self):
        return self.min_val

    def maxValue(self):
        return self.max_val

    def menuItems(self):
        raise AttributeError("not a menu template")


class _MockTypeEnum:
    """A tiny stand-in for a hou.parmTemplateType enum member."""
    def __init__(self, n: str):
        self._n = n

    def name(self) -> str:
        return self._n


class MockFloatParmTemplate(MockParmTemplate):
    """Mock hou.FloatParmTemplate. Accepts the diverse H18-H21 ctor shapes that
    edini.harness._build_float_parm_template tries (keyword default_value,
    positional list default, default-only, bare name/label/components)."""

    def __init__(self, name: str = "", label: str = "", num_components: int = 1,
                 *args, **kwargs):
        super().__init__(name, label, num_components)
        # Resolve the default value across ctor variants.
        default = 0.0
        mn = kwargs.get("min", 0.0)
        mx = kwargs.get("max", 10.0)
        if "default_value" in kwargs:
            dv = kwargs["default_value"]
            # real API takes a tuple-of-tuples or list; pull first element.
            try:
                default = float(dv[0] if not isinstance(dv, (int, float))
                                else dv)
            except Exception:
                default = 0.0
        elif args:
            # First positional after components is the default list/tuple.
            try:
                default = float(args[0][0])
            except Exception:
                default = 0.0
        self.default = float(default)
        self.min_val = float(mn)
        self.max_val = float(mx)
        self._type_name = "Float"


class MockIntParmTemplate(MockParmTemplate):
    """Mock hou.IntParmTemplate — integer parameter."""

    def __init__(self, name: str = "", label: str = "", num_components: int = 1,
                 default: int = 0, *args, **kwargs):
        super().__init__(name, label, num_components)
        self.default = int(default)
        self.min_val = float(kwargs.get("min", 0))
        self.max_val = float(kwargs.get("max", 10))
        self._type_name = "Int"


class MockMenuParmTemplate(MockParmTemplate):
    """Mock hou.MenuParmTemplate — enum/menu parameter with token list."""

    def __init__(self, name: str = "", label: str = "",
                 menu_items: list[str] | None = None, default: int = 0):
        super().__init__(name, label)
        self._menu_items = list(menu_items or [])
        self.default = int(default)
        self._type_name = "Menu"

    def menuItems(self) -> list[str]:
        return list(self._menu_items)


class MockToggleParmTemplate(MockParmTemplate):
    """Mock hou.ToggleParmTemplate — boolean parameter."""

    def __init__(self, name: str = "", label: str = "", default: bool = False):
        super().__init__(name, label)
        self.default = bool(default)
        self._type_name = "Toggle"


class MockButtonParmTemplate(MockParmTemplate):
    """Mock hou.ButtonParmTemplate — a pressable button parameter.

    The default value is the string '0' to mirror real Houdini button parms
    (which eval to '0' as a string). type() reports 'Button'.
    """

    def __init__(self, name: str = "", label: str = ""):
        super().__init__(name, label)
        self.default = "0"
        self._type_name = "Button"


class MockStringParmTemplate(MockParmTemplate):
    """Mock hou.StringParmTemplate — string parameter."""

    def __init__(self, name: str = "", label: str = "", default: str = ""):
        super().__init__(name, label)
        self.default = str(default)
        self._type_name = "String"

    def menuItems(self) -> list[str]:
        # String templates may have menus; default empty.
        return []


class MockFolderParmTemplate(MockParmTemplate):
    """Mock hou.FolderParmTemplate — holds child templates.

    Doubles as a multiparm folder when ``is_multiparm`` is set: its child
    templates carry a ``#`` in their name (the per-instance marker), and the
    folder tracks an instance ``length``. ``setLength``/``setNumInstances``
    grow/shrink it, mirroring real Houdini's multiparm API (used by
    harness._setup_copy_apply_attributes tier 3).
    """

    def __init__(self, name: str = "", label: str = "", folder_type: int = 0,
                 is_multiparm: bool = False, length: int = 0):
        super().__init__(name, label)
        self.folder_type = folder_type
        self.is_multiparm = is_multiparm
        self._length = length
        self._children: list[Any] = []

    def addParmTemplate(self, tmpl: Any) -> None:
        self._children.append(tmpl)

    def parmTemplates(self) -> list[Any]:
        return list(self._children)

    # ── multiparm API (real Houdini folder templates expose these) ────────
    def length(self) -> int:
        return self._length

    def setLength(self, n: int) -> None:
        self._length = int(n)

    def setNumInstances(self, n: int) -> None:
        self._length = int(n)

    def numInstances(self) -> int:
        return self._length


class MockParmTemplateGroup:
    """Mock hou.ParmTemplateGroup — a list of top-level templates (folders or
    parms). append() adds one; find() locates a template by name."""

    def __init__(self):
        self._templates: list[Any] = []

    def append(self, tmpl: Any) -> None:
        self._templates.append(tmpl)

    def find(self, name: str):
        for tmpl in self._templates:
            try:
                if tmpl.name() == name:
                    return tmpl
            except Exception:
                continue
            # Recurse into folders.
            for child in getattr(tmpl, "parmTemplates", lambda: [])():
                try:
                    if child.name() == name:
                        return child
                except Exception:
                    continue
        return None

    def entries(self) -> list[Any]:
        return list(self._templates)

    def replace(self, old, new) -> None:
        """Replace a top-level template. ``old`` may be a name (str) or the
        template object itself, mirroring hou.ParmTemplateGroup.replace."""
        old_name = old if isinstance(old, str) else None
        for i, tmpl in enumerate(self._templates):
            try:
                tname = tmpl.name()
            except Exception:
                tname = ""
            match = (old_name == tname) if old_name is not None else (tmpl is old)
            if match:
                self._templates[i] = new
                return

    def asParmSpecs(self) -> dict[str, dict]:
        """Flatten all templates (recursing folders) to {name: {default,...}}."""
        out: dict[str, dict] = {}

        def walk(templates):
            for tmpl in templates:
                if isinstance(tmpl, MockFolderParmTemplate):
                    walk(tmpl.parmTemplates())
                elif isinstance(tmpl, MockFloatParmTemplate):
                    out[tmpl.name] = {
                        "default": tmpl.default,
                        "min": tmpl.min_val,
                        "max": tmpl.max_val,
                        "label": tmpl.label,
                    }
        walk(self._templates)
        return out


class MockNodeType:
    """Mock Houdini node type."""

    def __init__(self, name: str, description: str = "", category_name: str = "Sop",
                 max_inputs: int = 2, min_inputs: int = 0,
                 parm_template_group: Any = None):
        self._name = name
        self._description = description or name
        self._category_name = category_name
        self._max_inputs = max_inputs
        self._min_inputs = min_inputs
        self._ptg = parm_template_group

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

    def parmTemplateGroup(self):
        """Return the node type's parameter template group (may be None if the
        node type was constructed without one)."""
        return self._ptg


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
        self._number = 0

    def setPosition(self, pos):
        self._pos = (float(pos[0]), float(pos[1]), float(pos[2]))

    def position(self):
        return self._pos

    def setAttribValue(self, name: str, value: Any) -> None:
        self._attribs[name] = value

    def attribValue(self, name: str) -> Any:
        return self._attribs.get(name)

    def number(self) -> int:
        return self._number

    def stringAttribValue(self, name: str) -> str:
        v = self._attribs.get(name, "")
        return str(v) if v is not None else ""


class MockVertex:
    """Mock Houdini vertex — wraps a point reference."""

    def __init__(self, point: "MockPoint"):
        self._point = point

    def point(self) -> "MockPoint":
        return self._point


class MockPrim:
    """Mock Houdini primitive for builder-mode geometry."""

    def __init__(self):
        self._vertices: list[MockPoint] = []
        self._attribs: dict[str, Any] = {}
        self._number = 0
        self._type_name = "Poly"
        self._closed = True

    def addVertex(self, pt) -> None:
        # Accept either a MockPoint (legacy) or wrap automatically
        if isinstance(pt, MockVertex):
            self._vertices.append(pt)
        else:
            self._vertices.append(MockVertex(pt))

    def vertices(self):
        return list(self._vertices)

    def setAttribValue(self, name: str, value: Any) -> None:
        self._attribs[name] = value

    def attribValue(self, name: str) -> Any:
        return self._attribs.get(name)

    def stringAttribValue(self, name: str) -> str:
        v = self._attribs.get(name, "")
        return str(v) if v is not None else ""

    def number(self) -> int:
        return self._number

    def type(self):
        return MockPrimType(self._type_name)

    def isClosed(self) -> bool:
        return self._closed


class MockPrimType:
    def __init__(self, name: str):
        self._name = name

    def name(self) -> str:
        return self._name

    def stringAttribValue(self, name: str) -> str:
        v = self._attribs.get(name, "")
        return str(v) if v is not None else ""


class MockVector3:
    """Mock hou.Vector3. Accepts the same constructor shapes real hou does:
    3 scalars, a 3-tuple/list, or another Vector3. Read-only indexing."""

    def __init__(self, *args):
        if len(args) == 3:
            self._v = (float(args[0]), float(args[1]), float(args[2]))
        elif len(args) == 1:
            a = args[0]
            # Unpack any 3-element sequence (tuple, list, Vector3).
            self._v = (float(a[0]), float(a[1]), float(a[2]))
        else:
            raise TypeError(
                f"MockVector3 expected 1 or 3 args, got {len(args)}")

    def __getitem__(self, i):
        return self._v[i]

    def __len__(self):
        return 3

    def __iter__(self):
        return iter(self._v)

    def __repr__(self):
        return f"MockVector3{self._v}"


class MockBoundingBox:
    """Mock hou.BoundingBox. Supports BOTH constructor overloads used in the
    codebase:
      - BoundingBox(min_seq, max_seq)   # 2 Vector3 / list / tuple args
      - BoundingBox(x0,y0,z0, x1,y1,z1)  # 6 scalars (the robust form)
    Mirrors real hou.BoundingBox semantics on H21."""

    def __init__(self, *args):
        if len(args) == 6:
            self._bounds = tuple(float(a) for a in args)
        elif len(args) == 2:
            mn = args[0]
            mx = args[1]
            self._bounds = (
                float(mn[0]), float(mn[1]), float(mn[2]),
                float(mx[0]), float(mx[1]), float(mx[2]),
            )
        else:
            raise TypeError(
                f"MockBoundingBox expected 2 or 6 args, got {len(args)}")

    def minvec(self):
        return (self._bounds[0], self._bounds[1], self._bounds[2])

    def maxvec(self):
        return (self._bounds[3], self._bounds[4], self._bounds[5])

    def __repr__(self):
        return f"MockBoundingBox{self._bounds}"


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
        pt._number = len(self._points)
        self._points.append(pt)
        self._point_count = len(self._points)
        return pt

    def createPolygon(self) -> MockPrim:
        """Create a polygon in builder mode."""
        self._builder_mode = True
        prim = MockPrim()
        prim._number = len(self._prims)
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
        # intrinsic "bounds" is interleaved (xmin,xmax,ymin,ymax,zmin,zmax);
        # hou.BoundingBox / MockBoundingBox store component-major
        # (xmin,ymin,zmin,xmax,ymax,zmax). Convert here so minvec()/maxvec()
        # on the mock match real hou semantics.
        return MockBoundingBox(
            b[0], b[2], b[4],   # xmin, ymin, zmin
            b[1], b[3], b[5],   # xmax, ymax, zmax
        )

    def pointAttribs(self):
        return [MockAttrib("P")]

    def primAttribs(self):
        return [MockAttrib(n) for n in self._builder_attribs.keys()]

    def vertexAttribs(self):
        return []

    def globalAttribs(self):
        return []

    def findPrimAttrib(self, name: str):
        if name in self._builder_attribs:
            return MockAttrib(name)
        return None


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
        # Multiparm support: maps a template name with '#' (e.g. 'useapply#')
        # to its template object, and to the folder count-parm name that
        # controls how many instances exist. Populated by createNode() from
        # the node-type PTG; used by parm() for lazy per-instance creation.
        self._multiparm_templates: dict[str, Any] = {}
        self._multiparm_count_parm: dict[str, str] = {}
        # Node comment (Houdini Notes panel) — the recipe library uses this
        # as its metadata source, so the mock must support read/write.
        self._comment: str = ""

    def path(self) -> str:
        return self._path

    def name(self) -> str:
        return self._name

    def setName(self, name: str, unique_name: bool = False) -> None:
        # Mirror real Houdini's node-name validation: names may only contain
        # letters, digits, underscores. :: and . are illegal. This makes
        # dynamic-naming bugs (e.g. postprocess node names built from a type
        # string like "fuse::2.0") fail in unit tests, not only under hython.
        import re as _re
        if not isinstance(name, str) or not _re.fullmatch(r"[A-Za-z0-9_]+", name):
            raise MockNode._hou_ref.InvalidNodeName(
                f"Invalid node name: {name!r}. Houdini node names may only "
                f"contain letters, digits, and underscores.")
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

    def comment(self) -> str:
        """Mock of hou.Node.comment — the Notes text shown on the node."""
        return self._comment

    def setComment(self, text: str) -> None:
        """Mock of hou.Node.setComment."""
        self._comment = text or ""

    def children(self) -> list[MockNode]:
        return list(self._children)

    def allSubChildren(self) -> list[MockNode]:
        result = [self]
        for child in self._children:
            result.extend(child.allSubChildren())
        return result

    def parm(self, name: str) -> MockParm | None:
        found = self._parms.get(name)
        if found is not None:
            return found
        # Multiparm lazy instantiation: if `name` matches a multiparm template
        # (e.g. `useapply1` → `useapply#`) and the folder's count parm allows
        # that instance index, materialize the instance parm on the fly. This
        # mirrors real Houdini, where setting a multiparm count creates the
        # per-instance parms automatically, so harness code can set
        # numapplyattrs=1 then read/write useapply1 etc. under the mock.
        import re as _re
        m = _re.match(r"^(.*?)(\d+)$", name)
        if m:
            prefix, num = m.group(1), int(m.group(2))
            tmpl = self._multiparm_templates.get(prefix + "#")
            if tmpl is not None:
                count_parm_name = self._multiparm_count_parm.get(prefix + "#")
                count = 0
                if count_parm_name and count_parm_name in self._parms:
                    try:
                        count = int(self._parms[count_parm_name].eval())
                    except Exception:
                        count = 0
                if 1 <= num <= count:
                    default = getattr(tmpl, "default", 0)
                    parm = MockParm(name, default)
                    self._parms[name] = parm
                    return parm
        return None

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
        # When an explicit node_name is supplied it must be a legal Houdini
        # node name (letters/digits/underscores only). Type names may legally
        # contain :: (e.g. "fuse::2.0" is a valid type), and Houdini sanitizes
        # the default name itself when node_name is None — so we only validate
        # the explicit case, mirroring real Houdini's behaviour.
        import re as _re
        if node_name is not None and not _re.fullmatch(r"[A-Za-z0-9_]+", node_name):
            raise MockNode._hou_ref.InvalidNodeName(
                f"Invalid node name: {node_name!r}. Houdini node names may only "
                f"contain letters, digits, and underscores.")
        actual_name = node_name or node_type_name
        child_path = f"{self._path}/{actual_name}"
        child = MockNode(child_path, actual_name, node_type_name, parent=self)
        # Auto-create known parms for specific node types
        if node_type_name == "attribwrangle":
            child._parms["snippet"] = MockParm("snippet", "")
            child._parms["snippet_attribname"] = MockParm("snippet_attribname", "result")
        elif node_type_name == "python":
            child._parms["python"] = MockParm("python", "")
        # For node types that declare a parm template group, materialize their
        # parms from it (mirrors how real Houdini populates a node's parms from
        # its type definition). This lets _set_parm_safe find real parm names
        # like copytopoints::2.0's useidattrib/idattrib or normal's cuspangle.
        ntype = self._node_type_for_create(node_type_name)
        if ntype is not None and getattr(ntype, "_ptg", None) is not None:
            for tmpl in ntype._ptg._templates:
                # NOTE: MockParmTemplate stores `name` as a STRING attribute in
                # __init__, which shadows the name() method — so read the attr,
                # don't call it. (The existing find() swallows this via try/except.)
                nm = getattr(tmpl, "name", None)
                if not isinstance(nm, str):
                    continue
                if nm not in child._parms:
                    default = getattr(tmpl, "default", 0)
                    child._parms[nm] = MockParm(nm, default)
            # Index multiparm folders: for each folder whose child templates
            # carry a '#' in their name, bind each child template to the
            # folder's count parm (num<folderbase>) so parm() can lazily create
            # per-instance parms when the count is raised.
            for folder in ntype._ptg._templates:
                fname = getattr(folder, "name", None)
                if not (isinstance(fname, str) and fname.endswith("#")):
                    continue
                children = []
                try:
                    children = folder.parmTemplates()
                except Exception:
                    children = []
                if not children:
                    continue
                count_parm = "num" + fname[:-1]
                for ctmpl in children:
                    cname = getattr(ctmpl, "name", None)
                    if isinstance(cname, str) and "#" in cname:
                        child._multiparm_templates[cname] = ctmpl
                        child._multiparm_count_parm[cname] = count_parm
        self._children.append(child)
        if MockNode._hou_ref is not None:
            MockNode._hou_ref._nodes[child.path()] = child
        return child

    def _node_type_for_create(self, node_type_name: str):
        """Look up the MockNodeType for a createNode type name, checking the
        SOP category (and its namespace variants like copytopoints::2.0)."""
        hou = MockNode._hou_ref
        if hou is None:
            return None
        try:
            cat = hou.sopNodeTypeCategory()
        except Exception:
            return None
        # Direct lookup (e.g. "normal", "attribfrompieces").
        nt = cat.nodeType(node_type_name)
        if nt is not None:
            return nt
        # Namespace variant: the registry stores the versioned name
        # (e.g. "copytopoints::2.0") under the bare key ("copytopoints").
        nt = cat.nodeType(node_type_name.split("::")[0])
        return nt

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
        if force and self._type_name == "python":
            code_parm = self._parms.get("python")
            code = code_parm.eval() if code_parm else ""
            if code:
                hou_ref = MockNode._hou_ref
                if hou_ref is None:
                    return
                try:
                    # Simulate Python SOP cooking context: hou.pwd() returns this node
                    old_pwd = hou_ref._pwd_path
                    hou_ref._pwd_path = self._path
                    result_payload = {}
                    namespace = {
                        "hou": hou_ref,
                        "sandbox_root_path": self._parent._path if self._parent else "",
                        "result": result_payload,
                    }
                    exec(code, namespace)
                    hou_ref._pwd_path = old_pwd
                except Exception as e:
                    hou_ref._pwd_path = old_pwd
                    self._errors.append(f"Python error: {_traceback_module.format_exc()}")

    def geometry(self):
        if self._geometry is None and self._type.name() == "python":
            self._geometry = MockGeometry()
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

    # ── Parameter template group (mocks hou.ParmTemplateGroup machinery) ──
    # The sandbox root installs asset-level params via setParmTemplateGroup +
    # FolderParmTemplate. The group is held on the node; setParmTemplateGroup
    # materializes its templates into real MockParm entries so parm()/evalParm()
    # see them — mirroring how real Houdini exposes template parms.
    def parmTemplateGroup(self):
        return getattr(self, "_ptg", None) or MockParmTemplateGroup()

    def setParmTemplateGroup(self, ptg) -> None:
        self._ptg = ptg
        for name, spec in ptg.asParmSpecs().items():
            existing = self._parms.get(name)
            if existing is None:
                self._parms[name] = MockParm(name, spec.get("default", 0.0),
                                             spec.get("label", name))
            else:
                existing._value = spec.get("default", existing._value)

    def setSpareParmGroup(self, ptg) -> None:
        # Legacy fallback path — same effect as setParmTemplateGroup in mock.
        self.setParmTemplateGroup(ptg)

    def evalParm(self, name: str) -> Any:
        p = self._parms.get(name)
        return p.eval() if p is not None else 0.0

    def setSpareParms(self, parms) -> None:
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
        self.set_view_to_bbox_called = False
        self.last_bbox = None
        self._type = None

    def homeAll(self) -> None:
        self.home_all_called = True

    def setViewToBoundingBox(self, bbox, frame_time=0.0, padding=1.0) -> None:
        """Record bounding-box framing (the preferred framing method)."""
        self.set_view_to_bbox_called = True
        self.last_bbox = bbox

    def type(self):
        return self._type

    def setType(self, view_type) -> None:
        self._type = view_type

    def changeType(self, view_type) -> None:
        self._type = view_type

    def draw(self, update=False, force_update=False) -> None:
        pass


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


class MockAttribType:
    """Minimal stand-in for hou.attribType (mock ignores the value but real
    component code references hou.attribType.Prim etc.)."""

    Prim = "Prim"
    Point = "Point"
    Vertex = "Vertex"
    Global = "Global"


def _make_normal_ptg():
    """Build a realistic Normal SOP parm template group (H21 names).
    Note: H21 names the cusp-angle parm 'cuspangle' — NOT 'cangle' (a stale
    name agents keep guessing) nor 'cusp'. These real names let the manifest/
    parm-name tests exercise the exact failure mode that prompted the
    C-station."""
    g = MockParmTemplateGroup()
    g.append(MockMenuParmTemplate("type", "Add Normals to",
                                  ["typepoint", "typevertex", "typeprim",
                                   "typedetail"], default=1))
    g.append(MockFloatParmTemplate("cuspangle", "Cusp Angle",
                                   num_components=1, default_value=(60.0,),
                                   min=0.0, max=180.0))
    return g


def _make_sweep_ptg():
    """Sweep 2.0 parm template group (subset relevant to the builder).

    The builder forces ``surfaceshape=0`` when a section_code is present
    (dual-wrangle mode), because any non-zero surfaceshape (1=roundtube,
    2=extrude) makes Sweep ignore the second-input cross-section. Exposing
    ``surfaceshape`` as a mock parm lets unit tests verify the enforcement.
    Also includes ``surfacetype`` and ``endcaptype`` used by recipes."""
    g = MockParmTemplateGroup()
    g.append(MockMenuParmTemplate("surfaceshape", "Surface Shape",
                                  ["splines", "roundtube", "extrude"],
                                  default=0))
    g.append(MockMenuParmTemplate("surfacetype", "Surface Type",
                                  ["interpolating", "noninterp"], default=2))
    g.append(MockMenuParmTemplate("endcaptype", "End Caps",
                                  ["noends", "onend", "bothends"], default=1))
    return g


def _make_copytopoints_ptg():
    """Copy to Points 2.0 parm template group (H21.0.440 structure).

    Key H21 facts (verified on real 21.0.440, NOT just the manifest):
      - piece-attribute dispatch uses `useidattrib` (toggle) + `idattrib`
        (name), and works on UNPACKED source geometry.
      - There is NO Apply Attributes multiparm folder and NO numapplyattrs
        count parm on a fresh node (the manifest's useapply#/... templates
        are latent). Attribute transfer is driven by the `resettargetattribs`
        BUTTON, which when pressed populates the `targetattribs` multiparm
        (an int whose value = instance count) with default entries.
      - `targetattribs` is the count parm (value = number of apply entries).

    The mock records presses of `resettargetattribs` (via MockNode's button
    tracking) so tests can assert the harness pressed it. The real fill-in
    of useapply1/etc. is validated in Houdini runtime, not in the mock.
    """
    g = MockParmTemplateGroup()
    g.append(MockStringParmTemplate("sourcegroup", "Source Group"))
    g.append(MockStringParmTemplate("targetgroup", "Target Points"))
    g.append(MockToggleParmTemplate("useidattrib", "Piece Attribute", default=False))
    g.append(MockStringParmTemplate("idattrib", "Piece Attribute", default=""))
    g.append(MockToggleParmTemplate("pack", "Pack and Instance", default=False))
    # The real H21 transfer mechanism: a button + its multiparm count parm.
    g.append(MockButtonParmTemplate("resettargetattribs", "Reset Attributes from Target"))
    g.append(MockIntParmTemplate("targetattribs", "Attributes from Target", default=0))
    return g


def _make_attribfrompieces_ptg():
    """Attribute from Pieces parm template group (subset). The `pieceattrib`
    names the source piece attribute (default `name` in H21)."""
    g = MockParmTemplateGroup()
    g.append(MockStringParmTemplate("pieceattrib", "Piece Attribute", default="name"))
    g.append(MockMenuParmTemplate("mode", "Mode",
                                  ["piece", "patch", "worley"], default=0))
    g.append(MockIntParmTemplate("seed", "Seed", default=0))
    return g


def _make_pack_ptg():
    """Pack SOP parm template group (subset). `packbyname` toggles per-name
    packing; `nameattribute` names the grouping attribute."""
    g = MockParmTemplateGroup()
    g.append(MockToggleParmTemplate("packedfragments",
                                    "Create Packed Fragments", default=True))
    g.append(MockToggleParmTemplate("packbyname", "Pack By Name", default=False))
    g.append(MockStringParmTemplate("nameattribute", "Name Attribute", default="name"))
    return g


def _make_connectivity_ptg():
    """Connectivity SOP parm template group (subset). `attribname` controls
    the output attribute name (default `class`; we set it to `piece`)."""
    g = MockParmTemplateGroup()
    g.append(MockStringParmTemplate("attribname", "Attribute", default="class"))
    return g


def _make_wrangle_ptg():
    """Attrib Wrangle parm template group (subset)."""
    g = MockParmTemplateGroup()
    g.append(MockStringParmTemplate("snippet", "VEXpression"))
    g.append(MockMenuParmTemplate("class", "Run Over",
                                  ["detail", "point", "prim", "vertex"],
                                  default=1))
    return g


class MockHou:
    """Complete mock of the hou module for testing."""

    paneTabType = type("paneTabType", (), {
        "SceneViewer": 1,
        "NetworkEditor": 2,
    })()

    class Ramp:
        pass

    MockGeometry = MockGeometry

    # Vector3 / BoundingBox — exposed as hou.Vector3 / hou.BoundingBox so
    # code paths that build bboxes (e.g. capture_component_detail) are
    # exercisable under the mock. See procedural-modeling-bugs.md Bug 1.
    Vector3 = MockVector3
    BoundingBox = MockBoundingBox

    # Sentinel: node_utils._node_parms_live checks this to skip the live
    # fallback path under the mock (so tests don't pretend Houdini is online).
    _MOCK = True

    # Parameter template classes (mocked). These mirror hou.FloatParmTemplate /
    # hou.FolderParmTemplate / hou.ParmTemplateGroup and the hou.folderType enum
    # so harness._install_spare_params can exercise the success path.
    FloatParmTemplate = MockFloatParmTemplate
    IntParmTemplate = MockIntParmTemplate
    MenuParmTemplate = MockMenuParmTemplate
    ToggleParmTemplate = MockToggleParmTemplate
    ButtonParmTemplate = MockButtonParmTemplate
    StringParmTemplate = MockStringParmTemplate
    FolderParmTemplate = MockFolderParmTemplate
    ParmTemplateGroup = MockParmTemplateGroup
    parmNamingScheme = type("parmNamingScheme", (), {"Base1": 0})()
    parmLook = type("parmLook", (), {"Regular": 0})()
    parmNaming = type("parmNaming", (), {"Base1": 0})()
    folderType = type("folderType", (), {"Tabs": 0, "Simple": 1})()

    def applicationVersionString(self) -> str:
        return "20.0.0 (mock)"

    def __init__(self):
        self._nodes: dict[str, MockNode] = {}
        self._selected_nodes: list[MockNode] = []
        self._hip_file = MockHipFile("test.hip")
        self._pwd_path = "/"
        self._home_dir = "/home/test"
        self.shelves = MockShelves()
        self.ui = MockUI()
        self.attribType = MockAttribType

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
            "attribwrangle": MockNodeType(
                "attribwrangle", "Attribute Wrangle", "Sop", 1, 1,
                parm_template_group=_make_wrangle_ptg()),
            "file": MockNodeType("file", "File", "Sop", 1, 0),
            "pyro": MockNodeType("pyro", "Pyro Solver", "Sop", 5, 2),
            "copytopoints": MockNodeType(
                "copytopoints::2.0", "Copy to Points", "Sop", 2, 1,
                parm_template_group=_make_copytopoints_ptg()),
            "attribfrompieces": MockNodeType(
                "attribfrompieces", "Attribute from Pieces", "Sop", 2, 1,
                parm_template_group=_make_attribfrompieces_ptg()),
            "pack": MockNodeType(
                "pack", "Pack", "Sop", 1, 0,
                parm_template_group=_make_pack_ptg()),
            "unpack": MockNodeType("unpack", "Unpack", "Sop", 1, 0),
            "connectivity": MockNodeType("connectivity", "Connectivity", "Sop", 1, 0),
            "fuse": MockNodeType("fuse", "Fuse", "Sop", 1, 0),
            "clean": MockNodeType("clean", "Clean", "Sop", 1, 0),
            "normal": MockNodeType(
                "normal", "Normal", "Sop", 1, 0,
                parm_template_group=_make_normal_ptg()),
            "sweep": MockNodeType(
                "sweep::2.0", "Sweep", "Sop", 2, 1,
                parm_template_group=_make_sweep_ptg()),
        })
        obj_cat = MockCategory("Object", {
            "geo": MockNodeType("geo", "Geometry", "Object", 1, 0),
            "subnet": MockNodeType("subnet", "Subnetwork", "Object", 1, 0),
            "cam": MockNodeType("cam", "Camera", "Object", 0, 0),
            "light": MockNodeType("light", "Light", "Object", 0, 0),
            # Network containers — used as category layers in a recipe tree
            # (e.g. a dopnet holding recipe subnets). recipe_library must
            # descend them as categories but NOT pierce their work nodes.
            "dopnet": MockNodeType("dopnet", "DOP Network", "Object", 1, 0),
            "popnet": MockNodeType("popnet", "POP Network", "Object", 1, 0),
            "sopnet": MockNodeType("sopnet", "SOP Network", "Object", 1, 0),
            "ropnet": MockNodeType("ropnet", "ROP Network", "Object", 1, 0),
            "copnet": MockNodeType("copnet", "COP Network", "Object", 1, 0),
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

    class InvalidNodeName(Exception):
        """Mock of hou.InvalidNodeName — raised by setName/createNode on
        illegal node names (containing ::, ., etc). Mirrors real Houdini's
        node-name validation so dynamic-naming bugs (e.g. postprocess node
        named ``post_0_fuse::2.0``) surface in unit tests instead of only
        under real hython."""
        pass


def create_mock_hou() -> MockHou:
    """Create a fresh mock hou instance."""
    hou = MockHou()
    MockNode._hou_ref = hou
    return hou
