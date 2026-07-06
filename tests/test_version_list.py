"""NodeVersionList — left panel showing a node's session versions."""
from tests.qt_helpers import qapp, SignalSpy
from edini.ui.components.version_list import NodeVersionList


def test_starts_empty():
    vl = NodeVersionList()
    assert vl.version_count() == 0


def test_set_versions_populates():
    vl = NodeVersionList()
    vl.set_versions([
        {"version": 1, "summary": "make a box", "meta": "14:05 · 0.8k", "current": False},
        {"version": 2, "summary": "spiral stairs", "meta": "14:32 · 1.2k", "current": True},
    ])
    assert vl.version_count() == 2


def test_set_versions_replaces():
    vl = NodeVersionList()
    vl.set_versions([{"version": 1, "summary": "a", "meta": "x", "current": True}])
    vl.set_versions([{"version": 1, "summary": "b", "meta": "x", "current": True},
                     {"version": 2, "summary": "c", "meta": "y", "current": False}])
    assert vl.version_count() == 2


def test_new_version_button_emits_signal():
    vl = NodeVersionList()
    spy = SignalSpy(vl.version_created)
    # Simulate clicking the "+ New Version" button
    vl._new_btn.click()
    assert len(spy) == 1
    assert spy.calls[0] == 1   # first new version is v1


def test_new_version_button_next_after_populated():
    vl = NodeVersionList()
    vl.set_versions([
        {"version": 1, "summary": "a", "meta": "x", "current": False},
        {"version": 2, "summary": "b", "meta": "y", "current": True},
    ])
    spy = SignalSpy(vl.version_created)
    vl._new_btn.click()
    assert spy.calls[0] == 3   # next after v1,v2 is v3


def test_select_version_emits_signal():
    vl = NodeVersionList()
    vl.set_versions([
        {"version": 1, "summary": "a", "meta": "x", "current": False},
        {"version": 2, "summary": "b", "meta": "y", "current": True},
    ])
    spy = SignalSpy(vl.version_selected)
    vl.select_version(1)
    assert spy.calls == [1]


def test_mark_current():
    vl = NodeVersionList()
    vl.set_versions([
        {"version": 1, "summary": "a", "meta": "x", "current": True},
        {"version": 2, "summary": "b", "meta": "y", "current": False},
    ])
    vl.mark_current(2)
    assert vl.current_version() == 2
