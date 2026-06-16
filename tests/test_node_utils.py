"""Unit tests for node_utils — all public handler functions.

Uses mock_hou to run without Houdini runtime.
Run: pytest tests/test_node_utils.py -v
"""
import sys
import os
import unittest

from tests.mock_hou import create_mock_hou, MockParm, MockNode

_mock_hou = create_mock_hou()
sys.modules["hou"] = _mock_hou

# Add python3.11libs to path so "edini.node_utils" resolves to the right copy
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))

# Force reimport so we pick up the mock hou
for _mod in list(sys.modules):
    if _mod.startswith("edini"):
        del sys.modules[_mod]

from edini.node_utils import (
    get_scene_info, create_node, delete_node, connect_nodes,
    set_param, get_param, list_nodes, get_node_info, layout_nodes,
    search_nodes, get_help, inspect_geometry,
    run_python, run_vex, create_hda, get_hda_info,
    get_selection, check_errors, set_display_flag,
)


def _register_created_node(result: dict) -> None:
    """After create_node(), register the new node in mock hou._nodes.

    MockNode.createNode creates a child on the parent but does NOT add it
    to the global MockHou._nodes dict.  Without this, subsequent hou.node(path)
    lookups will return None.
    """
    if result.get("success"):
        path = result["path"]
        parent_path = path.rsplit("/", 1)[0] or "/"
        parent = _mock_hou.node(parent_path)
        if parent:
            for child in parent.children():
                if child.path() == path and path not in _mock_hou._nodes:
                    _mock_hou._nodes[path] = child
                    break


# ===================================================================
# TestGetSceneInfo
# ===================================================================

class TestGetSceneInfo(unittest.TestCase):
    """Tests for get_scene_info()."""

    def test_success(self):
        r = get_scene_info()
        self.assertTrue(r["success"])

    def test_hip_file(self):
        r = get_scene_info()
        self.assertEqual(r["hip_file"], "test.hip")

    def test_root_children(self):
        r = get_scene_info()
        self.assertIn("obj", r["root_children"])

    def test_total_nodes(self):
        r = get_scene_info()
        # At minimum root + /obj = 2
        self.assertGreaterEqual(r["total_nodes"], 2)


# ===================================================================
# TestCreateNode
# ===================================================================

class TestCreateNode(unittest.TestCase):
    """Tests for create_node()."""

    def test_basic_create(self):
        r = create_node("box", name="mybox", parent_path="/obj")
        self.assertTrue(r["success"])
        self.assertEqual(r["name"], "mybox")
        self.assertTrue(r["path"].endswith("/mybox"))
        _register_created_node(r)
        # Verify it's now findable
        n = _mock_hou.node(r["path"])
        self.assertIsNotNone(n)

    def test_default_parent(self):
        """Without parent_path, should default to /obj."""
        r = create_node("sphere")
        self.assertTrue(r["success"])
        self.assertTrue(r["path"].startswith("/obj/"))
        _register_created_node(r)

    def test_nonexistent_parent(self):
        r = create_node("box", parent_path="/nonexistent")
        self.assertFalse(r["success"])
        self.assertIn("not found", r["error"].lower())

    def test_type_preserved(self):
        r = create_node("grid", name="mygrid")
        self.assertTrue(r["success"])
        self.assertEqual(r["type"], "grid")
        _register_created_node(r)


# ===================================================================
# TestDeleteNode
# ===================================================================

class TestDeleteNode(unittest.TestCase):
    """Tests for delete_node()."""

    def test_delete_existing(self):
        r = create_node("box", name="to_delete")
        _register_created_node(r)
        path = r["path"]
        d = delete_node(path)
        self.assertTrue(d["success"])
        self.assertEqual(d["path"], path)
        # Should no longer be in _nodes
        self.assertIsNone(_mock_hou.node(path))

    def test_delete_nonexistent(self):
        r = delete_node("/obj/no_such_node")
        self.assertFalse(r["success"])
        self.assertIn("not found", r["error"].lower())


