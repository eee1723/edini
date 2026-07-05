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

    Version management (new/switch/delete versions) is wired in T5.3.
    """
    def __init__(self, runtime, shell, core_path: str):
        super().__init__(runtime, shell)
        self._core_path = core_path

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
