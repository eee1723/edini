"""InputBar — message input + multimodal toolbar + send/abort button.

Extracted from AgentPanel._build_ui (Stage 2, Task 1.5). Encapsulates the
chat input row so it can be reused by the HDA window (Stage 4) with
``show_attachment_bar=False``.

Emits ``submit_requested(text, images)`` on send. Multimodal actions
(screenshot / upload / drag-drop) are forwarded via *request* signals so the
parent wires the real media_manager / hou logic — InputBar itself has NO
dependency on ``hou`` or ``edini.media_manager`` (keeps it reusable and
testable headless).

This module also owns ``_InputDialog`` (the IME / CJK popout), moved here from
``edini.project.panel.project_widget`` so both ProjectPanelWidget and
ProjectChatDialog import it from one place. project_widget re-exports it for
backward compatibility.
"""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from edini.ui.theme import accent_color, fs
from edini.ui.image_attachment import ImageAttachmentWidget


# ═══════════════════════════════════════════════════════════════════════
# Color helpers (copied verbatim from agent_panel so InputBar is self-contained)
# ═══════════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════════
# InputBar
# ═══════════════════════════════════════════════════════════════════════

class InputBar(QtWidgets.QWidget):
    """Chat input row: QPlainTextEdit + attachment bar + toolbar + send button.

    Signals:
        submit_requested(str, object)  — (text, images:list[dict] | None)
        stop_requested()               — alias of abort (kept for parity)
        abort_requested()              — user pressed the Abort button
        screenshot_requested()         — parent wires to media_manager capture
        files_requested()              — parent wires to a file picker
        images_dropped(list)           — parent wires to attachment-bar add
    """

    submit_requested = QtCore.Signal(str, object)   # text, images(list|None)
    stop_requested = QtCore.Signal()
    abort_requested = QtCore.Signal()
    screenshot_requested = QtCore.Signal()
    files_requested = QtCore.Signal()
    images_dropped = QtCore.Signal(list)            # list[MediaItem-like]

    def __init__(self, show_attachment_bar: bool = True, parent=None):
        super().__init__(parent)
        self._busy = False
        self._show_attachment_bar = show_attachment_bar
        self._attachment_bar: ImageAttachmentWidget | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # ── Attachment preview bar (optional) ──
        if self._show_attachment_bar:
            self._attachment_bar = ImageAttachmentWidget()
            root.addWidget(self._attachment_bar)

        # ── Input row ──
        input_row = QtWidgets.QHBoxLayout()
        input_row.setSpacing(8)
        self.input_edit = QtWidgets.QPlainTextEdit(self)
        self.input_edit.setPlaceholderText("描述你希望 Edini 完成的任务... (Enter 发送)")
        self.input_edit.setFixedHeight(68)
        input_row.addWidget(self.input_edit, 1)

        # ── Action column (right side) ──
        action_col = QtWidgets.QVBoxLayout()
        action_col.setSpacing(6)

        # ── Multimodal toolbar row ──
        a = accent_color()
        _mm_btn_style = f"""
            QPushButton {{
                background: #1a1a2e;
                color: #c0c0d0;
                border: 1px solid #2a2a40;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: {fs(12)};
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: #252540;
                border-color: {a}66;
                color: #e5e5eb;
            }}
            QPushButton:pressed {{
                background: #2a2a48;
                border-color: {a}99;
            }}
        """

        toolbar_row = QtWidgets.QHBoxLayout()
        toolbar_row.setSpacing(6)

        self._screenshot_btn = QtWidgets.QPushButton("📷 截图")
        self._screenshot_btn.setToolTip("截取 Houdini Scene Viewer 视窗画面")
        self._screenshot_btn.setMinimumHeight(34)
        self._screenshot_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._screenshot_btn.setStyleSheet(_mm_btn_style)
        self._screenshot_btn.clicked.connect(self.screenshot_requested.emit)
        toolbar_row.addWidget(self._screenshot_btn)

        self._file_pick_btn = QtWidgets.QPushButton("📁 上传")
        self._file_pick_btn.setToolTip("从磁盘选择图片 (png, jpg, gif, webp, bmp)")
        self._file_pick_btn.setMinimumHeight(34)
        self._file_pick_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._file_pick_btn.setStyleSheet(_mm_btn_style)
        self._file_pick_btn.clicked.connect(self.files_requested.emit)
        toolbar_row.addWidget(self._file_pick_btn)

        action_col.addLayout(toolbar_row)

        # ── Spacer between toolbar and action controls ──
        action_col.addSpacing(4)

        # ── Chat-only checkbox ──
        from edini.ui.styled_checkbox import StyledCheckBox
        self.chat_only_check = StyledCheckBox("仅对话", self)
        action_col.addWidget(self.chat_only_check, alignment=QtCore.Qt.AlignRight)

        # ── Execute / Abort button ──
        self._action_btn = QtWidgets.QPushButton("执行")
        self._action_btn.setObjectName("PrimaryButton")
        self._action_btn.setMinimumWidth(90)
        self._action_btn.setMinimumHeight(34)
        self._action_btn.clicked.connect(self._on_action_btn)
        action_col.addWidget(self._action_btn)
        action_col.addStretch(1)

        input_row.addLayout(action_col)
        root.addLayout(input_row)

        # Apply the idle (non-busy) styling to the action button.
        self._apply_action_style()

        # ── Event filter (Enter-to-send) + drag-drop on input_edit ──
        self.input_edit.installEventFilter(self)
        self.input_edit.setAcceptDrops(True)
        self.input_edit.dragEnterEvent = self._on_drag_enter
        self.input_edit.dragMoveEvent = self._on_drag_move
        self.input_edit.dropEvent = self._on_drop

    # ------------------------------------------------------------------
    # Button toggle
    # ------------------------------------------------------------------

    def _on_action_btn(self):
        if self._busy:
            self.abort_requested.emit()
            self.stop_requested.emit()
        else:
            self.submit()

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def submit(self):
        """Collect text (+ images) and emit submit_requested.

        No-op when the text is empty. Clears the input box and attachment bar.
        """
        text = self.text().strip()
        if not text:
            return

        # Collect images from the attachment bar (if shown).
        images: list[dict] | None = None
        if self._show_attachment_bar and self._attachment_bar is not None:
            images = []
            for item in self._attachment_bar.items():
                images.append({
                    "type": "image",
                    "data": item.base64,
                    "mimeType": item.mime_type,
                    "filename": item.filename,
                    "source": item.source.value,
                })
            self._attachment_bar.clear()

        self.input_edit.clear()
        self.submit_requested.emit(text, images if images else None)

    # ------------------------------------------------------------------
    # Busy state
    # ------------------------------------------------------------------

    def is_busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool):
        self._busy = busy
        self._apply_action_style()

    def _apply_action_style(self):
        """Mirror AgentPanel.set_busy's button styling verbatim."""
        if self._busy:
            self._action_btn.setText("中止")
            self._action_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #dc2626;
                    color: #f1f1f1;
                    border: none;
                    border-radius: 5px;
                    padding: 6px 14px;
                    font-size: {fs(12)};
                    font-weight: 600;
                    min-height: 24px;
                }}
                QPushButton:hover {{ background-color: #ef4444; }}
                QPushButton:pressed {{ background-color: #b91c1c; }}
            """)
        else:
            self._action_btn.setText("执行")
            self._action_btn.setObjectName("PrimaryButton")
            a = accent_color()
            self._action_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {a};
                    color: #0a0a10;
                    border: none;
                    border-radius: 5px;
                    padding: 6px 20px;
                    font-size: {fs(12)};
                    font-weight: 600;
                }}
                QPushButton:hover {{ background-color: {_lighter(a, 0.3)}; }}
                QPushButton:pressed {{ background-color: {_darker(a, 0.15)}; }}
            """)

    # ------------------------------------------------------------------
    # Public text API
    # ------------------------------------------------------------------

    def text(self) -> str:
        return self.input_edit.toPlainText()

    def set_text(self, t: str):
        self.input_edit.setPlainText(t)

    def clear(self):
        self.input_edit.clear()

    # ------------------------------------------------------------------
    # Attachment-bar passthrough
    # ------------------------------------------------------------------

    def attachment_bar(self):
        """Return the ImageAttachmentWidget, or None if hidden."""
        return self._attachment_bar if self._show_attachment_bar else None

    # ------------------------------------------------------------------
    # Event filter: Enter-to-send (mirrors AgentPanel.eventFilter)
    # ------------------------------------------------------------------

    def eventFilter(self, watched, event):
        if watched is self.input_edit and event is not None:
            ev_type = int(event.type())
            if ev_type == int(QtCore.QEvent.KeyPress):
                key = int(event.key())
                modifiers = event.modifiers()
                if key in (int(QtCore.Qt.Key_Return), int(QtCore.Qt.Key_Enter)):
                    if modifiers & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier):
                        cursor = self.input_edit.textCursor()
                        cursor.insertText("\n")
                        self.input_edit.setTextCursor(cursor)
                        return True
                    if modifiers == QtCore.Qt.NoModifier:
                        if self._busy:
                            self.abort_requested.emit()
                            self.stop_requested.emit()
                        else:
                            self.submit()
                        return True
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------------
    # Drag-drop forwarding (no media_manager import — parent handles add)
    # ------------------------------------------------------------------
    # NOTE: we cannot avoid importing mime_has_images / from_mime_data here
    # without moving that logic to the parent. To keep InputBar reusable we
    # accept the drop event and forward via images_dropped, but we still need
    # to *detect* that the mime data carries images. We do the lightweight
    # has-images check inline (no media_manager dep) and let the parent
    # resolve the actual MediaItems.

    @staticmethod
    def _mime_has_images(mime_data) -> bool:
        if mime_data is None:
            return False
        if mime_data.hasImage():
            return True
        for url in mime_data.urls() or []:
            if url.isLocalFile() and url.toLocalFile().lower().endswith(
                (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
            ):
                return True
        return False

    def _on_drag_enter(self, event):
        if self._mime_has_images(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _on_drag_move(self, event):
        if self._mime_has_images(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _on_drop(self, event):
        # Forward the raw mime data to the parent; it owns the media_manager
        # logic (from_mime_data). We pass the urls (file paths) so the parent
        # can rebuild MediaItems without re-parsing the event.
        urls = [u for u in (event.mimeData().urls() or []) if u.isLocalFile()]
        if urls:
            self.images_dropped.emit(urls)
            event.acceptProposedAction()
        else:
            event.ignore()


# ═══════════════════════════════════════════════════════════════════════
# _InputDialog — IME / CJK popout (moved from project_widget.py)
# ═══════════════════════════════════════════════════════════════════════

class _InputDialog(QtWidgets.QDialog):
    """Popout text-input dialog with full IME (Chinese/CJK) support.

    Why this exists: Houdini's Python Panel container intercepts keyboard
    events BEFORE Qt's input-method pipeline (SideFX-acknowledged bug), so IME
    composition (preedit) never reaches an embedded QPlainTextEdit — the
    candidate window doesn't appear and the widget loses focus. This does NOT
    affect Houdini's native parameter pane (different UI toolkit) or a real
    top-level Qt window parented to hou.qt.mainWindow().

    Fix from first principles: since a genuine top-level Qt window is the one
    condition under which IME already works, move text entry into this QDialog
    (parented to hou.qt.mainWindow). It's a real OS window, so the IME attaches
    normally and Chinese input works perfectly.

    Usage: the panel keeps a small inline box for quick English input; a
    "input" button opens this dialog for CJK / longer messages. Enter or the
    Send button returns the text to the panel via the submitted signal.
    """

    # Emitted with the typed text when the user sends (Enter / Send button).
    submitted = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edini Project — Input")
        self.resize(520, 220)
        self._build_ui()

    def _build_ui(self) -> None:
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        hint = QtWidgets.QLabel("在此输入消息(支持中文输入法)。Enter 发送,Shift+Enter 换行。")
        hint.setStyleSheet(f"color:#8b8fa8;font-size:{fs(10)};")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.edit = QtWidgets.QPlainTextEdit()
        self.edit.setAttribute(QtCore.Qt.WA_InputMethodEnabled, True)
        self.edit.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.edit.setPlaceholderText("输入消息…")
        self.edit.keyPressEvent = self._on_key  # Enter to send
        lay.addWidget(self.edit, 1)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QtWidgets.QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        send_btn = QtWidgets.QPushButton("发送")
        send_btn.setDefault(True)
        send_btn.clicked.connect(self._do_send)
        btn_row.addWidget(send_btn)
        lay.addLayout(btn_row)

    def _on_key(self, event):
        from PySide6 import QtCore as _qc
        if event.key() in (_qc.Qt.Key_Return, _qc.Qt.Key_Enter) \
           and not (event.modifiers() & (_qc.Qt.ShiftModifier | _qc.Qt.ControlModifier)):
            self._do_send()
            return
        QtWidgets.QPlainTextEdit.keyPressEvent(self.edit, event)

    def _do_send(self) -> None:
        text = self.edit.toPlainText().strip()
        if not text:
            return
        self.submitted.emit(text)
        self.edit.clear()
        self.accept()

    def open_for_input(self) -> None:
        """Show the dialog modally and clear it for fresh input."""
        self.edit.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()
