"""Edini main window — 3-panel layout with QSplitter.

Pi manages all sessions via RPC. Edini is a thin UI wrapper.
"""
import importlib
import os

from PySide6 import QtCore, QtWidgets

from edini.rpc_client import RpcClient
from edini.tool_executor import ToolExecutor
from edini.ui.chat_runtime import ChatRuntime
from edini.ui.theme import apply_theme, accent_color
from edini.ui.agent_panel import AgentPanel
from edini.ui.history_panel import HistoryPanel
from edini.ui.context_panel import ContextPanel
from edini.ui.pi_sessions import load_pi_messages
from edini.config import get_settings
from edini.ui.snapshot_engine import snapshot as snap_scene, diff as diff_snapshots, restore as restore_snapshot

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None


def _get_working_dir() -> str:
    """Get the working directory for pi: HIP path in Houdini, CWD otherwise."""
    if hou:
        try:
            hip = hou.hipFile.path()
            if hip:
                # Use HIP dir so pi sessions are scoped to the project
                return os.path.dirname(hip) or hip
        except Exception:
            pass
    return os.getcwd()


class EdiniMainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edini Agent")
        self.resize(1520, 1000)

        self._tool_executor = ToolExecutor()
        self._rpc_client = RpcClient()
        self._chat_runtime = ChatRuntime(self._rpc_client, self)
        self._current_session_path = ""
        self._active_session_path = ""
        self._browsing_session_path = ""
        self._extracting_knowledge = False

        # Undo/redo stack for change tree
        self._pre_snapshot: dict = {}
        self._undo_stack: list[dict] = []
        self._undo_pointer = -1
        self._round_counter = 0

        self._round_elapsed = QtCore.QElapsedTimer()
        self._round_timer = QtCore.QTimer(self)
        self._round_timer.setInterval(1000)
        self._round_timer.timeout.connect(self._on_round_tick)

        self._build_ui()
        self._bind_events()
        self._bootstrap()

    def _build_ui(self):
        from edini.ui.theme import init_theme_from_config
        init_theme_from_config()
        apply_theme(self)

        central = QtWidgets.QWidget(self)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.main_splitter = QtWidgets.QSplitter(central)
        self.main_splitter.setOrientation(QtCore.Qt.Horizontal)

        # Left: History panel
        self.history_panel = HistoryPanel(self.main_splitter)
        self.history_panel.setMinimumWidth(200)
        self.history_panel.setMaximumWidth(260)

        # Center: Agent panel
        self.agent_panel = AgentPanel(self.main_splitter)
        self.agent_panel.setMinimumWidth(500)

        # Right: Context panel
        self.context_panel = ContextPanel(self.main_splitter)
        self.context_panel.setMinimumWidth(340)
        self.context_panel.setMaximumWidth(400)

        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setCollapsible(2, False)
        self.main_splitter.setSizes([240, 720, 400])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)

        root.addWidget(self.main_splitter, 1)

        self.setCentralWidget(central)

        self.status = QtWidgets.QStatusBar(self)
        self.setStatusBar(self.status)
        self.status.showMessage("Ready")

    def _bind_events(self):
        # Chat runtime signals
        self._chat_runtime.started.connect(self._on_agent_started)
        self._chat_runtime.stream_chunk.connect(self.agent_panel.append_stream_chunk)
        self._chat_runtime.thinking_chunk.connect(self._on_thinking)
        self._chat_runtime.tool_started.connect(self._on_tool_call)
        self._chat_runtime.tool_completed.connect(self._on_tool_result)
        self._chat_runtime.completed.connect(self._on_agent_done)
        self._chat_runtime.failed.connect(self._on_error)
        self._chat_runtime.busy_changed.connect(self._on_busy_changed)
        self._chat_runtime.stats_updated.connect(self.context_panel.set_usage)

        # Agent panel signals
        self.agent_panel.submit_requested.connect(self._on_agent_submit)
        self.agent_panel.abort_requested.connect(self._on_abort_request)
        self.agent_panel.knowledge_accepted.connect(self._on_knowledge_accepted)
        self.agent_panel.knowledge_rejected.connect(self._on_knowledge_rejected)

        # Change tree signals
        self.agent_panel.change_tree_widget.undo_round_requested.connect(
            self._on_change_undo)
        self.agent_panel.change_tree_widget.redo_requested.connect(
            self._on_change_redo)
        self.agent_panel.change_tree_widget.node_path_requested.connect(
            self._on_change_node_requested)

        # History panel signals
        self.history_panel.new_session_requested.connect(self._on_new_session)
        self.history_panel.session_selected.connect(self._on_session_selected)
        self.history_panel.session_deleted.connect(self._on_session_deleted)
        self.history_panel.back_to_current_requested.connect(self._on_back_to_current)

        # Pi status
        self._rpc_client.status_changed.connect(self._on_status_changed)
        self._rpc_client.extension_info.connect(self.context_panel.set_tools_info)
        # Pi session management responses
        self._rpc_client.session_switched.connect(self._on_pi_session_switched)
        self._rpc_client.messages_received.connect(self._on_pi_messages_received)

        # Scene refresh timer
        self._scene_timer = QtCore.QTimer(self)
        self._scene_timer.setInterval(3000)
        self._scene_timer.timeout.connect(self.context_panel.refresh_scene_info)
        self._scene_timer.start()

        # Stats polling timer (during agent execution)
        self._stats_poll_timer = QtCore.QTimer(self)
        self._stats_poll_timer.setInterval(3000)
        self._stats_poll_timer.timeout.connect(self._rpc_client.send_get_stats)

    def _bootstrap(self):
        cwd = _get_working_dir()
        self._rpc_client.set_cwd(cwd)
        self.history_panel.set_cwd(cwd)

        self._tool_executor.start()
        self._rpc_client.start()
        self.history_panel.load_sessions()
        self.context_panel.refresh_scene_info()
        self.context_panel.refresh_knowledge()
        settings = get_settings()
        self.context_panel.set_provider_model(
            settings.get("provider", "deepseek"),
            settings.get("model_id", "deepseek-chat"),
        )
        self.context_panel.set_tools_info("16 loaded, port 9876")
        from edini.ui.hotkey import install_event_filter
        install_event_filter()

    # ── Signal handlers ──

    def _on_agent_submit(self, text: str, images=None):
        # Take pre-snapshot for change tracking
        self._pre_snapshot = snap_scene()
        self.agent_panel.begin_assistant_message()
        self._rpc_client.send_prompt(text, images=images)

    def _on_agent_started(self, _):
        self.agent_panel.set_busy(True)
        self._stats_poll_timer.start()
        self._round_elapsed.start()
        self._round_timer.start()
        self.status.showMessage("Processing...")

    def _on_agent_done(self, _):
        self._stats_poll_timer.stop()
        self._round_timer.stop()
        self._on_round_tick()  # final update

        # ── Change tree: take post-snapshot and diff ──
        post_snapshot = snap_scene()
        if self._pre_snapshot:
            change_diff = diff_snapshots(self._pre_snapshot, post_snapshot)
            summary = change_diff.get("summary", {})
            has_changes = (
                summary.get("created", 0) > 0 or
                summary.get("deleted", 0) > 0 or
                summary.get("modified", 0) > 0
            )
            if has_changes:
                # Detect manual modifications between rounds
                if self._undo_stack and self._undo_pointer >= 0:
                    last_post = self._undo_stack[self._undo_pointer].get("post", {})
                    manual_check = diff_snapshots(last_post, self._pre_snapshot)
                    ms = manual_check.get("summary", {})
                    if (ms.get("created", 0) > 0 or ms.get("deleted", 0) > 0 or
                            ms.get("modified", 0) > 0):
                        self._undo_stack.clear()
                        self._undo_pointer = -1
                        self.agent_panel.change_tree_widget.clear_all()
                        self.status.showMessage("场景被手动修改，撤销历史已清空", 3000)

                # Truncate redo entries if pointer not at top
                if self._undo_pointer < len(self._undo_stack) - 1:
                    self._undo_stack = self._undo_stack[:self._undo_pointer + 1]

                self._round_counter += 1
                self._undo_stack.append({
                    "pre": dict(self._pre_snapshot),
                    "post": post_snapshot,
                    "diff": change_diff,
                    "round_num": self._round_counter,
                })
                self._undo_pointer = len(self._undo_stack) - 1

                self.agent_panel.change_tree_widget.add_round(
                    change_diff, self._round_counter)
                self.agent_panel.change_tree_widget.set_undo_pointer(
                    self._undo_pointer)

            self._pre_snapshot = {}

        # Expand change tree after conversation
        self.agent_panel.change_tree_widget.expand()

        # If this was an extraction response, handle separately
        if self._extracting_knowledge:
            self._handle_extraction_response()
            return

        self.agent_panel.finish_streaming()
        self.agent_panel.set_busy(False)

        self.context_panel.refresh_scene_info()
        self._rpc_client.send_get_stats()
        self._update_statusbar()
        self.status.showMessage("Ready")
        # Refresh session list (message count updated)
        self.history_panel.load_sessions()

        # Auto knowledge extraction
        self._maybe_extract_knowledge()

    def _on_tool_call(self, tool_name: str, tool_call_id: str, args: dict):
        self.agent_panel.add_tool_card(tool_name, args, tool_call_id)

    def _on_tool_result(self, tool_name: str, tool_call_id: str, result: str):
        self.agent_panel.set_tool_result(tool_call_id, result)

    def _on_thinking(self, text: str):
        self.agent_panel.add_thinking_step(0, text)

    def _on_abort_request(self):
        self._rpc_client.send_abort()
        self.agent_panel.show_aborted()
        self._round_timer.stop()

        # Take post-snapshot on abort too (partial changes may exist)
        post_snapshot = snap_scene()
        if self._pre_snapshot:
            change_diff = diff_snapshots(self._pre_snapshot, post_snapshot)
            summary = change_diff.get("summary", {})
            if (summary.get("created", 0) > 0 or
                    summary.get("deleted", 0) > 0 or
                    summary.get("modified", 0) > 0):
                if self._undo_pointer < len(self._undo_stack) - 1:
                    self._undo_stack = self._undo_stack[:self._undo_pointer + 1]
                self._round_counter += 1
                self._undo_stack.append({
                    "pre": dict(self._pre_snapshot),
                    "post": post_snapshot,
                    "diff": change_diff,
                    "round_num": self._round_counter,
                })
                self._undo_pointer = len(self._undo_stack) - 1
                self.agent_panel.change_tree_widget.add_round(
                    change_diff, self._round_counter)
                self.agent_panel.change_tree_widget.set_undo_pointer(
                    self._undo_pointer)
            self._pre_snapshot = {}
        self.agent_panel.change_tree_widget.expand()

    def _on_error(self, msg: str):
        self._stats_poll_timer.stop()
        self._round_timer.stop()
        self.agent_panel.add_error(msg)
        self.agent_panel.set_busy(False)
        self.status.showMessage(f"Error: {msg}")

    def _on_round_tick(self):
        """Update the round elapsed time display in Pi Status."""
        if self._round_elapsed.isValid():
            elapsed = self._round_elapsed.elapsed() / 1000.0
            self.context_panel.set_round_time(elapsed)

    # ── Knowledge Extraction ──

    # ── Change Tree undo/redo / navigation ──

    def _on_change_undo(self, round_num: int):
        """Undo a specific round: restore post → pre state."""
        for entry in self._undo_stack:
            if entry.get("round_num") == round_num:
                restore_snapshot(entry["post"], entry["pre"])
                self._undo_pointer -= 1
                self.agent_panel.change_tree_widget.mark_undone(round_num)
                self.agent_panel.change_tree_widget.set_undo_pointer(
                    self._undo_pointer)
                self.status.showMessage(f"已撤销 Round {round_num}", 2000)
                return

    def _on_change_redo(self):
        """Redo the next undone round: restore pre → post state."""
        if self._undo_pointer + 1 < len(self._undo_stack):
            self._undo_pointer += 1
            entry = self._undo_stack[self._undo_pointer]
            restore_snapshot(entry["pre"], entry["post"])
            round_num = entry.get("round_num", 0)
            self.agent_panel.change_tree_widget.mark_redone(round_num)
            self.agent_panel.change_tree_widget.set_undo_pointer(
                self._undo_pointer)
            self.status.showMessage(f"已重做 Round {round_num}", 2000)

    def _on_change_node_requested(self, node_path: str):
        """Navigate Houdini viewport to the requested node path."""
        try:
            import hou
            node = hou.node(node_path)
            if node:
                node.setCurrent(True, clear_all_selected=True)
                self.status.showMessage(f"已跳转到节点: {node_path}", 1800)
            else:
                self.status.showMessage(f"未找到节点: {node_path}", 2200)
        except Exception:
            pass

    # ── Knowledge Extraction ──

    def _maybe_extract_knowledge(self):
        """After conversation finishes, optionally trigger knowledge extraction."""
        settings = get_settings()
        if not settings.get("knowledge_enabled", True):
            return
        if self._extracting_knowledge:
            return
        self._extracting_knowledge = True
        self.status.showMessage("Extracting knowledge...")

        prompt = (
            "Review the conversation above and identify mistakes, pitfalls, or tricky situations "
            "that are LIKELY TO BE REPEATED in future Houdini work.\n\n"
            "🔴 ONLY extract if ALL of these are true:\n"
            "1. A concrete mistake was made, or something unexpectedly failed\n"
            "2. The solution was non-obvious — an experienced Houdini user might also forget this\n"
            "3. Without this reminder, the same mistake would likely happen again\n\n"
            "✋ DO NOT extract:\n"
            "- Generic Houdini knowledge that any LLM already knows (node types, basic workflows)\n"
            "- Things that worked correctly the first time\n"
            "- Standard API documentation facts\n"
            "- Obvious tips like 'check your parameters before rendering'\n\n"
            "Return a JSON array. If nothing qualifies, return [].\n\n"
            "Each object:\n"
            '- type: "rule" OR "entry". Use this test: "If I start a brand new Houdini project tomorrow, '
            'will this still apply?" YES → "rule", NO (only applies to this specific case/tool) → "entry"\n'
            '- category: prefer "避坑", use "配置" for config issues, "工作流" for workflow gotchas\n'
            '- title: short summary in Chinese (max 30 chars)\n'
            '- content: WHAT went wrong + WHY + HOW to avoid next time (1-3 sentences)\n'
            '- tags: optional search keywords\n\n'
            'Rule examples: "Node creation order matters for DOP networks" (applies to all DOPs)\n'
            'Entry examples: "第3个Resample节点需要关闭MaxSegments否则崩" (applies to this one setup)\n\n'
            'Examples: [{"type":"rule","category":"避坑","title":"DOP解算中节点顺序影响结果","content":"在DOP网络中，解算器顺序改变会完全改变模拟结果。GasTurbulence必须关闭否则大尺度烟雾数值爆炸。所有DOP项目适用。","tags":["dop","sim"]}]'
        )
        self.agent_panel.begin_assistant_message()
        QtCore.QTimer.singleShot(300, lambda: self._rpc_client.send_prompt(prompt))

    def _handle_extraction_response(self):
        """Capture extraction response directly (not from timeline HTML)."""
        from edini.ui.knowledge_store import parse_extraction_response

        raw_text = self.agent_panel.get_raw_stream_text()
        self.agent_panel.cancel_current_stream()
        self.agent_panel.set_busy(False)

        items, error_text = parse_extraction_response(raw_text)

        if items:
            self.agent_panel.show_extraction_results(items)
            self.status.showMessage(
                f"Knowledge: {len(items)} items found — review below")
        else:
            self._extracting_knowledge = False
            if error_text:
                self.status.showMessage(
                    "Knowledge extraction failed — check Houdini Console")
            else:
                self.status.showMessage("No new knowledge to extract")

    def _on_knowledge_accepted(self, items: list):
        """User accepted extracted knowledge items — save them."""
        self._extracting_knowledge = False
        from edini.ui.knowledge_store import accept_extracted
        r, e = accept_extracted(items, self._current_session_path)
        parts = []
        if r:
            parts.append(f"{r} 条铁律")
        if e:
            parts.append(f"{e} 条知识")
        self.status.showMessage(f"Knowledge saved: {' + '.join(parts)}" if parts else "Ready")
        self.context_panel.refresh_knowledge()

    def _on_knowledge_rejected(self):
        """User rejected all extracted knowledge."""
        self._extracting_knowledge = False
        self.status.showMessage("Ready")

    def _on_busy_changed(self, busy: bool):
        pass

    def _on_status_changed(self, status: str):
        self._last_pi_status = status
        self.context_panel.set_pi_status(status)
        self._update_statusbar()
        # On first connect, set session name and request stats
        if status == "connected":
            if hou:
                try:
                    hip = hou.hipFile.name()
                    if hip:
                        name = os.path.splitext(os.path.basename(hip))[0]
                        self._rpc_client.send_set_session_name(name)
                except Exception:
                    pass
            self._rpc_client.send_get_stats()

    def _on_pi_session_switched(self, session_path: str):
        """Called when pi confirms a session switch (new or resumed)."""
        self._current_session_path = session_path
        self._rpc_client.send_get_stats()
        # Update list highlight to match active session
        highlight = self._browsing_session_path or session_path
        self.history_panel.highlight_session(highlight)

    def _on_pi_messages_received(self, messages: list):
        """Render messages from pi in the agent panel."""
        # This is a fallback; normally we load from local file synchronously
        self.agent_panel.clear_timeline()
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "user":
                self.agent_panel._append_user_message(content)
            elif role == "assistant":
                self.agent_panel._render_stored_assistant_message(m)

    def _on_new_session(self):
        # Save current session as active before creating new one (only if not already browsing)
        if not self._browsing_session_path:
            self._active_session_path = self._current_session_path
        self._browsing_session_path = ""
        self.history_panel.set_browsing_mode(False)

        self._current_session_path = ""
        self.agent_panel.clear_timeline()
        self.context_panel.reset_stats()
        self._rpc_client.send_new_session()
        # Schedule a reload after pi creates the session
        QtCore.QTimer.singleShot(500, self.history_panel.load_sessions)

    def _on_session_selected(self, session_path: str):
        if session_path == self._current_session_path and not self._browsing_session_path:
            return  # Already viewing this session in normal mode, no-op

        # Enter browsing mode if not already in it
        if not self._browsing_session_path:
            self._active_session_path = self._current_session_path
        self._browsing_session_path = session_path
        self.history_panel.set_browsing_mode(True)
        self.history_panel.highlight_session(session_path)

        self._current_session_path = session_path
        self.agent_panel.clear_timeline()
        self.context_panel.reset_stats()

        # Load messages directly from local JSONL for instant rendering
        messages = load_pi_messages(session_path)
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "user":
                self.agent_panel._append_user_message(content)
            elif role == "assistant":
                self.agent_panel._render_stored_assistant_message(m)

        # Tell pi to switch session (async, updates stats)
        self._rpc_client.send_switch_session(session_path)

    def _on_back_to_current(self):
        """Exit browsing mode and restore the previously active session."""
        target = self._active_session_path
        self._browsing_session_path = ""
        self.history_panel.set_browsing_mode(False)

        if target:
            self._current_session_path = target
            self.agent_panel.clear_timeline()
            self.context_panel.reset_stats()

            messages = load_pi_messages(target)
            for m in messages:
                role = m.get("role", "")
                content = m.get("content", "")
                if role == "user":
                    self.agent_panel._append_user_message(content)
                elif role == "assistant":
                    self.agent_panel._render_stored_assistant_message(m)

            self._rpc_client.send_switch_session(target)
            self.history_panel.highlight_session(target)
        else:
            self._current_session_path = ""
            self.agent_panel.clear_timeline()

    def _on_session_deleted(self, session_path: str):
        self.history_panel.remove_session(session_path)

        # If deleted session was the one being browsed, fall back to active
        if session_path == self._browsing_session_path:
            self._browsing_session_path = ""
            self.history_panel.set_browsing_mode(False)
            if self._active_session_path and self._active_session_path != session_path:
                self._on_session_selected(self._active_session_path)
                self.history_panel.set_browsing_mode(False)
            else:
                self._current_session_path = ""
                self.agent_panel.clear_timeline()
            return

        # If deleted session was the active one, clear it
        if session_path == self._active_session_path:
            self._active_session_path = ""

        if session_path == self._current_session_path:
            self._current_session_path = ""
            self.agent_panel.clear_timeline()

    def refresh_theme(self):
        """Called externally after settings change to reapply theme."""
        from edini.ui.theme import init_theme_from_config, refresh_window_theme
        init_theme_from_config()
        refresh_window_theme(self)

    def _update_statusbar(self):
        parts = []
        status = getattr(self, '_last_pi_status', 'connecting')
        icons = {"connected": "●", "connecting": "◌", "disconnected": "○"}
        parts.append(f"{icons.get(status, '●')} {status}")
        settings = get_settings()
        parts.append(f"{settings.get('provider','?')}/{settings.get('model_id','?')}")
        if hou:
            try:
                root = hou.node("/")
                count = len(root.allSubChildren()) if root else 0
                parts.append(f"Nodes:{count}")
            except Exception:
                pass
        self.status.showMessage("  │  ".join(parts))

    def closeEvent(self, event):
        from edini.ui.windows import _main_window as global_main
        self._rpc_client.stop()
        self._tool_executor.stop()
        super().closeEvent(event)
        # Release the global singleton so reopen creates a fresh window
        if global_main is self:
            import edini.ui.windows as win_mod
            win_mod._main_window = None
