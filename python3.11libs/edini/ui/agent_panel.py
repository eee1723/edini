"""AgentPanel — Chat timeline (QScrollArea + widgets) + collapsible panels."""
import html
import os
import re
import sys
from PySide6 import QtCore, QtGui, QtWidgets
from edini.ui.theme import accent_color, fs
from edini.media_manager import (
    MediaItem, capture_viewport,
    from_files, from_clipboard,
    MAX_ATTACHMENTS, clipboard_has_image,
)
from edini.ui.vision_overlay import VisionDescriptionBubble
from edini.ui.components.input_bar import InputBar
from edini.ui.components.timeline_view import _TimelineView
from edini.ui.components.bubbles import (
    UserBubble, AiBubble,
    _UserBubble, _AiBubble,            # backward-compat aliases
    _user_bubble_bg, _ai_bubble_bg,
    _user_bubble_style, _ai_bubble_style,
    _ClickableCard, _load_thumb_pixmap, _truncate_name, _open_image_file,
)
from edini.ui.components.thinking_panel import ThinkingPanel
from edini.ui.components.tool_panel import ToolPanel, _ToolCardWidget
from edini import screenshots


# ═══════════════════════════════════════════════════════════════════════
# Style helpers (unchanged)
# ═══════════════════════════════════════════════════════════════════════

def _thinking_collapsed_style() -> str:
    a = accent_color()
    return (
        f'color:#a1a1aa;font-size:{fs(10)};cursor:pointer;'
        f'background:rgba(0,188,212,0.06);padding:4px 8px;'
        f'border-radius:4px;margin:4px 32px 4px 0;display:block;'
        f'border-left:2px solid {a};'
    )

def _thinking_expanded_style() -> str:
    a = accent_color()
    return (
        f'color:#71717a;font-size:{fs(10)};display:block;'
        f'background:#0e0e15;padding:4px 8px;'
        f'border-left:2px solid {a};margin:4px 32px 4px 8px;'
    )

def _separator_style() -> str:
    return (
        f'text-align:center;color:#52525b;font-size:{fs(10)};'
        f'margin:10px 0;border-top:1px solid #2a2a3c;padding-top:6px;'
    )


# ═══════════════════════════════════════════════════════════════════════
# Tool Card Widget — relocated to edini/ui/components/tool_panel.py.
# Re-imported above as _ToolCardWidget. Stage 2, Task 1.4.
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# Timeline — QScrollArea + widget-based
# ═══════════════════════════════════════════════════════════════════════

# _ClickableCard, _UserBubble, _AiBubble relocated to edini/ui/components/bubbles.py
# (re-imported above). Local stubs removed in Stage 1, Task 1.3.


