"""Vision description bubble — rendered in the chat timeline when pi-visionizer
describes images before the main model processes them.
"""
from __future__ import annotations

import base64
import tempfile
import os
import subprocess
import sys
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt

from edini.ui.theme import fs


class VisionDescriptionBubble(QtWidgets.QFrame):
    """Collapsible bubble showing vision model's image description.

    Rendered in the timeline after a user message with images,
    before the AI's main response.
    """

    def __init__(
        self,
        descriptions: list[dict[str, Any]],
        parent=None,
    ):
        """
        Args:
            descriptions: list of dicts with keys:
                mimeType, description, model, elapsedMs
        """
        super().__init__(parent)
        self._descriptions = descriptions
        self._expanded = False  # collapsed by default
        self._image_base64_list: list[str] = []  # for "view original" feature (multi-image)

        self.setStyleSheet("""
            VisionDescriptionBubble {
                background: rgba(167,139,250,0.06);
                border: 1px solid rgba(167,139,250,0.15);
                border-radius: 6px;
            }
        """)

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(10, 6, 10, 6)
        self._layout.setSpacing(4)

        self._build_header()
        self._build_content()
        self._content_widget.setVisible(False)  # collapsed by default

    def _build_header(self):
        header_row = QtWidgets.QHBoxLayout()
        header_row.setSpacing(6)

        model_name = self._descriptions[0].get("model", "vision-model") if self._descriptions else "vision"
        total_ms = sum(d.get("elapsedMs", 0) for d in self._descriptions)
        elapsed_str = f"{total_ms / 1000:.1f}s" if total_ms > 0 else ""

        parts = ["👁️ 图片识别完成"]
        if model_name:
            parts.append(f"· {model_name}")
        if elapsed_str:
            parts.append(f"· {elapsed_str}")

        self._header_label = QtWidgets.QLabel(" ".join(parts))
        self._header_label.setStyleSheet(
            f"QLabel {{ color:#a78bfa; font-size:{fs(11)}; font-weight:600; border:none; }}"
        )
        header_row.addWidget(self._header_label, 1)

        self._toggle_btn = QtWidgets.QPushButton("▶ 展开")
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setFixedHeight(20)
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(167,139,250,0.12);
                color: #a78bfa;
                border: none;
                border-radius: 3px;
                padding: 0px 6px;
                font-size: {fs(10)};
            }}
            QPushButton:hover {{
                background: rgba(167,139,250,0.22);
            }}
        """)
        self._toggle_btn.clicked.connect(self._toggle)
        header_row.addWidget(self._toggle_btn)

        self._layout.addLayout(header_row)

    def _build_content(self):
        """Build the description text area."""
        self._content_widget = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(self._content_widget)
        content_layout.setContentsMargins(4, 2, 4, 2)
        content_layout.setSpacing(6)

        for d in self._descriptions:
            desc_text = d.get("description", "")
            if not desc_text:
                continue

            label = QtWidgets.QLabel(desc_text)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setStyleSheet(
                f"QLabel {{ color:#c4b5fd; font-size:{fs(11)}; line-height:1.5; "
                f"border:none; background:transparent; }}"
            )
            content_layout.addWidget(label)

        # "View original" link
        count = len(self._image_base64_list) if self._image_base64_list else 0
        btn_text = f"📸 查看原图 ({count})" if count > 1 else "📸 查看原图"
        view_btn = QtWidgets.QPushButton(btn_text)
        view_btn.setCursor(Qt.PointingHandCursor)
        view_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: #71717a;
                border: none;
                font-size: {fs(10)};
                text-align: left;
                padding: 0;
            }}
            QPushButton:hover {{
                color: #a78bfa;
            }}
        """)
        view_btn.clicked.connect(self._on_view_original)
        content_layout.addWidget(view_btn)

        self._layout.addWidget(self._content_widget)

    def _toggle(self):
        self._expanded = not self._expanded
        self._content_widget.setVisible(self._expanded)
        if self._expanded:
            self._toggle_btn.setText("▲ 收起")
        else:
            self._toggle_btn.setText("▼ 展开")

    def _on_view_original(self):
        """Open all original images in the OS default viewer via temp files."""
        if not self._image_base64_list:
            return
        mime_type = self._descriptions[0].get("mimeType", "image/jpeg") if self._descriptions else "image/jpeg"
        ext = _mime_to_ext(mime_type)
        for i, b64 in enumerate(self._image_base64_list):
            if not b64:
                continue
            try:
                fd, path = tempfile.mkstemp(suffix=ext, prefix=f"edini_view_{i}_")
                with os.fdopen(fd, "wb") as f:
                    f.write(base64.b64decode(b64))
                _open_with_os(path)
            except Exception:
                pass

    def set_original_images(self, base64_list: list[str]):
        """Provide original image data for 'view original' feature (multiple images)."""
        self._image_base64_list = [b for b in base64_list if b]
        # Update button text if already built
        if hasattr(self, '_toggle_btn'):
            count = len(self._image_base64_list)
            if count > 1:
                self._toggle_btn.setText(f"📸 查看原图 ({count})")

    def set_original_image(self, base64_data: str):
        """Backward-compat: single image."""
        self.set_original_images([base64_data])

    @staticmethod
    def create_from_notification(
        descriptions: list[dict[str, Any]],
        image_base64_list: list[str] | None = None,
    ) -> "VisionDescriptionBubble":
        """Factory: create a bubble from the vision_description notification data."""
        bubble = VisionDescriptionBubble(descriptions)
        if image_base64_list:
            bubble.set_original_images(image_base64_list)
        return bubble

    @staticmethod
    def create_error_bubble(error_msg: str) -> "VisionDescriptionBubble":
        """Factory: create a bubble showing a vision model error."""
        bubble = VisionDescriptionBubble([{
            "description": error_msg,
            "model": "vision-error",
            "elapsedMs": 0,
        }])
        bubble.setStyleSheet("""
            VisionDescriptionBubble {
                background: rgba(239,68,68,0.06);
                border: 1px solid rgba(239,68,68,0.2);
                border-radius: 6px;
            }
        """)
        bubble._header_label.setStyleSheet(
            f"QLabel {{ color:#f87171; font-size:{fs(11)}; font-weight:600; border:none; }}"
        )
        return bubble


def _open_with_os(path: str):
    """Open a file in the OS default viewer."""
    if not path or not os.path.isfile(path):
        return
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def _mime_to_ext(mime: str) -> str:
    m = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
    }
    return m.get(mime, ".jpg")
