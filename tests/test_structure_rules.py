import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
from edini.structure import evaluate_component_signals


def _sig(**kw):
    base = {"component_id": "c", "prim_types": {}, "instancing_nodes": set(),
            "python_emit_geometry": False, "inferred_repeats": False,
            "ctp_target_has_orient": False}
    base.update(kw)
    return base


def test_F1_bare_curves_at_out_fatal():
    r = evaluate_component_signals(_sig(prim_types={"NURBSCurve": 6}), None)
    assert r["overall"] == "fatal"
    assert r["fatal"][0]["rule"] == "F1_bare_curves_at_out"


def test_F2_declared_instancing_missing_node_fatal():
    declared = {"kind": "repeated",
                "repeats": [{"part": "spoke", "count": 28, "method": "copytopoints"}]}
    r = evaluate_component_signals(_sig(prim_types={"Poly": 500}), declared)
    assert any(f["rule"] == "F2_repeat_no_instancing" and f["confidence"] == "declared"
               for f in r["fatal"])


def test_F2_inferred_repeat_in_python_sop_fatal():
    r = evaluate_component_signals(
        _sig(prim_types={"Poly": 600}, python_emit_geometry=True, inferred_repeats=True), None)
    assert any(f["rule"] == "F2_repeat_no_instancing" and f["confidence"] == "inferred"
               for f in r["fatal"])


def test_F2_passes_when_ctp_present():
    declared = {"kind": "repeated",
                "repeats": [{"part": "spoke", "count": 28, "method": "copytopoints"}]}
    r = evaluate_component_signals(
        _sig(prim_types={"Poly": 500}, instancing_nodes={"copytopoints"}), declared)
    assert not any(f["rule"] == "F2_repeat_no_instancing" for f in r["fatal"])


def test_F4_ctp_without_orient_fatal():
    r = evaluate_component_signals(
        _sig(prim_types={"Poly": 400}, instancing_nodes={"copytopoints"},
              ctp_target_has_orient=False), None)
    assert any(f["rule"] == "F4_ctp_no_orient" for f in r["fatal"])


def test_F4_ctp_with_orient_clean():
    r = evaluate_component_signals(
        _sig(prim_types={"Poly": 400}, instancing_nodes={"copytopoints"},
              ctp_target_has_orient=True), None)
    assert not any(f["rule"] == "F4_ctp_no_orient" for f in r["fatal"])


def test_clean_component():
    r = evaluate_component_signals(
        _sig(prim_types={"Poly": 72}, instancing_nodes={"copytopoints"},
              ctp_target_has_orient=True), {"kind": "repeated",
              "repeats": [{"part": "leg", "count": 4, "method": "copytopoints"}]})
    assert r["overall"] == "clean"