# ===================================================================
# TestConnectNodes
# ===================================================================

class TestConnectNodes(unittest.TestCase):
    """Tests for connect_nodes()."""

    def _make_two(self):
        a = create_node("box", name="src_box")
        _register_created_node(a)
        b = create_node("null", name="dst_null")
        _register_created_node(b)
        return a["path"], b["path"]

    def test_connect_two_nodes(self):
        src, dst = self._make_two()
        r = connect_nodes(src, dst)
        self.assertTrue(r["success"])
        self.assertEqual(r["from"], src)
        self.assertEqual(r["to"], dst)
        self.assertEqual(r["input_index"], 0)

    def test_input_index(self):
        src, dst = self._make_two()
        r = connect_nodes(src, dst, input_index=2)
        self.assertTrue(r["success"])
        self.assertEqual(r["input_index"], 2)

    def test_missing_source(self):
        _, dst = self._make_two()
        r = connect_nodes("/obj/nope", dst)
        self.assertFalse(r["success"])
        self.assertIn("source", r["error"].lower())

    def test_missing_dest(self):
        src, _ = self._make_two()
        r = connect_nodes(src, "/obj/nope")
        self.assertFalse(r["success"])
        self.assertIn("destination", r["error"].lower())


# ===================================================================
# TestSetGetParam
# ===================================================================

class TestSetGetParam(unittest.TestCase):
    """Tests for set_param() and get_param()."""

    def _make_node(self):
        r = create_node("box", name="param_test")
        _register_created_node(r)
        node = _mock_hou.node(r["path"])
        # Add a mock parameter
        node._parms["size"] = MockParm("size", 1.0)
        return r["path"]

    def test_set_string(self):
        path = self._make_node()
        node = _mock_hou.node(path)
        node._parms["label"] = MockParm("label", "")
        r = set_param(path, "label", "hello")
        self.assertTrue(r["success"])
        self.assertEqual(r["value"], "hello")

    def test_set_number(self):
        path = self._make_node()
        r = set_param(path, "size", 3.5)
        self.assertTrue(r["success"])
        self.assertEqual(r["value"], 3.5)
        # Verify via get_param
        g = get_param(path, "size")
        self.assertTrue(g["success"])
        self.assertEqual(g["value"], 3.5)

    def test_get_param(self):
        path = self._make_node()
        r = get_param(path, "size")
        self.assertTrue(r["success"])
        self.assertEqual(r["value"], 1.0)

    def test_missing_param(self):
        path = self._make_node()
        r = get_param(path, "nonexistent")
        self.assertFalse(r["success"])
        self.assertIn("not found", r["error"].lower())

    def test_missing_node(self):
        r = set_param("/obj/ghost", "foo", 1)
        self.assertFalse(r["success"])
        self.assertIn("not found", r["error"].lower())


# ===================================================================
# TestListNodes
# ===================================================================

class TestListNodes(unittest.TestCase):
    """Tests for list_nodes()."""

    def test_root_children(self):
        r = list_nodes("/")
        self.assertTrue(r["success"])
        self.assertGreaterEqual(r["node_count"], 1)
        names = [n["name"] for n in r["nodes"]]
        self.assertIn("obj", names)

    def test_type_filter(self):
        # Create two nodes of different types under /obj
        a = create_node("box", name="list_box")
        _register_created_node(a)
        b = create_node("sphere", name="list_sphere")
        _register_created_node(b)
        r = list_nodes("/obj", type_filter="box")
        self.assertTrue(r["success"])
        for n in r["nodes"]:
            self.assertEqual(n["type"], "box")

    def test_missing_parent(self):
        r = list_nodes("/no/such/path")
        self.assertFalse(r["success"])
        self.assertIn("not found", r["error"].lower())


# ===================================================================
# TestGetNodeInfo
# ===================================================================

