# Edini UI 重构 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Edini 从一个需要 Python Shell 手动启动的浮动 QWidget，重构为 Houdini 原生菜单集成的三栏高级 UI（History | Chat Timeline | Pi+Context）

**Architecture:** 迁移代码到 `python3.11libs/edini/` 匹配 Houdini 包加载规范，通过 `MainMenuCommon.xml` 注册主菜单栏入口，QMainWindow + QSplitter 三栏布局实现（参考 EEEAi_Houdini），Pi JSON-RPC 事件完整映射到 UI 组件

**Tech Stack:** Python 3.11 / PySide6 / Hou Module / Pi Agent (Node.js) / JSON-RPC / Qt Stylesheets

---

## 文件结构概览

```
python3.11libs/                    ← Houdini 加载入口（新增）
├── MainMenuCommon.xml             ← Houdini 菜单定义
└── edini/
    ├── __init__.py               ← create_panel() 入口
    ├── config.py                  ← 配置 + 路径适配
    ├── rpc_client.py             ← Pi 子进程 + JSON-RPC
    ├── tool_executor.py          ← HTTP 工具执行器
    ├── node_utils.py             ← Houdini 操作
    ├── settings.json             ← 用户配置
    └── ui/
        ├── __init__.py           ← 导出 open_chat_window/open_settings
        ├── windows.py            ← 窗口单例管理
        ├── main_window.py        ← QMainWindow 三栏布局
        ├── agent_panel.py        ← 聊天时间线面板
        ├── history_panel.py      ← 会话历史面板
        ├── context_panel.py      ← Pi状态 + 场景信息
        ├── theme.py              ← 暗色主题 + 色彩预设
        ├── settings_dialog.py    ← 设置对话框
        ├── chat_runtime.py       ← Pi 事件适配层
        ├── session_store.py      ← 会话持久化
        ├── plan_progress_widget.py ← Plan 进度条
        ├── change_tree_widget.py   ← 节点变更追踪
        ├── hotkey.py             ← 热键注册
        └── styled_checkbox.py    ← 样式复选组件
```

---

## Phase 0: 基础设施 — 目录迁移 + Houdini 包注册

### Task 0.1: 创建新目录结构

**Files:**
- Create: `python3.11libs/edini/__init__.py`
- Create: `python3.11libs/edini/ui/__init__.py`
- Create: `python3.11libs/edini/sessions/.gitkeep`

- [ ] **Step 1: 创建目录并移动源码**

```bash
mkdir -p python3.11libs/edini/ui
mkdir -p python3.11libs/edini/sessions
cp edini/config.py python3.11libs/edini/config.py
cp edini/rpc_client.py python3.11libs/edini/rpc_client.py
cp edini/tool_executor.py python3.11libs/edini/tool_executor.py
cp edini/node_utils.py python3.11libs/edini/node_utils.py
cp edini/settings.json python3.11libs/edini/settings.json
```

- [ ] **Step 2: 写 `python3.11libs/edini/__init__.py`**

```python
"""Edini - Houdini AI Assistant powered by Pi."""
__version__ = "0.2.0"

def create_panel():
    from edini.ui.main_window import EdiniMainWindow
    return EdiniMainWindow()
```

- [ ] **Step 3: 写 `python3.11libs/edini/ui/__init__.py`**

```python
def open_chat_window():
    from edini.ui.windows import open_chat_window as _open
    return _open()

def open_settings():
    from edini.ui.windows import open_settings as _open
    return _open()

__all__ = ["open_chat_window", "open_settings"]
```

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/
git commit -m "feat: create python3.11libs directory structure for Houdini package loading"
```

### Task 0.2: 创建 Houdini 包注册文件

**Files:**
- Create: `python3.11libs/MainMenuCommon.xml`

- [ ] **Step 1: 写 MainMenuCommon.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<mainMenu>
  <menuBar>
    <subMenu id="edini_menu">
      <label>Edini</label>
      <scriptItem id="edini_open_chat">
        <label>Open Chat Panel</label>
        <scriptCode><![CDATA[
from edini.ui import open_chat_window
open_chat_window()
        ]]></scriptCode>
      </scriptItem>
      <separatorItem/>
      <scriptItem id="edini_settings">
        <label>Settings</label>
        <scriptCode><![CDATA[
from edini.ui import open_settings
open_settings()
        ]]></scriptCode>
      </scriptItem>
    </subMenu>
  </menuBar>
</mainMenu>
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/MainMenuCommon.xml
git commit -m "feat: add Houdini MainMenuCommon.xml for Edini menu bar integration"
```

### Task 0.3: 适配 config.py 路径

**Files:**
- Modify: `python3.11libs/edini/config.py`

- [ ] **Step 1: 更新 PROJECT_ROOT 和路径计算**

原有 config.py 中 `PROJECT_ROOT = Path(__file__).resolve().parent.parent`（从 `edini/config.py` 往上两级到项目根）。现在文件在 `python3.11libs/edini/config.py`，需要往上三级。

将 config.py 中：

```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent
```

改为：

```python
# config.py is at python3.11libs/edini/config.py
# Project root is 3 levels up: edini/ → python3.11libs/ → project root/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Pi extensions directory (at project root)
PI_EXTENSIONS_DIR = _PROJECT_ROOT / "pi-extensions"

# Local settings file (next to config.py, gitignored)
SETTINGS_FILE = Path(__file__).resolve().parent / "settings.json"
```

- [ ] **Step 2: 验证 `_find_pi()` 和其他函数不需要改动**

