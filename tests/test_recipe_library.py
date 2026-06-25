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


class TestCategoryInference(unittest.TestCase):
    """Pure-function tests for _infer_category — the new primitives must land
    in a useful category so recipe_list filters work."""

    def test_linear_array_is_array(self):
        cat = rl._infer_category("单位模板沿输入曲线均匀阵列 N 份", "linear_array_copy")
        self.assertEqual(cat, "array")

    def test_boolean_is_boolean(self):
        cat = rl._infer_category("两段输入几何做布尔运算", "boolean_op")
        self.assertEqual(cat, "boolean")

    def test_bevel_is_bevel(self):
        cat = rl._infer_category("给指定边组倒圆角/切角", "bevel_edges")
        self.assertEqual(cat, "bevel")


class TestParamNormalization(unittest.TestCase):
    """Pure-function tests for default comparison + multiparm lookup + ramp dict.
    No hou required."""

    def test_scalar_equals_single_element_list(self):
        # manifest wraps numeric defaults as [N]; parm.eval() returns N.
        self.assertTrue(rl._values_equal(4, [4]))
        self.assertTrue(rl._values_equal([4], 4))
        self.assertTrue(rl._values_equal(3.0, [3.0]))
        self.assertTrue(rl._values_equal(0.125, [0.125]))

    def test_scalar_not_equal_wrong_list(self):
        self.assertFalse(rl._values_equal(4, [5]))
        self.assertFalse(rl._values_equal(4, [4, 5]))

    def test_multiparm_lookup_template_name(self):
        # manifest key 'heightprofile#pos' should match live 'heightprofile2pos'
        defs = {"heightprofile#pos": [0.0], "order": [4]}
        self.assertEqual(rl._manifest_lookup("heightprofile2pos", defs), [0.0])
        self.assertEqual(rl._manifest_lookup("scaleramp3value", defs), None)
        self.assertEqual(rl._manifest_lookup("order", defs), [4])

    def test_ramp_dict_roundtrip_shape(self):
        # _ramp_to_dict needs a duck-typed ramp; build a fake.
        class FakeRamp:
            def keys(self): return (0.0, 1.0)
            def values(self): return (0.5, 1.0)
            def basis(self): return (1, 1)
            def isColor(self): return False
        d = rl._ramp_to_dict(FakeRamp())
        self.assertEqual(d["__type__"], rl._RAMP_MARKER)
        self.assertEqual(d["keys"], [0.0, 1.0])
        self.assertEqual(d["values"], [0.5, 1.0])
        self.assertTrue(rl._is_ramp_dict(d))
        self.assertFalse(rl._is_ramp_dict({"keys": [0.0]}))
        self.assertFalse(rl._is_ramp_dict("not a dict"))

    def test_string_scalar_equals_single_element_list(self):
        # manifest wraps String defaults as ['x']; parm.eval() returns 'x'.
        # This was the biggest false-positive source: attrib names like
        # 'roll' never matched ['roll'].
        self.assertTrue(rl._values_equal("", [""]))
        self.assertTrue(rl._values_equal([""], ""))
        self.assertTrue(rl._values_equal("roll", ["roll"]))
        self.assertFalse(rl._values_equal("roll", ["yaw"]))

    def test_manifest_defaults_prefers_versioned_name(self):
        # sweep::2.0 (81 real parms) and sweep (20 legacy parms) are DIFFERENT
        # nodes in the manifest. The lookup must use the exact versioned name,
        # not fall back to the unversioned base — otherwise every real parm is
        # reported as unknown and capture drowns in false-positive 'changed'.
        manifest = {"node_types": {
            "sweep": {"parms": [{"name": "legacy_parm", "default": [0]}]},
            "sweep::2.0": {"parms": [
                {"name": "surfacetype", "default": [5]},
                {"name": "endcaptype", "default": [0]}]},
        }}
        defs = rl._manifest_defaults("sweep::2.0", manifest)
        self.assertIn("surfacetype", defs)
        self.assertNotIn("legacy_parm", defs)

    def test_vector_xyzw_component_matches_parent(self):
        # 'upvectorx' should resolve to upvector[0] (a 3-vector default).
        defs = {"upvector": [0.0, 1.0, 0.0]}
        self.assertEqual(rl._manifest_lookup("upvectorx", defs), 0.0)
        self.assertEqual(rl._manifest_lookup("upvectory", defs), 1.0)
        self.assertEqual(rl._manifest_lookup("upvectorz", defs), 0.0)

    def test_vector_numeric_component_matches_parent(self):
        # 'uvscale1'/'uvscale2' should resolve to uvscale[0]/[1] (a 2-vector).
        # Must NOT collide with multiparms whose parent isn't a vector.
        defs = {"uvscale": [1.0, 1.0], "scaleramp#value": [0.0]}
        self.assertEqual(rl._manifest_lookup("uvscale1", defs), 1.0)
        self.assertEqual(rl._manifest_lookup("uvscale2", defs), 1.0)

    def test_folder_state_parm_detected(self):
        # Collapsible-folder UI state (up_folder etc.) is never authored and
        # never catalogued — it must be recognized so capture skips it.
        self.assertTrue(rl._is_folder_state_parm("up_folder"))
        self.assertTrue(rl._is_folder_state_parm("uv_folder"))
        # polyextrude::2.0 uses 'xformsection', 'outputsection' for tab state.
        self.assertTrue(rl._is_folder_state_parm("xformsection"))
        self.assertTrue(rl._is_folder_state_parm("outputsection"))
        # attribrandomize uses bare 'folder' / 'folder01'.
        self.assertTrue(rl._is_folder_state_parm("folder"))
        self.assertTrue(rl._is_folder_state_parm("folder01"))
        self.assertTrue(rl._is_folder_state_parm("stdswitcher1"))
        # Real authored parms must NOT be flagged.
        self.assertFalse(rl._is_folder_state_parm("surfacetype"))
        self.assertFalse(rl._is_folder_state_parm("dist"))
        self.assertFalse(rl._is_folder_state_parm("foldercount"))

    def test_multiparm_index_tail_matches_template(self):
        # 'value0' -> manifest template 'value#' (attribrandomize value0..3).
        # 'useapply1' -> 'useapply#' (copytopoints). Only matches when the '#'
        # template actually exists in the manifest — no false positives.
        defs = {"value#": [0.0], "useapply#": [0]}
        self.assertEqual(rl._manifest_lookup("value0", defs), [0.0])
        self.assertEqual(rl._manifest_lookup("value3", defs), [0.0])
        self.assertEqual(rl._manifest_lookup("useapply1", defs), [0])
        # A plain 'cols8' whose 'cols#' template doesn't exist stays unknown.
        self.assertIsNone(rl._manifest_lookup("cols8", defs))