class TestGetNodeInfo(unittest.TestCase):
    """Tests for get_node_info()."""

    def test_existing_node(self):
        r = create_node("box", name="info_node")
        _register_created_node(r)
        info = get_node_info(r["path"])
        self.assertTrue(info["success"])
        self.assertEqual(info["name"], "info_node")
        self.assertIn("parameters", info)

    def test_missing_node(self):
        info = get_node_info("/obj/ghost")
        self.assertFalse(info["success"])
        self.assertIn("not found", info["error"].lower())


# ===================================================================
# TestLayoutNodes
# ===================================================================

class TestLayoutNodes(unittest.TestCase):
    """Tests for layout_nodes()."""

    def test_existing_parent(self):
        r = layout_nodes("/obj")
        self.assertTrue(r["success"])
        self.assertEqual(r["parent"], "/obj")

    def test_missing_parent(self):
        r = layout_nodes("/no/such")
        self.assertFalse(r["success"])
        self.assertIn("not found", r["error"].lower())


# ===================================================================
# TestSearchNodes
# ===================================================================

class TestSearchNodes(unittest.TestCase):
    """Tests for search_nodes()."""

    def test_find_box(self):
        r = search_nodes("box")
        self.assertTrue(r["success"])
        names = [n["name"] for n in r["results"]]
        self.assertIn("box", names)

    def test_find_by_description(self):
        r = search_nodes("Sphere")
        self.assertTrue(r["success"])
        self.assertGreaterEqual(r["match_count"], 1)

    def test_limits_results(self):
        # "o" is broad — should match many but capped at 20
        r = search_nodes("o")
        self.assertTrue(r["success"])
        self.assertLessEqual(r["match_count"], 20)


# ===================================================================
# TestGetHelp
# ===================================================================

class TestGetHelp(unittest.TestCase):
    """Tests for get_help()."""

    def test_known_type(self):
        r = get_help("box")
        self.assertTrue(r["success"])
        self.assertEqual(r["name"], "box")
        self.assertIn("description", r)

    def test_unknown_type(self):
        r = get_help("totally_fake_node_type")
        self.assertFalse(r["success"])
        self.assertIn("not found", r["error"].lower())


# ===================================================================
# TestInspectGeometry
# ===================================================================

class TestInspectGeometry(unittest.TestCase):
    """Tests for inspect_geometry()."""

    def test_missing_node(self):
        r = inspect_geometry("/obj/ghost")
        self.assertFalse(r["success"])
        self.assertIn("not found", r["error"].lower())

    def test_no_geometry(self):
        # MockNode.geometry() returns None
        cr = create_node("box", name="geo_test")
        _register_created_node(cr)
        r = inspect_geometry(cr["path"])
        self.assertFalse(r["success"])
        self.assertIn("no geometry", r["error"].lower())

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


# ===================================================================
# TestRunPython
# ===================================================================

class TestRunPython(unittest.TestCase):
    """Tests for run_python()."""

    def test_simple_expression(self):
        r = run_python("x = 1 + 1")
        self.assertTrue(r["success"])

    def test_print_output(self):
        r = run_python("print('hello edini')")
        self.assertTrue(r["success"])
        self.assertIn("hello edini", r["output"])

    def test_syntax_error(self):
        r = run_python("def")
        self.assertFalse(r["success"])
        self.assertIn("error", r)

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

    def test_closed_stdout_returns_diagnostics(self):
        r = run_python("import sys\nsys.stdout.close()")

        self.assertFalse(r["success"])
        self.assertIn("closed", r["error"].lower())
        self.assertIn("i/o operation", r["error"].lower())
        self.assertIn("warning", r)

    def test_closed_stderr_with_exception_returns_diagnostics(self):
        r = run_python("import sys\nsys.stderr.close()\nraise RuntimeError('boom')")

        self.assertFalse(r["success"])
        self.assertIn("boom", r["error"])
        self.assertIn("RuntimeError", r["traceback"])
        self.assertIn("warning", r)


# ===================================================================
# TestRunVex
# ===================================================================

