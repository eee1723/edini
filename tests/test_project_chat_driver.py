"""ProjectChatDriver — HDA scope uses orange accent + node-level config."""
import sys
sys.path.insert(0, "python3.11libs")
from tests.qt_helpers import qapp
from edini.project.panel.chat_driver import ProjectChatDriver, make_hda_scope


def test_hda_scope_uses_orange():
    scope = make_hda_scope(core_path="/obj/geo1/build1", node_type="project_builder",
                           scene_provider=lambda: {})
    assert scope.accent_override == "#f59e0b"
    assert scope.scope_id == "project_hda"


def test_hda_scope_window_title_has_core_path():
    scope = make_hda_scope(core_path="/obj/geo1/build1", node_type="t",
                           scene_provider=lambda: {})
    assert "/obj/geo1/build1" in scope.window_title


def test_hda_scope_header_badge_has_core_path_and_type():
    scope = make_hda_scope(core_path="/obj/x", node_type="project_builder::1.0",
                           scene_provider=lambda: {})
    assert "/obj/x" in scope.header_badge
    assert "project_builder" in scope.header_badge or "::1.0" in scope.header_badge


def test_hda_scope_left_panel_is_versions():
    scope = make_hda_scope(core_path="/x", node_type="t", scene_provider=lambda: {})
    assert scope.left_panel_kind == "node_versions"


def test_hda_scope_disables_attachments_enables_snapshot():
    scope = make_hda_scope(core_path="/x", node_type="t", scene_provider=lambda: {})
    assert scope.show_attachment_bar is False
    assert scope.show_param_snapshot is True
    assert scope.show_eval_button is False


def test_project_chat_driver_is_subclass():
    from edini.ui.chat.base_driver import BaseChatDriver
    assert issubclass(ProjectChatDriver, BaseChatDriver)
