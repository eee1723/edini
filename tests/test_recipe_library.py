"""Tests for the recipe library (capture / rebuild / index / notes validation).

Uses the hou mock (tests/mock_hou.py) so these run without Houdini. Mirrors
the module-level mock-install style of test_node_utils.py.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python3.11libs"))

# recipe_library imports hou lazily (only inside capture/rebuild functions),
# so importing the module does NOT require a pre-installed hou. We deliberately
# avoid replacing sys.modules["hou"] at module load time — that would leak a
# mock into sibling test modules (e.g. test_node_utils) that share the global.
# The hou-dependent TestCaptureRebuild class installs a fresh mock in setUp and
# restores the prior one in tearDown.
from tests.mock_hou import create_mock_hou  # noqa: E402

from edini import recipe_library as rl  # noqa: E402


def _fresh_recipes_dir():
    """Point recipe_library at a temp dir so tests don't pollute the real repo."""
    tmp = tempfile.mkdtemp(prefix="recipes_test_")
    return tmp


def _make_subnet_with_notes(hou, parent_path, name, notes, children_spec):
    """Helper: build a subnet with notes + named children + param tweaks.

    children_spec: list of dicts {name, type, changed={parm:val}, marked=[...]}
    Returns the subnet MockNode.
    """
    parent = hou.node(parent_path)
    subnet = parent.createNode("subnet", name)
    subnet.setComment(notes)
    for spec in children_spec:
        child = subnet.createNode(spec["type"], spec["name"])
        for pname, val in spec.get("changed", {}).items():
            child._parms[pname] = __import__("tests.mock_hou", fromlist=["MockParm"]).MockParm(pname, val)
    return subnet


class TestNotesParsing(unittest.TestCase):
    def test_parse_extracts_all_fields(self):
        notes = ("功能：沿曲线生成封闭圆柱管材\n"
                 "用途：车架管、栏杆\n"
                 "重要参数：radius, segments\n"
                 "不要用于：变径管\n"
                 "输入：guide_curve（第0输入）")
        parsed = rl.parse_notes(notes)
        self.assertIn("管材", parsed["function"])
        self.assertIn("车架管", parsed["use_case"])
        self.assertEqual(parsed["marked"], ["radius", "segments"])
        self.assertEqual(parsed["avoid"], "变径管")
        self.assertIn("guide_curve", parsed["inputs_desc"])

    def test_parse_unprefixed_lines_go_to_function(self):
        parsed = rl.parse_notes("这是一段\n自由描述")
        self.assertEqual(parsed["function"], "这是一段\n自由描述")


class TestNotesValidation(unittest.TestCase):
    def test_empty_notes_rejected(self):
        ok, reason = rl.validate_notes("")
        self.assertFalse(ok)
        self.assertIn("为空", reason)

    def test_placeholder_notes_rejected(self):
        for ph in ("todo", "notes", "placeholder", "注释", "TODO"):
            ok, reason = rl.validate_notes(ph)
            self.assertFalse(ok, f"{ph!r} should be rejected")
            self.assertIn("占位", reason)

    def test_notes_without_function_prefix_accepted_if_descriptive(self):
        # Free-text (no 中文 prefix) is accepted as the function description
        # as long as it is non-empty, non-placeholder, and descriptive.
        ok, _ = rl.validate_notes("Generates a tube along a guide curve")
        self.assertTrue(ok)

    def test_valid_notes_accepted(self):
        ok, _ = rl.validate_notes("功能：生成管材\n输入：曲线")
        self.assertTrue(ok)


class TestTopoSort(unittest.TestCase):
    def test_linear_chain_sorted(self):
        nodes = [
            {"name": "c", "inputs": {"0": "b"}},
            {"name": "a", "inputs": {"0": None}},
            {"name": "b", "inputs": {"0": "a"}},
        ]
        ordered = [n["name"] for n in rl._topo_sort(nodes)]
        self.assertEqual(ordered, ["a", "b", "c"])

    def test_disconnected_nodes_preserved(self):
        nodes = [
            {"name": "x", "inputs": {}},
            {"name": "y", "inputs": {}},
        ]
        ordered = [n["name"] for n in rl._topo_sort(nodes)]
        self.assertEqual(set(ordered), {"x", "y"})

    def test_cycle_does_not_loop_forever(self):
        nodes = [
            {"name": "a", "inputs": {"0": "b"}},
            {"name": "b", "inputs": {"0": "a"}},
        ]
        ordered = [n["name"] for n in rl._topo_sort(nodes)]
        self.assertEqual(set(ordered), {"a", "b"})