class _Separator(QtWidgets.QFrame):
    """Centered separator line between message rounds."""
    def __init__(self, text: str = "──", parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(0)
        layout.addStretch(1)
        label = QtWidgets.QLabel(text)
        label.setStyleSheet(
            f"QLabel {{ color:#52525b; font-size:{fs(10)}; "
            f"background:transparent; border:none; }}"
        )
        layout.addWidget(label)
        layout.addStretch(1)
        self.setStyleSheet(
            f"QFrame {{ background: transparent; border: none; "
            f"border-top: 1px solid #2a2a3c; }}"
        )


class _ErrorBanner(QtWidgets.QFrame):
    """Error message banner."""
    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(0)
        layout.addStretch(1)
        label = QtWidgets.QLabel(f"⚠️ {html.escape(message)}")
        label.setWordWrap(True)
        label.setStyleSheet(
            f"QLabel {{ color:#f87171; font-size:{fs(11)}; "
            f"background:transparent; border:none; }}"
        )
        layout.addWidget(label)
        layout.addStretch(1)
        self.setStyleSheet(
            "QFrame { background: rgba(239,68,68,0.08); "
            "border-left: 3px solid #ef4444; border-radius: 4px; "
            "margin: 4px 16px; }"
        )


# ═══════════════════════════════════════════════════════════════════════
# Type Toggle Badge (unchanged)
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# AgentPanel
# ═══════════════════════════════════════════════════════════════════════

class AgentPanel(QtWidgets.QWidget):
    submit_requested = QtCore.Signal(str, object)   # text, images
    stop_requested = QtCore.Signal()
    abort_requested = QtCore.Signal()
    sig_eval_completed = QtCore.Signal(str, float)  # session_id, total_score

    STREAM_FLUSH_CHARS = 80
    STREAM_FLUSH_INTERVAL_MS = 80

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._stream_segments: list[dict] = []     # [{type: text|thinking, content: str}]
        self._current_text = ""                     # current paragraph (may be cleared by think flush)
        self._streaming_full_text = ""              # NEVER cleared — full accumulated stream text
        self._streaming = False
        self._request_count = 0
        self._session_id = ""

        # Streaming bubble — the AiBubble widget being built live
        self._streaming_bubble: _AiBubble | None = None

        # Thinking
        self._thinking_count = 0
        self._thinking_buf = ""
        self._thinking_buf_timer = QtCore.QTimer(self)
        self._thinking_buf_timer.setSingleShot(True)
        self._thinking_buf_timer.setInterval(600)
        self._thinking_buf_timer.timeout.connect(self._flush_thinking_buf)

        # Tool cards now owned by self._tool_panel (built in _build_ui).

        self._stream_flush_timer = QtCore.QTimer(self)
        self._stream_flush_timer.setSingleShot(True)
        self._stream_flush_timer.setInterval(self.STREAM_FLUSH_INTERVAL_MS)
        self._stream_flush_timer.timeout.connect(self._flush_stream)

        self._build_ui()
        self._bind_events()

    # ------------------------------------------------------------------
    # UI Build
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        # ── Timeline (QScrollArea + widgets) ──
        self.timeline_view = _TimelineView()
        root.addWidget(self.timeline_view, 1)

        # ── Thinking Panel (collapsible, below timeline) ──
        # Promoted to edini/ui/components/thinking_panel.py (Stage 2, Task 1.4).
        self._thinking_panel = ThinkingPanel()
        root.addWidget(self._thinking_panel)

        # ── Tool Call Panel (collapsible, below timeline) ──
        # Promoted to edini/ui/components/tool_panel.py (Stage 2, Task 1.4).
        self._tool_panel = ToolPanel()
        root.addWidget(self._tool_panel)

        # ── Change Tree Panel (collapsible) ──
        from edini.ui.change_tree_widget import ChangeTreeWidget
        self.change_tree_widget = ChangeTreeWidget()
        root.addWidget(self.change_tree_widget)

        # ── Input bar (text + attachment bar + toolbar + send button) ──
        # Extracted to edini.ui.components.input_bar (Stage 2, Task 1.5).
        # Multimodal actions (screenshot / upload / drag-drop) are forwarded
        # back here via request signals — InputBar has no hou/media_manager dep.
        self._input_bar = InputBar(show_attachment_bar=True)
        self._attachment_bar = self._input_bar.attachment_bar()
        self.input_edit = self._input_bar.input_edit
        root.addWidget(self._input_bar)

    def _bind_events(self):
        # Wire InputBar request signals to the real handlers (which need
        # media_manager / hou, so they live here, not in InputBar).
        self._input_bar.submit_requested.connect(self._on_input_submit)
        self._input_bar.abort_requested.connect(self._on_input_abort)
        self._input_bar.screenshot_requested.connect(self._on_capture_viewport)
        self._input_bar.files_requested.connect(self._on_pick_files)
        self._input_bar.images_dropped.connect(self._handle_dropped_images)

        # AgentPanel's eventFilter still owns the ContextMenu (paste image),
        # Escape (abort) and Ctrl+V (paste image) shortcuts — these need
        # media_manager. InputBar's own filter (installed first inside its
        # _build_ui) owns Enter-to-send + drag-drop and passes the rest through.
        self.input_edit.installEventFilter(self)

        # Right-click context menu on the input_edit — monkey-patched because
        # Houdini's Qt may block ContextMenu events from the event filter.
        self.input_edit.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)
        self.input_edit.contextMenuEvent = self._on_context_menu

    def eventFilter(self, watched, event):
        if watched is self.input_edit and event is not None:
            ev_type = int(event.type())

            # ── Right-click context menu: intercept paste when image on clipboard ──
            if ev_type == int(QtCore.QEvent.ContextMenu):
                has_img = clipboard_has_image()
                if has_img:
                    menu = QtWidgets.QMenu(self.input_edit)
                    paste_img = menu.addAction("📋 粘贴图片到附件栏")
                    paste_img.triggered.connect(self._paste_image_from_clipboard)
                    menu.addSeparator()
                    paste_text = menu.addAction("粘贴文本")
                    paste_text.triggered.connect(self._context_paste_text)
                    menu.addSeparator()
                    select_all = menu.addAction("全选")
                    select_all.triggered.connect(self.input_edit.selectAll)
                    self._context_menu = menu
                    result = menu.exec(event.globalPos())
                    self._context_menu = None
                    return True
                # No image on clipboard — let default context menu handle text paste
                return False

            if ev_type == int(QtCore.QEvent.KeyPress):
                key = int(event.key())
                modifiers = event.modifiers()
                if key == int(QtCore.Qt.Key_Escape):
                    if self._busy:
                        self._on_input_abort()
                    return True
                # NOTE: Enter/Return-to-send + Shift/Ctrl-Enter newline are
                # handled by InputBar.eventFilter (installed first); it consumes
                # them and we never see them here. Ctrl+V (paste image) below
                # still lives here because it needs media_manager.from_clipboard.
                if key == int(QtCore.Qt.Key_V):
                    if modifiers & QtCore.Qt.ControlModifier:
                        has_img = clipboard_has_image()
                        if has_img:
                            if self._attachment_bar.is_full():
                                self.add_error(f"最多 {MAX_ATTACHMENTS} 张图片")
                            else:
                                item = from_clipboard()
                                if item is not None:
                                    ok = self._attachment_bar.add(item)
                                else:
                                    pass
                            return True
                        else:
                            pass
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------------
    # InputBar signal handlers
    # ------------------------------------------------------------------

    def _on_input_abort(self):
        """Abort button / Escape: forward to main_window."""
        self.abort_requested.emit()

    def _on_input_submit(self, text: str, images):
        """InputBar emitted submit_requested(text, images). Re-emit on the
        AgentPanel signal and reset the per-turn UI state (what _on_send did).
        """
        if not text or self._busy:
            return
        self._request_count += 1
        self._stream_segments.clear()
        self._current_text = ""
        self._streaming_full_text = ""
        self._streaming = True
        self._thinking_count = 0

        # Reset panels to collapsed state
        self._tool_panel.clear()
        self._thinking_panel.reset()

        # Collapse change tree during conversation
        self.change_tree_widget.collapse()

        self.submit_requested.emit(text, images if images else None)

    # ------------------------------------------------------------------
    # Tool Call Panel — delegates to ToolPanel (Stage 2, Task 1.4)
    # ------------------------------------------------------------------

    def _toggle_tool_panel(self, event=None):
        self._tool_panel.toggle()

    def _collapse_tool_panel(self):
        """Collapse tool panel if currently expanded."""
        self._tool_panel.collapse()

    def _add_tool_card_ui(self, tool_name: str, args: dict, tool_call_id: str):
        # NOTE: ToolPanel.add_card signature is (tool_name, tool_call_id, args).
        self._tool_panel.add_card(tool_name, tool_call_id, args)

    def _update_tool_card_result(self, tool_call_id: str, result_text: str, success: bool = True):
        self._tool_panel.update_result(tool_call_id, result_text, success)

    def _clear_tool_cards(self):
        self._tool_panel.clear()

    # ------------------------------------------------------------------
    # Viewport screenshot
    # ------------------------------------------------------------------

    def _on_capture_viewport(self):
        item = capture_viewport()
        if item is None:
            self._input_bar._screenshot_btn.setText("❌ 失败")
            QtCore.QTimer.singleShot(2500, lambda: self._input_bar._screenshot_btn.setText("📷 截图"))
            self.add_error("截图失败 — 请查看 Houdini Console 获取详情")
            return
        if self._attachment_bar.is_full():
            self.add_error(f"最多 {MAX_ATTACHMENTS} 张图片，请先移除一些")
            return
        self._save_viewshot_to_disk(item)
        ok = self._attachment_bar.add(item)
        if ok:
            self._input_bar._screenshot_btn.setText("📸 ✓")
            QtCore.QTimer.singleShot(1500, lambda: self._input_bar._screenshot_btn.setText("📷 截图"))

    def _save_viewshot_to_disk(self, item: MediaItem):
        """Also persist viewport screenshots under $HIP/Edini_screenshots/<task>/."""
        import base64 as _b64
        session_path = getattr(self, "_current_session_path", "") or screenshots.current_session()
        if not session_path or not item.base64:
            return
        ext = ".jpg" if "jpeg" in item.mime_type or "jpg" in item.mime_type else ".png"
        try:
            target = screenshots.next_filename(session_path, "viewport", ext)
            raw = _b64.b64decode(item.base64)
            target.write_bytes(raw)
        except Exception:
            pass

    def _on_pick_files(self):
        """Open file dialog to select image files."""
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp);;All Files (*)",
        )
        if not paths:
            return
        items = from_files(paths)
        added = 0
        for item in items:
            if self._attachment_bar.is_full():
                break
            if self._attachment_bar.add(item):
                added += 1
        if added == 0 and self._attachment_bar.is_full():
            self.add_error(f"最多 {MAX_ATTACHMENTS} 张图片")

    def _paste_image_from_clipboard(self):
        """Paste image from clipboard (called from right-click context menu)."""
        if self._attachment_bar.is_full():
            self.add_error(f"最多 {MAX_ATTACHMENTS} 张图片")
            return
        item = from_clipboard()
        if item is not None:
            ok = self._attachment_bar.add(item)
        else:

            pass
    def _context_paste_text(self):
        """Paste text into input_edit (called from right-click context menu).

        Uses QTimer.singleShot to defer the paste until the context menu
        is fully dismissed and focus is restored to the input_edit.
        """
        QtCore.QTimer.singleShot(0, self._do_context_paste_text)

    def _do_context_paste_text(self):
        self.input_edit.setFocus(QtCore.Qt.OtherFocusReason)
        self.input_edit.paste()

    def _handle_dropped_images(self, urls):
        """InputBar forwarded a drop of local-file image urls. Resolve them
        to MediaItems via media_manager.from_files and add to the attachment bar.
        """
        paths = []
        from PySide6 import QtCore as _qc
        for url in urls or []:
            path = url.toLocalFile() if hasattr(url, "toLocalFile") else str(url)
            if path:
                paths.append(path)
        if not paths:
            return
        items = from_files(paths)
        for item in items:
            if self._attachment_bar.is_full():
                break
            self._attachment_bar.add(item)

    def _on_context_menu(self, event):
        """Right-click context menu handler — monkey-patched onto input_edit."""
        has_img = clipboard_has_image()
        if has_img:
            menu = QtWidgets.QMenu(self.input_edit)
            paste_img = menu.addAction("📋 粘贴图片到附件栏")
            paste_img.triggered.connect(self._paste_image_from_clipboard)
            menu.addSeparator()
            paste_text = menu.addAction("粘贴文本")
            paste_text.triggered.connect(self._context_paste_text)
            menu.addSeparator()
            select_all = menu.addAction("全选")
            select_all.triggered.connect(self.input_edit.selectAll)
            self._context_menu = menu
            result = menu.exec(event.globalPos())
            self._context_menu = None
        else:
            # Let QPlainTextEdit show its default context menu
            QtWidgets.QPlainTextEdit.contextMenuEvent(self.input_edit, event)

    def get_raw_stream_text(self) -> str:
        """Get the raw accumulated text of the current streaming response."""
        if self._streaming_bubble:
            return self._streaming_bubble.get_raw_text()
        parts = []
        for seg in self._stream_segments:
            if seg["type"] == "text":
                parts.append(seg["content"])
        if self._current_text:
            parts.append(self._current_text)
        return "\n".join(parts)

    def cancel_current_stream(self):
        """Cancel the current streaming response without rendering separator."""
        self._streaming = False
        self._stream_flush_timer.stop()
        if self._streaming_bubble:
            self.timeline_view.remove_last_widget()
            self._streaming_bubble = None
        self._stream_segments.clear()
        self._current_text = ""
        self._streaming_full_text = ""
        self._thinking_buf = ""
        self._clear_tool_cards()
        self._clear_thinking()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_busy(self, busy: bool):
        # Delegate to InputBar — the action button now lives there (T1.5).
        # InputBar.set_busy applies the full busy/idle styling verbatim.
        self._busy = busy
        self._input_bar.set_busy(busy)

    def set_session_id(self, sid: str):
        self._session_id = sid

    def set_request_count(self, count: int):
        self._request_count = count

    # ── Streaming ──

    def begin_assistant_message(self):
        """Prepare for a new assistant response."""
        self._stream_segments.clear()
        self._current_text = ""
        self._streaming_full_text = ""
        self._thinking_buf = ""
        self._streaming = True
        self._thinking_count = 0
        self._streaming_bubble = None  # Will be created on first chunk

    def append_stream_chunk(self, text: str):
        """Stream a chunk of text. Creates or updates the streaming bubble."""
        if self._thinking_buf.strip():
            self._flush_thinking_buf()
        self._current_text += text
        self._streaming_full_text += text

        # Create the streaming bubble on first content
        if self._streaming_bubble is None and self._streaming_full_text.strip():
            self._streaming_bubble = _AiBubble()
            self.timeline_view.add_widget(self._streaming_bubble)

        # Update bubble in-place with FULL accumulated text
        if self._streaming_bubble:
            self._streaming_bubble.update_streaming(self._streaming_full_text)

        # Update live thinking panel
        if self._thinking_buf:
            self._update_live_thinking()
            if not self._thinking_panel.is_expanded() and not self._thinking_panel.has_content():
                self._auto_expand_thinking()

        if len(self._current_text) >= self.STREAM_FLUSH_CHARS:
            self._flush_stream()
        elif not self._stream_flush_timer.isActive():
            self._stream_flush_timer.start()

    def _flush_stream(self):
        """No-op in widget mode — updates happen in append_stream_chunk."""
        pass

    def finish_streaming(self):
        """Finalize the streaming response."""
        self._streaming = False
        self._stream_flush_timer.stop()
        if self._thinking_buf.strip():
            self._flush_thinking_buf()

        # Finalize the bubble
        if self._streaming_bubble:
            self._streaming_bubble.finalize()
            self._streaming_bubble = None
        # Add round-end separator
        self.timeline_view.add_widget(_Separator("── 本轮结束 ──"))
        # Auto-collapse panels after completion
        self._collapse_tool_panel()
        self._collapse_thinking_panel()
        # Trigger background evaluation
        self._trigger_background_eval()

    # ── Tool cards ──

    def add_tool_card(self, tool_name: str, args: dict, tool_call_id: str = ""):
        self._add_tool_card_ui(tool_name, args, tool_call_id)

    def set_tool_result(self, tool_call_id: str, result: str):
        self._update_tool_card_result(tool_call_id, result, True)

    # ── Inline capture images and descriptions ──

    def add_inline_capture_image(self, filepath: str, width: int = 0, height: int = 0):
        """Show a captured viewport/network screenshot inline in the timeline."""
        resolved = os.path.abspath(filepath) if not os.path.isabs(filepath) else filepath
        if not os.path.exists(resolved):
            return
        widget = _CaptureImageWidget(resolved, width, height)
        self.timeline_view.add_widget(widget)

    def add_inline_description(self, text: str):
        """Show a vision model description bubble inline in the timeline."""
        if not text.strip():
            return
        bubble = _DescriptionBubble(text)
        self.timeline_view.add_widget(bubble)

    # ── Thinking ──

    def add_thinking_step(self, step_num: int, text: str):
        # Pi streams thinking_delta token-by-token (Chinese per-char, English
        # per sub-word), NOT word-by-word. So we must accumulate by plain
        # concatenation — inserting a separator between chunks corrupts the
        # text ("需"+"要"+"我" → "需 要 我"). Mirrors base_driver.
        # _on_thinking_chunk exactly.
        clean = _clean_thinking(text)
        if not clean:
            return
        self._thinking_count += 1
        self._thinking_buf += clean
        # On a paragraph break, finalize completed paragraphs into BOTH the
        # timeline segments AND the ThinkingPanel's own _thinking_full (via
        # append()). Without the panel.append() call, render_live() only shows
        # the in-progress tail — when the buffer flushes, the panel appears to
        # "wipe" the accumulated reasoning. append() pins each paragraph so it
        # stays visible.
        if '\n\n' in self._thinking_buf:
            parts = re.split(r'\n\n+', self._thinking_buf)
            for para in parts[:-1]:
                if para.strip():
                    self._stream_segments.append({"type": "thinking", "content": para.strip()})
                    self._thinking_panel.append(para.strip())
            self._thinking_buf = parts[-1]
        # Update thinking panel view in real-time as thinking arrives
        self._update_live_thinking()
        if not self._thinking_panel.is_expanded() and not self._thinking_panel.has_content():
            self._auto_expand_thinking()

    def _flush_thinking_buf(self):
        if not self._thinking_buf.strip():
            return
        if self._current_text.strip():
            self._stream_segments.append({"type": "text", "content": self._current_text})
            self._current_text = ""
        paragraphs = re.split(r'\n\n+', self._thinking_buf.strip())
        for para in paragraphs:
            if para.strip():
                self._append_thinking_text(para.strip())
        self._thinking_buf = ""
        self._update_live_thinking()

    # ── Messages ──

    def _append_user_message(self, text: str, images: list[dict] | None = None):
        """Append a user message bubble to the timeline."""
        self.timeline_view.add_widget(_UserBubble(text, images))

    def _append_assistant_message(self, text: str):
        """Append a non-streaming assistant message."""
        bubble = _AiBubble()
        bubble.set_stored_content(text)
        self.timeline_view.add_widget(bubble)
        self.timeline_view.add_widget(_Separator("──"))

    def _render_stored_assistant_message(self, msg: dict):
        """Render a stored assistant message (from loaded history)."""
        content = msg.get("content", "")
        thinking = msg.get("thinking", [])
        for t in thinking:
            if t.strip():
                self._append_thinking_text(t.strip())
        if content:
            bubble = _AiBubble()
            bubble.set_stored_content(content)
            self.timeline_view.add_widget(bubble)
        # A failed model turn is persisted with stopReason="error" and an
        # empty content array. Surface the errorMessage so the user can see
        # why a turn produced no output (e.g. insufficient quota, bad params)
        # instead of an empty timeline.
        if msg.get("stopReason") == "error" and msg.get("errorMessage"):
            self.add_error(msg["errorMessage"])
        self.timeline_view.add_widget(_Separator("──"))

    def add_error(self, message: str):
        """Show an error banner."""
        self.timeline_view.add_widget(_ErrorBanner(message))

    def show_aborted(self):
        """Show 'aborted' marker."""
        self._clear_tool_cards()
        self._clear_thinking()
        # Remove streaming bubble if present (remove_last_widget handles deleteLater)
        if self._streaming_bubble:
            self.timeline_view.remove_last_widget()
            self._streaming_bubble = None
        self.timeline_view.add_widget(_Separator("── 已中止 ──"))
        self._collapse_tool_panel()
        self._collapse_thinking_panel()
        self._trigger_background_eval()
        self.set_busy(False)

    def _trigger_background_eval(self):
        """Run evaluator in background thread after session ends."""
        session_path = getattr(self, '_current_session_path', None)
        _debug_log(str(session_path or ""), "trigger_eval", f"session_path={session_path!r}")
        if not session_path:
            _debug_log("", "trigger_eval", "no session path, returning")
            return
        import threading
        t = threading.Thread(
            target=self._run_evaluation,
            args=(session_path,),
            daemon=True,
        )
        t.start()

    def _run_evaluation(self, session_path: str):
        """Evaluate a single session in background thread."""
        import os
        _debug_log(session_path, "eval_start", f"path={session_path}")
        try:
            from edini.eval.log_parser import LogParser
            from edini.eval.evaluator import EvaluatorPipeline
            from edini.eval.store import EvalStore

            if not os.path.exists(session_path):
                _debug_log(session_path, "eval_fail", "session file not found")
                return

            session = LogParser.parse(session_path)
            if not session:
                _debug_log(session_path, "eval_fail", "LogParser returned None")
                return
            store = EvalStore()
            if store.has_evaluated(session.session_id):
                _debug_log(session_path, "eval_skip", f"already evaluated: {session.session_id[:20]}")
                return
            try:
                result = EvaluatorPipeline().evaluate(session)
            except Exception as inner_e:
                _debug_log(session_path, "eval_exception_detail",
                           f"EvaluatorPipeline.evaluate() failed: {inner_e}")
                import traceback
                _debug_log(session_path, "eval_traceback", traceback.format_exc())
                # Fallback: deterministic-only evaluation (skip LLM judge)
                _debug_log(session_path, "eval_retry", "retrying with force_no_judge=True")
                result = EvaluatorPipeline(force_judge=False).evaluate(session)
                # Patch the judge-based scores to None if they failed
                if result.tool_accuracy is None:
                    result.tool_accuracy = 0.5
                if result.task_completion is None:
                    result.task_completion = 0.5
            store.save_result(session.session_id, result)
            _debug_log(session_path, "eval_done",
                       f"saved {session.session_id[:20]} score={result.total_score:.3f}")
            self.sig_eval_completed.emit(session.session_id, result.total_score)
        except Exception as e:
            import traceback
            _debug_log(session_path, "eval_exception", str(e))
            _debug_log(session_path, "eval_traceback", traceback.format_exc())



    def clear_timeline(self):
        """Clear all messages from the timeline."""
        self.timeline_view.clear_all()
        self._clear_tool_cards()
        self._clear_thinking()
        self._streaming_bubble = None
        self._stream_segments.clear()
        self._current_text = ""
        self._streaming_full_text = ""

    # ------------------------------------------------------------------
    # Thinking Panel — delegates to ThinkingPanel (Stage 2, Task 1.4)
    # ------------------------------------------------------------------

    def _toggle_thinking_panel(self, event=None):
        self._thinking_panel.toggle()

    def _auto_expand_thinking(self):
        self._thinking_panel.auto_expand()

    def _collapse_thinking_panel(self):
        """Collapse thinking panel if currently expanded."""
        self._thinking_panel.collapse()

    def _append_thinking_text(self, text: str):
        # Called externally by main_window (history rendering) and internally.
        self._thinking_panel.append(text)

    def _update_live_thinking(self):
        if not self._thinking_buf:
            return
        self._thinking_panel.render_live(self._thinking_buf)

    def _clear_thinking(self):
        # Clear content but preserve expand state (matches original).
        self._thinking_panel.clear()