`_find_pi()` 中使用的 `APPDATA` 是系统路径，不受影响。`get_pi_command()` 中的 `-e` 参数使用 `PI_EXTENSIONS_DIR`，已通过上面的常量修正。

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/config.py
git commit -m "fix: adapt config.py paths for new python3.11libs structure"
```

### Task 0.4: 改写 install.py

**Files:**
- Modify: `scripts/install.py`

- [ ] **Step 1: 重写 install.py 为 Houdini packages 模式**

```python
"""Edini installation script for Houdini.

Registers Edini as a Houdini package so it appears in the menu bar.
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path


def get_edini_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_houdini_packages_dir() -> Path | None:
    candidates = [
        Path(os.environ.get("HOUDINI_USER_PREF_DIR", "")) / "packages",
        Path.home() / "Documents" / "houdini21.0" / "packages",
        Path.home() / "Documents" / "houdini21.5" / "packages",
    ]
    try:
        import hou
        prefs = hou.getenv("HOUDINI_USER_PREF_DIR") or hou.homeHoudiniDirectory()
        candidates.insert(0, Path(prefs) / "packages")
    except ImportError:
        pass
    for d in candidates:
        if d.exists() and d.is_dir():
            return d
    return None


def install() -> None:
    root = get_edini_root()
    packages_dir = get_houdini_packages_dir()

    if packages_dir is None:
        print("ERROR: Could not find Houdini packages directory.")
        print("Please set HOUDINI_USER_PREF_DIR or manually install.")
        sys.exit(1)

    packages_dir.mkdir(parents=True, exist_ok=True)
    package_file = packages_dir / "edini.json"

    # Unix-style path for Houdini JSON
    path_forward = str(root).replace("\\", "/")

    with open(package_file, "w") as f:
        json.dump({
            "env": [
                {"EDINI_PATH": path_forward}
            ],
            "path": "$EDINI_PATH",
            "houdini": {
                "python3.11libs": "$EDINI_PATH/python3.11libs"
            }
        }, f, indent=2)

    print(f"Edini installed!")
    print(f"  Package file: {package_file}")
    print(f"  Project root: {root}")
    print()
    print("Next steps:")
    print("  1. Restart Houdini")
    print("  2. Menu: Edini → Open Chat Panel")
    print("  3. Or run: scripts/setup_pi.bat")


if __name__ == "__main__":
    install()
```

- [ ] **Step 2: Commit**

```bash
git add scripts/install.py
git commit -m "feat: rewrite install.py for Houdini packages JSON registration"
```

### Task 0.5: 验证 Houdini 包可加载

- [ ] **Step 1: 运行 install.py 注册包**

```bash
python scripts/install.py
```
Expected: 输出 `Edini installed!` 并显示 packages 路径。

- [ ] **Step 2: 验证包文件内容**

```bash
cat "$USERPROFILE/Documents/houdini21.0/packages/edini.json" 2>/dev/null || cat "$USERPROFILE/Documents/houdini21.5/packages/edini.json"
```
Expected: 包含 `EDINI_PATH` 指向 Edini 项目根目录。

- [ ] **Step 3: 验证 Python 路径可导入（不需要完整 Houdini，测试配置）**

```bash
cd F:/zz/Edini && python -c "import sys; sys.path.insert(0,'python3.11libs'); from edini.config import PROJECT_ROOT; print(PROJECT_ROOT)"
```
Expected: 打印项目根路径。如果报错需要先确保 `python3.11libs` 在 path 中。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "verify: Houdini package load path confirmed"
```

---

## Phase 1: 核心 UI — 三栏布局 + 时间线

### Task 1.1: 创建 theme.py

**Files:**
- Create: `python3.11libs/edini/ui/theme.py`

- [ ] **Step 1: 写 theme.py — 颜色常量 + 预设 + 基础样式**

```python
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
    _, accent = apply_main_theme(window)
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/theme.py
git commit -m "feat: add dark theme system with 4 accent color presets (cyan/orange/blue/purple)"
```

### Task 1.2: 创建 chat_runtime.py — Pi 事件适配层

**Files:**
- Create: `python3.11libs/edini/ui/chat_runtime.py`

- [ ] **Step 1: 写 chat_runtime.py**

```python
"""Lightweight adapter between Pi RpcClient signals and the agent panel UI."""
from PySide6.QtCore import QObject, Signal


class ChatRuntime(QObject):
    """Wraps RpcClient, providing structured signals for the UI panel."""

    started = Signal(dict)
    stream_chunk = Signal(str)
    completed = Signal(dict)
    failed = Signal(str)
    tool_started = Signal(str, str, dict)      # tool_name, tool_call_id, args
    tool_completed = Signal(str, str, str)     # tool_name, tool_call_id, result
    stats_updated = Signal(dict)
    busy_changed = Signal(bool)

    def __init__(self, rpc_client, parent=None):
        super().__init__(parent)
        self._rpc = rpc_client
        self._bind()

    def _bind(self):
        r = self._rpc
        r.text_delta.connect(self._on_text_delta)
        r.tool_call.connect(self._on_tool_call)
        r.agent_started.connect(self._on_agent_start)
        r.agent_finished.connect(self._on_agent_finish)
        r.error_occurred.connect(self._on_error)
        r.stats_updated.connect(self._on_stats)

    def _on_text_delta(self, text: str):
        self.stream_chunk.emit(text)

    def _on_tool_call(self, tool_name: str, tool_call_id: str, args: dict):
        self.tool_started.emit(tool_name, tool_call_id, args)

    def _on_agent_start(self):
        self.started.emit({})
        self.busy_changed.emit(True)

    def _on_agent_finish(self):
        self.completed.emit({})
        self.busy_changed.emit(False)

    def _on_error(self, msg: str):
        self.failed.emit(msg)
        self.busy_changed.emit(False)

    def _on_stats(self, data: dict):
        self.stats_updated.emit(data)
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/chat_runtime.py
git commit -m "feat: add ChatRuntime adapter layer between Pi RpcClient and UI"
```

### Task 1.3: 创建 main_window.py — 三栏布局框架

**Files:**
- Create: `python3.11libs/edini/ui/main_window.py`

- [ ] **Step 1: 写 main_window.py 基础框架**

```python
"""Edini main window — 3-panel layout with QSplitter."""
import importlib
from PySide6 import QtCore, QtWidgets

from edini.rpc_client import RpcClient
from edini.tool_executor import ToolExecutor
from edini.ui.chat_runtime import ChatRuntime
from edini.ui.theme import apply_main_theme

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None


class EdiniMainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edini Agent")
        self.resize(1360, 860)

        self._tool_executor = ToolExecutor()
        self._rpc_client = RpcClient()
        self._chat_runtime = ChatRuntime(self._rpc_client, self)
        self._current_session_id = ""

        self._build_ui()
        self._bind_events()
        self._bootstrap()

    def _build_ui(self):
        self._title_font, self._accent = apply_main_theme(self)

        central = QtWidgets.QWidget(self)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.main_splitter = QtWidgets.QSplitter(central)
        self.main_splitter.setOrientation(QtCore.Qt.Horizontal)

        # Left: History placeholder
        self.history_panel = QtWidgets.QWidget(self.main_splitter)
        self.history_panel.setMinimumWidth(200)
        self.history_panel.setMaximumWidth(260)
        history_layout = QtWidgets.QVBoxLayout(self.history_panel)
        history_layout.addWidget(QtWidgets.QLabel("History (TODO)"))

        # Center: Agent panel placeholder
        self.agent_panel = QtWidgets.QWidget(self.main_splitter)
        self.agent_panel.setMinimumWidth(500)
        agent_layout = QtWidgets.QVBoxLayout(self.agent_panel)
        agent_layout.addWidget(QtWidgets.QLabel("Chat Timeline (TODO)"))

        # Right: Context placeholder
        self.context_panel = QtWidgets.QWidget(self.main_splitter)
        self.context_panel.setMinimumWidth(340)
        self.context_panel.setMaximumWidth(400)
        context_layout = QtWidgets.QVBoxLayout(self.context_panel)
        context_layout.addWidget(QtWidgets.QLabel("Context Panel (TODO)"))

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
        self._chat_runtime.started.connect(self._on_agent_started)
        self._chat_runtime.completed.connect(self._on_agent_done)
        self._chat_runtime.failed.connect(self._on_error)
        self._chat_runtime.busy_changed.connect(self._on_busy_changed)
        self._rpc_client.status_changed.connect(self._on_status_changed)

    def _bootstrap(self):
        self._tool_executor.start()
        self._rpc_client.start()
        self._rpc_client.send_get_stats()

    def _on_agent_started(self, _):
        self.status.showMessage("Processing...")

    def _on_agent_done(self, _):
        self.status.showMessage("Ready")

    def _on_error(self, msg: str):
        self.status.showMessage(f"Error: {msg}")

    def _on_busy_changed(self, busy: bool):
        pass

    def _on_status_changed(self, status: str):
        self.status.showMessage(f"Pi: {status}")

    def closeEvent(self, event):
        self._rpc_client.stop()
        self._tool_executor.stop()
        super().closeEvent(event)
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/main_window.py
git commit -m "feat: add EdiniMainWindow with 3-panel QSplitter layout (placeholder panels)"
```

### Task 1.4: 创建 windows.py — 窗口单例管理

**Files:**
- Create: `python3.11libs/edini/ui/windows.py`

- [ ] **Step 1: 写 windows.py**

```python
"""Window singleton management for Edini within Houdini."""
import importlib

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None

_main_window = None
_settings_dialog = None


def _main_parent():
    if hou is None:
        return None
    try:
        return hou.qt.mainWindow()
    except Exception:
        return None


def open_chat_window(toggle=False):
    global _main_window
    if _main_window is None:
        from edini.ui.main_window import EdiniMainWindow
        _main_window = EdiniMainWindow(_main_parent())

    if toggle and _main_window.isVisible() and _main_window.isActiveWindow():
        _main_window.showMinimized()
        return _main_window

    _main_window.show()
    _main_window.raise_()
    _main_window.activateWindow()
    return _main_window


def open_settings():
    global _settings_dialog
    if _settings_dialog is None:
        from edini.ui.settings_dialog import SettingsDialog
        _settings_dialog = SettingsDialog(_main_parent() if _main_window else None)
    _settings_dialog.show()
    _settings_dialog.raise_()
    _settings_dialog.activateWindow()
    return _settings_dialog
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/windows.py
git commit -m "feat: add window singleton management (open_chat_window, open_settings)"
```

### Task 1.5: 集成测试 — 验证三栏窗口可启动

- [ ] **Step 1: 测试 Python 导入路径**

```bash
cd F:/zz/Edini && python -c "
import sys
sys.path.insert(0, 'python3.11libs')
from edini.ui.theme import get_active_theme
print('Theme:', get_active_theme()['name'])
from edini.ui.main_window import EdiniMainWindow
print('MainWindow class:', EdiniMainWindow)
print('OK - imports work')
"
```
Expected: 打印主题名和类名，无报错。

- [ ] **Step 2: Commit**

```bash
git commit -m "verify: import chain works from python3.11libs/edini/"
```

---

## Phase 2: 聊天时间线面板（agent_panel.py）

### Task 2.1: 创建 styled_checkbox.py

**Files:**
- Create: `python3.11libs/edini/ui/styled_checkbox.py`

- [ ] **Step 1: 写 styled_checkbox.py**

```python
"""Styled checkbox widget matching the dark theme."""
from PySide6 import QtCore, QtWidgets


class StyledCheckBox(QtWidgets.QCheckBox):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            QCheckBox {
                color: #a1a1aa;
                font-size: 11px;
                spacing: 4px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #3d3d55;
                border-radius: 3px;
                background: #1a1a24;
            }
            QCheckBox::indicator:checked {
                background: #06b6d4;
                border-color: #06b6d4;
            }
        """)
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/styled_checkbox.py
git commit -m "feat: add StyledCheckBox dark theme component"
```

### Task 2.2: 创建 agent_panel.py — 聊天时间线（核心）

**Files:**
- Create: `python3.11libs/edini/ui/agent_panel.py`

- [ ] **Step 1: 写 agent_panel.py**

```python
"""AgentPanel — Chat timeline with streaming text, tool cards, and markdown rendering."""
import html
import re
from PySide6 import QtCore, QtWidgets


