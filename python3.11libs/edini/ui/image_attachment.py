"""Image attachment preview bar for agent panel input area.

Shows up to 5 thumbnail cards above the text input when images are added
via screenshot, file pick, clipboard paste, or drag-drop.
"""
from __future__ import annotations

import base64
from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from edini.media_manager import MediaItem, MediaSource, MAX_ATTACHMENTS
from edini.ui.theme import fs

# Source icon per MediaSource
_SOURCE_ICONS = {
    MediaSource.VIEWPORT: "📸",
    MediaSource.DRAG_DROP: "📁",
    MediaSource.CLIPBOARD: "📋",
    MediaSource.FILE_PICK: "📁",
    MediaSource.TOOL: "🔧",
}


class _AttachmentCard(QtWidgets.QFrame):
    """Single image attachment card: thumbnail + filename + source icon + remove button."""

    removed = QtCore.Signal(int)  # index

    THUMB_W = 120
    THUMB_H = 68
    CARD_W = 136

    def __init__(self, item: MediaItem, index: int, parent=None):
        super().__init__(parent)
        self._index = index
        self.setFixedWidth(self.CARD_W)
        self.setStyleSheet(f"""
            _AttachmentCard {{
                background: #141420;
                border: 1px solid #252540;
                border-radius: 4px;
            }}
        """)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 2)
        layout.setSpacing(2)

        # Thumbnail
        thumb_label = QtWidgets.QLabel()
        thumb_label.setFixedSize(self.THUMB_W, self.THUMB_H)
        thumb_label.setAlignment(Qt.AlignCenter)
        thumb_label.setStyleSheet(
            "QLabel { background: #0a0a14; border-radius: 2px; border: none; }"
        )
        if item.thumbnail:
            pixmap = _base64_to_pixmap(item.thumbnail)
            if pixmap:
                scaled = pixmap.scaled(
                    self.THUMB_W, self.THUMB_H,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
                thumb_label.setPixmap(scaled)
        else:
            thumb_label.setText("🖼️")
        layout.addWidget(thumb_label)

        # Info row: source icon + filename
        info_row = QtWidgets.QHBoxLayout()
        info_row.setSpacing(2)
        source_icon = _SOURCE_ICONS.get(item.source, "📁")
        icon_label = QtWidgets.QLabel(source_icon)
        icon_label.setStyleSheet(
            f"QLabel {{ color:#71717a; font-size:{fs(9)}; border:none; }}"
        )
        icon_label.setFixedWidth(16)
        info_row.addWidget(icon_label)

        name_label = QtWidgets.QLabel(_truncate_name(item.filename, 14))
        name_label.setStyleSheet(
            f"QLabel {{ color:#a1a1aa; font-size:{fs(10)}; border:none; }}"
        )
        info_row.addWidget(name_label, 1)
        layout.addLayout(info_row)

        # Remove button (overlayed in top-right)
        remove_btn = QtWidgets.QPushButton("✕")
        remove_btn.setFixedSize(18, 18)
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(0,0,0,0.6);
                color: #a1a1aa;
                border: none;
                border-radius: 9px;
                font-size: {fs(9)};
            }}
            QPushButton:hover {{
                background: #ef4444;
                color: #fff;
            }}
        """)
        remove_btn.clicked.connect(lambda: self.removed.emit(self._index))
        # Float the remove button
        remove_btn.setParent(self)
        remove_btn.move(self.CARD_W - 20, 2)

    def update_index(self, new_index: int):
        self._index = new_index


def _base64_to_pixmap(b64: str) -> QtGui.QPixmap | None:
    try:
        data = base64.b64decode(b64)
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(data)
        return pixmap if not pixmap.isNull() else None
    except Exception:
        return None


def _truncate_name(name: str, max_len: int) -> str:
    if len(name) <= max_len:
        return name
    return name[:max_len - 1] + "…"


class ImageAttachmentWidget(QtWidgets.QWidget):
    """Horizontal bar of image attachment cards above the text input.

    Signals:
        attachments_changed() — emitted when items are added or removed
    """

    attachments_changed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[MediaItem] = []
        self._cards: list[_AttachmentCard] = []

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignLeft)
        self.setFixedHeight(104)
        self.setVisible(False)

        self.setStyleSheet(
            "ImageAttachmentWidget { background: transparent; border: none; }"
        )

    def items(self) -> list[MediaItem]:
        return list(self._items)

    def count(self) -> int:
        return len(self._items)

    def is_full(self) -> bool:
        return len(self._items) >= MAX_ATTACHMENTS

    def add(self, item: MediaItem) -> bool:
        """Add a MediaItem. Returns True if added, False if rejected (full/invalid)."""
        from edini.media_manager import validate
        ok, _ = validate(item)
        if not ok:
            return False
        if self.is_full():
            return False
        self._items.append(item)
        self._rebuild_cards()
        self.setVisible(True)
        self.attachments_changed.emit()
        return True

    def remove(self, index: int):
        if 0 <= index < len(self._items):
            self._items.pop(index)
            self._rebuild_cards()
            if not self._items:
                self.setVisible(False)
            self.attachments_changed.emit()

    def clear(self):
        self._items.clear()
        self._rebuild_cards()
        self.setVisible(False)
        self.attachments_changed.emit()

    def _rebuild_cards(self):
        # Remove all existing cards
        for card in self._cards:
            self.layout().removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        # Rebuild
        for i, item in enumerate(self._items):
            card = _AttachmentCard(item, i, self)
            card.removed.connect(self.remove)
            self._cards.append(card)
            self.layout().addWidget(card)