class TestRunVex(unittest.TestCase):
    """Tests for run_vex()."""

    def test_basic(self):
        r = run_vex("@Cd = 1;")
        self.assertTrue(r["success"])
        self.assertIn("wrangle_path", r)
        # Clean up the created wrangle node
        n = _mock_hou.node(r["wrangle_path"])
        if n:
            del _mock_hou._nodes[r["wrangle_path"]]

    def test_with_input(self):
        cr = create_node("box", name="vex_input")
        _register_created_node(cr)
        r = run_vex("@Cd = 1;", node_path=cr["path"])
        self.assertTrue(r["success"])
        n = _mock_hou.node(r["wrangle_path"])
        if n:
            del _mock_hou._nodes[r["wrangle_path"]]


# ===================================================================
# TestCreateHda
# ===================================================================

class TestCreateHda(unittest.TestCase):
    """Tests for create_hda()."""

    def test_from_node(self):
        cr = create_node("box", name="hda_source")
        _register_created_node(cr)
        r = create_hda(cr["path"], "my_hda", "My HDA")
        self.assertTrue(r["success"])
        self.assertEqual(r["name"], "my_hda")

    def test_missing_node(self):
        r = create_hda("/obj/ghost", "nope", "Nope")
        self.assertFalse(r["success"])
        self.assertIn("not found", r["error"].lower())


# ===================================================================
# TestGetHdaInfo
# ===================================================================

class TestGetHdaInfo(unittest.TestCase):
    """Tests for get_hda_info()."""

    def test_unknown_hda(self):
        r = get_hda_info("nonexistent_hda")
        self.assertFalse(r["success"])
        self.assertIn("not found", r["error"].lower())


# ===================================================================
# TestGetSelection
# ===================================================================

class TestGetSelection(unittest.TestCase):
    """Tests for get_selection()."""

    def test_empty_selection(self):
        _mock_hou.set_selected([])
        r = get_selection()
        self.assertTrue(r["success"])
        self.assertEqual(r["count"], 0)
        self.assertEqual(r["nodes"], [])

    def test_with_selection(self):
        cr = create_node("box", name="sel_node")
        _register_created_node(cr)
        node = _mock_hou.node(cr["path"])
        _mock_hou.set_selected([node])
        r = get_selection()
        self.assertTrue(r["success"])
        self.assertEqual(r["count"], 1)
        self.assertEqual(r["nodes"][0]["name"], "sel_node")


# ===================================================================
# TestCheckErrors
# ===================================================================

class TestCheckErrors(unittest.TestCase):
    """Tests for check_errors()."""

    def test_scene_scan(self):
        r = check_errors()
        self.assertTrue(r["success"])
        self.assertIn("error_nodes", r)
        self.assertIn("warning_nodes", r)

    def test_single_node(self):
        cr = create_node("box", name="err_node")
        _register_created_node(cr)
        r = check_errors(cr["path"])
        self.assertTrue(r["success"])
        self.assertIn("error_count", r)
        self.assertIn("warning_count", r)
        self.assertIn("errors", r)
        self.assertIn("warnings", r)

    def test_missing_node(self):
        r = check_errors("/obj/ghost")
        self.assertFalse(r["success"])
        self.assertIn("not found", r["error"].lower())


# ===================================================================
# TestSetDisplayFlag
# ===================================================================

class TestSetDisplayFlag(unittest.TestCase):
    """Tests for set_display_flag()."""

    def test_set_flag(self):
        cr = create_node("box", name="disp_node")
        _register_created_node(cr)
        r = set_display_flag(cr["path"])
        self.assertTrue(r["success"])
        self.assertEqual(r["path"], cr["path"])

    def test_missing_node(self):
        r = set_display_flag("/obj/ghost")
        self.assertFalse(r["success"])
        self.assertIn("not found", r["error"].lower())