class AgentPanel(QtWidgets.QWidget):
    submit_requested = QtCore.Signal(str)
    stop_requested = QtCore.Signal()

    STREAM_FLUSH_CHARS = 80
    STREAM_FLUSH_INTERVAL_MS = 80

    def __init__(self, parent=None):
        super().__init__(parent)
        self._busy = False
        self._raw_stream_text = ""
        self._streaming = False
        self._request_count = 0
        self._session_id = ""

        self._stream_flush_timer = QtCore.QTimer(self)
        self._stream_flush_timer.setSingleShot(True)
        self._stream_flush_timer.setInterval(self.STREAM_FLUSH_INTERVAL_MS)
        self._stream_flush_timer.timeout.connect(self._flush_stream)

        self._build_ui()
        self._bind_events()

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Session label
        self.session_label = QtWidgets.QLabel("会话: -")
        self.session_label.setStyleSheet("color: #71717a; font-size: 10px;")
        self.session_label.setVisible(False)
        root.addWidget(self.session_label)

        # Plan progress widget placeholder
        from edini.ui.plan_progress_widget import PlanProgressWidget
        self.plan_progress_widget = PlanProgressWidget(self)
        self.plan_progress_widget.setMaximumHeight(260)
        root.addWidget(self.plan_progress_widget)

        # Change tree placeholder
        from edini.ui.change_tree_widget import ChangeTreeWidget
        self.change_tree_widget = ChangeTreeWidget(self)
        self.change_tree_widget.setMaximumHeight(200)
        root.addWidget(self.change_tree_widget)

        # Timeline view
        self.timeline_view = QtWidgets.QTextBrowser(self)
        self.timeline_view.setReadOnly(True)
        self.timeline_view.setOpenLinks(False)
        self.timeline_view.setPlaceholderText("Edini 对话时间线将在此显示...")
        root.addWidget(self.timeline_view, 1)

        # Input row
        input_row = QtWidgets.QHBoxLayout()
        self.input_edit = QtWidgets.QPlainTextEdit(self)
        self.input_edit.setPlaceholderText("描述你希望 Edini 完成的任务...")
        self.input_edit.setFixedHeight(80)
        input_row.addWidget(self.input_edit, 1)

        action_col = QtWidgets.QVBoxLayout()
        from edini.ui.styled_checkbox import StyledCheckBox
        self.chat_only_check = StyledCheckBox("仅对话", self)
        self.send_btn = QtWidgets.QPushButton("执行", self)
        self.send_btn.setObjectName("PrimaryButton")
        self.send_btn.setMinimumWidth(96)
        action_col.addWidget(self.chat_only_check)
        action_col.addWidget(self.send_btn)
        action_col.addStretch(1)
        input_row.addLayout(action_col)
        root.addLayout(input_row)

    def _bind_events(self):
        self.send_btn.clicked.connect(self._on_send)
        self.input_edit.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.input_edit and event is not None:
            if int(event.type()) == int(QtCore.QEvent.KeyPress):
                key = int(event.key())
                if key in (int(QtCore.Qt.Key_Return), int(QtCore.Qt.Key_Enter)):
                    modifiers = event.modifiers()
                    if modifiers & (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier):
                        cursor = self.input_edit.textCursor()
                        cursor.insertText("\n")
                        self.input_edit.setTextCursor(cursor)
                        return True
                    if modifiers == QtCore.Qt.NoModifier:
                        self._on_send()
                        return True
        return super().eventFilter(watched, event)

    def _on_send(self):
        text = self.input_edit.toPlainText().strip()
        if not text or self._busy:
            return
        self.input_edit.clear()
        self._append_user_message(text)
        self._request_count += 1
        self._raw_stream_text = ""
        self._streaming = True
        self.submit_requested.emit(text)

    # ------------------------------------------------------------------
    # Public API (called by main_window)
    # ------------------------------------------------------------------

    def set_busy(self, busy: bool):
        self._busy = busy
        self.send_btn.setEnabled(not busy)

    def set_session_id(self, sid: str):
        self._session_id = sid

    def set_request_count(self, count: int):
        self._request_count = count

    def begin_assistant_message(self):
        """Start a new AI bubble for streaming."""
        self._raw_stream_text = ""
        self._streaming = True

    def append_stream_chunk(self, text: str):
        """Append a text delta to the streaming AI message."""
        self._raw_stream_text += text
        if len(self._raw_stream_text) >= self.STREAM_FLUSH_CHARS:
            self._flush_stream()
        elif not self._stream_flush_timer.isActive():
            self._stream_flush_timer.start()

    def _flush_stream(self):
        if not self._raw_stream_text:
            return
        escaped = html.escape(self._raw_stream_text)
        rendered = _format_message(escaped)
        # Replace last AI bubble content
        html_content = self.timeline_view.toHtml()
        # Simple approach: set full HTML with streaming indicator
        bubble_html = f'<div style="color:#e5e5eb;font-size:12px;line-height:1.6;padding:8px 12px;background:#1a1a24;border-radius:8px;margin:4px 40px 4px 0;">{rendered}<span style="color:#06b6d4;">▊</span></div>'
        self.timeline_view.setHtml(html_content + bubble_html)

    def finish_streaming(self):
        """Finalize the streaming message (remove cursor)."""
        self._streaming = False
        self._stream_flush_timer.stop()
        if self._raw_stream_text:
            escaped = html.escape(self._raw_stream_text)
            rendered = _format_message(escaped)
            bubble_html = f'<div style="color:#e5e5eb;font-size:12px;line-height:1.6;padding:8px 12px;background:#1a1a24;border-radius:8px;margin:4px 40px 4px 0;">{rendered}</div>'
            current = self.timeline_view.toHtml()
            self.timeline_view.setHtml(current + bubble_html)
        self._raw_stream_text = ""

    def add_tool_card(self, tool_name: str, args: dict):
        """Add a tool call card to the timeline."""
        args_str = str(args)[:200]
        card_html = (
            f'<div style="color:#67e8f9;font-size:11px;background:#0e2a2e;'
            f'border-left:3px solid #06b6d4;padding:6px 10px;margin:4px 20px 4px 0;'
            f'border-radius:4px;">'
            f'🔧 <b>{html.escape(tool_name)}</b><br>'
            f'<span style="color:#94a3b8;">{html.escape(args_str)}</span>'
            f'</div>'
        )
        current = self.timeline_view.toHtml()
        self.timeline_view.setHtml(current + card_html)

    def add_error(self, message: str):
        """Add an error banner."""
        err_html = (
            f'<div style="color:#fca5a5;font-size:11px;background:#2e1a1a;'
            f'border-left:3px solid #ef4444;padding:6px 10px;margin:4px 40px;'
            f'border-radius:4px;">'
            f'⚠️ {html.escape(message)}'
            f'</div>'
        )
        current = self.timeline_view.toHtml()
        self.timeline_view.setHtml(current + err_html)

    def add_separator(self, text: str = "── 本轮结束 ──"):
        """Add a separator line."""
        sep_html = (
            f'<div style="text-align:center;color:#52525b;font-size:10px;'
            f'margin:16px 0;border-top:1px solid #2a2a3c;padding-top:8px;">'
            f'{html.escape(text)}</div>'
        )
        current = self.timeline_view.toHtml()
        self.timeline_view.setHtml(current + sep_html)

    def clear_timeline(self):
        self.timeline_view.clear()

    def _append_user_message(self, text: str):
        """Add a user message bubble to the timeline."""
        escaped = html.escape(text)
        bubble_html = (
            f'<div style="color:#e5e5eb;font-size:12px;line-height:1.6;'
            f'padding:8px 12px;background:#1a3a5c;border-radius:8px;'
            f'margin:4px 0 4px 40px;text-align:right;">'
            f'{escaped}'
            f'</div>'
        )
        current = self.timeline_view.toHtml()
        self.timeline_view.setHtml(current + bubble_html)