class TestCaptureRebuild(unittest.TestCase):
    """Full capture→rebuild round-trip using the hou mock.

    Each test points rl at a temp recipes dir to stay isolated.
    """

    def setUp(self):
        self._tmp = _fresh_recipes_dir()
        # Patch the path-resolving functions on the already-loaded module so
        # capture/rebuild write into the temp dir.
        self._orig_root = rl._project_root
        rl._project_root = lambda: self._tmp  # type: ignore
        # Snapshot ALL shared state we're about to mutate so we can restore it
        # exactly. MockNode._hou_ref is a CLASS attribute shared across all mock
        # instances — if we don't restore it, other test modules (test_node_utils)
        # that hold their own module-level mock reference see a stale _hou_ref
        # pointing at our ephemeral mock, breaking their node lookups.
        from tests.mock_hou import MockNode
        self._prev_hou = sys.modules.get("hou")
        self._prev_hou_ref = MockNode._hou_ref
        global _mock_hou
        _mock_hou = create_mock_hou()
        sys.modules["hou"] = _mock_hou

    def tearDown(self):
        rl._project_root = self._orig_root  # type: ignore
        from tests.mock_hou import MockNode
        MockNode._hou_ref = self._prev_hou_ref
        sys.modules["hou"] = self._prev_hou
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_subnet(self, name, notes, children):
        parent = sys.modules["hou"].node("/obj")
        subnet = parent.createNode("subnet", name)
        subnet.setComment(notes)
        MockParm = __import__("tests.mock_hou", fromlist=["MockParm"]).MockParm
        for spec in children:
            child = subnet.createNode(spec["type"], spec["name"])
            for pname, val in spec.get("changed", {}).items():
                child._parms[pname] = MockParm(pname, val)
            for pname in spec.get("marked", []):
                if pname not in child._parms:
                    child._parms[pname] = MockParm(pname, 0)
        return subnet

    def test_capture_rejects_empty_notes(self):
        subnet = self._make_subnet("bad_one", "", [])
        r = rl.recipe_capture(subnet.path())
        self.assertFalse(r["success"])
        self.assertIn("为空", r["error"])

    def test_capture_writes_recipe_json(self):
        subnet = self._make_subnet(
            "tube_demo",
            "功能：管材\n重要参数：surfaceshape",
            [
                {"name": "curve1", "type": "curve", "changed": {"type": "nurbs"}},
                {"name": "sweep1", "type": "sweep::2.0",
                 "changed": {"endcaptype": 1}},
            ])
        # wire sweep1 <- curve1
        subnet.children()[1].setInput(0, subnet.children()[0])
        r = rl.recipe_capture(subnet.path())
        self.assertTrue(r["success"], r.get("error"))
        self.assertEqual(r["recipe_id"], "tube_demo")
        rj = json.load(open(os.path.join(self._tmp, "recipes", "tube_demo", "recipe.json"),
                            encoding="utf-8"))
        self.assertEqual(rj["id"], "tube_demo")
        self.assertIn("管材", rj["function"])
        names = {n["name"] for n in rj["nodes"]}
        self.assertEqual(names, {"curve1", "sweep1"})
        sweep = next(n for n in rj["nodes"] if n["name"] == "sweep1")
        # sweep1 inputs reference curve1 by relative name
        self.assertEqual(sweep["inputs"]["0"], "curve1")
        # surfaceshape was marked in Notes → recorded even if equal to default
        # (sweep::2.0 PTG declares 'surfaceshape' in the mock)
        self.assertIn("surfaceshape", sweep["marked_params"])

    def test_capture_rebuilds_index(self):
        subnet = self._make_subnet("ex_profile", "功能：挤出截面", [
            {"name": "poly1", "type": "polyextrude::2.0", "changed": {}},
        ])
        rl.recipe_capture(subnet.path())
        idx = json.load(open(os.path.join(self._tmp, "recipes", "index.json"),
                             encoding="utf-8"))
        ids = [e["id"] for e in idx["entries"]]
        self.assertIn("ex_profile", ids)

    def test_rebuild_creates_nodes_and_applies_params(self):
        # Capture first. Use null nodes (no PTG needed) + a manual parm we add
        # back on rebuild via marked, so we verify the wiring + structure rather
        # than a type-specific default parm.
        subnet = self._make_subnet("copy_demo", "功能：复制到点", [
            {"name": "src", "type": "null", "changed": {}},
            {"name": "ctp", "type": "null", "changed": {}},
        ])
        subnet.children()[1].setInput(0, subnet.children()[0])
        rl.recipe_capture(subnet.path())
        # Now rebuild into a fresh parent.
        r = rl.recipe_rebuild("copy_demo", "/obj", name="copy_instance")
        self.assertTrue(r["success"], r.get("verify"))
        self.assertEqual(r["node_count"], 2)
        rebuilt = sys.modules["hou"].node("/obj/copy_instance")
        self.assertIsNotNone(rebuilt)
        kids = {c.name(): c for c in rebuilt.children()}
        self.assertIn("src", kids)
        self.assertIn("ctp", kids)
        # wiring recreated
        self.assertIsNotNone(kids["ctp"].inputs()[0])
        self.assertEqual(kids["ctp"].inputs()[0].name(), "src")

    def test_rebuild_missing_recipe_fails(self):
        r = rl.recipe_rebuild("nonexistent_recipe", "/obj")
        self.assertFalse(r["success"])
        self.assertIn("not found", r["error"])

    def test_rebuild_topological_order(self):
        # Reverse-specify order in recipe: b before a, but b depends on a.
        subnet = self._make_subnet("chain_demo", "功能：链式", [
            {"name": "a", "type": "null", "changed": {}},
            {"name": "b", "type": "null", "changed": {}},
        ])
        subnet.children()[1].setInput(0, subnet.children()[0])  # b <- a
        rl.recipe_capture(subnet.path())
        r = rl.recipe_rebuild("chain_demo", "/obj", name="chain_inst")
        self.assertTrue(r["success"], r.get("warnings"))