class TestPythonScriptGeneration(unittest.TestCase):
    """Pure-function tests for _generate_python_script.

    The script is reference material for edini: it must surface the author's
    marked parameters (the ones that matter) and reproduce non-trivial changed
    params, while skipping noise (identity transforms, empty strings, folder
    state). Built from a hand-constructed recipe dict so it stays isolated.
    """

    def _tube_recipe(self):
        """A minimal recipe mirroring tube_along_curve's shape."""
        return {
            "id": "tube_along_curve", "name": "tube_along_curve",
            "function": "沿曲线生成封闭圆柱管材",
            "use_case": "弯把、前叉", "avoid": "变径管",
            "vex_snippets": [],
            "nodes": [
                {"name": "path_line", "type": "line", "inputs": {},
                 "changed_params": {"diry": 1.0, "tx": 0.0},
                 "marked_params": {}, "expressions": {}},
                {"name": "section", "type": "circle", "inputs": {},
                 "changed_params": {"radx": 0.012, "rady": 0.012, "type": 1},
                 "marked_params": {}, "expressions": {}},
                {"name": "sweep1", "type": "sweep::2.0",
                 "inputs": {"0": "path_line", "1": "section"},
                 "changed_params": {"surfacetype": 2, "endcaptype": 1,
                                    "tx": 0.0, "curvegroup": ""},
                 "marked_params": {"surfacetype": 2, "endcaptype": 1},
                 "expressions": {}},
            ],
        }

    def test_generates_function_with_create_and_wire(self):
        script = rl._generate_python_script(self._tube_recipe())
        self.assertIn("def build_tube_along_curve(parent):", script)
        self.assertIn("createNode('sweep::2.0', 'sweep1')", script)
        # wiring present, after creation
        self.assertIn("sweep1.setInput(0, path_line)", script)
        self.assertIn("sweep1.setInput(1, section)", script)

    def test_marked_params_get_author_comment(self):
        script = rl._generate_python_script(self._tube_recipe())
        self.assertIn("surfacetype').set(2)  # author-marked", script)
        self.assertIn("endcaptype').set(1)  # author-marked", script)

    def test_noise_params_filtered(self):
        # Identity transforms (tx=0) and empty strings (curvegroup='') carry
        # no intent and must not clutter the script.
        script = rl._generate_python_script(self._tube_recipe())
        self.assertNotIn("'tx'", script)
        self.assertNotIn("'curvegroup'", script)

    def test_vex_snippet_inlined(self):
        recipe = self._tube_recipe()
        recipe["vex_snippets"] = [{
            "node": "sweep1", "code": "v@P.x = 1;", "runover": 1}]
        recipe["nodes"][2]["type"] = "attribwrangle"
        script = rl._generate_python_script(recipe)
        self.assertIn('"""', script)
        self.assertIn("v@P.x = 1;", script)
        self.assertIn("run-over: class=1", script)


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

    # ── Promoted-parameter / exposed_parms closure ──────────────────────
    # These prove the loop that the recipe-capture button enables:
    # a subnet-level parm carrying a ch("../inner/parm") reference (i.e. a
    # Promote Parameter result) is captured into exposed_parms[], and a
    # rebuild override on that subnet_parm flows through to the inner node.

    def _promote_parm(self, subnet, subnet_parm, inner_node, inner_parm, value):
        """Stand up a promoted subnet parm: a top-level parm whose expression
        is ch("../inner_node/inner_parm"). Mirrors Houdini's Promote Parameter."""
        MockParm = __import__("tests.mock_hou", fromlist=["MockParm"]).MockParm
        p = MockParm(subnet_parm, value)
        p.setExpression(f'ch("../{inner_node}/{inner_parm}")')
        subnet._parms[subnet_parm] = p

    def test_promoted_parm_captured_as_exposed(self):
        """A subnet parm with a ch("../sweep1/rad") reference lands in
        exposed_parms with the inner node.parm target recorded."""
        subnet = self._make_subnet("tube_p", "功能：扫管", [
            {"name": "sweep1", "type": "null",
             "changed": {"rad": 0.012}},
        ])
        self._promote_parm(subnet, "rad", "sweep1", "rad", 0.012)
        rl.recipe_capture(subnet.path())
        rj = json.load(open(os.path.join(self._tmp, "recipes", "tube_p",
                                         "recipe.json"), encoding="utf-8"))
        exposed = {e["subnet_parm"]: e for e in rj["exposed_parms"]}
        self.assertIn("rad", exposed)
        self.assertEqual(exposed["rad"]["target"], "sweep1.rad")

    # NOTE: the override-flows-to-inner-node path (recipe_rebuild overrides
    # setting the inner node's parm) is verified against the real sweep::2.0
    # node in Houdini, where a real 'rad' parm exists. Under the mock, a null
    # node has no rad parm for the override to land on, so it can't be asserted
    # here without faking the very thing under test.


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
                           # tube marks endcaptype (a convention); extrude marks dist.
                           "nodes": [{"name": "core", "type": "sweep",
                                      "changed_params": {}, "marked_params": (
                                          {"endcaptype": 1} if "tube" in cat
                                          else {"dist": 0.5}),
                                      "expressions": {}, "inputs": {}}],
                           "exposed_parms": [],
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

    def test_list_search_by_marked_parm(self):
        # marked_parms are the author's convention signal (e.g. endcaptype).
        # Searching by a convention name must find the recipe that encodes it.
        r = rl.recipe_list(query="endcaptype")
        self.assertEqual(r["matched"], 1)
        self.assertEqual(r["matches"][0]["id"], "tube_one")
        # The marked_parms should also surface in the match summary.
        self.assertIn("endcaptype", r["matches"][0].get("marked_parms", []))

    def test_read_returns_full_recipe(self):
        r = rl.recipe_read("tube_one")
        self.assertTrue(r["success"])
        self.assertEqual(r["recipe"]["id"], "tube_one")

    def test_read_missing_recipe(self):
        r = rl.recipe_read("nope")
        self.assertFalse(r["success"])


