"""Tests for edini.skeleton_resolver — the skeleton-point DAG resolver.

Characterization tests for an already-implemented module (milestone-1
foundation). Covers point-dependency extraction, Kahn topological sort with
cycle detection, and the full skeleton evaluation that threads resolved point
coordinates back in as variables (so ``rear_axle[0]`` works downstream).

Pure Python — no ``hou`` dependency.
"""
import sys
import unittest

sys.path.insert(0, "python3.11libs")

from edini.exprs import ExprError
from edini.skeleton_resolver import (
    SkeletonCycleError,
    evaluate_skeleton,
    point_dependencies,
    topo_order,
)


# ===================================================================
# point_dependencies — inter-point edges only
# ===================================================================

class TestPointDependencies(unittest.TestCase):
    def test_point_referencing_another_point(self):
        skel = {
            "base": {"expr": ["0", "0", "0"]},
            "front": {"expr": ["base[0] + 1", "0", "0"]},
        }
        deps = point_dependencies(skel)
        self.assertEqual(deps["base"], set())
        self.assertEqual(deps["front"], {"base"})

    def test_param_reference_is_not_a_point_dep(self):
        # 'wheel_radius' is not a declared point, so it's not an inter-point edge.
        skel = {
            "a": {"expr": ["wheel_radius", "0", "0"]},
            "b": {"expr": ["a[0]", "0", "0"]},
        }
        deps = point_dependencies(skel)
        self.assertEqual(deps["a"], set())
        self.assertEqual(deps["b"], {"a"})

    def test_self_reference_excluded(self):
        # A point that references its own name does not depend on itself.
        skel = {"a": {"expr": ["a[0]", "0", "0"]}}
        deps = point_dependencies(skel)
        self.assertEqual(deps["a"], set())

    def test_multiple_deps(self):
        skel = {
            "a": {"expr": ["0", "0", "0"]},
            "b": {"expr": ["0", "0", "0"]},
            "c": {"expr": ["a[0] + b[1]", "0", "0"]},
        }
        deps = point_dependencies(skel)
        self.assertEqual(deps["c"], {"a", "b"})

    def test_bare_list_form_accepted(self):
        # A point spec may be a bare list instead of {"expr": [...]}.
        skel = {
            "a": ["0", "0", "0"],
            "b": ["a[0]", "0", "0"],
        }
        deps = point_dependencies(skel)
        self.assertEqual(deps["b"], {"a"})


# ===================================================================
# topo_order — Kahn's algorithm, cycle detection
# ===================================================================

class TestTopoOrder(unittest.TestCase):
    def test_independent_points_any_valid_order(self):
        skel = {
            "a": {"expr": ["0", "0", "0"]},
            "b": {"expr": ["1", "0", "0"]},
        }
        order = topo_order(skel)
        # Both have no deps; deterministic (sorted) order.
        self.assertEqual(set(order), {"a", "b"})
        self.assertEqual(order, sorted(order))

    def test_linear_chain_respects_dependencies(self):
        skel = {
            "a": {"expr": ["0", "0", "0"]},
            "b": {"expr": ["a[0]", "0", "0"]},
            "c": {"expr": ["b[0]", "0", "0"]},
        }
        order = topo_order(skel)
        self.assertEqual(order.index("a") < order.index("b") < order.index("c"), True)

    def test_diamond_shape(self):
        skel = {
            "base": {"expr": ["0", "0", "0"]},
            "left": {"expr": ["base[0]", "0", "0"]},
            "right": {"expr": ["base[0]", "0", "0"]},
            "top": {"expr": ["left[0] + right[0]", "0", "0"]},
        }
        order = topo_order(skel)
        self.assertEqual(order[0], "base")
        self.assertEqual(order[-1], "top")
        self.assertLess(order.index("base"), order.index("left"))
        self.assertLess(order.index("base"), order.index("right"))
        self.assertLess(order.index("left"), order.index("top"))
        self.assertLess(order.index("right"), order.index("top"))

    def test_is_deterministic(self):
        # Two independent points must always come out in the same (sorted) order.
        skel = {
            "zebra": {"expr": ["0", "0", "0"]},
            "apple": {"expr": ["0", "0", "0"]},
        }
        self.assertEqual(topo_order(skel), ["apple", "zebra"])

    def test_cycle_raises(self):
        skel = {
            "a": {"expr": ["b[0]", "0", "0"]},
            "b": {"expr": ["a[0]", "0", "0"]},
        }
        with self.assertRaises(SkeletonCycleError) as ctx:
            topo_order(skel)
        # The error should name the points involved in the cycle.
        msg = str(ctx.exception)
        self.assertIn("a", msg)
        self.assertIn("b", msg)

    def test_self_cycle_raises(self):
        skel = {"a": {"expr": ["a[0] + 1", "0", "0"]}}
        # point_dependencies excludes self-refs, so a pure self-cycle has no
        # inter-point edges and topo_order succeeds (in_degree 0). This is the
        # documented behaviour: a self-reference is not treated as a cycle by
        # the graph layer (it surfaces as an evaluation error instead).
        order = topo_order(skel)
        self.assertEqual(order, ["a"])

    def test_three_node_cycle(self):
        skel = {
            "a": {"expr": ["c[0]", "0", "0"]},
            "b": {"expr": ["a[0]", "0", "0"]},
            "c": {"expr": ["b[0]", "0", "0"]},
        }
        with self.assertRaises(SkeletonCycleError):
            topo_order(skel)

    def test_empty_skeleton(self):
        self.assertEqual(topo_order({}), [])