def _format_message(text: str) -> str:
    """Convert plain text with markdown-ish syntax to simple HTML."""
    out = text

    # Code blocks: ``` ... ```
    out = re.sub(
        r'```(\w*)\n(.*?)```',
        r'<pre style="background:#0e0e15;color:#d4d4d4;padding:8px;'
        r'border-radius:4px;font-family:monospace;font-size:11px;'
        r'margin:4px 0;overflow-x:auto;">\2</pre>',
        out, flags=re.DOTALL,
    )

    # Inline code: `...`
    out = re.sub(
        r'`([^`]+)`',
        r'<code style="background:#1a1a24;color:#67e8f9;padding:1px 4px;'
        r'border-radius:3px;font-family:monospace;font-size:11px;">\1</code>',
        out,
    )

    # Bold: **...**
    out = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', out)

    # Newlines
    out = out.replace("\n", "<br>")

    return out
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/agent_panel.py
git commit -m "feat: add AgentPanel — chat timeline with streaming text, tool cards, markdown rendering"
```

### Task 2.3: 在主窗口中集成 AgentPanel

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py`

- [ ] **Step 1: 替换 agent_panel 占位为真实 AgentPanel + 连接信号**

在 `main_window.py` 中，将：

```python
        # Center: Agent panel placeholder
        self.agent_panel = QtWidgets.QWidget(self.main_splitter)
        self.agent_panel.setMinimumWidth(500)
        agent_layout = QtWidgets.QVBoxLayout(self.agent_panel)
        agent_layout.addWidget(QtWidgets.QLabel("Chat Timeline (TODO)"))
```

替换为：

```python
        # Center: Agent panel
        from edini.ui.agent_panel import AgentPanel
        self.agent_panel = AgentPanel(self.main_splitter)
        self.agent_panel.setMinimumWidth(500)
```

然后在 `_bind_events` 中添加：

```python
        self.agent_panel.submit_requested.connect(self._on_agent_submit)
        self._chat_runtime.stream_chunk.connect(self.agent_panel.append_stream_chunk)
        self._chat_runtime.tool_started.connect(self._on_tool_call)
```

