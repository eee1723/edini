"""Tests for edini.exprs — the safe arithmetic expression engine.

These are characterization tests for an already-implemented module (milestone-1
foundation). They lock in the documented behaviour of ``evaluate``,
``evaluate_tuple`` and ``extract_refs`` and, crucially, the security boundary:
anything outside the strict subset (attribute access, imports, arbitrary calls,
assignments, boolean logic) MUST raise ``ExprError``.

Pure Python — no ``hou`` dependency. Mirrors the module-level sys.path
injection style of test_node_utils.py / test_verify_orientation.py.
"""
import math
import sys
import unittest

sys.path.insert(0, "python3.11libs")

from edini.exprs import ExprError, evaluate, evaluate_tuple, extract_refs


# ===================================================================
# evaluate — happy paths
# ===================================================================

class TestEvaluateLiterals(unittest.TestCase):
    def test_integer_literal(self):
        self.assertEqual(evaluate("42", {}), 42.0)

    def test_float_literal(self):
        self.assertAlmostEqual(evaluate("3.14", {}), 3.14)

    def test_negative_literal(self):
        self.assertEqual(evaluate("-5", {}), -5.0)

    def test_returns_float(self):
        """The contract: evaluate always returns a float, never an int."""
        result = evaluate("2", {})
        self.assertIsInstance(result, float)


class TestEvaluateParamsAndConstants(unittest.TestCase):
    def test_param_reference(self):
        self.assertEqual(evaluate("wheel_radius", {"wheel_radius": 0.34}), 0.34)

    def test_unknown_name_raises(self):
        with self.assertRaises(ExprError) as ctx:
            evaluate("nope", {})
        self.assertIn("unknown name", str(ctx.exception))

    def test_param_non_numeric_raises(self):
        with self.assertRaises(ExprError) as ctx:
            evaluate("x", {"x": "not a number"})
        self.assertIn("not numeric", str(ctx.exception))

    def test_constant_pi(self):
        self.assertAlmostEqual(evaluate("pi", {}), math.pi)

    def test_constant_e(self):
        self.assertAlmostEqual(evaluate("e", {}), math.e)

    def test_constant_tau(self):
        self.assertAlmostEqual(evaluate("tau", {}), math.tau)

    def test_param_shadows_constant_when_in_params(self):
        # A param named 'e' resolves to the param value, not math.e.
        self.assertEqual(evaluate("e", {"e": 2.5}), 2.5)


class TestEvaluateArithmetic(unittest.TestCase):
    def test_add(self):
        self.assertEqual(evaluate("1 + 2", {}), 3.0)

    def test_subtract(self):
        self.assertEqual(evaluate("10 - 4", {}), 6.0)

    def test_multiply(self):
        self.assertEqual(evaluate("3 * 4", {}), 12.0)

    def test_divide(self):
        self.assertAlmostEqual(evaluate("9 / 2", {}), 4.5)

    def test_modulo(self):
        self.assertEqual(evaluate("10 % 3", {}), 1.0)

    def test_power(self):
        self.assertEqual(evaluate("2 ** 3", {}), 8.0)

    def test_precedence(self):
        # Multiplication binds tighter than addition.
        self.assertEqual(evaluate("1 + 2 * 3", {}), 7.0)

    def test_parentheses(self):
        self.assertEqual(evaluate("(1 + 2) * 3", {}), 9.0)

    def test_unary_plus(self):
        self.assertEqual(evaluate("+5", {}), 5.0)

    def test_unary_minus(self):
        self.assertEqual(evaluate("-5", {}), -5.0)

    def test_chained_arithmetic_with_params(self):
        self.assertAlmostEqual(
            evaluate("wheel_radius - bb_drop", {"wheel_radius": 0.34, "bb_drop": 0.07}),
            0.27,
        )

    def test_division_by_zero_raises(self):
        with self.assertRaises(ExprError) as ctx:
            evaluate("1 / 0", {})
        self.assertIn("division by zero", str(ctx.exception).lower())