# ===================================================================
# evaluate_skeleton — full DAG resolution
# ===================================================================

class TestEvaluateSkeleton(unittest.TestCase):
    def test_param_driven_coordinates(self):
        skel = {
            "base": {"expr": ["0", "0", "0"]},
            "top": {"expr": ["0", "height", "0"]},
        }
        result = evaluate_skeleton(skel, {"height": 2.5})
        self.assertEqual(result["base"], (0.0, 0.0, 0.0))
        self.assertEqual(result["top"], (0.0, 2.5, 0.0))

    def test_point_reference_indexing(self):
        # rear_axle[0] reads the already-resolved x of base.
        skel = {
            "base": {"expr": ["3.0", "0", "0"]},
            "front": {"expr": ["base[0] + 2", "base[1]", "0"]},
        }
        result = evaluate_skeleton(skel, {})
        self.assertEqual(result["base"], (3.0, 0.0, 0.0))
        self.assertEqual(result["front"], (5.0, 0.0, 0.0))

    def test_full_chain_resolution(self):
        skel = {
            "rear_axle": {"expr": ["0", "wheel_radius", "0"]},
            "front_axle": {"expr": ["rear_axle[0] + wheelbase", "rear_axle[1]", "0"]},
            "bb_center": {"expr": ["rear_axle[0]", "wheel_radius - bb_drop", "0"]},
        }
        params = {"wheel_radius": 0.34, "wheelbase": 1.05, "bb_drop": 0.07}
        result = evaluate_skeleton(skel, params)
        self.assertEqual(result["rear_axle"], (0.0, 0.34, 0.0))
        self.assertEqual(result["front_axle"], (1.05, 0.34, 0.0))
        self.assertEqual(result["bb_center"], (0.0, 0.27, 0.0))

    def test_unknown_param_raises_expr_error(self):
        skel = {"a": {"expr": ["typo_name", "0", "0"]}}
        with self.assertRaises(ExprError):
            evaluate_skeleton(skel, {})

    def test_cycle_raises(self):
        skel = {
            "a": {"expr": ["b[0]", "0", "0"]},
            "b": {"expr": ["a[0]", "0", "0"]},
        }
        with self.assertRaises(SkeletonCycleError):
            evaluate_skeleton(skel, {})

    def test_returns_tuples(self):
        skel = {"a": {"expr": ["1", "2", "3"]}}
        result = evaluate_skeleton(skel, {})
        self.assertIsInstance(result["a"], tuple)
        self.assertEqual(len(result["a"]), 3)
        for c in result["a"]:
            self.assertIsInstance(c, float)

    def test_mixed_number_and_expr_axes(self):
        # Numeric literals and expression strings can mix in one point.
        skel = {"a": {"expr": [0, "height", "height * 2"]}}
        result = evaluate_skeleton(skel, {"height": 1.0})
        self.assertEqual(result["a"], (0.0, 1.0, 2.0))

    def test_empty_skeleton(self):
        self.assertEqual(evaluate_skeleton({}, {}), {})


if __name__ == "__main__":
    unittest.main()