在类中添加方法：

```python
    def _on_agent_submit(self, text: str):
        self.agent_panel.begin_assistant_message()
        self._rpc_client.send_prompt(text)

    def _on_tool_call(self, tool_name: str, tool_call_id: str, args: dict):
        self.agent_panel.add_tool_card(tool_name, args)
```

更新 `_on_agent_started`：

```python
    def _on_agent_started(self, _):
        self.agent_panel.set_busy(True)
        self.status.showMessage("Processing...")
```

更新 `_on_agent_done`：

```python
    def _on_agent_done(self, _):
        self.agent_panel.finish_streaming()
        self.agent_panel.set_busy(False)
        self.status.showMessage("Ready")
```

更新 `_on_error`：

```python
    def _on_error(self, msg: str):
        self.agent_panel.add_error(msg)
        self.agent_panel.set_busy(False)
        self.status.showMessage(f"Error: {msg}")
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/main_window.py
git commit -m "feat: integrate AgentPanel with Pi signal flow in main window"
```

---

## Phase 3: 功能面板 — History + Context + Settings

### Task 3.1: 创建 placeholder 组件（plan_progress + change_tree）

**Files:**
- Create: `python3.11libs/edini/ui/plan_progress_widget.py`
- Create: `python3.11libs/edini/ui/change_tree_widget.py`

- [ ] **Step 1: 写 plan_progress_widget.py（基础骨架）**

```python
"""Plan-Execute progress widget."""
from PySide6 import QtCore, QtWidgets


class PlanProgressWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QtWidgets.QLabel("Plan Progress")
        self._label.setStyleSheet("font-size:11px;font-weight:600;color:#a1a1aa;")
        self._label.setVisible(False)
        layout.addWidget(self._label)

        self._progress = QtWidgets.QProgressBar(self)
        self._progress.setMinimum(0)
        self._progress.setMaximum(1)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("")
        self._progress.setFixedHeight(14)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self.setVisible(False)

    def begin_plan(self, plan_id: str, strategy: str = ""):
        self._progress.setMaximum(1)
        self._progress.setValue(0)
        self._progress.setFormat("计划已创建")
        self._progress.setVisible(True)
        self._label.setVisible(True)
        self.setVisible(True)

    def set_run_progress(self, executed: int, estimated: int, stage: str = ""):
        if estimated > 0:
            self._progress.setMaximum(estimated)
            self._progress.setValue(executed)
            self._progress.setFormat(f"{executed} / ~{estimated}")

    def reset_plan_state(self):
        self._progress.setVisible(False)
        self._label.setVisible(False)
        self.setVisible(False)
```

- [ ] **Step 2: 写 change_tree_widget.py（基础骨架）**

```python
"""Change tree widget — shows node modifications made by Edini."""
from PySide6 import QtCore, QtWidgets


class ChangeTreeWidget(QtWidgets.QWidget):
    node_path_requested = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QtWidgets.QLabel("Changes")
        self._label.setStyleSheet("font-size:11px;font-weight:600;color:#a1a1aa;")
        self._label.setVisible(False)
        layout.addWidget(self._label)

        self.change_tree = QtWidgets.QTreeWidget(self)
        self.change_tree.setHeaderHidden(True)
        self.change_tree.setVisible(False)
        self.change_tree.setMaximumHeight(180)
        layout.addWidget(self.change_tree)

        self.setVisible(False)

    def add_change(self, action: str, node_path: str, detail: str):
        self._label.setVisible(True)
        self.change_tree.setVisible(True)
        self.setVisible(True)
        item = QtWidgets.QTreeWidgetItem([f"{action}: {node_path}"])
        item.setToolTip(0, detail)
        self.change_tree.addTopLevelItem(item)

    def clear_changes(self):
        self.change_tree.clear()
        self._label.setVisible(False)
        self.change_tree.setVisible(False)
        self.setVisible(False)
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/plan_progress_widget.py python3.11libs/edini/ui/change_tree_widget.py
git commit -m "feat: add PlanProgressWidget and ChangeTreeWidget placeholder components"
```

### Task 3.2: 创建 session_store.py

**Files:**
- Create: `python3.11libs/edini/ui/session_store.py`

- [ ] **Step 1: 写 session_store.py**

```python
"""Session storage — JSON file per session, local persistence."""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

SESSIONS_DIR = Path(__file__).resolve().parent.parent / "sessions"


def _ensure_dir():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def create_session(session_id: str, title: str = "New Session") -> dict:
    _ensure_dir()
    now = datetime.now().isoformat()
    record = {
        "session_id": session_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    with open(_session_path(session_id), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return record


def load_session(session_id: str) -> Optional[dict]:
    path = _session_path(session_id)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_session(record: dict):
    _ensure_dir()
    record["updated_at"] = datetime.now().isoformat()
    sid = record["session_id"]
    with open(_session_path(sid), "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)


def delete_session(session_id: str):
    path = _session_path(session_id)
    if path.exists():
        os.remove(path)


def list_sessions() -> list:
    _ensure_dir()
    result = []
    for p in sorted(SESSIONS_DIR.glob("*.json"), key=os.path.getmtime, reverse=True):
        try:
            with open(p, "r", encoding="utf-8") as f:
                record = json.load(f)
            result.append(record)
        except Exception:
            pass
    return result


def append_message(session_id: str, msg: dict):
    record = load_session(session_id)
    if record is None:
        record = create_session(session_id)
    record.setdefault("messages", []).append(msg)
    save_session(record)


def load_messages(session_id: str) -> list:
    record = load_session(session_id)
    if record is None:
        return []
    return record.get("messages", [])
```

- [ ] **Step 2: 更新 .gitignore 忽略 sessions 目录**

在 `.gitignore` 中添加 `sessions/` 行：

```bash
echo "sessions/" >> .gitignore
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/session_store.py .gitignore
git commit -m "feat: add session_store with JSON file per session persistence"
```

### Task 3.3: 创建 history_panel.py

**Files:**
- Create: `python3.11libs/edini/ui/history_panel.py`

- [ ] **Step 1: 写 history_panel.py**

