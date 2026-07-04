"""SceneCard accepts a dict — no hou dependency."""
import sys
sys.path.insert(0, "python3.11libs")
from tests.qt_helpers import qapp
from edini.ui.status.scene_card import SceneCard


def test_set_scene_info_updates_labels():
    c = SceneCard()
    c.set_scene_info({
        "hip": "test.hip",
        "path": "/obj/geo1",
        "selected": "box1 (geo)",
        "nodes": "5 here / 100 total",
    })
    assert "test.hip" in c.hip_label.text()
    assert "/obj/geo1" in c.path_label.text()
    assert "box1" in c.selected_label.text()


def test_none_values_show_dash():
    c = SceneCard()
    c.set_scene_info({"hip": None, "path": None, "selected": None, "nodes": None})
    assert "—" in c.hip_label.text() or "-" in c.hip_label.text()
    assert "—" in c.path_label.text() or "-" in c.path_label.text()


def test_unknown_fields_ignored():
    c = SceneCard()
    # Should not crash on unknown fields (forward-compat for future graph data)
    c.set_scene_info({"hip": "x", "future_graph_field": "ignored"})


def test_partial_update():
    c = SceneCard()
    c.set_scene_info({"hip": "a.hip", "path": "/x", "selected": None, "nodes": None})
    assert "a.hip" in c.hip_label.text()
    # selected/nodes show dash
    assert "—" in c.selected_label.text() or "-" in c.selected_label.text()


def test_initial_state_all_dash():
    c = SceneCard()
    assert "—" in c.hip_label.text() or "-" in c.hip_label.text()
