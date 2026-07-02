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


class TestComponentSchema(unittest.TestCase):
    def test_empty_declaration_has_no_assembly_field(self):
        """新范式：declaration 不再有 assembly 字段。"""
        from edini.project.state import empty_declaration
        d = empty_declaration("car")
        self.assertNotIn("assembly", d)

    def test_add_component_appends_to_components(self):
        from edini.project.state import empty_declaration, add_component
        decl = empty_declaration("car")
        add_component(decl, component_id="chassis", purpose="车架")
        self.assertEqual(len(decl["components"]), 1)
        self.assertEqual(decl["components"][0]["id"], "chassis")
        self.assertEqual(decl["components"][0]["purpose"], "车架")

    def test_add_component_with_ports(self):
        from edini.project.state import empty_declaration, add_component
        decl = empty_declaration("car")
        add_component(decl, component_id="chassis", purpose="车架",
                      ports_out=[
                          {"index": 0, "kind": "geometry", "description": "车架几何"},
                          {"index": 1, "kind": "anchors", "points": [
                              {"name": "wheel_mount_fr", "role": "mount",
                               "description": "前轮安装点"}],
                           "description": "信息锚点"}],
                      ports_in=[])
        comp = decl["components"][0]
        self.assertEqual(len(comp["ports"]["out"]), 2)
        self.assertEqual(comp["ports"]["out"][1]["points"][0]["name"],
                         "wheel_mount_fr")

    def test_add_component_with_params(self):
        from edini.project.state import empty_declaration, add_component
        decl = empty_declaration("car")
        add_component(decl, component_id="chassis", purpose="车架",
                      params=[{"name": "length", "label": "车长",
                               "default": 4, "min": 1, "max": 20}])
        self.assertEqual(decl["components"][0]["params"][0]["name"], "length")

    def test_add_component_rejects_duplicate_id(self):
        from edini.project.state import empty_declaration, add_component
        decl = empty_declaration("car")
        add_component(decl, component_id="chassis", purpose="车架")
        with self.assertRaises(ValueError):
            add_component(decl, component_id="chassis", purpose="再来")

    def test_add_component_rejects_bad_id(self):
        """组件 id = subnet 名，必须合法（字母数字下划线）。"""
        from edini.project.state import empty_declaration, add_component
        decl = empty_declaration("car")
        with self.assertRaises(ValueError):
            add_component(decl, component_id="bad name!", purpose="x")
        with self.assertRaises(ValueError):
            add_component(decl, component_id="has/slash", purpose="x")

    def test_get_component_by_id(self):
        from edini.project.state import empty_declaration, add_component, get_component
        decl = empty_declaration("car")
        add_component(decl, component_id="chassis", purpose="车架")
        add_component(decl, component_id="wheels", purpose="车轮")
        self.assertEqual(get_component(decl, "wheels")["purpose"], "车轮")
        self.assertIsNone(get_component(decl, "nonexistent"))


if __name__ == "__main__":
    unittest.main()