```python
"""History panel — session list with create/select/delete."""
import uuid
from PySide6 import QtCore, QtWidgets
from edini.ui.session_store import list_sessions, create_session, delete_session


class HistoryPanel(QtWidgets.QWidget):
    session_selected = QtCore.Signal(str)
    session_deleted = QtCore.Signal(str)
    new_session_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QtWidgets.QLabel("History")
        title.setStyleSheet("font-size:12px;font-weight:700;color:#e5e5eb;")
        layout.addWidget(title)

        self.new_btn = QtWidgets.QPushButton("+ New Session")
        self.new_btn.setObjectName("PrimaryButton")
        layout.addWidget(self.new_btn)

        self.session_list = QtWidgets.QListWidget(self)
        self.session_list.setStyleSheet("""
            QListWidget {
                background-color: #0e0e15;
                border: none;
                color: #a1a1aa;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #1a1a24;
            }
            QListWidget::item:selected {
                background-color: rgba(6, 182, 212, 0.15);
                color: #67e8f9;
            }
            QListWidget::item:hover {
                background-color: #1a1a24;
            }
        """)
        layout.addWidget(self.session_list, 1)

        self._bind()

    def _bind(self):
        self.new_btn.clicked.connect(self._on_new)
        self.session_list.itemClicked.connect(self._on_select)
        self.session_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.session_list.customContextMenuRequested.connect(self._on_context_menu)

    def _on_new(self):
        self.new_session_requested.emit()

    def _on_select(self, item):
        if item and item.data(QtCore.Qt.UserRole):
            self.session_selected.emit(item.data(QtCore.Qt.UserRole))

    def _on_context_menu(self, pos):
        item = self.session_list.itemAt(pos)
        if not item:
            return
        sid = item.data(QtCore.Qt.UserRole)
        if not sid:
            return
        menu = QtWidgets.QMenu(self)
        delete_action = menu.addAction("删除")
        action = menu.exec(self.session_list.mapToGlobal(pos))
        if action == delete_action:
            delete_session(sid)
            self.session_deleted.emit(sid)

    def add_session(self, sid: str, title: str):
        item = QtWidgets.QListWidgetItem(title)
        item.setData(QtCore.Qt.UserRole, sid)
        self.session_list.insertItem(0, item)

    def remove_session(self, sid: str):
        for i in range(self.session_list.count()):
            item = self.session_list.item(i)
            if item and item.data(QtCore.Qt.UserRole) == sid:
                self.session_list.takeItem(i)
                break

    def load_sessions(self):
        self.session_list.clear()
        sessions = list_sessions()
        for s in sessions:
            self.add_session(s["session_id"], s.get("title", "New Session"))
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/history_panel.py
git commit -m "feat: add HistoryPanel with session CRUD and context menu delete"
```

### Task 3.4: 创建 context_panel.py

**Files:**
- Create: `python3.11libs/edini/ui/context_panel.py`

- [ ] **Step 1: 写 context_panel.py**

```python
"""Context panel — Pi status (top) + Scene info (bottom)."""
import importlib
from PySide6 import QtCore, QtWidgets

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None


class ContextPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        # ── Pi Status ──
        pi_title = QtWidgets.QLabel("Pi Status")
        pi_title.setStyleSheet("font-size:11px;font-weight:600;color:#71717a;")
        layout.addWidget(pi_title)

        self.panel = QtWidgets.QWidget(self)
        pi_layout = QtWidgets.QVBoxLayout(self.panel)
        pi_layout.setContentsMargins(0, 0, 0, 0)
        pi_layout.setSpacing(4)

        self.status_label = QtWidgets.QLabel("⬤ Connecting...")
        self.status_label.setStyleSheet("color:#a1a1aa;font-size:12px;")
        pi_layout.addWidget(self.status_label)

        self.provider_model_label = QtWidgets.QLabel("Model: -")
        self.provider_model_label.setStyleSheet("color:#71717a;font-size:11px;")
        pi_layout.addWidget(self.provider_model_label)

        pi_layout.addWidget(_section_divider())

        self.token_in_label = QtWidgets.QLabel("Input: -")
        self.token_out_label = QtWidgets.QLabel("Output: -")
        self.token_total_label = QtWidgets.QLabel("Total: -")
        self.cost_label = QtWidgets.QLabel("Cost: -")
        for lbl in [self.token_in_label, self.token_out_label, self.token_total_label, self.cost_label]:
            lbl.setStyleSheet("color:#71717a;font-size:11px;")
            pi_layout.addWidget(lbl)

        pi_layout.addWidget(_section_divider())

        self.ctx_label = QtWidgets.QLabel("Context: -")
        self.ctx_label.setStyleSheet("color:#71717a;font-size:11px;")
        pi_layout.addWidget(self.ctx_label)

        self.ctx_progress = QtWidgets.QProgressBar(self)
        self.ctx_progress.setMinimum(0)
        self.ctx_progress.setMaximum(100)
        self.ctx_progress.setValue(0)
        self.ctx_progress.setTextVisible(True)
        self.ctx_progress.setFormat("0%")
        self.ctx_progress.setFixedHeight(12)
        pi_layout.addWidget(self.ctx_progress)

        self.stream_rate_label = QtWidgets.QLabel("Stream Rate: -")
        self.stream_rate_label.setStyleSheet("color:#71717a;font-size:11px;")
        pi_layout.addWidget(self.stream_rate_label)

        layout.addWidget(self.panel)

        # ── Scene Info ──
        layout.addWidget(_section_divider())

        scene_title = QtWidgets.QLabel("Scene Info")
        scene_title.setStyleSheet("font-size:11px;font-weight:600;color:#71717a;")
        layout.addWidget(scene_title)

        self.scene_panel = QtWidgets.QWidget(self)
        scene_layout = QtWidgets.QVBoxLayout(self.scene_panel)
        scene_layout.setContentsMargins(0, 0, 0, 0)
        scene_layout.setSpacing(4)

        self.hip_label = QtWidgets.QLabel("HIP: -")
        self.path_label = QtWidgets.QLabel("Path: -")
        self.selected_label = QtWidgets.QLabel("Selected: -")
        self.node_count_label = QtWidgets.QLabel("Nodes: -")
        for lbl in [self.hip_label, self.path_label, self.selected_label, self.node_count_label]:
            lbl.setStyleSheet("color:#71717a;font-size:11px;")
            scene_layout.addWidget(lbl)

        self.refresh_btn = QtWidgets.QPushButton("⟳ Refresh")
        self.refresh_btn.setObjectName("GhostButton")
        self.refresh_btn.clicked.connect(self.refresh_scene_info)
        scene_layout.addWidget(self.refresh_btn)

        layout.addWidget(self.scene_panel)
        layout.addStretch(1)

    # ── Pi Status updates ──

    def set_pi_status(self, status: str):
        colors = {
            "connected": "#16a34a",
            "connecting": "#d97706",
            "disconnected": "#ef4444",
            "error": "#ef4444",
        }
        color = colors.get(status, "#71717a")
        self.status_label.setText(f"<span style='color:{color};'>●</span> {status.title()}")

    def set_provider_model(self, provider: str, model: str):
        self.provider_model_label.setText(f"Model: {provider}/{model}")

    def set_usage(self, stats: dict):
        tokens = stats.get("tokens", {})
        cost = stats.get("cost", 0)
        ctx = stats.get("contextUsage")
        self.token_in_label.setText(f"Input: {tokens.get('input', 0):,}")
        self.token_out_label.setText(f"Output: {tokens.get('output', 0):,}")
        self.token_total_label.setText(f"Total: {tokens.get('total', 0):,}")
        self.cost_label.setText(f"Cost: ${cost:.4f}" if cost else "Cost: -")
        if ctx:
            pct = ctx.get("percent", 0)
            self.ctx_progress.setValue(int(pct))
            self.ctx_progress.setFormat(f"{pct}%")
            self.ctx_label.setText(f"Context: {pct}% used")

    def set_stream_rate(self, rate: float):
        self.stream_rate_label.setText(f"Stream Rate: {rate:.0f} tok/s")

    # ── Scene Info ──

    def refresh_scene_info(self):
        if hou is None:
            return
        try:
            hip = hou.hipFile.name() or "Untitled"
            self.hip_label.setText(f"HIP: {hip}")
            pwd = hou.pwd()
            self.path_label.setText(f"Path: {pwd.path()}" if pwd else "Path: -")

            sel = hou.selectedNodes()
            if sel:
                n = sel[0]
                children = len(n.allSubChildren())
                self.selected_label.setText(f"Selected: {n.path()} ({n.type().name()}, {children} children)")
            else:
                self.selected_label.setText("Selected: -")

            root = hou.node("/")
            count = len(root.allSubChildren()) if root else 0
            self.node_count_label.setText(f"Nodes: {count}")
        except Exception:
            pass


def _section_divider():
    div = QtWidgets.QFrame()
    div.setFrameShape(QtWidgets.QFrame.HLine)
    div.setStyleSheet("border:none;border-top:1px solid #2a2a3c;margin:4px 0;")
    return div
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/context_panel.py
git commit -m "feat: add ContextPanel with Pi status (top) and Scene info (bottom)"
```