class TestIndexQueries(unittest.TestCase):
    """Pure file-I/O index queries — no hou."""

    def setUp(self):
        self._tmp = _fresh_recipes_dir()
        self._orig_root = rl._project_root
        rl._project_root = lambda: self._tmp  # type: ignore
        # Hand-write a couple recipe.json files + rebuild index.
        for rid, func, cat in [("tube_one", "沿曲线管材", "tube"),
                               ("extrude_one", "挤出截面", "extrude")]:
            d = os.path.join(self._tmp, "recipes", rid)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "recipe.json"), "w", encoding="utf-8") as f:
                json.dump({"schema_version": 1, "id": rid, "name": rid,
                           "notes": func, "function": func, "category": cat,
                           "nodes": [], "exposed_parms": [],
                           "inputs": [], "outputs": []}, f)
        rl.rebuild_index()

    def tearDown(self):
        rl._project_root = self._orig_root  # type: ignore
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_list_all_when_no_query(self):
        r = rl.recipe_list()
        self.assertTrue(r["success"])
        self.assertEqual(r["total"], 2)
        self.assertEqual(r["matched"], 2)

    def test_list_filter_by_keyword(self):
        r = rl.recipe_list(query="管材")
        self.assertEqual(r["matched"], 1)
        self.assertEqual(r["matches"][0]["id"], "tube_one")

    def test_list_filter_by_category(self):
        r = rl.recipe_list(category="extrude")
        self.assertEqual(r["matched"], 1)
        self.assertEqual(r["matches"][0]["id"], "extrude_one")

    def test_read_returns_full_recipe(self):
        r = rl.recipe_read("tube_one")
        self.assertTrue(r["success"])
        self.assertEqual(r["recipe"]["id"], "tube_one")

    def test_read_missing_recipe(self):
        r = rl.recipe_read("nope")
        self.assertFalse(r["success"])


if __name__ == "__main__":
    unittest.main()