# ─────────────────────────────────────────────────────────────────────────────
# New schema: kind / tree_path / vex_snippets / output-node filtering /
# recursive tree capture. These all use the same hou-mock fixture as above.
# ─────────────────────────────────────────────────────────────────────────────
class TestVexCapture(unittest.TestCase):
    """Wrangle nodes: snippet extracted into vex_snippets[] (not changed_params),
    runover recorded alongside. kind flips to 'vex' when a wrangle is present."""

    def setUp(self):
        self._tmp = _fresh_recipes_dir()
        self._orig_root = rl._project_root
        rl._project_root = lambda: self._tmp  # type: ignore
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
        return subnet

    def test_wrangle_snippet_goes_to_vex_snippets(self):
        subnet = self._make_subnet("vex_demo", "功能：协方差矩阵", [
            {"name": "wr1", "type": "attribwrangle",
             "changed": {"snippet": "v@P += 0;", "class": 1}},
        ])
        r = rl.recipe_capture(subnet.path())
        self.assertTrue(r["success"], r.get("error"))
        rj = json.load(open(os.path.join(self._tmp, "recipes", "vex_demo", "recipe.json"),
                            encoding="utf-8"))
        # snippet must NOT pollute changed_params
        wr = next(n for n in rj["nodes"] if n["name"] == "wr1")
        self.assertNotIn("snippet", wr.get("changed_params", {}))
        # snippet must appear in vex_snippets with runover
        self.assertTrue(any("v@P" in s["code"] for s in rj.get("vex_snippets", [])))
        snip = rj["vex_snippets"][0]
        self.assertIn("runover", snip)
        # kind must be 'vex'
        self.assertEqual(rj["kind"], "vex")

    def test_network_kind_when_no_wrangle(self):
        subnet = self._make_subnet("net_demo", "功能：管材", [
            {"name": "c1", "type": "null", "changed": {}},
        ])
        r = rl.recipe_capture(subnet.path())
        rj = json.load(open(os.path.join(self._tmp, "recipes", "net_demo", "recipe.json"),
                            encoding="utf-8"))
        self.assertEqual(rj["kind"], "network")
        self.assertEqual(rj.get("vex_snippets"), [])

    def test_rebuild_restores_snippet(self):
        subnet = self._make_subnet("vex_reb", "功能：测试", [
            {"name": "wr1", "type": "attribwrangle",
             "changed": {"snippet": "v@P.x = 1;", "class": 0}},
        ])
        rl.recipe_capture(subnet.path())
        r = rl.recipe_rebuild("vex_reb", "/obj", name="vex_reb_inst")
        self.assertTrue(r["success"], r.get("verify", {}).get("mismatches"))
        rebuilt = sys.modules["hou"].node("/obj/vex_reb_inst")
        wr = rebuilt.children()[0]
        self.assertEqual(wr._parms["snippet"].eval(), "v@P.x = 1;")
        self.assertEqual(wr._parms["class"].eval(), 0)