### Task 3.5: 在主窗口中集成 HistoryPanel + ContextPanel

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py`

- [ ] **Step 1: 替换 history_panel 占位为真实组件**

将 `main_window.py` 中 `_build_ui` 的：

```python
        # Left: History placeholder
        self.history_panel = QtWidgets.QWidget(self.main_splitter)
        self.history_panel.setMinimumWidth(200)
        self.history_panel.setMaximumWidth(260)
        history_layout = QtWidgets.QVBoxLayout(self.history_panel)
        history_layout.addWidget(QtWidgets.QLabel("History (TODO)"))
```

替换为：

```python
        # Left: History panel
        from edini.ui.history_panel import HistoryPanel
        self.history_panel = HistoryPanel(self.main_splitter)
        self.history_panel.setMinimumWidth(200)
        self.history_panel.setMaximumWidth(260)
```

将右侧 context 占位替换为：

```python
        # Right: Context panel
        from edini.ui.context_panel import ContextPanel
        self.context_panel = ContextPanel(self.main_splitter)
        self.context_panel.setMinimumWidth(340)
        self.context_panel.setMaximumWidth(400)
```

- [ ] **Step 2: 添加会话管理和场景刷新信号连接**

在 `_bind_events` 中添加：

```python
        self.history_panel.new_session_requested.connect(self._on_new_session)
        self.history_panel.session_selected.connect(self._on_session_selected)
        self.history_panel.session_deleted.connect(self._on_session_deleted)

        # Scene refresh timer
        self._scene_timer = QtCore.QTimer(self)
        self._scene_timer.setInterval(3000)
        self._scene_timer.timeout.connect(self.context_panel.refresh_scene_info)
        self._scene_timer.start()
```

在类中添加方法：

```python
    def _on_new_session(self):
        import uuid
        from edini.ui.session_store import create_session, list_sessions
        sid = "sess-" + uuid.uuid4().hex[:8]
        create_session(sid, "New Session")
        self._current_session_id = sid
        self.agent_panel.clear_timeline()
        self.history_panel.load_sessions()
        self.agent_panel.set_session_id(sid)

    def _on_session_selected(self, sid: str):
        from edini.ui.session_store import load_messages
        self._current_session_id = sid
        self.agent_panel.clear_timeline()
        # Render loaded messages (simplified: just show as text)
        msgs = load_messages(sid)
        for m in msgs:
            if m.get("role") == "user":
                self.agent_panel._append_user_message(m.get("content", ""))
            elif m.get("role") == "assistant":
                self.agent_panel._append_assistant_message(m.get("content", ""))
        self.agent_panel.set_session_id(sid)

    def _on_session_deleted(self, sid: str):
        self.history_panel.remove_session(sid)
        if sid == self._current_session_id:
            self._current_session_id = ""
            self.agent_panel.clear_timeline()
```

更新 `_bootstrap`：

```python
    def _bootstrap(self):
        self._tool_executor.start()
        self._rpc_client.start()
        self.history_panel.load_sessions()
        self.context_panel.refresh_scene_info()
```

更新 `_on_stats_updated` 信号连接和 `_on_status_changed`：

在 `_bind_events` 中添加：

```python
        self._chat_runtime.stats_updated.connect(self.context_panel.set_usage)