class TestSetParamsBatch(unittest.TestCase):
    """Tests for set_params_batch() — bulk parameter setting."""

    def setUp(self):
        cr = create_node("box", name="batch_test", parent_path="/obj")
        _register_created_node(cr)
        self.node_path = cr["path"]
        node = _mock_hou.node(self.node_path)
        node._parms["tx"] = MockParm("tx", 0.0)
        node._parms["ty"] = MockParm("ty", 0.0)
        node._parms["tz"] = MockParm("tz", 0.0)

    def test_set_params_batch_all_success(self):
        from edini.node_utils import set_params_batch
        result = set_params_batch(self.node_path, {"tx": 1.5, "ty": 2.0, "tz": 3.0})
        self.assertTrue(result["success"])
        self.assertEqual(result["set_count"], 3)
        self.assertEqual(result["total_count"], 3)
        self.assertNotIn("partial", result)

    def test_set_params_batch_missing_param(self):
        from edini.node_utils import set_params_batch
        result = set_params_batch(self.node_path, {"tx": 1.0, "nonexistent": 99})
        self.assertTrue(result["success"])
        self.assertTrue(result.get("partial"))
        self.assertEqual(result["set_count"], 1)
        self.assertIn("nonexistent", result["failed_params"])

    def test_set_params_batch_node_not_found(self):
        from edini.node_utils import set_params_batch
        result = set_params_batch("/obj/missing", {"tx": 1.0})
        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])


# ===================================================================
# TestInspectGeometryHealth
# ===================================================================

