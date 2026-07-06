"""ChatWindowShell — 3-panel assembler driven by ScopeConfig."""
from tests.qt_helpers import qapp
from edini.ui.chat.scope import ScopeConfig
from edini.ui.chat.window_shell import ChatWindowShell


def _provider():
    return {}


def _make_agent_scope():
    return ScopeConfig(scope_id="agent", window_title="Edini Agent",
                       accent_override=None, header_badge=None,
                       left_panel_kind="global_sessions", show_change_tree=True,
                       show_eval_button=True, show_attachment_bar=True,
                       show_param_snapshot=False, scene_data_provider=_provider)


def _make_hda_scope():
    return ScopeConfig(scope_id="project_hda", window_title="Project HDA",
                       accent_override="#f59e0b", header_badge="core: /obj/x",
                       left_panel_kind="node_versions", show_change_tree=True,
                       show_eval_button=False, show_attachment_bar=False,
                       show_param_snapshot=True, scene_data_provider=_provider)


def test_shell_has_three_panels():
    shell = ChatWindowShell(_make_agent_scope())
    assert shell.left_panel is not None
    assert shell.center_widget is not None
    assert shell.context_panel is not None


def test_shell_accent_override_sets_objectname():
    shell = ChatWindowShell(_make_hda_scope())
    assert shell.objectName() == "ChatShell_project_hda"


def test_shell_no_accent_no_objectname():
    shell = ChatWindowShell(_make_agent_scope())
    # agent scope has accent_override=None → no special objectName
    assert shell.objectName() == "" or "ChatShell" not in shell.objectName()


def test_shell_exposes_subcomponents():
    shell = ChatWindowShell(_make_agent_scope())
    assert shell.timeline is not None
    assert shell.thinking_panel is not None
    assert shell.tool_panel is not None
    assert shell.input_bar is not None


def test_shell_header_shows_title():
    shell = ChatWindowShell(_make_agent_scope())
    assert "Edini Agent" in shell.header_text()


def test_shell_header_shows_badge_for_hda():
    shell = ChatWindowShell(_make_hda_scope())
    assert "core: /obj/x" in shell.header_text()


def test_shell_accepts_custom_left_panel():
    from PySide6 import QtWidgets
    custom = QtWidgets.QLabel("custom left")
    shell = ChatWindowShell(_make_agent_scope(), left_panel=custom)
    assert shell.left_panel is custom


def test_shell_hda_hides_attachment_bar():
    """HDA scope (show_attachment_bar=False) → InputBar without attachment bar."""
    shell = ChatWindowShell(_make_hda_scope())
    assert shell.input_bar._show_attachment_bar is False