# ═══════════════════════════════════════════════════════════════════════
# Formatting helpers (unchanged)
# ═══════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════
# Image helpers
# ═══════════════════════════════════════════════════════════════════════

_SOURCE_ICON_MAP = {
    "viewport": "📸",
    "pick": "📁",
    "drag": "📁",
    "paste": "📋",
    "tool": "🔧",
}


def _source_icon(source: str) -> str:
    return _SOURCE_ICON_MAP.get(source, "🖼️")


# _truncate_name, _load_thumb_pixmap, _open_image_file relocated to
# edini/ui/components/bubbles.py (re-imported above). Stage 1, Task 1.3.


# ═══════════════════════════════════════════════════════════════════════
# Markdown rendering now lives in edini.ui.components.markdown.
# Re-exported here for backward compatibility during staged migration.
# ═══════════════════════════════════════════════════════════════════════

from edini.ui.components.markdown import (
    _format_lite, _format_full, _DarkRenderer,
)


def _clean_thinking(text: str) -> str:
    if re.match(r'^(\d+\.\s+\w+\s*)+$', text):
        return re.sub(r'\d+\.\s+', '', text).strip()
    return text


# _format_args + _format_tool_result_short moved to
# edini/ui/components/tool_panel.py (used only by _ToolCardWidget).
# Stage 2, Task 1.4.


