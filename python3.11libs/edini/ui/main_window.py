"""Edini main window — 3-panel layout with QSplitter.

Pi manages all sessions via RPC. Edini is a thin UI wrapper.
"""
import importlib
import json
import os

from PySide6 import QtCore, QtWidgets

from edini.rpc_client import RpcClient
from edini.tool_executor import ToolExecutor, get_tool_executor
from edini import screenshots
from edini.ui.chat_runtime import ChatRuntime
from edini.ui.theme import apply_theme, accent_color
from edini.ui.agent_panel import AgentPanel
from edini.ui.history_panel import HistoryPanel
from edini.ui.context_panel import ContextPanel
from edini.ui.reflect_worker import ReflectWorker
from edini.ui.vision_overlay import VisionDescriptionBubble
from edini.eval.store import EvalStore
from edini.ui.eval_tab import EvalTab
from edini.ui.pi_sessions import load_pi_messages, load_pi_messages_with_images
from edini.config import get_settings, read_pi_settings, migrate_legacy_settings
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

        self._tool_executor = get_tool_executor()
        self._rpc_client = RpcClient()
        self._chat_runtime = ChatRuntime(self._rpc_client, self)
        self._current_session_path = ""
        self._active_session_path = ""
        self._browsing_session_path = ""
        self._reflect_worker: ReflectWorker | None = None
        self._last_capture_path = ""  # track capture→describe pairing
        self._cwd = _get_working_dir()

        # Undo/redo stack for change tree
        self._pre_snapshot: dict = {}
        self._undo_stack: list[dict] = []
        self._undo_pointer = -1
        self._round_counter = 0

        self._round_elapsed = QtCore.QElapsedTimer()
        self._round_timer = QtCore.QTimer(self)
        self._round_timer.setInterval(1000)
        self._round_timer.timeout.connect(self._on_round_tick)

        # Multimodal state
        self._pending_images: list[dict] | None = None   # images from current request
        self._pending_cache_meta: list[dict] | None = None  # metadata pending cache write
        self._pending_descriptions: list[dict] | None = None  # descriptions pending cache write
        self._recognizing_placeholder: QtWidgets.QWidget | None = None
        self._available_models: list = []

        # Migrate legacy edini settings → pi config files
        migration_msg = migrate_legacy_settings()
        if migration_msg:
            print(f"[Edini] {migration_msg}", flush=True)

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

        # Eval dashboard button in status bar
        self._eval_btn = QtWidgets.QPushButton("\U0001f4ca Eval")
        self._eval_btn.setFixedWidth(60)
        self._eval_btn.setStyleSheet(
            f"QPushButton {{"
            f"  color:#a1a1aa;background:#18182a;border:1px solid #252540;"
            f"  border-radius:4px;font-size:9pt;padding:2px 6px;"
            f"}}"
            f"QPushButton:hover {{ color:#e5e5eb;border-color:#0bc; }}"
        )
        self._eval_btn.clicked.connect(self._show_eval_dashboard)
        self.status.addPermanentWidget(self._eval_btn)

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
        self._rpc_client.vision_description.connect(self._on_vision_description)
        # Pi model discovery
        self._rpc_client.models_received.connect(self._on_models_received)
        self._rpc_client.model_changed.connect(self._on_model_changed)
        # Pi session management responses
        self._rpc_client.session_switched.connect(self._on_pi_session_switched)
        self._rpc_client.messages_received.connect(self._on_pi_messages_received)

        # Scene refresh timer
        self._scene_timer = QtCore.QTimer(self)
        self._scene_timer.setInterval(1500)
        self._scene_timer.timeout.connect(self.context_panel.refresh_scene_info)
        self._scene_timer.start()

        # Stats polling timer (during agent execution)
        self._stats_poll_timer = QtCore.QTimer(self)
        self._stats_poll_timer.setInterval(3000)
        self._stats_poll_timer.timeout.connect(self._rpc_client.send_get_stats)

    def _bootstrap(self):
        # Startup banner (comment out prints for production)
        cwd = _get_working_dir()
        self._rpc_client.set_cwd(cwd)
        self.history_panel.set_cwd(cwd)

        # ToolExecutor is now a process-level singleton (get_tool_executor),
        # already started on first access. start() is idempotent — kept as a
        # defensive no-op. NOTE: closeEvent no longer stops it, so the shared
        # HTTP server survives window close/reopen (other consumers depend on it).
        self._tool_executor.start()
        self._rpc_client.start()
        self.history_panel.load_sessions()
        self.context_panel.refresh_scene_info()
        self.context_panel.refresh_knowledge()
        pi_sett = read_pi_settings()
        self.context_panel.set_provider_model(
            pi_sett.get("defaultProvider", "?"),
            pi_sett.get("defaultModel", "?"),
        )
        # Show vision model status from edini settings
        edini_sett = get_settings()
        self.context_panel.set_vision_model(
            edini_sett.get("vision_provider", ""),
            edini_sett.get("vision_model_id", ""),
        )
        self.context_panel.set_tools_info("16 loaded, port 9876")
        from edini.ui.hotkey import install_event_filter
        install_event_filter()

    # ── Signal handlers ──

    def _on_agent_submit(self, text: str, images=None):
        # Take pre-snapshot for change tracking
        self._pre_snapshot = snap_scene()
        self.agent_panel.begin_assistant_message()

        # Save images for vision_description bubble
        self._pending_images = images

        # Build image metadata and show in user bubble
        if images:
            # Build metadata with inline base64 for "view original" fallback
            import base64 as _b64
            image_meta: list[dict] = []
            for i, img in enumerate(images):
                b64_data = img.get("data", "")
                raw_size = len(_b64.b64decode(b64_data)) if b64_data else 0
                mime = img.get("mimeType", "image/png")
                ext = mime.split("/")[-1] if "/" in mime else "png"
                # Use original filename if available, otherwise generate one
                orig_name = img.get("filename", "")
                if orig_name:
                    display_name = orig_name
                else:
                    display_name = f"image_{i+1}.{ext}"
                image_meta.append({
                    "index": i,
                    "mime_type": mime,
                    "filename": display_name,
                    "size_bytes": raw_size,
                    "source": img.get("source", "unknown"),
                    "cache_path": "",  # filled when session path known
                    "_b64_pending": b64_data,  # fallback for "view original" before cache write
                })

            # Always defer cache write to ensure session path is available.
            # Written in _on_pi_session_switched (normal) or _on_agent_done (fallback).
            self._pending_cache_meta = image_meta

            self.agent_panel._append_user_message(text, image_meta)
        else:
            self.agent_panel._append_user_message(text)

        # Add "recognizing" placeholder if images are attached
        if images:
            self._recognizing_placeholder = _RecognizingPlaceholder()
            self.agent_panel.timeline_view.add_widget(self._recognizing_placeholder)

        self._rpc_client.send_prompt(text, images=images)

    def _on_agent_started(self, _):
        self.agent_panel.set_busy(True)
        self._stats_poll_timer.start()
        self._round_elapsed.start()
        self._round_timer.start()
        self.status.showMessage("Processing...")
        # Request session path so image cache + descriptions can be written.
        # Without this, the path stays empty during normal prompt flow
        # (it's only set by explicit new_session / switch_session commands).
        self._rpc_client.send_get_state()

    def _cleanup_recognizing(self):
        """Remove recognizing placeholder if still present.

        Does NOT clear _pending_images — that data is still needed for
        deferred cache writes that happen after session path arrives.
        """
        if self._recognizing_placeholder:
            self._recognizing_placeholder.deleteLater()
            self._recognizing_placeholder = None

    def _on_agent_done(self, _):
        self._cleanup_recognizing()
        # Flush pending image cache and descriptions before clearing.
        # Handles the race where agent_end arrives before session_switched.
        self._flush_pending_image_cache()
        self._flush_pending_descriptions(self._current_session_path)
        # Only clear pending data if session path is confirmed.
        # If session_path is still empty, _on_pi_session_switched will
        # flush the cache later — keep _pending_* alive until then.
        if self._current_session_path:
            self._pending_images = None
            self._pending_cache_meta = None
            self._pending_descriptions = None
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

        # Expand change tree after conversation (only if there are changes)
        if self._undo_stack:
            self.agent_panel.change_tree_widget.expand()

        # Sync session path for background evaluation
        self.agent_panel._current_session_path = self._current_session_path

        # If session path not yet available (race: agent_end before session_switched),
        # defer evaluation and reflection until session path arrives
        if not self._current_session_path:
            self._rpc_client.session_switched.connect(
                self._on_deferred_eval_and_reflect, QtCore.Qt.QueuedConnection
            )
        else:
            self.agent_panel.finish_streaming()
            # Trigger knowledge reflection in background
            self._trigger_reflection()

        self.agent_panel.set_busy(False)

        self.context_panel.refresh_scene_info()
        self._rpc_client.send_get_stats()
        self._update_statusbar()
        self.status.showMessage("Ready")
        # Refresh session list (message count updated)
        self.history_panel.load_sessions()

    def _on_tool_call(self, tool_name: str, tool_call_id: str, args: dict):
        self.agent_panel.add_tool_card(tool_name, args, tool_call_id)

    def _on_tool_result(self, tool_name: str, tool_call_id: str, result: str):
        self.agent_panel.set_tool_result(tool_call_id, result)

        # ── Inline rendering for capture and describe tools ──
        try:
            data = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            data = {}

        if tool_name == "houdini_capture_network" and data.get("success"):
            path = data.get("path", "")
            w = data.get("width", 0)
            h = data.get("height", 0)
            if path:
                self._last_capture_path = path
                self.agent_panel.add_inline_capture_image(path, w, h)

        elif tool_name == "houdini_capture_review" and data.get("success"):
            path = data.get("path", "")
            if path:
                self._last_capture_path = path
                self.agent_panel.add_inline_capture_image(path, 0, 0)

        elif tool_name == "describe_image":
            # Render as unified VisionDescriptionBubble (same pipeline as user-uploaded images)
            content = data.get("content", [])
            details = data.get("details", {})
            if isinstance(content, list) and len(content) > 0:
                text = content[0].get("text", "")
            else:
                text = data.get("description", "") or str(data)
            if text:
                image_path = details.get("path", "")
                model_label = details.get("model", "vision-model")
                elapsed_ms = details.get("elapsedMs", 0)
                self._add_vision_bubble_for_describe(text, image_path, model_label, elapsed_ms)

    def _on_thinking(self, text: str):
        self.agent_panel.add_thinking_step(0, text)

    def _on_abort_request(self):
        self._cleanup_recognizing()
        # Flush pending image cache before clearing (image data is still valid)
        self._flush_pending_image_cache()
        self._flush_pending_descriptions(self._current_session_path)
        if self._current_session_path:
            self._pending_images = None
            self._pending_cache_meta = None
            self._pending_descriptions = None
        self._rpc_client.send_abort()
        self.agent_panel._current_session_path = self._current_session_path
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
        if self._undo_stack:
            self.agent_panel.change_tree_widget.expand()

    def _on_error(self, msg: str):
        self._cleanup_recognizing()
        # Flush pending image cache before clearing (image data is still valid)
        self._flush_pending_image_cache()
        self._flush_pending_descriptions(self._current_session_path)
        if self._current_session_path:
            self._pending_images = None
            self._pending_cache_meta = None
            self._pending_descriptions = None
        self._stats_poll_timer.stop()
        self._round_timer.stop()
        self.agent_panel.add_error(msg)
        self.agent_panel.set_busy(False)
        self.status.showMessage(f"Error: {msg}")

    def _flush_pending_image_cache(self):
        """Write pending images to cache if session path is now known.

        Called from both _on_pi_session_switched (normal path) and
        _on_agent_done (fallback for when agent_end races ahead of session_switched).
        """
        if not self._pending_cache_meta or not self._pending_images:
            return
        session_path = self._current_session_path
        if not session_path:
            return
        try:
            from edini.image_cache import save_images
            saved_meta = save_images(session_path, self._pending_images)
            if saved_meta:
                for sm in saved_meta:
                    idx = sm.get("index", -1)
                    if 0 <= idx < len(self._pending_cache_meta):
                        self._pending_cache_meta[idx]["cache_path"] = sm.get("cache_path", "")
                        self._pending_cache_meta[idx]["filename"] = sm.get(
                            "filename", self._pending_cache_meta[idx]["filename"]
                        )
                        self._pending_cache_meta[idx].pop("_b64_pending", None)
        except Exception as e:
            import traceback; traceback.print_exc()

    def _flush_pending_descriptions(self, session_path: str):
        """Save any pending vision descriptions to cache."""
        if self._pending_descriptions and session_path:
            try:
                from edini.image_cache import save_descriptions
                ok = save_descriptions(session_path, self._pending_descriptions)
                self._pending_descriptions = None
            except Exception as e:
                pass

    def _render_vision_description(self, m: dict):
        """Render a cached vision_description entry in the timeline."""
        descriptions = m.get("descriptions", [])
        if not descriptions:
            return

        # Load cached image data for "view original" feature
        image_base64_list: list[str] = []
        try:
            import base64 as _b64
            from edini.image_cache import load_image_meta
            session_path = self._current_session_path or self._browsing_session_path
            if session_path:
                meta_list = load_image_meta(session_path)
                if meta_list:
                    for meta in meta_list:
                        cache_path = meta.get("cache_path", "")
                        if cache_path and os.path.isfile(cache_path):
                            with open(cache_path, "rb") as f:
                                data = f.read()
                            image_base64_list.append(_b64.b64encode(data).decode("ascii"))
        except Exception as e:
            import traceback; traceback.print_exc()

        has_error = any(
            d.get("description", "").startswith("[Error:")
            or d.get("description", "").startswith("[Image: unable")
            for d in descriptions
        )
        if has_error:
            error_msg = descriptions[0].get("description", "Vision model error")
            bubble = VisionDescriptionBubble.create_error_bubble(error_msg)
        else:
            bubble = VisionDescriptionBubble.create_from_notification(
                descriptions, image_base64_list,
            )
        self.agent_panel.timeline_view.add_widget(bubble)

    def _add_vision_bubble_for_describe(
        self, text: str, image_path: str, model_label: str, elapsed_ms: int
    ):
        """Render a VisionDescriptionBubble for an agent-initiated describe_image call.

        Same pipeline as user-uploaded image descriptions — reads the image file
        for the 'view original' thumbnail, uses the vision model metadata, and
        shows a recognizable header.
        """
        # Determine if this describes a screenshot we just captured
        is_screenshot = bool(image_path and self._last_capture_path
            and os.path.normpath(image_path) == os.path.normpath(self._last_capture_path))

        # Build description dict matching VisionDescriptionBubble format
        elapsed_str = f"{elapsed_ms / 1000:.1f}s" if elapsed_ms > 0 else ""
        model_str = model_label or "vision"

        header_icon = "📸 截图识别完成" if is_screenshot else "👁️ 图片识别完成"
        header_parts = [header_icon, f"· {model_str}"]
        if elapsed_str:
            header_parts.append(f"· {elapsed_str}")

        desc = [{
            "mimeType": "image/png",
            "description": text,
            "model": model_str,
            "elapsedMs": elapsed_ms,
        }]

        # Read image file for view-original thumbnail
        image_base64_list: list[str] = []
        if image_path and os.path.isfile(image_path):
            try:
                import base64 as _b64
                with open(image_path, "rb") as f:
                    image_base64_list.append(_b64.b64encode(f.read()).decode("ascii"))
            except Exception:
                pass

        # Cache screenshot if it's a capture
        if is_screenshot and image_base64_list:
            self._cache_screenshot(image_path, image_base64_list[0])

        bubble = VisionDescriptionBubble.create_from_notification(desc, image_base64_list)
        # Override header for screenshot context
        if is_screenshot:
            bubble._header_label.setText(" ".join(header_parts))
        self.agent_panel.timeline_view.add_widget(bubble)

    def _cache_screenshot(self, image_path: str, base64_data: str):
        """Cache an agent-captured screenshot into edini_images/ for persistence."""
        session_path = self._current_session_path or self._browsing_session_path
        if not session_path:
            return
        try:
            import base64 as _b64
            from edini.image_cache import get_image_cache_dir, save_images
            img_dir = str(get_image_cache_dir(session_path))
            os.makedirs(img_dir, exist_ok=True)
            # Write image file
            img_data = _b64.b64decode(base64_data)
            fname = os.path.basename(image_path) or "screenshot_capture.png"
            dest = os.path.join(img_dir, fname)
            with open(dest, "wb") as f:
                f.write(img_data)
            # Save via existing save_images pipeline
            save_images(session_path, [{
                "data": base64_data,
                "mimeType": "image/png",
                "filename": fname,
                "source": "agent_capture",
            }])
        except Exception:
            pass

    def _on_vision_description(self, payload: dict):
        """Handle vision_description notification from pi-visionizer."""
        # Skip describe_image sourced notifications — already rendered via tool result
        if payload.get("source") == "describe_image":
            return

        descriptions = payload.get("descriptions", [])
        # Save all image data before cleanup
        all_image_data: list[str] = []
        if self._pending_images:
            all_image_data = [
                img.get("data", "") for img in self._pending_images
                if img.get("data")
            ]

        # Persist descriptions to cache for history loading
        if descriptions:
            if self._current_session_path:
                try:
                    from edini.image_cache import save_descriptions
                    ok = save_descriptions(self._current_session_path, descriptions)
                except Exception as e:
                    pass
            else:
                self._pending_descriptions = descriptions

        # Remove "recognizing" placeholder if still present
        self._cleanup_recognizing()

        if not descriptions:
            return
        has_error = any(
            d.get("description", "").startswith("[Error:")
            or d.get("description", "").startswith("[Image: unable")
            for d in descriptions
        )
        if has_error:
            error_msg = descriptions[0].get("description", "Vision model error")
            bubble = VisionDescriptionBubble.create_error_bubble(error_msg)
        else:
            bubble = VisionDescriptionBubble.create_from_notification(
                descriptions, all_image_data,
            )

        self.agent_panel.timeline_view.add_widget(bubble)

    def _on_round_tick(self):
        """Update the round elapsed time display in Pi Status."""
        if self._round_elapsed.isValid():
            elapsed = self._round_elapsed.elapsed() / 1000.0
            self.context_panel.set_round_time(elapsed)

    # ── Knowledge Reflection (background) ──

    def _trigger_reflection(self):
        """Start background knowledge reflection after conversation ends."""
        settings = get_settings()
        if not settings.get("knowledge_enabled", True):
            print("[Edini] Reflection skipped: knowledge_enabled=False", flush=True)
            return
        if not self._current_session_path:
            print("[Edini] Reflection skipped: no session path", flush=True)
            return

        try:
            from edini.config import read_pi_auth, read_pi_settings, read_pi_models
            pi_settings = read_pi_settings()
            pi_auth = read_pi_auth()

            provider = (settings.get("reflection_provider")
                       or pi_settings.get("defaultProvider", "deepseek"))
            model = (settings.get("reflection_model")
                    or pi_settings.get("defaultModel", "deepseek-chat"))

            provider_auth = pi_auth.get(provider, {})
            if isinstance(provider_auth, dict):
                api_key = provider_auth.get("key", "")
            elif isinstance(provider_auth, str):
                api_key = provider_auth
            else:
                api_key = ""

            base_url = None
            models_conf = read_pi_models()
            prov_conf = models_conf.get("providers", {}).get(provider, {})
            if isinstance(prov_conf, dict) and "baseUrl" in prov_conf:
                base_url = prov_conf["baseUrl"]

            if not api_key:
                print(f"[Edini] Reflection skipped: no API key for provider '{provider}'", flush=True)
                return

            print(f"[Edini] Starting reflection with {provider}/{model} on {self._current_session_path}", flush=True)

        except Exception as e:
            print(f"[Edini] Reflection skipped: config error - {e}", flush=True)
            return

        self.context_panel.knowledge_zone.show_reflection_status(
            "🔄 Reflecting...")

        self._reflect_worker = ReflectWorker(
            session_path=self._current_session_path,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
        self._reflect_worker.reflection_done.connect(
            self._on_reflection_done)
        self._reflect_worker.reflection_failed.connect(
            self._on_reflection_failed)
        self._reflect_worker.reflection_status.connect(
            self.context_panel.knowledge_zone.show_reflection_status)
        self._reflect_worker.start()

    def _on_reflection_done(self, items: list):
        """Handle reflection results."""
        if items:
            self.context_panel.knowledge_zone.show_reflection_results(items)
            self.context_panel.knowledge_zone.items_accepted.connect(
                self._on_knowledge_items_accepted, QtCore.Qt.UniqueConnection)
        else:
            self.context_panel.knowledge_zone._reflect_area.setVisible(False)
        self.status.showMessage("Ready")

    def _on_reflection_failed(self, error: str):
        """Handle reflection failure silently."""
        self.context_panel.knowledge_zone.show_reflection_status(
            f"⚠️ Reflection failed: {error[:50]}")
        QtCore.QTimer.singleShot(
            3000,
            lambda: self.context_panel.knowledge_zone._reflect_area.setVisible(False))
        self.status.showMessage("Ready")

    def _on_knowledge_items_accepted(self, items: list):
        """Save accepted knowledge items."""
        from edini.ui.knowledge_store import (
            add_rule, add_entry, merge_entry,
        )
        for item in items:
            action = item.get("_action", "new")
            if action == "merge":
                target = item.get("_merge_target", {})
                target_id = target.get("id", "")
                if target_id:
                    merge_entry(
                        target_id,
                        item.get("title", ""),
                        item.get("content", ""),
                        item.get("tags"),
                    )
            else:
                if item.get("type") == "rule":
                    add_rule(
                        item.get("category", "避坑"),
                        item.get("title", ""),
                        item.get("content", ""))
                else:
                    add_entry(
                        item.get("category", "技巧"),
                        item.get("title", ""),
                        item.get("content", ""),
                        tags=item.get("tags", []),
                        source_session=self._current_session_path)
        self.context_panel.knowledge_zone.refresh()

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

    def _on_busy_changed(self, busy: bool):

        pass

    def _on_status_changed(self, status: str):
        self._last_pi_status = status
        self.context_panel.set_pi_status(status)
        self._update_statusbar()
        # On first connect: discover models, sync model from pi config, request stats
        if status == "connected":
            self._rpc_client.send_get_available_models()
            # Set model from pi's own settings (auth.json + models.json + settings.json)
            pi_sett = read_pi_settings()
            provider = pi_sett.get("defaultProvider", "")
            model_id = pi_sett.get("defaultModel", "")
            if provider and model_id:
                self._rpc_client.send_set_model(provider, model_id)
            if hou:
                try:
                    hip = hou.hipFile.name()
                    if hip:
                        name = os.path.splitext(os.path.basename(hip))[0]
                        self._rpc_client.send_set_session_name(name)
                except Exception:
                    pass
            self._rpc_client.send_get_stats()

    def _on_models_received(self, models: list):
        """Handle available models from Pi RPC. Stores them and refreshes display."""
        self._available_models = models
        self._update_statusbar()

    def _on_model_changed(self, model: dict):
        """Handle model change confirmation from Pi RPC."""
        name = model.get("name", model.get("id", "?"))
        provider = model.get("provider", "?")
        self.context_panel.set_provider_model(provider, name)
        self._update_statusbar()

    def _on_pi_session_switched(self, session_path: str):
        """Called when pi confirms a session switch (new or resumed)."""
        self._current_session_path = session_path
        screenshots.set_current_session(session_path)

        # Flush any pending image cache writes
        self._flush_pending_image_cache()

        # Also flush pending descriptions
        self._flush_pending_descriptions(session_path)

        # Clear pending data after cache has been written
        self._pending_images = None
        self._pending_cache_meta = None
        self._pending_descriptions = None

        self._rpc_client.send_get_stats()
        # Update list highlight to match active session
        highlight = self._browsing_session_path or session_path
        self.history_panel.highlight_session(highlight)

    def _on_pi_messages_received(self, messages: list):
        """Render messages from pi in the agent panel."""
        # This is a fallback; normally we load from local file synchronously
        messages = self._merge_consecutive_assistants(messages)
        messages = messages
        self.agent_panel.clear_timeline()
        for m in messages:
            self._render_history_message(m)

    def _merge_consecutive_assistants(self, messages: list) -> list:
        """Merge consecutive assistant messages into single entries.

        Pi stores each assistant content block as a separate JSONL entry
        when tool calls split the response. For display, consecutive
        assistant messages (no user between them) should render as one bubble.
        """
        merged = []
        i = 0
        while i < len(messages):
            m = messages[i]
            role = m.get("role", "")
            if role != "assistant":
                merged.append(m)
                i += 1
                continue

            # Collect consecutive assistant messages
            texts = []
            thinkings = []

            content = m.get("content", "")
            if content:
                texts.append(content)
            for t in m.get("thinking", []):
                if t.strip():
                    thinkings.append(t.strip())

            j = i + 1
            while j < len(messages) and messages[j].get("role") == "assistant":
                nm = messages[j]
                nc = nm.get("content", "")
                if nc:
                    texts.append(nc)
                for t in nm.get("thinking", []):
                    if t.strip():
                        thinkings.append(t.strip())
                j += 1

            merged_entry: dict = {
                "role": "assistant",
                "content": "\n\n".join(texts),
                "thinking": thinkings,
            }
            # Preserve a failed turn's error reason/message so the UI can show
            # why the assistant produced no output (e.g. insufficient quota,
            # bad request params). A single error entry is enough to flag the
            # merged turn; we surface the first one found.
            for src in messages[i:j]:
                if src.get("stopReason") == "error":
                    merged_entry["stopReason"] = "error"
                    if src.get("errorMessage"):
                        merged_entry["errorMessage"] = src["errorMessage"]
                    break
            merged.append(merged_entry)
            i = j
        return merged

    def _reset_change_tree(self):
        """Clear change tree and undo stack (on session switch)."""
        self.agent_panel.change_tree_widget.clear_all()
        self._undo_stack.clear()
        self._undo_pointer = -1
        self._round_counter = 0

    def _render_history_message(self, m: dict) -> None:
        """Render a single message dict (user/assistant/vision) into the panel.

        Shared by all history-loading paths (RPC messages, session select,
        back-to-current) so error handling stays consistent: a failed model
        turn (stopReason="error") is surfaced instead of silently producing
        an empty bubble.
        """
        _type = m.get("_type", m.get("role", ""))
        content = m.get("content", "")
        if _type == "user":
            self.agent_panel._append_user_message(content, m.get("images"))
        elif _type == "vision_description":
            self._render_vision_description(m)
        elif _type == "assistant":
            thinking = m.get("thinking", [])
            for t in thinking:
                self.agent_panel._append_thinking_text(t)
            if content:
                self.agent_panel._append_assistant_message(content)
            if m.get("stopReason") == "error" and m.get("errorMessage"):
                self.agent_panel.add_error(m["errorMessage"])

    def _refresh_current_stats(self, delay_ms: int = 300):
        """Request stats from Pi after a delay (to let session switch settle)."""
        QtCore.QTimer.singleShot(delay_ms, self._rpc_client.send_get_stats)

    def _on_new_session(self):
        # Save current session as active before creating new one (only if not already browsing)
        if not self._browsing_session_path:
            self._active_session_path = self._current_session_path
        self._browsing_session_path = ""
        self.history_panel.set_browsing_mode(False)

        self._current_session_path = ""
        self.agent_panel.clear_timeline()
        self._reset_change_tree()
        self.context_panel.reset_stats()
        self._rpc_client.send_new_session()
        self._refresh_current_stats(800)  # wait for new session to be created
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
        self._reset_change_tree()
        self.context_panel.reset_stats()

        # Load messages directly from local JSONL for instant rendering
        messages = load_pi_messages_with_images(session_path)
        messages = self._merge_consecutive_assistants(messages)
        messages = messages
        for m in messages:
            self._render_history_message(m)

        # Tell pi to switch session (async, updates stats)
        self._rpc_client.send_switch_session(session_path)
        self._refresh_current_stats(500)  # fallback if session_switched callback fails

    def _on_back_to_current(self):
        """Exit browsing mode and restore the previously active session."""
        target = self._active_session_path
        self._browsing_session_path = ""
        self.history_panel.set_browsing_mode(False)

        if target:
            self._current_session_path = target
            self.agent_panel.clear_timeline()
            self._reset_change_tree()
            self.context_panel.reset_stats()

            messages = load_pi_messages_with_images(target)
            messages = self._merge_consecutive_assistants(messages)
            messages = messages
            for m in messages:
                self._render_history_message(m)

            self._rpc_client.send_switch_session(target)
            self._refresh_current_stats(500)  # fallback if session_switched callback fails
            self.history_panel.highlight_session(target)
        else:
            self._on_new_session()

    def _on_session_deleted(self, session_path: str):
        self.history_panel.remove_session(session_path)

        # Prune orphaned image cache for this session
        from edini.image_cache import prune_orphan_caches
        from edini.ui.pi_sessions import get_pi_session_dir
        try:
            cwd = _get_working_dir()
            prune_orphan_caches(str(get_pi_session_dir(cwd)))
        except Exception:
            pass

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

    def _on_deferred_eval_and_reflect(self, session_path: str):
        """Called when session_switched fires after agent_end (deferred eval + reflection)."""
        self._rpc_client.session_switched.disconnect(self._on_deferred_eval_and_reflect)
        self.agent_panel._current_session_path = session_path
        self.agent_panel.finish_streaming()
        self._trigger_reflection()

    def _show_eval_dashboard(self):
        """Open evaluation dashboard as a modeless dialog."""
        if hasattr(self, '_eval_dialog') and self._eval_dialog is not None:
            self._eval_dialog.raise_()
            self._eval_dialog.activateWindow()
            # Refresh data when dialog is brought to front
            for child in self._eval_dialog.findChildren(EvalTab):
                child.refresh()
            return

        from PySide6 import QtWidgets
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Agent Evaluation Dashboard")
        dialog.resize(960, 640)
        dialog.setMinimumSize(800, 500)
        dialog.setStyleSheet(
            "QDialog { background:#0d0d1a; }"
        )
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        eval_store = EvalStore()
        eval_tab = EvalTab(eval_store, parent=dialog)
        eval_tab.navigate_to_session.connect(self._on_eval_navigate)
        layout.addWidget(eval_tab)
        eval_tab.refresh()

        self._eval_dialog = dialog
        dialog.finished.connect(lambda: setattr(self, '_eval_dialog', None))
        dialog.show()

    def _on_eval_navigate(self, session_id: str):
        """Navigate to a session from evaluation dashboard."""
        from edini.ui.pi_sessions import list_pi_sessions
        sessions = list_pi_sessions(self._cwd)
        for s in sessions:
            if s["session_id"] == session_id:
                target_path = s["path"]
                self._on_session_selected(target_path)
                break

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
        # Show model info from pi config (not old edini settings)
        pi_sett = read_pi_settings()
        provider = pi_sett.get("defaultProvider", "?")
        model = pi_sett.get("defaultModel", "?")
        parts.append(f"{provider}/{model}")
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
        # NOTE: ToolExecutor is a process-level singleton shared by all RPC
        # consumers (main window + Project HDA panels + future ones). Do NOT
        # stop it here — closing one window must not kill the HTTP server
        # other panels' Pi subprocesses are still calling. It is reaped on
        # Houdini process exit (daemon thread).
        super().closeEvent(event)
        # Release the global singleton so reopen creates a fresh window
        if global_main is self:
            import edini.ui.windows as win_mod
            win_mod._main_window = None


# ═══════════════════════════════════════════════════════════════════════
# Timeline placeholder widgets
# ═══════════════════════════════════════════════════════════════════════

class _RecognizingPlaceholder(QtWidgets.QFrame):
    """Placeholder shown while vision model is processing images."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            _RecognizingPlaceholder {
                background: rgba(167,139,250,0.04);
                border: 1px dashed rgba(167,139,250,0.2);
                border-radius: 6px;
                margin: 2px 32px;
            }
        """)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        spinner = QtWidgets.QLabel("🔍")
        spinner.setStyleSheet("QLabel { color: #a78bfa; font-size: 14px; border: none; }")
        layout.addWidget(spinner)

        label = QtWidgets.QLabel("正在识别图片…")
        label.setStyleSheet("QLabel { color: #a78bfa; font-size: 11px; border: none; }")
        layout.addWidget(label)
        layout.addStretch()
