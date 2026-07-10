import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
import pytest
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


def test_structure_not_dict():
    errs = lint_structure_decl({"id": "x", "structure": [1, 2]})
    assert [e["code"] for e in errs] == ["structure_not_dict"]


def test_bad_kind():
    errs = lint_structure_decl({"id": "x", "structure": {"kind": "wheel"}})
    assert "bad_kind" in [e["code"] for e in errs]


def test_bad_repeat_entry():
    errs = lint_structure_decl({"id": "x", "structure": {
        "kind": "repeated", "repeats": [42]}})
    assert "bad_repeat_entry" in [e["code"] for e in errs]


def test_planar_requires_axis():
    errs = lint_structure_decl({"id": "top", "structure": {"kind": "planar"}})
    assert "missing_axis" in [e["code"] for e in errs]


@pytest.mark.parametrize("count", [None, "28"])
def test_bad_repeat_count_none_and_string(count):
    errs = lint_structure_decl({"id": "spokes", "structure": {
        "kind": "repeated",
        "repeats": [{"part": "spoke", "count": count, "method": "copytopoints"}]}})
    assert "bad_repeat_count" in [e["code"] for e in errs]


from edini.project.state import empty_declaration, add_structure_to_component


def test_add_structure_to_component_persists():
    decl = empty_declaration("p")
    decl["components"].append({"id": "wheel"})
    add_structure_to_component(decl, "wheel",
                               {"kind": "radial", "expected_axis": "Z"})
    c = decl["components"][0]
    assert c["structure"]["kind"] == "radial"
    assert c["structure"]["expected_axis"] == "Z"