class TestInspectGeometryHealth(unittest.TestCase):
    """Tests for inspect_geometry_health() — structural geometry checks."""

    def _make_node_with_geo(self, name):
        cr = create_node("null", name=name)
        _register_created_node(cr)
        node = _mock_hou.node(cr["path"])
        geo = _mock_hou.MockGeometry()
        geo.clear()
        node._geometry = geo
        return node, geo

    def _add_triangle(self, geo, pts, cid=None, _point_cache=None):
        """Add a triangle polygon from three (x,y,z) positions.

        _point_cache: an optional dict mapping a rounded position tuple to an
        existing MockPoint, so coincident corners reuse the SAME point number
        (mirroring real Houdini topology where vertices share points). When
        provided, edge-valence checks behave realistically.
        """
        from tests.mock_hou import MockPoint
        cache = _point_cache if _point_cache is not None else {}
        verts = []
        for p in pts:
            key = (round(p[0], 6), round(p[1], 6), round(p[2], 6))
            if key in cache:
                verts.append(cache[key])
            else:
                pt = MockPoint()
                pt.setPosition(p)
                geo._points.append(pt)
                pt._number = len(geo._points) - 1
                geo._point_count = len(geo._points)
                cache[key] = pt
                verts.append(pt)
        poly = geo.createPolygon()
        for v in verts:
            poly.addVertex(v)
        if cid is not None:
            poly.setAttribValue("component_id", cid)
        return poly

    def test_missing_node(self):
        from edini.node_utils import inspect_geometry_health
        r = inspect_geometry_health("/obj/ghost")
        self.assertFalse(r["success"])

    def test_clean_geometry_passes_all_checks(self):
        from edini.node_utils import inspect_geometry_health
        node, geo = self._make_node_with_geo("health_clean")
        # A closed tetrahedron: 4 triangles, all edges shared by exactly 2
        # prims (manifold, no boundary edges), no degenerate faces, all points
        # referenced. This is the "healthy closed solid" case.
        cache = {}
        v = [(0, 0, 0), (1, 0, 0), (0.5, 1, 0), (0.5, 0.4, 0.9)]
        tris = [
            (v[0], v[1], v[2]),  # base
            (v[0], v[1], v[3]),
            (v[1], v[2], v[3]),
            (v[2], v[0], v[3]),
        ]
        for t in tris:
            self._add_triangle(geo, list(t), _point_cache=cache)

        r = inspect_geometry_health(node.path())
        self.assertTrue(r["success"])
        self.assertTrue(r["overall_ok"], f"should be healthy: {r['summary']}")
        for name, check in r["checks"].items():
            self.assertTrue(check["passed"], f"{name} should pass: {check}")

    def test_orphan_points_detected(self):
        from edini.node_utils import inspect_geometry_health
        node, geo = self._make_node_with_geo("health_orphan")
        self._add_triangle(geo, [(0, 0, 0), (1, 0, 0), (0, 1, 0)])
        # Add an orphan point referenced by no prim
        from tests.mock_hou import MockPoint
        orphan = MockPoint()
        orphan.setPosition((5, 5, 5))
        geo._points.append(orphan)
        orphan._number = len(geo._points) - 1
        geo._point_count = len(geo._points)

        r = inspect_geometry_health(node.path())
        self.assertTrue(r["success"])
        self.assertFalse(r["overall_ok"])
        self.assertFalse(r["checks"]["orphan_points"]["passed"])
        self.assertEqual(r["checks"]["orphan_points"]["count"], 1)
        self.assertIn("Fuse", r["checks"]["orphan_points"]["fix"])

    def test_degenerate_prims_detected(self):
        from edini.node_utils import inspect_geometry_health
        node, geo = self._make_node_with_geo("health_degenerate")
        # Degenerate: three colinear points → zero area
        self._add_triangle(geo, [(0, 0, 0), (1, 0, 0), (2, 0, 0)])
        r = inspect_geometry_health(node.path())
        self.assertFalse(r["checks"]["degenerate_prims"]["passed"])
        self.assertEqual(r["checks"]["degenerate_prims"]["count"], 1)

    def test_small_but_valid_triangle_not_flagged_degenerate(self):
        """Regression: a legitimate small-area triangle (like a tube fan-cap,
        area ~2e-4) must NOT be flagged degenerate. The prior implementation
        compared 0.5*|cross|² (== 2·area², NOT area) against the eps, which
        made a 2e-4-area face register as 8e-8 < 1e-7 → false positive. The
        fixed detector compares the true area directly."""
        from edini.node_utils import inspect_geometry_health
        node, geo = self._make_node_with_geo("health_small_valid")
        # Triangle with area = 0.5 * base(0.02) * height(0.02) = 2e-4.
        # Old buggy detector: 2 * (2e-4)^2 = 8e-8 < 1e-7 → wrongly "degenerate".
        self._add_triangle(geo, [(0, 0, 0), (0.02, 0, 0), (0.01, 0.02, 0)])
        r = inspect_geometry_health(node.path())
        self.assertTrue(r["checks"]["degenerate_prims"]["passed"],
                        msg=f"false positive: {r['checks']['degenerate_prims']}")
        self.assertEqual(r["checks"]["degenerate_prims"]["count"], 0)

    def test_nonmanifold_edges_detected(self):
        from edini.node_utils import inspect_geometry_health
        node, geo = self._make_node_with_geo("health_nonmanifold")
        # Three triangles all sharing edge (0)-(1) → non-manifold (count=3).
        # Use a shared point cache so the two corner points are reused
        # (real topology), giving the edge a valence of 3.
        cache = {}
        p_shared = [(0, 0, 0), (1, 0, 0)]
        self._add_triangle(geo, [p_shared[0], p_shared[1], (0, 1, 0)], _point_cache=cache)
        self._add_triangle(geo, [p_shared[0], p_shared[1], (0, -1, 0)], _point_cache=cache)
        self._add_triangle(geo, [p_shared[0], p_shared[1], (0, 0, 1)], _point_cache=cache)
        r = inspect_geometry_health(node.path())
        self.assertFalse(r["checks"]["nonmanifold_edges"]["passed"])
        self.assertGreaterEqual(r["checks"]["nonmanifold_edges"]["count"], 1)

    def test_open_boundary_edges_detected(self):
        from edini.node_utils import inspect_geometry_health
        node, geo = self._make_node_with_geo("health_open_boundary")
        # A single triangle has 3 boundary edges (each shared by 1 prim)
        self._add_triangle(geo, [(0, 0, 0), (1, 0, 0), (0, 1, 0)])
        r = inspect_geometry_health(node.path())
        self.assertFalse(r["checks"]["open_boundary_edges"]["passed"])
        self.assertEqual(r["checks"]["open_boundary_edges"]["count"], 3)

    def test_summary_lists_all_check_names(self):
        from edini.node_utils import inspect_geometry_health
        node, geo = self._make_node_with_geo("health_summary")
        self._add_triangle(geo, [(0, 0, 0), (1, 0, 0), (0, 1, 0)])
        r = inspect_geometry_health(node.path())
        expected = {"orphan_points", "open_curves", "degenerate_prims",
                    "nonmanifold_edges", "open_boundary_edges",
                    "coincident_points"}
        self.assertEqual(set(r["summary"].keys()), expected)