class TestOutputNodeFiltering(unittest.TestCase):
    """output/stashed_geo nodes must NOT be captured as recipe nodes."""

    def setUp(self):
        self._tmp = _fresh_recipes_dir()
        self._orig_root = rl._project_root
        rl._project_root = lambda: self._tmp  # type: ignore
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

    def test_output_node_not_captured(self):
        parent = sys.modules["hou"].node("/obj")
        subnet = parent.createNode("subnet", "with_out")
        subnet.setComment("功能：测试输出节点过滤")
        c1 = subnet.createNode("null", "real1")
        out = subnet.createNode("output", "output0")
        out.setInput(0, c1)
        r = rl.recipe_capture(subnet.path())
        self.assertTrue(r["success"])
        self.assertEqual(r["node_count"], 1)  # only real1, not output0
        rj = json.load(open(os.path.join(self._tmp, "recipes", "with_out", "recipe.json"),
                            encoding="utf-8"))
        names = {n["name"] for n in rj["nodes"]}
        self.assertEqual(names, {"real1"})


class TestTreeCapture(unittest.TestCase):
    """recipe_capture_tree: recursive leaf capture with tree_path-based id."""

    def setUp(self):
        self._tmp = _fresh_recipes_dir()
        self._orig_root = rl._project_root
        rl._project_root = lambda: self._tmp  # type: ignore
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

    def _build_tree(self):
        """Build a 2-level tree mirroring the user's structure:
        /obj/sopnet1/Procedural_Modeling/Base_Sweep  (leaf: curve+circle+sweep)
        /obj/sopnet1/Sim/RBD/Voronoi_Fracture         (leaf: box+scatter+voro)
        """
        hou = sys.modules["hou"]
        obj = hou.node("/obj")
        sopnet = obj.createNode("subnet", "sopnet1")
        pm = sopnet.createNode("subnet", "Procedural_Modeling")
        bs = pm.createNode("subnet", "Base_Sweep")
        bs.createNode("curve::2.0", "guide_curve")
        bs.createNode("circle", "profile")
        sweep = bs.createNode("sweep::2.0", "sweep1")
        sweep.setInput(0, bs.children()[0])
        sweep.setInput(1, bs.children()[1])
        sim = sopnet.createNode("subnet", "Sim")
        rbd = sim.createNode("subnet", "RBD")
        voro = rbd.createNode("subnet", "Voronoi_Fracture")
        box = voro.createNode("box", "box1")
        scat = voro.createNode("scatter::2.0", "scatter1")
        scat.setInput(0, box)
        return sopnet

    def test_capture_tree_finds_all_leaves(self):
        sopnet = self._build_tree()
        r = rl.recipe_capture_tree("/obj/sopnet1")
        self.assertTrue(r["success"])
        self.assertEqual(r["captured_count"], 2)
        self.assertEqual(r["skipped_count"], 0)
        ids = {c["recipe_id"] for c in r["captured"]}
        self.assertEqual(ids, {"Procedural_Modeling.Base_Sweep",
                               "Sim.RBD.Voronoi_Fracture"})

    def test_capture_tree_tree_path_stored(self):
        self._build_tree()
        rl.recipe_capture_tree("/obj/sopnet1")
        rj = json.load(open(os.path.join(self._tmp, "recipes",
                                         "Procedural_Modeling.Base_Sweep", "recipe.json"),
                            encoding="utf-8"))
        self.assertEqual(rj["tree_path"], ["sopnet1", "Procedural_Modeling"])

    def test_capture_tree_auto_generates_notes(self):
        """Empty Notes → auto-generated default, recorded as warning."""
        self._build_tree()
        r = rl.recipe_capture_tree("/obj/sopnet1")
        # every captured recipe should have auto-notes warning
        for c in r["captured"]:
            self.assertTrue(any("auto-generated notes" in w.lower()
                                or "auto" in w.lower() for w in c.get("warnings", [])),
                            f"no auto-notes warning for {c['recipe_id']}")
        rj = json.load(open(os.path.join(self._tmp, "recipes",
                                         "Procedural_Modeling.Base_Sweep", "recipe.json"),
                            encoding="utf-8"))
        # generated notes must contain tree path + node types
        self.assertIn("Base_Sweep", rj["notes"])

    def test_capture_tree_skips_empty_subnet(self):
        """A subnet with no children at all is neither container nor leaf."""
        hou = sys.modules["hou"]
        obj = hou.node("/obj")
        sopnet = obj.createNode("subnet", "sopnet1")
        # empty container (no children)
        sopnet.createNode("subnet", "Empty_Cat")
        # real leaf
        pm = sopnet.createNode("subnet", "Procedural_Modeling")
        bs = pm.createNode("subnet", "Base_Sweep")
        bs.createNode("null", "n1")
        r = rl.recipe_capture_tree("/obj/sopnet1")
        self.assertEqual(r["captured_count"], 1)

    def test_capture_tree_query_by_tree_path(self):
        self._build_tree()
        rl.recipe_capture_tree("/obj/sopnet1")
        # query by category component
        r = rl.recipe_list(query="Sim")
        self.assertEqual(r["matched"], 1)
        self.assertEqual(r["matches"][0]["id"], "Sim.RBD.Voronoi_Fracture")

    def test_capture_tree_does_not_pierce_network_containers(self):
        """Regression: a leaf subnet containing a *network container* node
        (popnet/dopnet/sopnet) must be captured as ONE recipe — the network
        container is part of the recipe's content, NOT a category layer to
        descend into.

        Real-world failure: in actual Houdini, a popnet node's type().name()
        returns a value the walker treated as a descendable container, so a
        leaf like Pop_Force (containing a popnet) was wrongly pierced:
        Pop_Force was treated as a container and the popnet's internals were
        captured as a bogus 'Sim.Pop.Pop_Force.popnet1' recipe.

        We simulate BOTH possible real-world type-name shapes by parametrising
        the popnet node's reported type name, since Houdini network containers
        may report 'popnet' OR 'subnet' depending on context. The fix must hold
        for both."""
        from tests.mock_hou import MockNodeType

        for reported_type in ("popnet", "subnet"):
            with self.subTest(reported_type=reported_type):
                hou = create_mock_hou()
                sys.modules["hou"] = hou
                # Register popnet under whatever name it reports, so createNode
                # + type().name() yield `reported_type`.
                sop_cat = hou.sopNodeTypeCategory()
                sop_cat._node_types["popnet"] = MockNodeType(
                    reported_type, "POP Network", "Sop", 4, 0)
                obj = hou.node("/obj")
                sopnet = obj.createNode("subnet", "sopnet1")
                sim = sopnet.createNode("subnet", "Sim")
                pop = sim.createNode("subnet", "Pop")
                popforce = pop.createNode("subnet", "Pop_Force")
                # Pop_Force's direct child is a popnet node; its children are
                # solver nodes INSIDE popnet, not direct children of Pop_Force.
                popnet = popforce.createNode("popnet", "popnet1")
                popnet.createNode("null", "solver_node")
                r = rl.recipe_capture_tree("/obj/sopnet1")
                self.assertTrue(r["success"])
                ids = {c["recipe_id"] for c in r["captured"]}
                self.assertIn("Sim.Pop.Pop_Force", ids,
                              f"type={reported_type!r}: missing correct leaf")
                self.assertNotIn("Sim.Pop.Pop_Force.popnet1", ids,
                                 f"type={reported_type!r}: pierced into popnet")
                rj = json.load(open(os.path.join(
                    self._tmp, "recipes", "Sim.Pop.Pop_Force", "recipe.json"),
                    encoding="utf-8"))
                self.assertEqual(rj["tree_path"], ["sopnet1", "Sim", "Pop"])

    def test_capture_tree_descends_network_container_category(self):
        """Regression: a network container (dopnet/popnet/sopnet) used as a
        CATEGORY LAYER (its children are subnets, not work nodes) MUST be
        descended — recipes organized under a dopnet must be captured.

        Real-world failure: walk() only descended 'subnet'/'geo', so a dopnet
        holding recipe subnets (e.g. /obj/hda/dopnet/noise_forece) was skipped
        entirely and its recipes were never captured. This is the mirror image
        of the pierce bug: there we wrongly descend work-filled networks, here
        we wrongly skip subnet-filled networks.

        A dopnet that is a pure category layer (all kids are subnets) descends;
        a dopnet whose kids are DOP work nodes is a leaf's content (handled by
        _is_leaf_subnet on the parent subnet)."""
        hou = create_mock_hou()
        sys.modules["hou"] = hou
        obj = hou.node("/obj")
        # /obj/hda/dopnet/noise_forece  (dopnet = category, noise_forece = leaf)
        hda = obj.createNode("subnet", "hda")
        dopnet = hda.createNode("dopnet", "dopnet")
        nf = dopnet.createNode("subnet", "noise_forece")
        nf.createNode("null", "popsolver")   # work node → noise_forece is a leaf
        r = rl.recipe_capture_tree("/obj/hda")
        self.assertTrue(r["success"], r)
        ids = {c["recipe_id"] for c in r["captured"]}
        self.assertIn("dopnet.noise_forece", ids,
                      "dopnet category layer must be descended to find noise_forece")


