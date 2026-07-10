import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
from edini.structure import lint_structure_decl


def test_missing_structure_is_error():
    errs = lint_structure_decl({"id": "frame"})
    assert [e["code"] for e in errs] == ["structure_missing"]


def test_solid_needs_no_axis():
    errs = lint_structure_decl({"id": "body", "structure": {"kind": "solid"}})
    assert errs == []


def test_radial_requires_axis():
    errs = lint_structure_decl({"id": "wheel", "structure": {"kind": "radial"}})
    assert "missing_axis" in [e["code"] for e in errs]


def test_repeated_requires_repeats():
    errs = lint_structure_decl({"id": "spokes", "structure": {"kind": "repeated"}})
    assert "repeated_without_repeats" in [e["code"] for e in errs]


def test_instancing_repeat_needs_count_ge_2():
    errs = lint_structure_decl({"id": "spokes", "structure": {
        "kind": "repeated", "repeats": [{"part": "spoke", "count": 1, "method": "copytopoints"}]}})
    assert "bad_repeat_count" in [e["code"] for e in errs]


def test_valid_radial_passes():
    errs = lint_structure_decl({"id": "wheel", "structure": {
        "kind": "radial", "expected_axis": "Z",
        "repeats": [{"part": "spoke", "count": 28, "method": "copytopoints"}]}})
    assert errs == []