class TestEvaluateFunctions(unittest.TestCase):
    def test_abs(self):
        self.assertEqual(evaluate("abs(-3)", {}), 3.0)

    def test_min(self):
        self.assertEqual(evaluate("min(1, 2, 3)", {}), 1.0)

    def test_max(self):
        self.assertEqual(evaluate("max(1, 2, 3)", {}), 3.0)

    def test_round(self):
        self.assertEqual(evaluate("round(3.14159, 2)", {}), 3.14)

    def test_sqrt(self):
        self.assertAlmostEqual(evaluate("sqrt(16)", {}), 4.0)

    def test_sin(self):
        self.assertAlmostEqual(evaluate("sin(0)", {}), 0.0)

    def test_cos(self):
        self.assertAlmostEqual(evaluate("cos(0)", {}), 1.0)

    def test_radians(self):
        self.assertAlmostEqual(evaluate("radians(180)", {}), math.pi)

    def test_degrees(self):
        self.assertAlmostEqual(evaluate("degrees(pi)", {}), 180.0)

    def test_nested_function_calls(self):
        # sin(radians(90)) == 1.0
        self.assertAlmostEqual(evaluate("sin(radians(90))", {}), 1.0, places=6)

    def test_function_with_param_arg(self):
        self.assertEqual(evaluate("abs(x)", {"x": -2.5}), 2.5)


# ===================================================================
# Subscript — the point-axis reference syntax (name[0])
# ===================================================================

class TestEvaluateSubscript(unittest.TestCase):
    """``name[<int>]`` is the ONLY allowed subscript form: a resolved skeleton
    point (bound to a tuple) indexed by an integer literal. This is how
    skeleton points reference each other (``rear_axle[0]``)."""

    def test_integer_subscript_on_tuple(self):
        env = {"rear_axle": (1.0, 2.0, 3.0)}
        self.assertEqual(evaluate("rear_axle[0]", env), 1.0)
        self.assertEqual(evaluate("rear_axle[1]", env), 2.0)
        self.assertEqual(evaluate("rear_axle[2]", env), 3.0)

    def test_subscript_used_in_arithmetic(self):
        env = {"base": (10.0, 0.0, 0.0)}
        self.assertEqual(evaluate("base[0] + 5", env), 15.0)

    def test_subscript_unknown_name_raises(self):
        with self.assertRaises(ExprError):
            evaluate("missing[0]", {})

    def test_subscript_out_of_range_raises(self):
        env = {"p": (1.0, 2.0, 3.0)}
        with self.assertRaises(ExprError):
            evaluate("p[5]", env)

    def test_subscript_non_integer_index_raises(self):
        env = {"p": (1.0, 2.0, 3.0)}
        # A float index is not an integer literal.
        with self.assertRaises(ExprError):
            evaluate("p[1.5]", env)

    def test_subscript_string_key_raises(self):
        env = {"p": (1.0, 2.0, 3.0)}
        with self.assertRaises(ExprError):
            evaluate("p['x']", env)


# ===================================================================
# Security boundary — everything outside the whitelist is rejected
# ===================================================================

class TestEvaluateSecurityBoundary(unittest.TestCase):
    """The expression engine is a sandbox: a malicious or buggy expression must
    NEVER escape into arbitrary Python. Each disallowed AST element raises."""

    def assert_rejected(self, expr, params=None):
        with self.assertRaises(ExprError):
            evaluate(expr, params or {})

    def test_attribute_access_rejected(self):
        self.assert_rejected("(1).__class__")

    def test_dunder_import_rejected(self):
        self.assert_rejected("__import__('os')")

    def test_open_function_rejected(self):
        self.assert_rejected("open('/etc/passwd')")

    def test_import_statement_rejected(self):
        self.assert_rejected("__import__")

    def test_assignment_rejected(self):
        # Assignment is a statement, not an expression — but we must still
        # reject it cleanly rather than mis-evaluate.
        with self.assertRaises(ExprError):
            evaluate("x = 1", {})

    def test_boolean_and_rejected(self):
        self.assert_rejected("1 and 2")

    def test_boolean_or_rejected(self):
        self.assert_rejected("1 or 2")

    def test_not_rejected(self):
        self.assert_rejected("not 1")

    def test_comparison_rejected(self):
        self.assert_rejected("1 < 2")

    def test_ternary_rejected(self):
        self.assert_rejected("1 if True else 0")

    def test_lambda_rejected(self):
        self.assert_rejected("lambda: 1")

    def test_list_comprehension_rejected(self):
        self.assert_rejected("[x for x in range(3)]")

    def test_keyword_argument_rejected(self):
        # round(x, ndigits=2) — keyword args are disallowed even on whitelisted
        # functions.
        self.assert_rejected("round(3.14, ndigits=1)")

    def test_non_name_call_rejected(self):
        # Calling a method / attribute is rejected: func is an Attribute, not
        # a bare Name. (A parenthesised bare name like ``(abs)(-1)`` is NOT a
        # violation — the parens are syntactic no-ops and the AST is still a
        # Name call, identical to ``abs(-1)``.)
        with self.assertRaises(ExprError):
            evaluate("'s'.upper()", {})

    def test_bool_literal_rejected(self):
        self.assert_rejected("True")

    def test_string_literal_rejected(self):
        self.assert_rejected("'hello'")

    def test_empty_expression_raises(self):
        with self.assertRaises(ExprError):
            evaluate("", {})

    def test_whitespace_only_expression_raises(self):
        with self.assertRaises(ExprError):
            evaluate("   ", {})

    def test_non_string_expression_raises(self):
        with self.assertRaises(ExprError):
            evaluate(123, {})  # type: ignore[arg-type]

    def test_syntax_error_raises(self):
        with self.assertRaises(ExprError):
            evaluate("1 +", {})

    def test_non_finite_result_raises(self):
        # tan(pi/2) overflows to a huge number; but a genuine inf/NaN source
        # is division yielding infinity via overflow. We use acos out of range.
        with self.assertRaises(ExprError):
            evaluate("acos(2)", {})