class TestNewPrimitivesNotesContract(unittest.TestCase):
    """The three new primitives (linear_array_copy, boolean_op, bevel_edges)
    are authored in build_recipes_standalone.py as Notes on subnets. Before
    capture can run (needs real Houdini), their Notes must pass validation and
    expose the right marked params. These are pure-function checks."""

    LINEAR_ARRAY_NOTES = (
        "功能：单位模板沿输入曲线均匀阵列 N 份（copytopoints，朝向对齐曲线切线）\n"
        "用途：链条、飞轮片排列、栏杆、铆钉沿缝——任何「模板 + 沿曲线等距 N 份 = 线性阵列」的场景\n"
        "输入：第0输入=模板几何（单位尺寸）；第1输入=路径曲线（决定分布轨迹）\n"
        "重要参数：array_count\n"
        "不要用于：绕轴环形（用 radial_copy）、单段弯曲管（用 tube_along_curve）、随机散布（用 scatter+copytopoints）"
    )
    BOOLEAN_NOTES = (
        "功能：两段输入几何做布尔运算（union/subtract/intersect）并清流形重算法线\n"
        "用途：开孔、挖槽、组合实体、拼接零件——任何「两个实体做集合运算成一体」的场景\n"
        "输入：第0输入=A 几何；第1输入=B 几何（subtract 时 B 从 A 挖除）\n"
        "重要参数：op, subtractchoices, booleanop\n"
        "不要用于：曲面缝合（用 merge+fuse）、变形融合（用 metaball）"
    )
    BEVEL_NOTES = (
        "功能：给指定边组倒圆角/切角（polybevel），让硬边实体获得机械圆角过渡\n"
        "用途：零件棱边圆角、孔口倒角、外观件做机械感——任何「把锐边磨圆/切角」的场景\n"
        "输入：第0输入=带锐边的实体几何\n"
        "重要参数：bevel, weight, segments, group\n"
        "不要用于：整体平滑（用 subdivide）、细分配曲面（用 subdiv）"
    )

    def test_linear_array_notes_valid_and_marked(self):
        ok, _ = rl.validate_notes(self.LINEAR_ARRAY_NOTES)
        self.assertTrue(ok)
        parsed = rl.parse_notes(self.LINEAR_ARRAY_NOTES)
        self.assertIn("array_count", parsed["marked"])
        self.assertIn("均匀阵列", parsed["function"])
        self.assertEqual(rl._infer_category(parsed["function"], "linear_array_copy"),
                         "array")

    def test_boolean_notes_valid_and_marked(self):
        ok, _ = rl.validate_notes(self.BOOLEAN_NOTES)
        self.assertTrue(ok)
        parsed = rl.parse_notes(self.BOOLEAN_NOTES)
        self.assertIn("op", parsed["marked"])
        self.assertEqual(rl._infer_category(parsed["function"], "boolean_op"),
                         "boolean")

    def test_bevel_notes_valid_and_marked(self):
        ok, _ = rl.validate_notes(self.BEVEL_NOTES)
        self.assertTrue(ok)
        parsed = rl.parse_notes(self.BEVEL_NOTES)
        self.assertIn("segments", parsed["marked"])
        self.assertEqual(rl._infer_category(parsed["function"], "bevel_edges"),
                         "bevel")

    def test_avoid_clauses_captured(self):
        """Each new primitive's 不要用于 line must round-trip into the avoid
        field so recipe_list can warn against misuse."""
        for notes in (self.LINEAR_ARRAY_NOTES, self.BOOLEAN_NOTES,
                      self.BEVEL_NOTES):
            parsed = rl.parse_notes(notes)
            self.assertTrue(parsed["avoid"],
                            f"avoid empty for notes: {notes[:30]!r}")


