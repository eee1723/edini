"""Edini theme system — refined dark palette. Per-element font sizes."""
from PySide6 import QtGui

_font_scale = 1.0
_theme_key = "cyan"

THEMES = {
    "cyan":   {"name": "北极青",    "accent": "#06b6d4"},
    "orange": {"name": "Houdini 橙","accent": "#f59e0b"},
    "blue":   {"name": "深海蓝",    "accent": "#3b82f6"},
    "purple": {"name": "极光紫",    "accent": "#8b5cf6"},
}


def set_font_scale(v: float):
    global _font_scale
    _font_scale = max(0.8, min(1.4, v))
    from edini.config import save_settings
    save_settings({"font_scale": v})


def get_font_scale() -> float:
    return _font_scale


def fs(base: int) -> str:
    """Return font-size string: base pt * font_scale."""
    return f"{int(base * _font_scale)}pt"


def set_theme(key: str):
    global _theme_key
    if key in THEMES:
        _theme_key = key
        from edini.config import save_settings
        save_settings({"theme_color": key})


def get_theme() -> str:
    return _theme_key


def accent_color() -> str:
    return THEMES[_theme_key]["accent"]


def accent_name() -> str:
    return THEMES[_theme_key]["name"]


def init_theme_from_config() -> None:
    """Load theme/font_scale from config at startup."""
    from edini.config import get_settings
    settings = get_settings()
    global _theme_key, _font_scale
    tc = settings.get("theme_color", "cyan")
    if tc in THEMES:
        _theme_key = tc
    fs_val = settings.get("font_scale", 1.0)
    _font_scale = max(0.8, min(1.4, float(fs_val)))


