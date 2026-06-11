"""Tests for Edini procedural harness helpers."""
import os
import sys
import unittest

from tests.mock_hou import create_mock_hou

_mock_hou = create_mock_hou()
sys.modules["hou"] = _mock_hou
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))

for _mod in list(sys.modules):
    if _mod.startswith("edini"):
        del sys.modules[_mod]

from edini import harness


class TestHarnessImports(unittest.TestCase):
    def test_harness_module_imports(self):
        self.assertTrue(hasattr(harness, "make_job_id"))


if __name__ == "__main__":
    unittest.main()
