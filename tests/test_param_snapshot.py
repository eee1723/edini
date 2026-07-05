"""ParamSnapshotPanel — shows HDA params + diff on change."""
import sys
sys.path.insert(0, "python3.11libs")
from tests.qt_helpers import qapp
from edini.ui.components.param_snapshot import ParamSnapshotPanel


def test_snapshot_displays_params():
    p = ParamSnapshotPanel()
    p.set_params({"height": "5.0", "steps": "20", "width": "2.0"})
    text = p.params_text()
    assert "height" in text
    assert "5.0" in text
    assert "steps" in text


def test_diff_highlights_changed():
    p = ParamSnapshotPanel()
    p.set_params({"height": "5.0", "steps": "20"})
    p.set_params({"height": "8.0", "steps": "20"})  # height changed
    diffed = p.changed_params()
    assert "height" in diffed
    assert "steps" not in diffed


def test_no_change_no_diff():
    p = ParamSnapshotPanel()
    p.set_params({"height": "5.0"})
    p.set_params({"height": "5.0"})  # same
    assert len(p.changed_params()) == 0


def test_added_param_is_diff():
    p = ParamSnapshotPanel()
    p.set_params({"height": "5.0"})
    p.set_params({"height": "5.0", "width": "2.0"})  # width added
    assert "width" in p.changed_params()


def test_empty_params():
    p = ParamSnapshotPanel()
    p.set_params({})
    assert p.params_text() == "" or p.params_text().strip() == ""