def build_stylesheet() -> str:
    a = accent_color()
    # Element-specific font sizes (no global QWidget font-size override)
    return f"""
QMainWindow     {{ background-color:#0c0c14; }}
QWidget         {{ color:#c8ccd4; font-family:"Segoe UI","Microsoft YaHei",sans-serif; }}
QMenuBar        {{ background-color:#0a0a10; color:#8a8f98; border-bottom:1px solid #1e1e2c; padding:2px 4px; }}
QMenuBar::item:selected {{ color:{a}; background-color:#141420; }}
QMenu           {{ background-color:#101018; border:1px solid #1e1e2c; padding:4px; }}
QMenu::item     {{ padding:4px 24px 4px 12px; font-size:{fs(12)}; }}
QMenu::item:selected {{ background-color:#1a1a2a; color:{a}; }}
QMenu::separator {{ height:1px; background:#1e1e2c; margin:4px 8px; }}
QStatusBar      {{ background-color:#0a0a10; color:#6a6e76; border-top:1px solid #1e1e2c; font-size:{fs(10)}; padding:0 8px; }}
QSplitter::handle {{ background-color:#1a1a28; width:1px; }}
QSplitter::handle:hover {{ background-color:{a}; }}
QScrollBar:vertical     {{ background:#0c0c14; width:8px; margin:0; }}
QScrollBar::handle:vertical {{ background:#2a2a3a; min-height:32px; border-radius:4px; }}
QScrollBar::handle:vertical:hover {{ background:#3a3a4a; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
QScrollBar:horizontal   {{ background:#0c0c14; height:8px; }}
QScrollBar::handle:horizontal {{ background:#2a2a3a; min-width:32px; border-radius:4px; }}
QScrollBar::handle:horizontal:hover {{ background:#3a3a4a; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width:0; }}
QTextBrowser    {{ background-color:#0e0e18; border:none; color:#c8ccd4; selection-background-color:rgba(0,188,212,0.25); font-size:{fs(12)}; }}
QPlainTextEdit  {{ background-color:#10101a; color:#c8ccd4; border:1px solid #1e1e2c; border-radius:6px; padding:10px 12px; font-size:{fs(13)}; }}
QPlainTextEdit:focus {{ border-color:{a}; }}
QLineEdit       {{ background-color:#10101a; color:#c8ccd4; border:1px solid #1e1e2c; border-radius:4px; padding:6px 10px; font-size:{fs(12)}; }}
QLineEdit:focus {{ border-color:{a}; }}
QPushButton     {{ background-color:#141420; color:#9ea2aa; border:1px solid #1e1e2c; border-radius:5px; padding:6px 14px; font-size:{fs(12)}; min-height:24px; }}
QPushButton:hover {{ background-color:#1a1a2a; color:#c8ccd4; border-color:#2a2a3c; }}
QPushButton:pressed {{ background-color:#0e0e18; }}
QPushButton#PrimaryButton {{ background-color:{a}; color:#0a0a10; border:none; font-weight:600; padding:6px 20px; }}
QPushButton#PrimaryButton:hover {{ background-color:{_lighter(a,0.3)}; }}
QPushButton#PrimaryButton:pressed {{ background-color:{_darker(a,0.15)}; }}
QPushButton#GhostButton {{ background-color:transparent; border:none; color:#6a6e76; padding:4px 0; font-size:{fs(11)}; }}
QPushButton#GhostButton:hover {{ color:{a}; }}
QLabel          {{ color:#c8ccd4; background:transparent; font-size:{fs(12)}; }}
QListWidget     {{ background-color:#0a0a10; border:1px solid #141420; border-radius:4px; color:#9ea2aa; font-size:{fs(12)}; outline:none; }}
QListWidget::item {{ padding:8px 12px; border-bottom:1px solid #101018; }}
QListWidget::item:selected {{ background-color:rgba(0,188,212,0.10); color:{a}; border-left:2px solid {a}; padding-left:10px; }}
QListWidget::item:hover {{ background-color:#141420; }}
QProgressBar    {{ background-color:#0e0e18; border:1px solid #1a1a28; border-radius:3px; text-align:center; color:#c8ccd4; font-size:{fs(10)}; height:12px; }}
QProgressBar::chunk {{ background-color:{a}; border-radius:2px; }}
QTabWidget::pane {{ border:1px solid #1e1e2c; background-color:#0c0c14; top:-1px; }}
QTabBar::tab    {{ background:#101018; color:#6a6e76; padding:6px 16px; font-size:{fs(12)}; border:1px solid #1e1e2c; border-bottom:none; border-top-left-radius:4px; border-top-right-radius:4px; margin-right:2px; }}
QTabBar::tab:selected {{ background:#0c0c14; color:{a}; border-bottom:1px solid #0c0c14; }}
QTabBar::tab:hover {{ color:#c8ccd4; }}
QComboBox       {{ background-color:#10101a; color:#c8ccd4; border:1px solid #1e1e2c; border-radius:4px; padding:4px 10px; font-size:{fs(12)}; }}
QComboBox:hover {{ border-color:#2a2a3c; }}
QComboBox:focus {{ border-color:{a}; }}
QComboBox::drop-down {{ border:none; width:20px; }}
QComboBox QAbstractItemView {{ background-color:#101018; border:1px solid #1e1e2c; selection-background-color:#1a1a2a; selection-color:{a}; font-size:{fs(12)}; }}
QCheckBox       {{ color:#8a8f98; font-size:{fs(10)}; spacing:6px; }}
QCheckBox::indicator {{ width:14px; height:14px; border:1px solid #2a2a3a; border-radius:3px; background:#10101a; }}
QCheckBox::indicator:checked {{ background:{a}; border-color:{a}; }}
QCheckBox::indicator:hover {{ border-color:#3a3a4a; }}
QToolTip        {{ background-color:#141420; color:#c8ccd4; border:1px solid #1e1e2c; border-radius:4px; padding:4px 8px; font-size:{fs(11)}; }}
QFrame[frameShape="4"] {{ border-top:1px solid #1e1e2c; }}
QDialog         {{ background-color:#0c0c14; }}
QInputDialog    {{ background-color:#0c0c14; }}
QInputDialog QLabel {{ color:#c8ccd4; font-size:{fs(12)}; }}
QInputDialog QLineEdit {{ background-color:#10101a; color:#c8ccd4; border:1px solid #1e1e2c; border-radius:4px; padding:6px 10px; font-size:{fs(12)}; }}
"""


def apply_theme(window) -> None:
    window.setStyleSheet(build_stylesheet())


def refresh_window_theme(window) -> None:
    """Force reapply stylesheet (used after settings change)."""
    window.setStyleSheet(build_stylesheet())
    window.repaint()


def _lighter(h: str, a: float) -> str:
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"#{min(255,int(r+(255-r)*a)):02x}{min(255,int(g+(255-g)*a)):02x}{min(255,int(b+(255-b)*a)):02x}"


def _darker(h: str, a: float) -> str:
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"#{max(0,int(r*(1-a))):02x}{max(0,int(g*(1-a))):02x}{max(0,int(b*(1-a))):02x}"
