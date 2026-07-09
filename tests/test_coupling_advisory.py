"""The cross-component coupling advisory (P1b, 2026-07-09).

Context: ``project_finalize`` / ``verify_parametric`` cannot tell a *coupled*
multi-component model from a set of *independent parametric islands* — they
check each param drives the MERGED bbox, not that component B follows A. The
2026-07-09 Rubik's-cube session was the latter: ``cubies`` + ``stickers`` both
read ``grid_n/unit/gap`` but don't connect (no ports.in, zero anchors), so
stickers re-derive the face position by duplicated formula instead of
measuring the cube. It passed finalize. This advisory surfaces that condition
without making it a hard gate (legitimate independent components exist).

``_coupling_advisories`` is pure declaration logic — no hou — so it is tested
in isolation.
"""
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
# verify.py imports hou in a try/except; stub it so the import is deterministic.
if "hou" not in sys.modules:
    sys.modules["hou"] = types.ModuleType("hou")

from edini.verify import _coupling_advisories  # noqa: E402


def _comp(cid, in_ports=None, anchor_names=None):
    """Build a minimal declaration component with optional ports.in / anchors."""
    out = [{"index": 0, "kind": "geometry"}]
    if anchor_names:
        out.append({"index": 1, "kind": "anchors",
                    "points": [{"name": n} for n in anchor_names]})
    return {"id": cid, "ports": {"out": out, "in": in_ports or []}}


class TestCouplingAdvisory(unittest.TestCase):

    def test_no_advisory_for_single_component(self):
        self.assertEqual(_coupling_advisories([_comp("only")]), [])

    def test_no_advisory_for_empty(self):
        self.assertEqual(_coupling_advisories([]), [])

    def test_advisory_for_independent_islands(self):
        """The cube pattern: 2 components, neither consumes the other."""
        comps = [_comp("cubies"), _comp("stickers")]
        adv = _coupling_advisories(comps)
        self.assertEqual(len(adv), 1)
        self.assertEqual(adv[0]["kind"], "independent_components")
        self.assertEqual(adv[0]["severity"], "advisory")
        self.assertEqual(adv[0]["component_count"], 2)
        self.assertEqual(adv[0]["anchors_declared"], 0)
        # The message must point at the two remediation paths.
        self.assertIn("ports.in", adv[0]["message"])
        self.assertIn("project_add_anchors", adv[0]["message"])
        self.assertIn("merging", adv[0]["message"])

    def test_no_advisory_when_a_component_consumes_anchors(self):
        """A ports.in entry (B consumes A's anchors) → coupled → no advisory."""
        comps = [
            _comp("tabletop", anchor_names=["leg_mount_fr"]),
            _comp("legs", in_ports=[{"from": "tabletop", "port": 1,
                                     "anchor": "leg_mount_fr"}]),
        ]
        self.assertEqual(_coupling_advisories(comps), [])

    def test_advisory_even_if_anchors_declared_but_unconsumed(self):
        """Anchors emitted but nobody consumes them → still islands."""
        comps = [_comp("a", anchor_names=["p"]), _comp("b")]
        adv = _coupling_advisories(comps)
        self.assertEqual(len(adv), 1)
        self.assertEqual(adv[0]["anchors_declared"], 1)

    def test_advisory_non_blocking_shape(self):
        """The advisory is data only — carries no 'failure' / blocking flag."""
        adv = _coupling_advisories([_comp("a"), _comp("b")])
        self.assertNotIn("blocking", adv[0])
        self.assertNotIn("fail", str(adv[0]["severity"]).lower())


if __name__ == "__main__":
    unittest.main()
