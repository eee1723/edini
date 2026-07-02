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
    """Duck-typed node modeling a node whose hidden STATE parm is installed
    on its type (so always present). parm(name) lazily materializes a
    _FakeParm on first access — mirroring how a real Project HDA node exposes
    its type-installed parms. set_parm_value() also creates if needed."""
    def __init__(self):
        self._parms = {}
    def parm(self, name):
        if name not in self._parms:
            self._parms[name] = _FakeParm()
        return self._parms[name]
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
        self.assertEqual(loaded["version"], 1)
        self.assertEqual(loaded["plan"], [])

    def test_load_none_parm_returns_empty(self):
        """Directly exercise the `parm is None` branch of load_declaration.

        The lazy _FakeNode.parm() never returns None, so we use an inline
        node whose parm() always returns None to cover the absent-parm path.
        """
        from edini.project.state import load_declaration

        class _NoStateParmNode:
            def parm(self, name):
                return None  # truly-absent parm

        loaded = load_declaration(_NoStateParmNode())
        self.assertIsNone(loaded["project"]["name"])


class TestSaveDeclaration(unittest.TestCase):
    def test_save_writes_json_to_parm(self):
        from edini.project.state import save_declaration, load_declaration, STATE_PARM
        node = _FakeNode()
        decl = {"version": 1, "project": {"name": "bike"}, "plan": [],
                "design_params": [], "components": [], "log": [], "drift": []}
        save_declaration(node, decl)
        self.assertEqual(node.parm(STATE_PARM).eval(), json.dumps(decl))
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

    def test_save_raises_when_parm_absent(self):
        from edini.project.state import save_declaration
        # A node whose parm() returns None for the state parm.
        class _NoStateParmNode:
            def parm(self, name):
                return None
        with self.assertRaises(RuntimeError):
            save_declaration(_NoStateParmNode(), {"version": 1})


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


class TestAssembly(unittest.TestCase):
    def test_empty_declaration_has_assembly_none(self):
        from edini.project.state import empty_declaration
        d = empty_declaration("x")
        self.assertIsNone(d["assembly"])

    def test_set_assembly_stores_dict(self):
        from edini.project.state import empty_declaration, set_assembly, get_assembly
        d = empty_declaration("x")
        asm = {"id": "car", "root": {"shape": {"type": "box"}}}
        set_assembly(d, asm)
        self.assertEqual(get_assembly(d), asm)

    def test_set_assembly_none_clears(self):
        from edini.project.state import empty_declaration, set_assembly, get_assembly
        d = empty_declaration("x")
        set_assembly(d, {"id": "car", "root": {"shape": {"type": "box"}}})
        set_assembly(d, None)
        self.assertIsNone(get_assembly(d))

    def test_set_assembly_rejects_missing_keys(self):
        from edini.project.state import empty_declaration, set_assembly
        d = empty_declaration("x")
        with self.assertRaises(ValueError):
            set_assembly(d, {"id": "car"})  # missing 'root'
        with self.assertRaises(ValueError):
            set_assembly(d, {"root": {}})  # missing 'id'

    def test_set_assembly_rejects_non_dict(self):
        from edini.project.state import empty_declaration, set_assembly
        d = empty_declaration("x")
        with self.assertRaises(TypeError):
            set_assembly(d, "not a dict")

    def test_assembly_round_trips_through_save_load(self):
        from edini.project.state import (empty_declaration, set_assembly,
                                         save_declaration, load_declaration)
        node = _FakeNode()
        d = empty_declaration("car")
        set_assembly(d, {"id": "car", "params": {"length": 4.0},
                         "root": {"shape": {"type": "box"}}})
        save_declaration(node, d)
        loaded = load_declaration(node)
        self.assertIsNotNone(loaded["assembly"])
        self.assertEqual(loaded["assembly"]["id"], "car")
        self.assertEqual(loaded["assembly"]["params"]["length"], 4.0)


class TestInstallStateParm(unittest.TestCase):
    """Tests that build_state_parm_template builds a hidden string parm template.
    Uses the repo's mock_hou so no Houdini runtime is needed."""
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
        from mock_hou import create_mock_hou
        cls._mock = create_mock_hou()
        cls._saved_hou = sys.modules.get("hou")
        sys.modules["hou"] = cls._mock
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


if __name__ == "__main__":
    unittest.main()
