"""ProjectChatDriver — HDA-specific driver. Node-level scope + scene provider.

Subclass of BaseChatDriver. The HDA window owns its own RpcClient (one Pi
subprocess per core node, per spec decision #11), wrapped by ChatRuntime.
"""
from edini.ui.chat.base_driver import BaseChatDriver
from edini.ui.chat.scope import ScopeConfig


def make_hda_scope(core_path: str, node_type: str, scene_provider) -> ScopeConfig:
    """Build the ScopeConfig for a Project HDA chat window.

    Orange accent (#f59e0b) is FIXED — does not follow global theme — so the
    HDA window is visually distinct from the main agent window at a glance.
    """
    return ScopeConfig(
        scope_id="project_hda",
        window_title=f"Project HDA \u00b7 {core_path}",
        accent_override="#f59e0b",
        header_badge=f"{core_path}  [{node_type}]" if node_type else core_path,
        left_panel_kind="node_versions",
        show_change_tree=True,        # modeling needs undo/redo rounds
        show_eval_button=False,       # HDA focuses on modeling, not eval
        show_attachment_bar=False,    # HDA focuses on modeling, not multimodal
        show_param_snapshot=True,     # HDA-only: show params + diff
        scene_data_provider=scene_provider,
    )


class ProjectChatDriver(BaseChatDriver):
    """HDA driver: owns core_path, provides node-level scene info.

    Version management is wired in __init__: the left panel is replaced with a
    NodeVersionList, and new/switch version clicks swap the active Pi session.
    """
    def __init__(self, runtime, shell, core_path: str):
        super().__init__(runtime, shell)
        self._core_path = core_path
        self._current_version: int | None = None
        self._init_version_list()

    def set_current_version(self, version: int):
        """Mark a version as the active one (called by the dialog on connect).

        This does NOT switch the Pi session — it only updates the UI marker so
        the version list reflects which session is live. Use _on_select_version
        for an actual user-driven switch.
        """
        self._current_version = version
        if getattr(self, "_version_list", None) is not None:
            self._version_list.mark_current(version)

    def _init_version_list(self):
        """Scan for existing versions and wire the NodeVersionList into the shell."""
        from edini.ui.components.version_list import NodeVersionList
        from edini.ui.version_scanner import scan_node_versions

        self._version_list = NodeVersionList()
        # Scan existing versions for this node (Pi sessions dir may not exist yet).
        # Pass the project cwd so the scanner looks in the project's session dir
        # (matches where logs are now written via set_cwd in the panels).
        try:
            from edini.config import get_pi_working_dir
            versions = scan_node_versions(self._core_path, cwd=get_pi_working_dir())
        except Exception:
            versions = []
        # Mark the highest version as current if any exist
        if versions:
            self._current_version = max(v["version"] for v in versions)
            for v in versions:
                v["current"] = (v["version"] == self._current_version)
        self._version_list.set_versions(versions)
        # Wire signals
        self._version_list.version_created.connect(self._on_new_version)
        self._version_list.version_selected.connect(self._on_select_version)
        # Replace the placeholder left panel
        self._shell.replace_left(self._version_list)

    def _on_new_version(self, version: int):
        """User clicked '+ New Version' — start a fresh Pi session."""
        from edini.ui.components.version_naming import make_version_session_name
        name = make_version_session_name(self._core_path, version)
        self._runtime.rpc.send_set_session_name(name)
        self._current_version = version
        # Clear the timeline for the new (empty) version
        self._shell.timeline.clear()
        # Reset thinking/tool panels to the initial state
        self._shell.thinking_panel.reset()
        self._shell.tool_panel.clear()
        self._version_list.mark_current(version)

    def _on_select_version(self, version: int):
        """User clicked a version — switch Pi session to it.

        History backfill depends on Pi replaying messages_received on session
        switch (spec §6.4, best-effort). For now we clear the timeline; if Pi
        replays history, new messages will populate it, otherwise it stays
        empty until the next user prompt.
        """
        from edini.ui.components.version_naming import make_version_session_name
        name = make_version_session_name(self._core_path, version)
        self._runtime.rpc.send_set_session_name(name)
        self._current_version = version
        self._shell.timeline.clear()
        self._shell.thinking_panel.reset()
        self._shell.tool_panel.clear()
        self._version_list.mark_current(version)

    def collect_scene_info(self) -> dict:
        """Node-level scene info for the ContextPanel.

        Stage 5 will enrich this with real HDA param/child-node data.
        For now, returns the core_path as the context path.
        """
        return {
            "hip": None,              # filled in Stage 5 from hou.hipFile
            "path": self._core_path,
            "selected": None,
            "nodes": None,
            "node_type": None,        # filled in Stage 5
            "params_summary": None,
        }