class TestDashboardFunctions(unittest.TestCase):
    """Tests for scan_recipe_tree / create_recipe_manager / set_node_notes.

    Uses the hou mock like TestCaptureRebuild, with per-test scene isolation.
    """

    def setUp(self):
        from tests.mock_hou import MockNode
        self._prev_hou = sys.modules.get("hou")
        self._prev_hou_ref = MockNode._hou_ref
        self._orig_rl_hou = rl._hou  # save the real lazy-import function
        self._hou = create_mock_hou()
        sys.modules["hou"] = self._hou
        # Point recipe_library at this mock's hou.
        rl._hou = lambda: sys.modules["hou"]
        # Isolate project root so scan/write tests don't collide with the real
        # recipe library (e.g. a real recipe.json named like a mock node).
        self._orig_root = rl._project_root
        self._tmp = tempfile.mkdtemp(prefix="recipes_dash_")
        rl._project_root = lambda: self._tmp  # type: ignore

    def tearDown(self):
        from tests.mock_hou import MockNode
        MockNode._hou_ref = self._prev_hou_ref
        sys.modules["hou"] = self._prev_hou
        rl._hou = self._orig_rl_hou  # restore the real lazy-import function
        rl._project_root = self._orig_root  # type: ignore
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _build_tree(self):
        """Build /obj/mgr/procedural_modeling/[tube, copy] + sim/noise."""
        hou = self._hou
        obj = hou.node("/obj")
        mgr = obj.createNode("subnet", "mgr")
        pm = mgr.createNode("subnet", "procedural_modeling")
        tube = pm.createNode("subnet", "tube_along_curve")
        tube.createNode("null", "n1")          # work node → leaf
        tube.setComment("功能：沿曲线管材")
        ctp = pm.createNode("subnet", "copy_to_points")
        ctp.createNode("null", "n2")
        sim = mgr.createNode("subnet", "sim")
        noise = sim.createNode("subnet", "noise_forcece")
        noise.createNode("null", "solver")
        return mgr

    def test_scan_returns_nested_structure(self):
        self._build_tree()
        r = rl.scan_recipe_tree("/obj/mgr")
        self.assertTrue(r["success"], r)
        tree = r["tree"]
        self.assertEqual(tree["name"], "mgr")
        self.assertEqual(tree["type"], "container")
        # procedural_modeling + sim are children
        child_names = {c["name"] for c in tree["children"]}
        self.assertEqual(child_names, {"procedural_modeling", "sim"})
        # procedural_modeling is a container holding 2 leaves
        pm = next(c for c in tree["children"] if c["name"] == "procedural_modeling")
        self.assertEqual(pm["type"], "container")
        leaf_names = {c["name"] for c in pm["children"]}
        self.assertEqual(leaf_names, {"tube_along_curve", "copy_to_points"})
        # tube_along_curve is a leaf with node_count + category
        tube = next(c for c in pm["children"] if c["name"] == "tube_along_curve")
        self.assertEqual(tube["type"], "leaf")
        self.assertEqual(tube["node_count"], 1)
        self.assertEqual(tube["category"], "tube")
        self.assertIn("管材", tube["notes"])

    def test_scan_missing_root(self):
        r = rl.scan_recipe_tree("/obj/does_not_exist")
        self.assertFalse(r["success"])
        self.assertIn("not found", r["error"])

    def test_scan_is_readonly(self):
        """scan must not write any recipe.json files."""
        self._build_tree()
        rl.scan_recipe_tree("/obj/mgr")
        # No recipes dir should have been created under a temp project root.
        # (recipe_library writes to <project>/recipes — scanning shouldn't.)
        import os
        root = rl._project_root()
        recipes = os.path.join(root, "recipes")
        # The default project root IS the repo; just confirm no new recipe dirs
        # were created for our mock tree nodes.
        for rid in ("tube_along_curve", "copy_to_points", "noise_forcece"):
            self.assertFalse(os.path.exists(os.path.join(recipes, rid, "recipe.json")),
                             f"scan wrote {rid}/recipe.json — not read-only!")

    def test_set_node_notes_validates_and_writes(self):
        hou = self._hou
        obj = hou.node("/obj")
        n = obj.createNode("subnet", "n")
        r = rl.set_node_notes(n.path(), "功能：测试配方")
        self.assertTrue(r["success"])
        self.assertEqual(n.comment(), "功能：测试配方")

    def test_set_node_notes_rejects_empty(self):
        hou = self._hou
        n = hou.node("/obj").createNode("subnet", "n")
        r = rl.set_node_notes(n.path(), "")
        self.assertFalse(r["success"])
        self.assertIn("为空", r["error"])

    def test_create_recipe_manager_builds_hda(self):
        r = rl.create_recipe_manager("/obj", "test_mgr")
        self.assertTrue(r["success"], r)
        self.assertTrue(r["hda_path"].endswith("test_mgr"))
        mgr = self._hou.node(r["hda_path"])
        self.assertIsNotNone(mgr)
        # Initial procedural_modeling category container exists
        kids = {c.name() for c in mgr.children()}
        self.assertIn("procedural_modeling", kids)
        # Comment set
        self.assertIn("Recipe Manager", mgr.comment())

    def test_create_recipe_manager_refuses_existing(self):
        hou = self._hou
        hou.node("/obj").createNode("subnet", "dup")  # pre-existing
        r = rl.create_recipe_manager("/obj", "dup")
        self.assertFalse(r["success"])
        self.assertIn("already exists", r["error"])

    def test_create_recipe_manager_seeded_from_source(self):
        """Seeded mode: move a scene subtree into the HDA + serialize leaves."""
        import os, shutil
        tmp = tempfile.mkdtemp(prefix="recipes_seed_")
        orig_root = rl._project_root
        rl._project_root = lambda: tmp  # type: ignore
        try:
            hou = self._hou
            # Build a source tree: /obj/myroot/procedural_modeling/tube + noise
            obj = hou.node("/obj")
            src = obj.createNode("subnet", "myroot")
            pm = src.createNode("subnet", "procedural_modeling")
            tube = pm.createNode("subnet", "tube_x")
            tube.createNode("null", "inner")  # work node → leaf
            tube.setComment("功能：测试管材配方")
            sim = src.createNode("subnet", "sim")
            noise = sim.createNode("subnet", "noise_x")
            noise.createNode("null", "solver")
            noise.setComment("功能：噪声力场")
            # Seed the HDA from this source.
            r = rl.create_recipe_manager("/obj", "seeded_mgr", source_root=src.path())
            self.assertTrue(r["success"], r)
            self.assertIn("seeded", r)
            seeded = r["seeded"]
            self.assertEqual(seeded["moved"], 2, "2 top-level children moved")
            self.assertGreaterEqual(seeded["captured"], 2, "leaves captured")
            # HDA now contains the moved children.
            mgr = hou.node(r["hda_path"])
            kids = {c.name() for c in mgr.children()}
            self.assertIn("procedural_modeling", kids)
            self.assertIn("sim", kids)
            # Source root is now empty (children moved out).
            self.assertEqual(len(src.children()), 0)
            # recipe.json database was written for the leaves.
            entries = []
            for d in os.listdir(os.path.join(tmp, "recipes")):
                if os.path.isdir(os.path.join(tmp, "recipes", d)):
                    entries.append(d)
            self.assertTrue(any("tube_x" in e or "tube" in e for e in entries),
                            f"tube recipe in DB: {entries}")
        finally:
            rl._project_root = orig_root  # type: ignore
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