def _expand_hex(h: str) -> str:
    if len(h) == 4:
        return f"#{h[1]}{h[1]}{h[2]}{h[2]}{h[3]}{h[3]}"
    if len(h) == 5:
        return f"#{h[1]}{h[1]}{h[2]}{h[2]}{h[3]}{h[3]}{h[4]}{h[4]}"
    return h


def _lighter(h: str, a: float) -> str:
    h = _expand_hex(h)
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"#{min(255,int(r+(255-r)*a)):02x}{min(255,int(g+(255-g)*a)):02x}{min(255,int(b+(255-b)*a)):02x}"


def _darker(h: str, a: float) -> str:
    h = _expand_hex(h)
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"#{max(0,int(r*(1-a))):02x}{max(0,int(g*(1-a))):02x}{max(0,int(b*(1-a))):02x}"


# ==========================================================================
# Inline Capture Image Widget
# ==========================================================================

def _debug_log(session_path: str, tag: str, msg: str):
    """Write debug log to temp file for diagnostics."""
    import os, datetime
    log_file = os.path.join(
        os.environ.get("TEMP", "/tmp"), "edini_eval_debug.log"
    )
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().isoformat()}] [{tag}] {msg}\n")
    except Exception:
        pass

class _CaptureImageWidget(QtWidgets.QFrame):
    """Shows a captured viewport/network screenshot inline in the timeline."""

    def __init__(self, filepath: str, width: int = 0, height: int = 0, parent=None):
        super().__init__(parent)
        self._filepath = filepath

        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setMaximumWidth(500)
        self.setStyleSheet("""
            _CaptureImageWidget {
                background-color: #1a1a24;
                border-radius: 8px;
                border: 1px solid #2a2a3c;
                margin: 4px 0;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Label
        filename = os.path.basename(filepath)
        label = QtWidgets.QLabel(f"📷 <b>Viewport Capture</b> <span style='color:#71717a;'>{filename}</span>")
        label.setStyleSheet("color: #a1a1aa; font-size: 11px; border: none; background: transparent;")
        layout.addWidget(label)

        # Image
        pixmap = QtGui.QPixmap(filepath)
        if pixmap.isNull():
            err_label = QtWidgets.QLabel("⚠️ Image not found")
            err_label.setStyleSheet("color: #ef4444; font-size: 11px; border: none;")
            layout.addWidget(err_label)
            return

        max_w = 480
        if pixmap.width() > max_w:
            pixmap = pixmap.scaledToWidth(max_w, QtCore.Qt.SmoothTransformation)

        img_label = QtWidgets.QLabel()
        img_label.setPixmap(pixmap)
        img_label.setAlignment(QtCore.Qt.AlignCenter)
        img_label.setStyleSheet("border: none; background: transparent;")
        img_label.setCursor(QtCore.Qt.PointingHandCursor)
        img_label.setToolTip("Click to open full-size image")
        img_label.mousePressEvent = lambda e: self._open_full()
        layout.addWidget(img_label)

        if width and height:
            info = QtWidgets.QLabel(f"<span style='color:#52525b;'>{width}×{height}</span>")
            info.setStyleSheet("color: #52525b; font-size: 10px; border: none;")
            layout.addWidget(info)

    def _open_full(self):
        """Open the image with the system default viewer."""
        import os as _os
        _os.startfile(self._filepath)


# ==========================================================================
# Description Bubble (for vision model responses)
# ==========================================================================

class _DescriptionBubble(QtWidgets.QFrame):
    """Shows a vision model description inline in the timeline."""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)

        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setMaximumWidth(500)
        self.setStyleSheet("""
            _DescriptionBubble {
                background-color: #1a2420;
                border-radius: 8px;
                border: 1px solid #2a3c30;
                margin: 4px 0;
            }
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)

        header = QtWidgets.QLabel("🔍 <b>Image Description</b>")
        header.setStyleSheet("color: #80c080; font-size: 11px; border: none; background: transparent;")
        layout.addWidget(header)

        # Clean up the description text
        description = text.strip()
        # Remove common prefixes like "The image shows" redundancy
        escaped = html.escape(description)
        body = QtWidgets.QLabel(escaped)
        body.setWordWrap(True)
        body.setStyleSheet("color: #a0c0a0; font-size: 12px; border: none; background: transparent;")
        layout.addWidget(body)