# ===================================================================
# TestGeometryInventory
# ===================================================================

class TestGeometryInventory(unittest.TestCase):
    """Tests for geometry_inventory() — per-component breakdown."""

    def _make_node_with_components(self, name, components):
        """components: dict of cid -> list of triangle point-tuples."""
        cr = create_node("null", name=name)
        _register_created_node(cr)
        node = _mock_hou.node(cr["path"])
        geo = _mock_hou.MockGeometry()
        geo.clear()
        node._geometry = geo
        geo.addAttrib(None, "component_id", "")
        for cid, tris in components.items():
            for tri in tris:
                from tests.mock_hou import MockPoint
                verts = []
                for p in tri:
                    pt = MockPoint()
                    pt.setPosition(p)
                    geo._points.append(pt)
                    pt._number = len(geo._points) - 1
                    geo._point_count = len(geo._points)
                    verts.append(pt)
                poly = geo.createPolygon()
                for v in verts:
                    poly.addVertex(v)
                poly.setAttribValue("component_id", cid)
        return node

    def test_no_component_id_attribute(self):
        from edini.node_utils import geometry_inventory
        cr = create_node("null", name="inv_no_cid")
        _register_created_node(cr)
        node = _mock_hou.node(cr["path"])
        node._geometry = _mock_hou.MockGeometry(point_count=4, prim_count=1)

        r = geometry_inventory(node.path())
        self.assertTrue(r["success"])
        self.assertFalse(r["has_component_id"])
        self.assertEqual(r["total_components"], 0)

    def test_inventory_lists_each_component(self):
        from edini.node_utils import geometry_inventory
        node = self._make_node_with_components("inv_multi", {
            "frame": [[(0, 0, 0), (2, 0, 0), (0, 2, 0)]],   # big
            "bolt": [[(5, 5, 5), (5.01, 5, 0), (5, 5.01, 0)]],  # tiny
        })
        r = geometry_inventory(node.path())
        self.assertTrue(r["success"])
        self.assertTrue(r["has_component_id"])
        self.assertEqual(r["total_components"], 2)
        ids = {c["component_id"] for c in r["components"]}
        self.assertEqual(ids, {"frame", "bolt"})

    def test_inventory_flags_small_components(self):
        from edini.node_utils import geometry_inventory
        node = self._make_node_with_components("inv_small", {
            "frame": [[(0, 0, 0), (3, 0, 0), (0, 3, 0)]],
            "tiny_chain": [[(0, 0, 0.01), (0.001, 0, 0.01), (0, 0.001, 0.01)]],
        })
        r = geometry_inventory(node.path())
        by_id = {c["component_id"]: c for c in r["components"]}
        # The tiny component's size_fraction should be well under the whole
        self.assertLess(by_id["tiny_chain"]["size_fraction"],
                        by_id["frame"]["size_fraction"])
        self.assertLess(by_id["tiny_chain"]["size_fraction"], 0.1)

    def test_inventory_text_is_present(self):
        from edini.node_utils import geometry_inventory
        node = self._make_node_with_components("inv_text", {
            "wheel": [[(0, 0, 0), (1, 0, 0), (0, 1, 0)]],
        })
        r = geometry_inventory(node.path())
        self.assertIn("GEOMETRY_INVENTORY", r["inventory_text"])
        self.assertIn("wheel", r["inventory_text"])


if __name__ == "__main__":
    unittest.main()