```

更新 `_on_status_changed`：

```python
    def _on_status_changed(self, status: str):
        self.context_panel.set_pi_status(status)
        self.status.showMessage(f"Pi: {status}")
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/main_window.py
git commit -m "feat: integrate HistoryPanel, ContextPanel, and session management in main window"
```

---

## Phase 4: 设置 + 打磨

### Task 4.1: 创建 settings_dialog.py

**Files:**
- Create: `python3.11libs/edini/ui/settings_dialog.py`

- [ ] **Step 1: 写 settings_dialog.py**

```python
"""Settings dialog — provider config and theme selection."""
from PySide6 import QtCore, QtWidgets
from edini.config import get_settings, save_settings
from edini.ui.theme import THEME_COLORS, get_theme_color, set_theme_color


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edini Settings")
        self.setMinimumWidth(440)
        self.setStyleSheet("""
            QDialog { background-color: #111118; }
            QLabel { color: #e5e5eb; font-size: 12px; }
            QLineEdit {
                background-color: #1a1a24;
                color: #e5e5eb;
                border: 1px solid #2a2a3c;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: #06b6d4; }
            QComboBox {
                background-color: #1a1a24;
                color: #e5e5eb;
                border: 1px solid #2a2a3c;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
            }
        """)

        settings = get_settings()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)

        # Tabs
        tabs = QtWidgets.QTabWidget(self)
        tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #2a2a3c; background: #0e0e15; }
            QTabBar::tab { background: #1a1a24; color: #71717a; padding: 8px 16px; }
            QTabBar::tab:selected { background: #0e0e15; color: #06b6d4; }
        """)

        # --- Provider Tab ---
        provider_tab = QtWidgets.QWidget()
        provider_form = QtWidgets.QFormLayout(provider_tab)
        provider_form.setSpacing(8)

        self._api_key = QtWidgets.QLineEdit()
        self._api_key.setEchoMode(QtWidgets.QLineEdit.Password)
        self._api_key.setText(settings.get("api_key", ""))
        provider_form.addRow("API Key:", self._api_key)

        self._provider = QtWidgets.QLineEdit()
        self._provider.setText(settings.get("provider", "deepseek"))
        provider_form.addRow("Provider:", self._provider)

        self._model_id = QtWidgets.QLineEdit()
        self._model_id.setText(settings.get("model_id", "deepseek-chat"))
        provider_form.addRow("Model ID:", self._model_id)

        tabs.addTab(provider_tab, "Provider")

        # --- Appearance Tab ---
        app_tab = QtWidgets.QWidget()
        app_form = QtWidgets.QFormLayout(app_tab)
        app_form.setSpacing(8)

        self._theme_combo = QtWidgets.QComboBox()
        current_theme = get_theme_color()
        for key, info in THEME_COLORS.items():
            self._theme_combo.addItem(info["name"], key)
            if key == current_theme:
                self._theme_combo.setCurrentIndex(self._theme_combo.count() - 1)
        app_form.addRow("Theme:", self._theme_combo)

        self._font_scale = QtWidgets.QComboBox()
        for val in ["0.8", "0.9", "1.0", "1.1", "1.2", "1.3", "1.4"]:
            self._font_scale.addItem(val)
        self._font_scale.setCurrentText("1.0")
        app_form.addRow("Font Scale:", self._font_scale)

        tabs.addTab(app_tab, "Appearance")

        layout.addWidget(tabs)

        # Buttons
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QtWidgets.QPushButton("Save")
        ok_btn.setObjectName("PrimaryButton")
        ok_btn.clicked.connect(self._on_save)
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _on_save(self):
        # Save provider settings
        save_settings({
            "api_key": self._api_key.text().strip(),
            "provider": self._provider.text().strip(),
            "model_id": self._model_id.text().strip(),
        })
        # Save theme
        key = self._theme_combo.currentData()
        if key:
            set_theme_color(key)
        self.accept()
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/settings_dialog.py
git commit -m "feat: add SettingsDialog with Provider and Appearance tabs"
```

### Task 4.2: 创建 hotkey.py 事件过滤器

**Files:**
- Create: `python3.11libs/edini/ui/hotkey.py`

- [ ] **Step 1: 写 hotkey.py**

```python
"""Global hotkey event filter for Alt+Shift+E smart launcher."""
import importlib
from PySide6 import QtCore, QtWidgets

try:
    hou = importlib.import_module("hou")
except Exception:
    hou = None

_filter_instance = None


def install_event_filter():
    global _filter_instance
    if _filter_instance is not None:
        return True
    if hou is None:
        return False
    try:
        app = QtWidgets.QApplication.instance()
    except Exception:
        return False
    _filter_instance = _HotkeyFilter()
    app.installEventFilter(_filter_instance)
    return True


class _HotkeyFilter(QtCore.QObject):
    def eventFilter(self, watched, event):
        if event.type() == QtCore.QEvent.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if (
                key == QtCore.Qt.Key_E
                and mods & QtCore.Qt.AltModifier
                and mods & QtCore.Qt.ShiftModifier
            ):
                from edini.ui import open_chat_window
                open_chat_window(toggle=True)
                return True
        return False
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/hotkey.py
git commit -m "feat: add Alt+Shift+E global hotkey event filter for Edini"
```

### Task 4.3: 在主窗口中集成设置对话框 + 热键

**Files:**
- Modify: `python3.11libs/edini/ui/main_window.py`

- [ ] **Step 1: 在 main_window.py 的 _bootstrap 中安装热键**

```python
    def _bootstrap(self):
        self._tool_executor.start()
        self._rpc_client.start()
        self.history_panel.load_sessions()
        self.context_panel.refresh_scene_info()
        # Install hotkey
        from edini.ui.hotkey import install_event_filter
        install_event_filter()
```

- [ ] **Step 2: Commit**

```bash
git add python3.11libs/edini/ui/main_window.py
git commit -m "feat: install Alt+Shift+E hotkey on window bootstrap"
```

### Task 4.4: 更新 wiki 文档（保存开发进度）

- [ ] **Step 1: 更新 wiki/pages/progress.md**

在"近期关键节点"中添加新条目：

```markdown
<div class="timeline-item timeline-done">
  <div class="timeline-date">2026-06-03</div>
  <div class="timeline-card">
    <div class="timeline-card-header">
      <span class="timeline-title">UI 重构：Houdini 原生菜单 + 三栏高级面板</span>
      <span class="status-tag status-done">完成</span>
    </div>
    <div class="timeline-summary">参照 EEEAi_Houdini 架构，将 Edini 重构为 Houdini 原生集成：python3.11libs 目录 + MainMenuCommon.xml 菜单注册 + Houdini packages JSON。三栏 QSplitter 布局（History | Chat Timeline | Pi+Scene Context），暗色主题系统（4 色霓虹预设 + 字体缩放），Pi JSON-RPC 事件完整 UI 映射（流式文本、tool card、token/成本、上下文进度条），会话历史本地持久化，Alt+Shift+E 热键。原有 rpc_client/tool_executor/node_utils 保留不变。</div>
    <div class="timeline-tags">
      <span>PySide6</span><span>QMainWindow</span><span>MainMenuCommon.xml</span><span>三栏布局</span><span>暗色主题</span><span>Pi面板</span><span>会话管理</span><span>热键</span>
    </div>
  </div>
</div>
```

- [ ] **Step 2: 重新构建 wiki HTML**

```bash
cd wiki && python scripts/build.py
```

- [ ] **Step 3: Commit**

```bash
git add wiki/pages/progress.md wiki/html/ docs/superpowers/
git commit -m "docs: update wiki with UI redesign completion"
```

### Task 4.5: 最终集成验证

- [ ] **Step 1: 测试完整导入链**

```bash
cd F:/zz/Edini && python -c "
import sys
sys.path.insert(0, 'python3.11libs')

# Test theme
from edini.ui.theme import get_active_theme, THEME_COLORS
print('Theme:', get_active_theme()['name'])
print('Available themes:', list(THEME_COLORS.keys()))

# Test all UI modules import
from edini.ui.main_window import EdiniMainWindow
from edini.ui.agent_panel import AgentPanel
from edini.ui.history_panel import HistoryPanel
from edini.ui.context_panel import ContextPanel
from edini.ui.settings_dialog import SettingsDialog
from edini.ui.chat_runtime import ChatRuntime
from edini.ui.session_store import create_session, list_sessions
from edini.ui.windows import open_chat_window, open_settings
from edini.ui.hotkey import install_event_filter
from edini.ui.styled_checkbox import StyledCheckBox
from edini.ui.plan_progress_widget import PlanProgressWidget
from edini.ui.change_tree_widget import ChangeTreeWidget

print('All imports OK!')
"
```
Expected: "All imports OK!" 无报错。

- [ ] **Step 2: Commit final validation**

```bash
git add -A
git commit -m "verify: all UI modules import successfully"
```

---

## 总结

| Phase | 内容 | Task 数 | 预估工作量 |
|-------|------|---------|-----------|
| P0 | 目录迁移 + Houdini 包注册 | 5 | 30 min |
| P1 | theme + chat_runtime + main_window + windows + agent_panel | 5 | 60 min |
| P2 | 功能面板 (history + context + session + settings) | 5 | 60 min |
| P3 | 打磨 (hotkey + wiki + 验证) | 5 | 30 min |
| **总计** | | **20** | **~3 hours** |
