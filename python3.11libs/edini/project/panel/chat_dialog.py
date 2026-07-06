"""ProjectChatDialog — HDA chat window using ChatWindowShell.

Full 3-panel: version list (left, Stage 5) | chat (center) | status+knowledge (right).
Uses ChatRuntime (no direct RpcClient signal wiring). Orange accent (#f59e0b)
makes it visually distinct from the main agent window at a glance.

One dialog per HDA core node; owns its RpcClient (independent Pi subprocess).
Session named after core_path.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from edini.ui.theme import apply_theme
from edini.ui.chat.window_shell import ChatWindowShell
from edini.ui.chat.chat_runtime import ChatRuntime
from edini.project.panel.chat_driver import ProjectChatDriver, make_hda_scope


class ProjectChatDialog(QtWidgets.QDialog):
    """Full chat window bound to a Project HDA core node.

    Launched from the HDA's "edini_chat" button. Owns its RpcClient (independent
    Pi subprocess per core node). 3-panel layout via ChatWindowShell.
    """

    def __init__(self, core_path: str, node_type: str = "", parent=None):
        super().__init__(parent)
        self._core_path = core_path
        self._node_type = node_type
        self._rpc = None
        self._runtime = None
        self._driver = None
        self.setWindowTitle(f"Edini — Project HDA · {core_path}")
        self.resize(1100, 720)

        # Left panel placeholder (NodeVersionList arrives in Stage 5)
        self._left_placeholder = QtWidgets.QLabel(
            "Versions\n(Stage 5 will add\nversion list here)")
        self._left_placeholder.setMinimumWidth(200)
        self._left_placeholder.setStyleSheet(
            "color:#71717a; padding:12px; background:#0a0a10;"
            "border-right:1px solid #1e1e2c;"
        )
        self._left_placeholder.setAlignment(QtCore.Qt.AlignCenter)

        scope = make_hda_scope(core_path, node_type, self._collect_scene)
        self._shell = ChatWindowShell(scope, left_panel=self._left_placeholder)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._shell)

        apply_theme(self)

    def _collect_scene(self) -> dict:
        """Gather node-level scene info. Enriched in Stage 5 with real HDA data."""
        return {"path": self._core_path}

    # ── RpcClient lifecycle ──

    def showEvent(self, event):
        """Lazy-start RpcClient on first visibility."""
        super().showEvent(event)
        if self._rpc is None:
            self._get_rpc()

    def _get_rpc(self):
        if self._rpc is not None:
            return self._rpc
        from edini.tool_executor import get_tool_executor
        get_tool_executor()
        from edini.rpc_client import RpcClient
        self._rpc = RpcClient(parent=self)
        # Inject scope env so the edini-context extension knows this Pi process
        # is bound to a specific Project HDA and injects workspace-lock directives.
        self._rpc.set_env_extra({
            "EDINI_SCOPE_ID": "project_hda",
            "EDINI_CORE_PATH": self._core_path,
        })
        self._rpc.status_changed.connect(self._on_rpc_status)
        self._rpc.start()
        return self._rpc

    def _on_rpc_status(self, status: str):
        # Always mirror the raw RPC status into the ContextPanel so the Pi
        # Status card reflects reality (connecting/connected/disconnected/error).
        self._shell.context_panel.set_pi_status(status)
        if status == "connected" and self._runtime is None:
            rpc = self._get_rpc()
            self._runtime = ChatRuntime(rpc)
            self._driver = ProjectChatDriver(
                self._runtime, self._shell, self._core_path)
            # Configure session + model.
            # Session name uses the versioned convention (core_path::vN) so the
            # version scanner can find this node's sessions. Start at v1 (or the
            # next free version if prior sessions exist for this node).
            from edini.ui.components.version_naming import (
                make_version_session_name, next_version,
            )
            from edini.ui.version_scanner import scan_node_versions
            try:
                existing = scan_node_versions(self._core_path)
                start_v = next_version([v["version"] for v in existing]) if existing else 1
            except Exception:
                start_v = 1
            self._driver.set_current_version(start_v)
            rpc.send_set_session_name(make_version_session_name(self._core_path, start_v))
            try:
                from edini.config import read_pi_settings
                s = read_pi_settings()
                p, m = s.get("defaultProvider", ""), s.get("defaultModel", "")
                if p and m:
                    rpc.send_set_model(p, m)
            except Exception:
                pass
            # Push initial scene info to the ContextPanel
            self._shell.context_panel.set_scene_info(self._collect_scene())

    def closeEvent(self, event):
        if self._rpc is not None:
            try:
                self._rpc.stop()
            except Exception:
                pass
        super().closeEvent(event)


# ── Active-dialog registry (one per core_path; re-click focuses existing) ──

_active_dialogs: dict[str, ProjectChatDialog] = {}


def open_chat_for_core(core_path: str, node_type: str = "") -> None:
    """Launch (or focus) the chat dialog for a Project HDA core node.

    Called by the HDA's PythonModule open_chat() (button callback). Parented to
    hou.qt.mainWindow() so it's a real top-level window (IME works).
    """
    import hou
    dlg = _active_dialogs.get(core_path)
    if dlg is None:
        dlg = ProjectChatDialog(core_path, node_type, parent=hou.qt.mainWindow())
        _active_dialogs[core_path] = dlg
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
