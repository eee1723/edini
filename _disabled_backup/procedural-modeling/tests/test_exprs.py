"""Tests for the safe recipe expression engine (edini.exprs)."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python3.11libs"))

from edini.exprs import ExprError, evaluate, evaluate_tuple


class TestEvaluate(unittest.TestCase):
    def test_plain_number(self):
        self.assertAlmostEqual(evaluate("1.5", {}), 1.5)

    def test_parameter_reference(self):
        self.assertAlmostEqual(evaluate("wheelbase", {"wheelbase": 1.2}), 1.2)

    def test_arithmetic(self):
        self.assertAlmostEqual(
            evaluate("wheelbase/2", {"wheelbase": 1.0}), 0.5)
        self.assertAlmostEqual(
            evaluate("wheel_r * 2 + 0.05", {"wheel_r": 0.35}), 0.75)
        self.assertAlmostEqual(
            evaluate("wheelbase**2", {"wheelbase": 3.0}), 9.0)

    def test_math_function_whitelist(self):
        self.assertAlmostEqual(
            evaluate("sin(pi/2)", {}), 1.0, places=6)
        self.assertAlmostEqual(
            evaluate("sqrt(wheel_r)", {"wheel_r": 0.25}), 0.5, places=6)
        self.assertAlmostEqual(
            evaluate("max(wheelbase, 0.8)", {"wheelbase": 1.2}), 1.2)

    def test_constant_pi(self):
        self.assertAlmostEqual(evaluate("pi", {}), math.pi)

    def test_unary_minus(self):
        self.assertAlmostEqual(
            evaluate("-wheelbase", {"wheelbase": 1.5}), -1.5)

    def test_unknown_parameter_rejected(self):
        with self.assertRaises(ExprError):
            evaluate("bogus + 1", {"wheelbase": 1.0})

    def test_non_numeric_param_rejected(self):
        with self.assertRaises(ExprError):
            evaluate("wheelbase", {"wheelbase": "oops"})

    def test_empty_expression_rejected(self):
        with self.assertRaises(ExprError):
            evaluate("   ", {})

    def test_division_by_zero_raises(self):
        with self.assertRaises(ExprError):
            evaluate("wheelbase / 0", {"wheelbase": 1.0})


class TestEvaluateSecurity(unittest.TestCase):
    """The whitelist is the security boundary — anything not allowed must fail."""

    def test_import_rejected(self):
        with self.assertRaises(ExprError):
            evaluate("__import__('os')", {})

    def test_attribute_access_rejected(self):
        with self.assertRaises(ExprError):
            evaluate("(1).bit_length()", {})

    def test_arbitrary_function_rejected(self):
        with self.assertRaises(ExprError):
            evaluate("open('x')", {})

    def test_lambda_rejected(self):
        with self.assertRaises(ExprError):
            evaluate("(lambda: 1)()", {})

    def test_subscript_rejected(self):
        with self.assertRaises(ExprError):
            evaluate("[1,2,3][0]", {})

    def test_comparison_rejected(self):
        with self.assertRaises(ExprError):
            evaluate("1 < 2", {})

    def test_boolean_op_rejected(self):
        with self.assertRaises(ExprError):
            evaluate("1 and 2", {})

    def test_keyword_args_rejected(self):
        with self.assertRaises(ExprError):
            evaluate("min(1, default=0)", {})

    def test_assignment_rejected(self):
        with self.assertRaises(ExprError):
            evaluate("x = 1", {})

    def test_builtin_not_whitelisted(self):
        # print/eval/exec are NOT in the whitelist even though they're builtins
        with self.assertRaises(ExprError):
            evaluate("print(1)", {})

    def test_no_dunder_escalation(self):
        # Even if someone tries type().__subclasses__(), attribute access is blocked
        with self.assertRaises(ExprError):
            evaluate("type(1)", {})


class TestEvaluateTuple(unittest.TestCase):
    def test_position_expressions(self):
        params = {"wheelbase": 1.0, "wheel_r": 0.35}
        result = evaluate_tuple(["wheelbase/2", "wheel_r", "0"], params, length=3)
        self.assertEqual(result, (0.5, 0.35, 0.0))

    def test_mixed_numbers_and_exprs(self):
        result = evaluate_tuple([1, "wheel_r*2", 0], {"wheel_r": 0.3}, length=3)
        self.assertEqual(result, (1.0, 0.6, 0.0))

    def test_wrong_length_rejected(self):
        with self.assertRaises(ExprError):
            evaluate_tuple(["1", "2"], {}, length=3)

    def test_non_list_rejected(self):
        with self.assertRaises(ExprError):
            evaluate_tuple("1.0", {}, length=1)

    def test_bool_rejected(self):
        # bools are ints in Python; we reject them explicitly to avoid silent
        # True->1.0 coercion in geometry contexts
        with self.assertRaises(ExprError):
            evaluate_tuple([True, 0, 0], {}, length=3)

    def test_non_finite_rejected(self):
        with self.assertRaises(ExprError):
            evaluate_tuple([float("nan"), 0, 0], {}, length=3)

    def test_orient_expressions(self):
        params = {}
        result = evaluate_tuple(["0", "0", "0", "1"], params, length=4)
        self.assertEqual(result, (0.0, 0.0, 0.0, 1.0))


if __name__ == "__main__":
    unittest.main()