# ===================================================================
# evaluate_tuple — fixed-length expression lists
# ===================================================================

class TestEvaluateTuple(unittest.TestCase):
    def test_three_string_exprs(self):
        env = {"wheel_radius": 0.34, "rear_x": 0.0}
        result = evaluate_tuple(
            ["rear_x", "wheel_radius", "0"], env, length=3, what="point"
        )
        self.assertEqual(result, (0.0, 0.34, 0.0))

    def test_mixed_numbers_and_strings(self):
        result = evaluate_tuple([1, "2", "1+2"], {}, length=3)
        self.assertEqual(result, (1.0, 2.0, 3.0))

    def test_all_numbers(self):
        result = evaluate_tuple([1.0, 2.0, 3.0], {}, length=3)
        self.assertEqual(result, (1.0, 2.0, 3.0))

    def test_wrong_length_raises(self):
        with self.assertRaises(ExprError) as ctx:
            evaluate_tuple([1, 2], {}, length=3)
        self.assertIn("exactly 3", str(ctx.exception))

    def test_non_list_raises(self):
        with self.assertRaises(ExprError):
            evaluate_tuple("not a list", {}, length=3)

    def test_bool_element_rejected(self):
        with self.assertRaises(ExprError):
            evaluate_tuple([True, 2, 3], {}, length=3)

    def test_non_numeric_non_string_element_rejected(self):
        with self.assertRaises(ExprError):
            evaluate_tuple([None, 2, 3], {}, length=3)

    def test_returns_tuple_type(self):
        result = evaluate_tuple([1, 2, 3], {}, length=3)
        self.assertIsInstance(result, tuple)

    def test_string_expr_propagates_error(self):
        with self.assertRaises(ExprError):
            evaluate_tuple(["unknown_name", "0", "0"], {}, length=3)


# ===================================================================
# extract_refs — parameter reference extraction for the dependency graph
# ===================================================================

class TestExtractRefs(unittest.TestCase):
    def test_single_param(self):
        self.assertEqual(extract_refs("wheel_radius"), ["wheel_radius"])

    def test_two_params_sorted(self):
        refs = extract_refs("wheel_radius - bb_drop")
        self.assertEqual(refs, ["bb_drop", "wheel_radius"])  # sorted

    def test_excludes_builtin_functions(self):
        refs = extract_refs("sin(radians(seat_angle)) + frame_scale * 0.5")
        self.assertEqual(refs, ["frame_scale", "seat_angle"])

    def test_excludes_constants(self):
        refs = extract_refs("pi * diameter")
        self.assertEqual(refs, ["diameter"])

    def test_excludes_numeric_literals(self):
        refs = extract_refs("123 + 4.56")
        self.assertEqual(refs, [])

    def test_deduplicates(self):
        refs = extract_refs("x + x * x")
        self.assertEqual(refs, ["x"])

    def test_empty_string(self):
        self.assertEqual(extract_refs(""), [])

    def test_only_numbers(self):
        self.assertEqual(extract_refs("1 + 2"), [])

    def test_underscore_names(self):
        refs = extract_refs("rear_axle[0] + front_axle[0]")
        self.assertEqual(refs, ["front_axle", "rear_axle"])

    def test_does_not_validate_names(self):
        # extract_refs is purely lexical — it doesn't know what's a real param.
        refs = extract_refs("foo_bar + baz")
        self.assertEqual(refs, ["baz", "foo_bar"])


if __name__ == "__main__":
    unittest.main()
