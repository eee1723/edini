"""ScopeConfig — diff entry point for chat windows."""
from edini.ui.chat.scope import ScopeConfig


def _provider():
    return {"hip": "x"}


def test_scope_is_frozen():
    s = ScopeConfig(scope_id="agent", window_title="Edini Agent",
                   accent_override=None, header_badge=None,
                   left_panel_kind="global_sessions", show_change_tree=True,
                   show_eval_button=True, show_attachment_bar=True,
                   show_param_snapshot=False, scene_data_provider=_provider)
    try:
        s.scope_id = "x"
        assert False, "frozen dataclass should not allow mutation"
    except AttributeError:
        pass


def test_agent_scope_fields():
    a = ScopeConfig(scope_id="agent", window_title="Edini Agent",
                   accent_override=None, header_badge=None,
                   left_panel_kind="global_sessions", show_change_tree=True,
                   show_eval_button=True, show_attachment_bar=True,
                   show_param_snapshot=False, scene_data_provider=_provider)
    assert a.scope_id == "agent"
    assert a.accent_override is None
    assert a.left_panel_kind == "global_sessions"
    assert a.show_eval_button is True
    assert a.show_param_snapshot is False


def test_hda_scope_fields():
    h = ScopeConfig(scope_id="project_hda", window_title="Project HDA",
                   accent_override="#f59e0b", header_badge="core: /obj/x",
                   left_panel_kind="node_versions", show_change_tree=True,
                   show_eval_button=False, show_attachment_bar=False,
                   show_param_snapshot=True, scene_data_provider=_provider)
    assert h.scope_id == "project_hda"
    assert h.accent_override == "#f59e0b"
    assert h.header_badge == "core: /obj/x"
    assert h.left_panel_kind == "node_versions"
    assert h.show_attachment_bar is False
    assert h.show_param_snapshot is True


def test_scene_provider_callable():
    s = ScopeConfig(scope_id="agent", window_title="T", accent_override=None,
                   header_badge=None, left_panel_kind="global_sessions",
                   show_change_tree=True, show_eval_button=True,
                   show_attachment_bar=True, show_param_snapshot=False,
                   scene_data_provider=_provider)
    result = s.scene_data_provider()
    assert result == {"hip": "x"}


def test_chat_runtime_reexport():
    """ChatRuntime accessible from edini.ui.chat package."""
    from edini.ui.chat.chat_runtime import ChatRuntime
    from edini.ui.chat_runtime import ChatRuntime as Orig
    assert ChatRuntime is Orig
