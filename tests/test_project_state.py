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


if __name__ == "__main__":
    unittest.main()
