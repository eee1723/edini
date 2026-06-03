"""Edini theme system — dark base + accent color presets + font scaling."""
from PySide6 import QtGui, QtCore

_font_scale = 1.0
_theme_color_key = "cyan"

THEME_COLORS = {
    "cyan": {
        "name": "北极青",
        "accent": "#06b6d4",
        "accent_light": "#22d3ee",
        "accent_dark": "#0891b2",
        "accent_text": "#67e8f9",
        "accent_bg": "rgba(6, 182, 212, 0.08)",
        "accent_bg_hover": "rgba(6, 182, 212, 0.18)",
        "accent_border": "#06b6d4",
        "selection": "rgba(6, 182, 212, 0.3)",
    },
    "orange": {
        "name": "Houdini 橙",
        "accent": "#f59e0b",
        "accent_light": "#fbbf24",
        "accent_dark": "#d97706",
        "accent_text": "#fcd34d",
        "accent_bg": "rgba(245, 158, 11, 0.08)",
        "accent_bg_hover": "rgba(245, 158, 11, 0.18)",
        "accent_border": "#f59e0b",
        "selection": "rgba(245, 158, 11, 0.3)",
    },
    "blue": {
        "name": "深海蓝",
        "accent": "#3b82f6",
        "accent_light": "#60a5fa",
        "accent_dark": "#2563eb",
        "accent_text": "#93c5fd",
        "accent_bg": "rgba(59, 130, 246, 0.08)",
        "accent_bg_hover": "rgba(59, 130, 246, 0.18)",
        "accent_border": "#3b82f6",
        "selection": "rgba(59, 130, 246, 0.3)",
    },
    "purple": {
        "name": "极光紫",
        "accent": "#8b5cf6",
        "accent_light": "#a78bfa",
        "accent_dark": "#7c3aed",
        "accent_text": "#c4b5fd",
        "accent_bg": "rgba(139, 92, 246, 0.08)",
        "accent_bg_hover": "rgba(139, 92, 246, 0.18)",
        "accent_border": "#8b5cf6",
        "selection": "rgba(139, 92, 246, 0.3)",
    },
}


def set_font_scale(scale: float):
    global _font_scale
    _font_scale = max(0.8, min(1.4, scale))


def get_font_scale() -> float:
    return _font_scale


def font_size(base_pt: int) -> str:
    return f"{int(base_pt * _font_scale)}pt"


def set_theme_color(key: str):
    global _theme_color_key
    if key in THEME_COLORS:
        _theme_color_key = key


def get_theme_color() -> str:
    return _theme_color_key


def get_active_theme() -> dict:
    return THEME_COLORS.get(_theme_color_key, THEME_COLORS["cyan"])


def apply_main_theme(window) -> tuple:
    """Apply dark theme stylesheet to a QMainWindow. Returns (title_font, accent_color)."""
    theme = get_active_theme()
    accent = theme["accent"]

    stylesheet = f"""
QMainWindow {{
    background-color: #111118;
}}

QWidget {{
    color: #e5e5eb;
    font-family: "Segoe UI", "Noto Sans SC", sans-serif;
    font-size: {font_size(12)};
}}

QMenuBar {{
    background-color: #0e0e15;
    color: #a1a1aa;
    border-bottom: 1px solid #2a2a3c;
    padding: 2px 4px;
}}

QMenuBar::item:selected {{
    background-color: {theme["accent_bg"]};
    color: {accent};
}}

QMenu {{
    background-color: #1a1a24;
    border: 1px solid #2a2a3c;
    padding: 4px;
}}

QMenu::item:selected {{
    background-color: {theme["accent_bg"]};
    color: {accent};
}}

QStatusBar {{
    background-color: #0e0e15;
    color: #71717a;
    border-top: 1px solid #2a2a3c;
    font-size: {font_size(11)};
}}

QSplitter::handle {{
    background-color: #2a2a3c;
    width: 2px;
}}

QScrollBar:vertical {{
    background: #0e0e15;
    width: 10px;
    margin: 2px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical {{
    background: #3d3d55;
    min-height: 24px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical:hover {{
    background: {accent};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: #0e0e15;
    height: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:horizontal {{
    background: #3d3d55;
    min-width: 24px;
    border-radius: 5px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {accent};
}}

QTextBrowser {{
    background-color: #111118;
    border: none;
    color: #e5e5eb;
    selection-background-color: {theme["selection"]};
}}

QPlainTextEdit {{
    background-color: #1a1a24;
    color: #e5e5eb;
    border: 1px solid #2a2a3c;
    border-radius: 6px;
    padding: 8px;
    font-size: {font_size(13)};
}}

QPlainTextEdit:focus {{
    border-color: {accent};
}}

QPushButton {{
    background-color: #1a1a24;
    color: #e5e5eb;
    border: 1px solid #2a2a3c;
    border-radius: 6px;
    padding: 6px 16px;
    font-size: {font_size(12)};
}}

QPushButton:hover {{
    background-color: #222233;
    border-color: {accent};
}}

QPushButton#PrimaryButton {{
    background-color: {accent};
    color: #0e0e15;
    border: none;
    font-weight: 600;
}}

QPushButton#PrimaryButton:hover {{
    background-color: {theme["accent_light"]};
}}

QPushButton#GhostButton {{
    background-color: transparent;
    border: none;
    color: #71717a;
    font-size: {font_size(11)};
}}

QPushButton#GhostButton:hover {{
    color: {accent};
}}

QLabel {{
    color: #e5e5eb;
    background: transparent;
}}

QProgressBar {{
    background-color: #1a1a24;
    border: 1px solid #2a2a3c;
    border-radius: 4px;
    text-align: center;
    color: #e5e5eb;
    font-size: {font_size(10)};
}}

QProgressBar::chunk {{
    background-color: {accent};
    border-radius: 3px;
}}

QToolTip {{
    background-color: #1a1a24;
    color: #e5e5eb;
    border: 1px solid #2a2a3c;
    border-radius: 4px;
    padding: 4px 8px;
}}
"""
    window.setStyleSheet(stylesheet)
    title_font = QtGui.QFont("Segoe UI", int(14 * _font_scale), QtGui.QFont.Bold)
    return title_font, accent


def refresh_window_theme(window):
    apply_main_theme(window)
