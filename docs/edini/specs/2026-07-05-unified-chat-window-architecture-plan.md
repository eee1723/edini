# 统一对话窗口架构 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把主 Agent 窗口与 Project HDA 对话窗口重构为共享组件库 + 装配器架构,让两窗口共享 90% 能力、表达 10% 差异,且 HDA 窗口从"简陋 QDialog"升级为完整三面板(版本列表 + 对话 + status/知识区)。

**Architecture:** 方案 A —— 扁平组件库 `edini/ui/components/` + 装配层 `edini/ui/chat/`(ChatRuntime + ChatWindowShell + ScopeConfig + BaseChatDriver)+ status 子系统 `edini/ui/status/`。`ChatRuntime` 成为唯一 RPC 适配层(两窗口都不直连 RpcClient)。差异通过 `ScopeConfig`(主题色/header/能力开关)注入,组件内部零分支。6 阶段渐进迁移,每阶段可交付、可回滚、冒烟测试把关。

**Tech Stack:** PySide6 (Qt for Python, Houdini 21 内置) · Python 3.11 · pytest(无 pytest-qt,集成测试用 mock + 信号断言)· vendored mistune 3.2.1 · Pi RPC(stdin/stdout JSON-RPC 子进程)。

**关联 spec:** `docs/edini/specs/2026-07-05-unified-chat-window-architecture-design.md`

---

## 测试约定(全计划通用)

本项目**无 pytest-qt / QtBot**。测试分两类:

**A. 纯逻辑单元测试(无需 Qt 事件循环):** 直接 import 被测类,构造对象,调方法,断言。PySide6 的 `QObject`/`QFrame` 可在无 `QApplication` 时构造用于纯数据方法测试(但 widget 显示类需 `QApplication`)。涉及 widget 显示的测试,在文件头加:
```python
from PySide6.QtWidgets import QApplication
import sys
_app = QApplication.instance() or QApplication(sys.argv)
```

**B. 集成测试(Qt 信号链):** 用 `QtSignalSpy`(PySide6 自带 `QtCore.Signal`)或手动连接信号到 list 收集。需 `QApplication`。

**hou mock:** 凡 import hou 的模块,测试文件头加:
```python
import sys
from tests.mock_hou import create_mock_hou
sys.modules["hou"] = create_mock_hou()
```

**运行测试:** `python -m pytest tests/test_xxx.py -v`(在项目根,`pytest.ini` 的 `testpaths = tests`,conftest 已把 `python3.11libs` 加进 path)。

---

## 阶段 0:现状基线 + 测试脚手架

### Task 0.1:Qt 测试 fixture 工具

**Files:**
- Create: `tests/qt_helpers.py`
- Test: (本文件即工具)

- [ ] **Step 1:写 fixture 工具**

```python
"""Qt test helpers — QApplication singleton + signal spy."""
import sys
from PySide6 import QtCore, QtWidgets

_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)


def qapp() -> QtWidgets.QApplication:
    """Return the shared QApplication (created once on import)."""
    return _app


class SignalSpy:
    """Collect emissions of a Qt signal into a list."""
    def __init__(self, signal: QtCore.SignalInstance):
        self.calls: list = []
        signal.connect(self._on)

    def _on(self, *args):
        self.calls.append(args[0] if len(args) == 1 else args)

    def __len__(self):
        return len(self.calls)
```

- [ ] **Step 2:验证 import**

Run: `python -m pytest tests/qt_helpers.py --collect-only -q 2>&1 | head -5`
Expected: 无 error(collect 忽略非 test 文件,但不该报 import error)

- [ ] **Step 3:Commit**

```bash
git add tests/qt_helpers.py
git commit -m "test: add Qt test helpers (QApplication singleton + SignalSpy)"
```

---

### Task 0.2:Bubble markdown 渲染冒烟测试(基线快照)

**Files:**
- Test: `tests/test_bubble_render.py`

**目的:** 锁定 `_AiBubble` 当前 markdown 渲染行为,阶段 1 合并 bubble 后必须保持一致。

- [ ] **Step 1:写测试**

```python
"""Baseline snapshot: _AiBubble markdown rendering behavior.

Locks the contract so the Stage-1 bubble merge cannot silently change
rendering. Tests the format functions directly (no QApplication needed
for pure string functions).
"""
import sys
sys.path.insert(0, "python3.11libs")

from edini.ui.agent_panel import _format_full, _format_lite


def test_format_full_renders_code_block():
    out = _format_full("```python\nprint('hi')\n```")
    assert "<code" in out or "<pre" in out
    assert "print" in out


def test_format_full_renders_bold():
    out = _format_full("**bold**")
    assert "<strong>bold</strong>" in out


def test_format_lite_does_not_crash_on_complex_input():
    # lite is a degraded renderer; just assert it returns a string
    out = _format_lite("# title\n- item\n```code\n```")
    assert isinstance(out, str)
    assert len(out) > 0


def test_format_full_handles_empty():
    assert isinstance(_format_full(""), str)


def test_format_full_handles_plain_text():
    out = _format_full("just plain text")
    assert "just plain text" in out
```

- [ ] **Step 2:运行,确认全绿**

Run: `python -m pytest tests/test_bubble_render.py -v`
Expected: 5 passed

- [ ] **Step 3:Commit**

```bash
git add tests/test_bubble_render.py
git commit -m "test: baseline bubble markdown rendering snapshot (Stage 0)"
```

---

### Task 0.3:ChatRuntime 信号透传基线测试

**Files:**
- Test: `tests/test_chat_runtime.py`

**目的:** 锁定 ChatRuntime 当前行为,阶段 3 增强后这些必须保持。

- [ ] **Step 1:写测试**

```python
"""ChatRuntime signal-adapter baseline."""
import sys
sys.path.insert(0, "python3.11libs")

from PySide6 import QtCore
from tests.qt_helpers import qapp, SignalSpy

from edini.ui.chat_runtime import ChatRuntime


class _FakeRpc(QtCore.QObject):
    """Minimal stand-in exposing only the signals ChatRuntime binds to."""
    text_delta = QtCore.Signal(str)
    thinking_delta = QtCore.Signal(str)
    tool_call = QtCore.Signal(str, str, object)
    tool_result = QtCore.Signal(str, str, str)
    agent_started = QtCore.Signal()
    agent_finished = QtCore.Signal()
    error_occurred = QtCore.Signal(str)
    stats_updated = QtCore.Signal(object)


def test_text_delta_becomes_stream_chunk():
    rpc = _FakeRpc()
    rt = ChatRuntime(rpc)
    spy = SignalSpy(rt.stream_chunk)
    rpc.text_delta.emit("hello")
    assert spy.calls == ["hello"]


def test_agent_started_emits_started_and_busy_true():
    rpc = _FakeRpc()
    rt = ChatRuntime(rpc)
    started_spy = SignalSpy(rt.started)
    busy_spy = SignalSpy(rt.busy_changed)
    rpc.agent_started.emit()
    assert len(started_spy) == 1
    assert busy_spy.calls == [True]


def test_agent_finished_emits_completed_and_busy_false():
    rpc = _FakeRpc()
    rt = ChatRuntime(rpc)
    completed_spy = SignalSpy(rt.completed)
    busy_spy = SignalSpy(rt.busy_changed)
    rpc.agent_finished.emit()
    assert len(completed_spy) == 1
    assert busy_spy.calls == [False]


def test_stats_passthrough():
    rpc = _FakeRpc()
    rt = ChatRuntime(rpc)
    spy = SignalSpy(rt.stats_updated)
    rpc.stats_updated.emit({"tokens": {"total": 100}})
    assert spy.calls == [{"tokens": {"total": 100}}]
```

- [ ] **Step 2:运行**

Run: `python -m pytest tests/test_chat_runtime.py -v`
Expected: 4 passed

- [ ] **Step 3:Commit**

```bash
git add tests/test_chat_runtime.py
git commit -m "test: ChatRuntime signal-adapter baseline (Stage 0)"
```

---

## 阶段 1:抽取叶子组件库(无行为变化)

**原则:** 先纯搬迁(抽到新文件 + agent_panel 改 import),行为零变化;bubble 合并作为本阶段最后子步。

### Task 1.1:创建 components 包 + markdown 模块

**Files:**
- Create: `python3.11libs/edini/ui/components/__init__.py`
- Create: `python3.11libs/edini/ui/components/markdown.py`
- Modify: `python3.11libs/edini/ui/agent_panel.py`(改 import,删定义)
- Test: `tests/test_bubble_render.py`(已存在,改为从新模块 import)

- [ ] **Step 1:创建 `components/__init__.py`**

```python
"""Reusable leaf widgets for chat windows. No RpcClient/ChatRuntime deps.

Layering rule (enforced by tests/test_layering.py): modules in this package
MUST NOT import edini.rpc_client, edini.ui.chat, or edini.main_window.
"""
```

- [ ] **Step 2:把 markdown 代码搬到 `components/markdown.py`**

从 `agent_panel.py:1630-1776` 整段搬出(包括 `import mistune`、`_DarkRenderer`、单例 parser、`_format_lite`、`_format_full`、`_format_inline_fallback`)。`components/markdown.py` 完整内容 = agent_panel.py 当前的 1630-1776 行,但 import 头部改为:

```python
"""Markdown rendering: dark-themed mistune renderer + lite/full formatters."""
import mistune as _mistune
from mistune import HTMLRenderer as _HTMLRenderer

# ... (原 _DarkRenderer, _md_parser, _format_lite, _format_full, _format_inline_fallback 原样搬入) ...
```

- [ ] **Step 3:在 `agent_panel.py` 替换原定义为 re-export**

把 `agent_panel.py` 的 1630-1776 行替换为:

```python
# Markdown rendering now lives in edini.ui.components.markdown.
# Re-exported here for backward compatibility during staged migration.
from edini.ui.components.markdown import (
    _format_lite, _format_full, _DarkRenderer,
)
```

- [ ] **Step 4:更新 test 改从新模块 import**

修改 `tests/test_bubble_render.py` 的 import:

```python
from edini.ui.components.markdown import _format_full, _format_lite
```

- [ ] **Step 5:运行测试**

Run: `python -m pytest tests/test_bubble_render.py -v`
Expected: 5 passed(行为不变)

- [ ] **Step 6:Commit**

```bash
git add python3.11libs/edini/ui/components/__init__.py \
        python3.11libs/edini/ui/components/markdown.py \
        python3.11libs/edini/ui/agent_panel.py \
        tests/test_bubble_render.py
git commit -m "refactor(components): extract markdown renderer to components/markdown.py"
```

---

### Task 1.2:抽取 TimelineView

**Files:**
- Create: `python3.11libs/edini/ui/components/timeline_view.py`
- Modify: `python3.11libs/edini/ui/agent_panel.py`(改 import)

- [ ] **Step 1:搬到新文件**

把 `agent_panel.py` 中 `_TimelineView` 类(约 393-619 行,含所有 smart-scroll 方法)整段搬到 `components/timeline_view.py`。头部:

```python
"""TimelineView — scrollable chat bubble container with smart auto-scroll."""
from PySide6 import QtCore, QtGui, QtWidgets
from edini.ui.theme import fs
```

注意:它引用的 `_load_thumb_pixmap`、`_truncate_name`、`_ClickableCard` 等辅助(用于 `_UserBubble` 内部)留在 agent_panel,因为 timeline 本身不直接用它们。

- [ ] **Step 2:agent_panel.py 改 import**

在 agent_panel.py 顶部加:
```python
from edini.ui.components.timeline_view import _TimelineView
```
删除 agent_panel.py 内 `_TimelineView` 的类定义。

- [ ] **Step 3:验证 import 不破**

Run: `python -c "import sys; sys.path.insert(0,'python3.11libs'); from edini.ui.agent_panel import _TimelineView; print('ok')"`
Expected: `ok`

- [ ] **Step 4:运行 bubble 测试(间接验证 import 链)**

Run: `python -m pytest tests/test_bubble_render.py -v`
Expected: 5 passed

- [ ] **Step 5:Commit**

```bash
git add python3.11libs/edini/ui/components/timeline_view.py \
        python3.11libs/edini/ui/agent_panel.py
git commit -m "refactor(components): extract TimelineView to components/"
```

---

### Task 1.3:抽取 bubbles(UserBubble + AiBubble,先不合并)

**Files:**
- Create: `python3.11libs/edini/ui/components/bubbles.py`
- Modify: `python3.11libs/edini/ui/agent_panel.py`
- Test: `tests/test_bubbles.py`

- [ ] **Step 1:先写测试,验证抽取后行为**

```python
"""Bubble widget behavior — verify extraction preserved behavior."""
import sys, os
sys.path.insert(0, "python3.11libs")
from tests.qt_helpers import qapp
from edini.ui.components.bubbles import UserBubble, AiBubble


def test_user_bubble_stores_text():
    b = UserBubble("hello world")
    assert "hello world" in b._label.text()


def test_aibubble_finalize_renders_markdown():
    b = AiBubble()
    b._raw_text = "**bold**"
    b.finalize()
    txt = b._label.text()
    assert "<strong>bold</strong>" in txt


def test_aibubble_update_streaming_uses_lite():
    b = AiBubble()
    b.update_streaming("**x**")
    # streaming mode should NOT yet show full-rendered <strong> (lite is degraded)
    # but raw must be stored
    assert b._raw_text == "**x**"
```

- [ ] **Step 2:运行,确认失败(模块尚不存在)**

Run: `python -m pytest tests/test_bubbles.py -v`
Expected: FAIL — `ModuleNotFoundError: edini.ui.components.bubbles`

- [ ] **Step 3:创建 bubbles.py**

把 `agent_panel.py` 的 `_UserBubble`(181-287 行)、`_AiBubble`(289-346 行)、以及它们依赖的 style helpers(`_user_bubble_bg`/`_ai_bubble_bg`/`_ai_bubble_style`/`_user_bubble_style`)、`_load_thumb_pixmap`/`_truncate_name`/`_ClickableCard` 搬到 `components/bubbles.py`。

**公开为非下划线名(Public API):**
```python
class UserBubble(QtWidgets.QFrame): ...      # 原 _UserBubble
class AiBubble(QtWidgets.QFrame): ...        # 原 _AiBubble

# 向后兼容别名(阶段 6 移除)
_UserBubble = UserBubble
_AiBubble = AiBubble
```

`_ai_bubble_style`、`_format_lite`、`_format_full` 从新位置 import:
```python
from edini.ui.components.markdown import _format_lite, _format_full
```

- [ ] **Step 4:agent_panel.py 改 import**

```python
from edini.ui.components.bubbles import (
    UserBubble, AiBubble, _UserBubble, _AiBubble,
    _user_bubble_bg, _ai_bubble_bg, _ai_bubble_style,
    _ClickableCard, _load_thumb_pixmap, _truncate_name,
)
```
删除 agent_panel.py 内这些类/函数的定义。

- [ ] **Step 5:运行测试**

Run: `python -m pytest tests/test_bubbles.py tests/test_bubble_render.py -v`
Expected: 8 passed

- [ ] **Step 6:Commit**

```bash
git add python3.11libs/edini/ui/components/bubbles.py \
        python3.11libs/edini/ui/agent_panel.py \
        tests/test_bubbles.py
git commit -m "refactor(components): extract UserBubble + AiBubble to components/"
```

---

### Task 1.4:抽取 ThinkingPanel + ToolPanel + ToolCardWidget

**Files:**
- Create: `python3.11libs/edini/ui/components/thinking_panel.py`
- Create: `python3.11libs/edini/ui/components/tool_panel.py`
- Modify: `python3.11libs/edini/ui/agent_panel.py`

**说明:** 当前 thinking_panel 和 tool_panel 是在 `AgentPanel._build_ui()` 里内联构造的 `QFrame`,没有独立类。本任务把它们提升为独立类,封装内部结构(toggle/header/view),暴露简单接口。

- [ ] **Step 1:写 ThinkingPanel + ToolPanel 测试**

`tests/test_panels.py`:
```python
"""ThinkingPanel + ToolPanel extracted classes."""
import sys
sys.path.insert(0, "python3.11libs")
from tests.qt_helpers import qapp
from edini.ui.components.thinking_panel import ThinkingPanel
from edini.ui.components.tool_panel import ToolPanel, ToolCardWidget


def test_thinking_panel_starts_collapsed():
    p = ThinkingPanel()
    assert p.is_expanded() is False
    p.append("thinking chunk")
    assert "(1)" in p.toggle_text()


def test_tool_panel_adds_card():
    p = ToolPanel()
    p.on_tool_started("build_node", "call_1", {"path": "/obj/x"})
    assert "build_node" in p.card_names()
    p.on_tool_completed("build_node", "call_1", "done")
    # card status should update (not crash)
    assert "build_node" in p.card_names()
```

- [ ] **Step 2:运行,确认失败**

Run: `python -m pytest tests/test_panels.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3:实现 ThinkingPanel**

`components/thinking_panel.py` — 把 `AgentPanel._build_ui()` 里构造 `_thinking_panel`/`_thinking_toggle`/`_thinking_view` 的代码(约 684-717 行)封装为类:

```python
"""ThinkingPanel — collapsible reasoning display."""
from PySide6 import QtCore, QtWidgets
from edini.ui.theme import fs


class ThinkingPanel(QtWidgets.QFrame):
    """Collapsible panel showing accumulated reasoning text.

    Collapsed by default (24px header); expands to 200px showing the buffer.
    """
    COLLAPSED_H = 24
    EXPANDED_H = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self._count = 0
        self._expanded = False
        self.setStyleSheet("QFrame { background: #0a0a12; border-top: 1px solid #1c1c2a; }")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(10, 3, 10, 4)
        lay.setSpacing(0)
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self._toggle = QtWidgets.QLabel("▸ Thinking (0)")
        self._toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self._toggle.setStyleSheet(f"color:#4a4a5a;font-size:{fs(10)};border:none;padding:1px 0;")
        self._toggle.mousePressEvent = lambda e: self.toggle()
        header.addWidget(self._toggle)
        header.addStretch()
        lay.addLayout(header)
        self._view = QtWidgets.QTextEdit()
        self._view.setReadOnly(True)
        self._view.setStyleSheet(
            f"QTextEdit {{ background: transparent; color: #8b8fa8; font-size:{fs(11)}; border: none; }}"
        )
        self._view.setVisible(False)
        lay.addWidget(self._view)
        self.setFixedHeight(self.COLLAPSED_H)

    def toggle(self):
        self._expanded = not self._expanded
        self._view.setVisible(self._expanded)
        self.setFixedHeight(self.EXPANDED_H if self._expanded else self.COLLAPSED_H)
        arrow = "▾" if self._expanded else "▸"
        self._toggle.setText(f"{arrow} Thinking ({self._count})")

    def is_expanded(self) -> bool:
        return self._expanded

    def append(self, text: str):
        self._count += 1
        self._view.append(text)
        arrow = "▾" if self._expanded else "▸"
        self._toggle.setText(f"{arrow} Thinking ({self._count})")

    def toggle_text(self) -> str:
        return self._toggle.text()

    def reset(self):
        self._count = 0
        self._view.clear()
        self._toggle.setText("▸ Thinking (0)")
```

- [ ] **Step 4:实现 ToolPanel + ToolCardWidget**

`components/tool_panel.py` — 把 `_ToolCardWidget`(agent_panel.py:69-179)整段搬入;新增 `ToolPanel` 类封装原 `_tool_panel` 框架(约 719-770 行):

```python
"""ToolPanel — collapsible container of ToolCardWidget instances."""
import html
from PySide6 import QtCore, QtWidgets
from edini.ui.theme import fs


class ToolCardWidget(QtWidgets.QFrame):
    # ... (原 _ToolCardWidget 实现,类名去下划线)
    # 公开方法: set_result(result_str), set_error(msg)
    # 保留 _ToolCardWidget = ToolCardWidget 别名


class ToolPanel(QtWidgets.QFrame):
    """Holds tool-call cards; updates in real-time as tools start/complete."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: dict[str, ToolCardWidget] = {}
        self._expanded = False
        self.setStyleSheet("""...""")  # 原 _tool_panel 样式
        self._layout_v = QtWidgets.QVBoxLayout(self)
        self._layout_v.setContentsMargins(10, 3, 10, 4)
        # toggle header
        self._toggle = QtWidgets.QLabel("▸ Tool Calls (0)")
        # ... 同 ThinkingPanel 模式
        self._cards_container = QtWidgets.QWidget()
        self._cards_container.setVisible(False)
        self._cards_layout = QtWidgets.QVBoxLayout(self._cards_container)
        self._layout_v.addWidget(self._cards_container)
        self.setFixedHeight(24)

    def on_tool_started(self, tool_name: str, tool_call_id: str, args: dict):
        card = ToolCardWidget(tool_name, args, tool_call_id)
        self._cards[tool_call_id] = card
        self._cards_layout.addWidget(card)
        self._update_toggle()

    def on_tool_completed(self, tool_name: str, tool_call_id: str, result: str):
        card = self._cards.get(tool_call_id)
        if card:
            card.set_result(result)

    def card_names(self) -> list[str]:
        return [c._tool_name for c in self._cards.values()]

    def _update_toggle(self):
        n = len(self._cards)
        arrow = "▾" if self._expanded else "▸"
        self._toggle.setText(f"{arrow} Tool Calls ({n})")
```

- [ ] **Step 5:agent_panel.py 改为实例化新类**

在 `AgentPanel._build_ui()` 里:
- 删除内联构造 `_thinking_panel` 的代码,替换为 `self._thinking_panel = ThinkingPanel()`
- 删除内联构造 `_tool_panel` 的代码,替换为 `self._tool_panel = ToolPanel()`
- 保留 `self.thinking_panel` / `self.tool_panel` 属性引用

- [ ] **Step 6:运行测试**

Run: `python -m pytest tests/test_panels.py tests/test_bubbles.py tests/test_bubble_render.py -v`
Expected: all passed

- [ ] **Step 7:Commit**

```bash
git add python3.11libs/edini/ui/components/thinking_panel.py \
        python3.11libs/edini/ui/components/tool_panel.py \
        python3.11libs/edini/ui/agent_panel.py \
        tests/test_panels.py
git commit -m "refactor(components): extract ThinkingPanel + ToolPanel + ToolCardWidget"
```

---

### Task 1.5:抽取 ChangeTree + Attachments + InputBar

**Files:**
- Create: `python3.11libs/edini/ui/components/change_tree.py`
- Create: `python3.11libs/edini/ui/components/attachments.py`
- Create: `python3.11libs/edini/ui/components/input_bar.py`
- Modify: `python3.11libs/edini/ui/agent_panel.py`

- [ ] **Step 1:抽取 ChangeTreeWidget**

把 `agent_panel.py` 里的 `ChangeTreeWidget`(用 grep 定位 `class ChangeTreeWidget`)整段搬到 `components/change_tree.py`。agent_panel.py 改 import:
```python
from edini.ui.components.change_tree import ChangeTreeWidget
```

- [ ] **Step 2:抽取 ImageAttachmentWidget**

`ImageAttachmentWidget` 当前在 `edini/ui/image_attachment.py`(独立文件,不在 agent_panel 内)。改为**re-export 桥接**:在 `components/attachments.py`:
```python
"""Attachment bar widgets. Re-exports from existing locations."""
from edini.ui.image_attachment import ImageAttachmentWidget

__all__ = ["ImageAttachmentWidget"]
```

- [ ] **Step 3:抽取 InputBar**

把 `AgentPanel._build_ui()` 里的输入框行(`input_edit` + 多模态工具栏 + `_action_btn`)封装为 `components/input_bar.py` 的 `InputBar` 类:

```python
"""InputBar — message input + multimodal toolbar + send/abort button."""
from PySide6 import QtCore, QtWidgets
from edini.ui.theme import fs


class InputBar(QtWidgets.QWidget):
    """The chat input row. Emits submit_requested(text, images) / stop_requested."""
    submit_requested = QtCore.Signal(str, object)   # text, images(list|None)
    stop_requested = QtCore.Signal()
    abort_requested = QtCore.Signal()

    def __init__(self, show_attachment_bar: bool = True, parent=None):
        super().__init__(parent)
        self._busy = False
        # ... 构造 QPlainTextEdit + 工具栏 + 执行按钮
        # show_attachment_bar=False 时隐藏截图/上传按钮(HDA 用)

    def text(self) -> str: ...
    def clear(self): ...
    def set_busy(self, busy: bool): ...
    def set_images(self, images: list): ...
```

把 `ProjectChatDialog` / `project_widget.py` 的 `_InputDialog` 也迁入此文件(IME popout 弹窗,两窗口共用)。

- [ ] **Step 4:agent_panel.py 改用 InputBar**

`_build_ui()` 中删除内联输入框构造,替换为 `self._input_bar = InputBar(show_attachment_bar=True)`,连接信号到 AgentPanel 的现有处理方法。

- [ ] **Step 5:验证 import**

Run: `python -c "import sys; sys.path.insert(0,'python3.11libs'); from edini.ui.agent_panel import AgentPanel; print('ok')"`
Expected: `ok`

- [ ] **Step 6:运行所有现有测试**

Run: `python -m pytest tests/ -v --ignore=tests/manual_*.py 2>&1 | tail -20`
Expected: 全绿(无回归)

- [ ] **Step 7:Commit**

```bash
git add python3.11libs/edini/ui/components/change_tree.py \
        python3.11libs/edini/ui/components/attachments.py \
        python3.11libs/edini/ui/components/input_bar.py \
        python3.11libs/edini/ui/agent_panel.py
git commit -m "refactor(components): extract ChangeTree + InputBar + Attachments re-export"
```

---

### Task 1.6:合并 AiBubble + StreamBubble 流式优化(关键)

**Files:**
- Modify: `python3.11libs/edini/ui/components/bubbles.py`
- Test: `tests/test_bubble_streaming.py`

**目的:** 把 `_StreamBubble` 的"流式期纯文本 + finalize 一次 markdown"优化并入 `AiBubble`,消除 O(n²) `update_streaming`。

- [ ] **Step 1:写流式状态机测试**

```python
"""AiBubble streaming state machine — plain text during stream, markdown on finalize."""
import sys
sys.path.insert(0, "python3.11libs")
from tests.qt_helpers import qapp
from edini.ui.components.bubbles import AiBubble


def test_append_chunk_accumulates_plain_text():
    b = AiBubble()
    b.append_chunk("hello ")
    b.append_chunk("world")
    assert b._raw_text == "hello world"


def test_finalize_renders_markdown_once():
    b = AiBubble()
    b.append_chunk("**bold**")
    # during streaming, content is plain (no <strong> yet)
    txt_during = b._label.text()
    assert "<strong>" not in txt_during
    b.finalize()
    txt_after = b._label.text()
    assert "<strong>bold</strong>" in txt_after


def test_legacy_update_streaming_still_works():
    """Backward-compat: old update_streaming(full_text) API still functions."""
    b = AiBubble()
    b.update_streaming("partial **x**")
    assert b._raw_text == "partial **x**"


def test_get_raw_text():
    b = AiBubble()
    b.append_chunk("abc")
    assert b.get_raw_text() == "abc"
```

- [ ] **Step 2:运行,确认失败**

Run: `python -m pytest tests/test_bubble_streaming.py -v`
Expected: FAIL — `AiBubble` 无 `append_chunk` 方法

- [ ] **Step 3:在 AiBubble 实现 append_chunk**

修改 `components/bubbles.py` 的 `AiBubble`,新增 `append_chunk` 方法(纯文本流式,O(1)):

```python
class AiBubble(QtWidgets.QFrame):
    def __init__(self, rich_html: str = "", parent=None):
        super().__init__(parent)
        # ... 现有构造 ...
        self._raw_text = ""
        self._streaming = False
        if rich_html:
            # 初始化即完成态(历史消息)
            wrapped = f'<div style="{_ai_bubble_style()}">{rich_html}</div>'
            self._label.setText(wrapped)
        else:
            # 流式态:纯文本
            self._streaming = True
            self._label.setTextFormat(QtCore.Qt.PlainText)

    def append_chunk(self, chunk: str) -> None:
        """O(1) plain-text append during streaming. No markdown reparse."""
        if not self._streaming:
            # 从已完成态重新进入流式(少见)
            self._streaming = True
            self._label.setTextFormat(QtCore.Qt.PlainText)
        self._raw_text += chunk
        self._label.setText(self._raw_text)

    def update_streaming(self, full_text: str):
        """Legacy API: replace full accumulated text (still O(1) plain)."""
        self._raw_text = full_text
        if self._streaming:
            self._label.setText(full_text)
        else:
            # legacy callers expected lite render; keep behavior
            self._label.setTextFormat(QtCore.Qt.RichText)
            rendered = _format_lite(full_text)
            self._label.setText(f'<div style="{_ai_bubble_style()}">{rendered}</div>')

    def finalize(self):
        """Stream complete: ONE markdown full render, switch to RichText."""
        self._streaming = False
        self._label.setTextFormat(QtCore.Qt.RichText)
        rendered = _format_full(self._raw_text)
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)

    def get_raw_text(self) -> str:
        return self._raw_text

    def set_stored_content(self, content: str):
        """Set from stored history (already complete)."""
        self._streaming = False
        self._raw_text = content
        self._label.setTextFormat(QtCore.Qt.RichText)
        rendered = _format_full(content)
        wrapped = f'<div style="{_ai_bubble_style()}">{rendered}</div>'
        self._label.setText(wrapped)
```

- [ ] **Step 4:运行测试**

Run: `python -m pytest tests/test_bubble_streaming.py tests/test_bubbles.py -v`
Expected: all passed

- [ ] **Step 5:Commit**

```bash
git add python3.11libs/edini/ui/components/bubbles.py \
        tests/test_bubble_streaming.py
git commit -m "refactor(bubble): merge StreamBubble O(1) streaming into AiBubble"
```

---

## 阶段 2:status 子系统数据驱动化

### Task 2.1:SceneCard 数据驱动 + ContextPanel 迁移

**Files:**
- Create: `python3.11libs/edini/ui/status/__init__.py`
- Create: `python3.11libs/edini/ui/status/scene_card.py`
- Create: `python3.11libs/edini/ui/status/context_panel.py`
- Create: `python3.11libs/edini/ui/status/knowledge_zone.py`(从 `edini/ui/knowledge_zone.py` re-export)
- Test: `tests/test_scene_card.py`

- [ ] **Step 1:写 SceneCard 测试**

```python
"""SceneCard accepts a dict — no hou dependency."""
import sys
sys.path.insert(0, "python3.11libs")
from tests.qt_helpers import qapp
from edini.ui.status.scene_card import SceneCard


def test_set_scene_info_updates_labels():
    c = SceneCard()
    c.set_scene_info({
        "hip": "test.hip",
        "path": "/obj/geo1",
        "selected": "box1 (geo)",
        "nodes": "5 here / 100 total",
        "node_type": None,
        "params_summary": None,
    })
    assert "test.hip" in c.hip_label.text()
    assert "/obj/geo1" in c.path_label.text()


def test_none_values_show_dash():
    c = SceneCard()
    c.set_scene_info({"hip": None, "path": None, "selected": None, "nodes": None})
    assert "—" in c.hip_label.text() or "-" in c.hip_label.text()


def test_unknown_fields_ignored():
    c = SceneCard()
    c.set_scene_info({"hip": "x", "future_graph_field": "ignored"})  # no crash
```

- [ ] **Step 2:运行,确认失败**

Run: `python -m pytest tests/test_scene_card.py -v`
Expected: FAIL

- [ ] **Step 3:实现 SceneCard**

`status/scene_card.py` — 把 `context_panel.py` 里 Card 2 "Scene" 的构造(140-154 行)+ `refresh_scene_info`(244-265 行)拆出,改为数据驱动:

```python
"""SceneCard — data-driven scene info card. NO hou.pwd() dependency."""
from PySide6 import QtWidgets
from edini.ui.theme import fs


def _card_label(text): ...
def _make_card(title, parent=None): ...   # 从 context_panel.py 搬 _make_card


class SceneCard(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._card, layout = _make_card("Scene", self)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)
        self.hip_label = _card_label("HIP: -")
        self.path_label = _card_label("Path: -")
        self.selected_label = _card_label("Selected: -")
        self.node_count_label = _card_label("Nodes: -")
        for lbl in [self.hip_label, self.path_label, self.selected_label, self.node_count_label]:
            layout.addWidget(lbl)

    def set_scene_info(self, info: dict):
        """Update from a scene-info dict. None values → '—'."""
        def v(key, label_key):
            val = info.get(key)
            return f"— " if val is None else val
        self.hip_label.setText(f"HIP: {info.get('hip') or '—'}")
        self.path_label.setText(f"Path: {info.get('path') or '—'}")
        self.selected_label.setText(f"Selected: {info.get('selected') or '—'}")
        self.node_count_label.setText(f"Nodes: {info.get('nodes') or '—'}")
```

- [ ] **Step 4:实现 status/context_panel.py + knowledge_zone.py**

`status/context_panel.py`:把 `context_panel.py` 的 `ContextPanel` 类搬入,但 Card 2 "Scene" 替换为 `SceneCard` 实例;新增 `set_scene_info(dict)` 方法转发到 SceneCard。Card 3 Knowledge Zone 用 `from edini.ui.status.knowledge_zone import KnowledgeZone`。

`status/knowledge_zone.py`:
```python
from edini.ui.knowledge_zone import KnowledgeZone
__all__ = ["KnowledgeZone"]
```

- [ ] **Step 5:旧 `context_panel.py` 改为 re-export 桥接**

```python
# edini/ui/context_panel.py
"""Backward-compat shim. Real impl now in edini.ui.status.context_panel."""
from edini.ui.status.context_panel import ContextPanel
__all__ = ["ContextPanel"]
```

- [ ] **Step 6:运行测试**

Run: `python -m pytest tests/test_scene_card.py -v`
Expected: 3 passed

- [ ] **Step 7:Commit**

```bash
git add python3.11libs/edini/ui/status/ \
        python3.11libs/edini/ui/context_panel.py \
        tests/test_scene_card.py
git commit -m "refactor(status): data-driven SceneCard + ContextPanel migration"
```

---

## 阶段 3:ChatRuntime 增强 + ChatWindowShell + ScopeConfig

### Task 3.1:ChatRuntime 增强透传 + rpc property

**Files:**
- Modify: `python3.11libs/edini/ui/chat_runtime.py`
- Test: `tests/test_chat_runtime.py`(扩展)

- [ ] **Step 1:扩展测试**

在 `tests/test_chat_runtime.py` 追加:

```python
def test_status_changed_passthrough():
    rpc = _FakeRpc()
    rpc.status_changed = QtCore.Signal(str)  # 加到 _FakeRpc 类定义
    rt = ChatRuntime(rpc)
    spy = SignalSpy(rt.status_changed)
    rpc.status_changed.emit("connected")
    assert spy.calls == ["connected"]


def test_rpc_property_exposes_underlying_client():
    rpc = _FakeRpc()
    rt = ChatRuntime(rpc)
    assert rt.rpc is rpc
```

注意:更新 `_FakeRpc` 类加 `status_changed`、`models_received`、`session_switched` 信号。

- [ ] **Step 2:运行,确认失败**

Run: `python -m pytest tests/test_chat_runtime.py -v`
Expected: FAIL — `status_changed` 信号不存在

- [ ] **Step 3:增强 ChatRuntime**

修改 `chat_runtime.py`:

```python
class ChatRuntime(QObject):
    # ... 现有信号 ...
    status_changed = Signal(str)
    models_received = Signal(object)
    session_switched = Signal(str)

    def __init__(self, rpc_client, parent=None):
        super().__init__(parent)
        self._rpc = rpc_client
        self._bind()

    @property
    def rpc(self):
        return self._rpc

    def _bind(self):
        r = self._rpc
        # ... 现有绑定 ...
        r.status_changed.connect(self.status_changed)
        r.models_received.connect(self.models_received)
        r.session_switched.connect(self.session_switched)
```

- [ ] **Step 4:运行测试**

Run: `python -m pytest tests/test_chat_runtime.py -v`
Expected: 6 passed

- [ ] **Step 5:Commit**

```bash
git add python3.11libs/edini/ui/chat_runtime.py tests/test_chat_runtime.py
git commit -m "feat(chat-runtime): passthrough status/models/session + rpc property"
```

---

### Task 3.2:ScopeConfig

**Files:**
- Create: `python3.11libs/edini/ui/chat/__init__.py`
- Create: `python3.11libs/edini/ui/chat/scope.py`
- Create: `python3.11libs/edini/ui/chat_runtime.py`(从 ui/ 迁入 ui/chat/,旧位置 re-export)
- Test: `tests/test_scope.py`

- [ ] **Step 1:把 chat_runtime.py 迁到 chat/**

把 `python3.11libs/edini/ui/chat_runtime.py` 移到 `python3.11libs/edini/ui/chat/chat_runtime.py`。旧位置留 re-export shim:
```python
# edini/ui/chat_runtime.py
from edini.ui.chat.chat_runtime import ChatRuntime
__all__ = ["ChatRuntime"]
```

- [ ] **Step 2:写 ScopeConfig 测试**

```python
"""ScopeConfig — diff entry point for chat windows."""
import sys
sys.path.insert(0, "python3.11libs")
from edini.ui.chat.scope import ScopeConfig


def _provider():
    return {"hip": "x"}


def test_scope_immutable():
    s = ScopeConfig(scope_id="agent", window_title="Edini Agent",
                   accent_override=None, header_badge=None,
                   left_panel_kind="global_sessions", show_change_tree=True,
                   show_eval_button=True, show_attachment_bar=True,
                   show_param_snapshot=False, scene_data_provider=_provider)
    try:
        s.scope_id = "x"
        assert False, "should be frozen"
    except AttributeError:
        pass


def test_agent_vs_hda_diff_fields():
    a = ScopeConfig(scope_id="agent", window_title="Edini Agent",
                   accent_override=None, header_badge=None,
                   left_panel_kind="global_sessions", show_change_tree=True,
                   show_eval_button=True, show_attachment_bar=True,
                   show_param_snapshot=False, scene_data_provider=_provider)
    h = ScopeConfig(scope_id="project_hda", window_title="Project HDA",
                   accent_override="#f59e0b", header_badge="core: /obj/x",
                   left_panel_kind="node_versions", show_change_tree=True,
                   show_eval_button=False, show_attachment_bar=False,
                   show_param_snapshot=True, scene_data_provider=_provider)
    assert a.accent_override is None
    assert h.accent_override == "#f59e0b"
    assert a.left_panel_kind != h.left_panel_kind
```

- [ ] **Step 3:运行,确认失败**

Run: `python -m pytest tests/test_scope.py -v`
Expected: FAIL

- [ ] **Step 4:实现 ScopeConfig**

```python
"""ScopeConfig — describes a chat window's scope identity.

Components read config fields but NEVER branch on scope_id. This is the
single legal place to express differences between windows.
"""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ScopeConfig:
    scope_id: str
    window_title: str
    accent_override: str | None       # None=follow global theme
    header_badge: str | None
    left_panel_kind: str              # "global_sessions" / "node_versions"
    show_change_tree: bool
    show_eval_button: bool
    show_attachment_bar: bool
    show_param_snapshot: bool
    scene_data_provider: Callable[[], dict]
```

- [ ] **Step 5:运行测试**

Run: `python -m pytest tests/test_scope.py -v`
Expected: 2 passed

- [ ] **Step 6:Commit**

```bash
git add python3.11libs/edini/ui/chat/ \
        python3.11libs/edini/ui/chat_runtime.py \
        tests/test_scope.py
git commit -m "feat(chat): ScopeConfig + relocate chat_runtime to chat/"
```

---

### Task 3.3:ChatWindowShell(组合器)

**Files:**
- Create: `python3.11libs/edini/ui/chat/window_shell.py`
- Test: `tests/test_window_shell.py`

- [ ] **Step 1:写测试**

```python
"""ChatWindowShell — 3-panel assembler driven by ScopeConfig."""
import sys
sys.path.insert(0, "python3.11libs")
from tests.qt_helpers import qapp
from edini.ui.chat.scope import ScopeConfig
from edini.ui.chat.window_shell import ChatWindowShell


def _provider():
    return {}


def test_shell_has_three_panels():
    scope = ScopeConfig(scope_id="agent", window_title="T", accent_override=None,
                        header_badge=None, left_panel_kind="global_sessions",
                        show_change_tree=True, show_eval_button=True,
                        show_attachment_bar=True, show_param_snapshot=False,
                        scene_data_provider=_provider)
    shell = ChatWindowShell(scope)
    assert shell.left_panel is not None
    assert shell.center_widget is not None
    assert shell.context_panel is not None


def test_shell_accent_override_sets_objectname():
    scope = ScopeConfig(scope_id="project_hda", window_title="T", accent_override="#f59e0b",
                        header_badge="b", left_panel_kind="node_versions",
                        show_change_tree=True, show_eval_button=False,
                        show_attachment_bar=False, show_param_snapshot=True,
                        scene_data_provider=_provider)
    shell = ChatWindowShell(scope)
    assert shell.objectName() == "ChatShell_project_hda"


def test_shell_exposes_subcomponents():
    scope = ScopeConfig(scope_id="agent", window_title="T", accent_override=None,
                        header_badge=None, left_panel_kind="global_sessions",
                        show_change_tree=True, show_eval_button=True,
                        show_attachment_bar=True, show_param_snapshot=False,
                        scene_data_provider=_provider)
    shell = ChatWindowShell(scope)
    assert shell.timeline is not None
    assert shell.thinking_panel is not None
    assert shell.tool_panel is not None
    assert shell.input_bar is not None
```

- [ ] **Step 2:运行,确认失败**

Run: `python -m pytest tests/test_window_shell.py -v`
Expected: FAIL

- [ ] **Step 3:实现 ChatWindowShell**

```python
"""ChatWindowShell — three-panel chat skeleton (composer, not base class)."""
from PySide6 import QtCore, QtWidgets
from edini.ui.theme import accent_color, fs
from edini.ui.components.timeline_view import _TimelineView as TimelineView
from edini.ui.components.thinking_panel import ThinkingPanel
from edini.ui.components.tool_panel import ToolPanel
from edini.ui.components.input_bar import InputBar
from edini.ui.status.context_panel import ContextPanel


def _accent_scope_stylesheet(accent: str, oid: str) -> str:
    """Local-only accent override, scoped by objectName."""
    return f"""
    #{oid} QSplitter::handle:hover {{ background-color:{accent}; }}
    #{oid} QListWidget::item:selected {{ border-left:2px solid {accent}; color:{accent}; }}
    #{oid} QProgressBar::chunk {{ background-color:{accent}; }}
    #{oid} QPushButton#PrimaryButton {{ background-color:{accent}; }}
    """


class ChatWindowShell(QtWidgets.QWidget):
    """3-panel: left (scope-defined) | center (chat) | right (ContextPanel)."""

    def __init__(self, scope, left_panel: QtWidgets.QWidget | None = None, parent=None):
        super().__init__(parent)
        self._scope = scope
        if scope.accent_override:
            self.setObjectName(f"ChatShell_{scope.scope_id}")
        self._build(left_panel)

    def _build(self, left_panel):
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(f"<b>{self._scope.window_title}</b>")
        title.setStyleSheet(f"color:#e5e5eb;font-size:{fs(13)};padding:6px 12px;")
        header.addWidget(title)
        if self._scope.header_badge:
            badge = QtWidgets.QLabel(self._scope.header_badge)
            badge.setStyleSheet(f"color:#a1a1aa;font-size:{fs(10)};padding:6px 0;")
            header.addWidget(badge)
        header.addStretch(1)
        root.addLayout(header)

        # 3-panel splitter
        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self._left_panel = left_panel if left_panel is not None else QtWidgets.QWidget()
        self._left_panel.setObjectName("LeftPanel")
        self._splitter.addWidget(self._left_panel)

        # Center
        self._center = self._build_center()
        self._splitter.addWidget(self._center)

        # Right
        self._context_panel = ContextPanel()
        self._splitter.addWidget(self._context_panel)

        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, False)
        self._splitter.setCollapsible(2, False)
        self._splitter.setSizes([240, 720, 400])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)
        root.addWidget(self._splitter, 1)

        if self._scope.accent_override:
            self.setStyleSheet(_accent_scope_stylesheet(self._scope.accent_override, self.objectName()))

    def _build_center(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._timeline = TimelineView()
        lay.addWidget(self._timeline, 1)
        self._thinking_panel = ThinkingPanel()
        lay.addWidget(self._thinking_panel)
        self._tool_panel = ToolPanel()
        lay.addWidget(self._tool_panel)
        self._input_bar = InputBar(show_attachment_bar=self._scope.show_attachment_bar)
        lay.addWidget(self._input_bar)
        return w

    # ── Component accessors (for driver signal binding) ──
    @property
    def timeline(self): return self._timeline
    @property
    def thinking_panel(self): return self._thinking_panel
    @property
    def tool_panel(self): return self._tool_panel
    @property
    def input_bar(self): return self._input_bar
    @property
    def context_panel(self): return self._context_panel
    @property
    def center_widget(self): return self._center
    @property
    def left_panel(self): return self._left_panel
```

- [ ] **Step 4:运行测试**

Run: `python -m pytest tests/test_window_shell.py -v`
Expected: 3 passed

- [ ] **Step 5:Commit**

```bash
git add python3.11libs/edini/ui/chat/window_shell.py tests/test_window_shell.py
git commit -m "feat(chat): ChatWindowShell 3-panel composer with accent override"
```

---

### Task 3.4:BaseChatDriver

**Files:**
- Create: `python3.11libs/edini/ui/chat/base_driver.py`
- Test: `tests/test_base_driver.py`

- [ ] **Step 1:写测试**

```python
"""BaseChatDriver binds ChatRuntime signals to ChatWindowShell components."""
import sys
sys.path.insert(0, "python3.11libs")
from tests.qt_helpers import qapp, SignalSpy
from PySide6 import QtCore
from edini.ui.chat.chat_runtime import ChatRuntime
from edini.ui.chat.scope import ScopeConfig
from edini.ui.chat.window_shell import ChatWindowShell
from edini.ui.chat.base_driver import BaseChatDriver


class _FakeRpc(QtCore.QObject):
    text_delta = QtCore.Signal(str)
    thinking_delta = QtCore.Signal(str)
    tool_call = QtCore.Signal(str, str, object)
    tool_result = QtCore.Signal(str, str, str)
    agent_started = QtCore.Signal()
    agent_finished = QtCore.Signal()
    error_occurred = QtCore.Signal(str)
    stats_updated = QtCore.Signal(object)
    status_changed = QtCore.Signal(str)
    models_received = QtCore.Signal(object)
    session_switched = QtCore.Signal(str)
    def send_prompt(self, *a, **k): pass


def _make_driver():
    rpc = _FakeRpc()
    rt = ChatRuntime(rpc)
    scope = ScopeConfig(scope_id="agent", window_title="T", accent_override=None,
                        header_badge=None, left_panel_kind="global_sessions",
                        show_change_tree=True, show_eval_button=True,
                        show_attachment_bar=True, show_param_snapshot=False,
                        scene_data_provider=lambda: {})
    shell = ChatWindowShell(scope)
    return BaseChatDriver(rt, shell), rpc


def test_stream_chunk_creates_ai_bubble_and_appends():
    drv, rpc = _make_driver()
    rpc.text_delta.emit("hello")
    # an AiBubble should now exist in timeline
    bubbles = drv._shell.timeline._container.findChildren(type(drv._shell.timeline))
    # just assert no crash + raw text accumulated somewhere
    rpc.agent_finished.emit()


def test_send_calls_rpc_send_prompt():
    drv, rpc = _make_driver()
    called = []
    rpc.send_prompt = lambda t, images=None: called.append((t, images))
    drv.send("hi there")
    assert called == [("hi there", None)]
```

- [ ] **Step 2:运行,确认失败**

Run: `python -m pytest tests/test_base_driver.py -v`
Expected: FAIL

- [ ] **Step 3:实现 BaseChatDriver**

```python
"""BaseChatDriver — wires ChatRuntime signals to ChatWindowShell components.

Plain QObject (NOT a QWidget base class). Holds runtime + shell. Subclasses
override hooks for left-panel / scene data / session switching.
"""
from PySide6 import QtCore, QtWidgets
from edini.ui.components.bubbles import AiBubble, UserBubble


class BaseChatDriver(QtCore.QObject):
    def __init__(self, runtime, shell):
        super().__init__(shell)
        self._runtime = runtime
        self._shell = shell
        self._current_ai = None
        self._bind_runtime()
        self._bind_input()

    def _bind_runtime(self):
        r, s = self._runtime, self._shell
        r.stream_chunk.connect(self._on_stream_chunk)
        r.thinking_chunk.connect(s.thinking_panel.append)
        r.tool_started.connect(s.tool_panel.on_tool_started)
        r.tool_completed.connect(s.tool_panel.on_tool_completed)
        r.completed.connect(self._on_turn_done)
        r.stats_updated.connect(s.context_panel.set_usage)
        r.status_changed.connect(s.context_panel.set_pi_status)
        r.started.connect(self._on_started)
        r.failed.connect(self._on_failed)

    def _bind_input(self):
        self._shell.input_bar.submit_requested.connect(self.send)

    def _on_stream_chunk(self, chunk: str):
        if self._current_ai is None and chunk.strip():
            self._current_ai = AiBubble()
            self._shell.timeline.add_widget(self._current_ai)
        if self._current_ai is not None:
            self._current_ai.append_chunk(chunk)

    def _on_turn_done(self, _=None):
        if self._current_ai is not None:
            self._current_ai.finalize()
            self._current_ai = None

    def _on_started(self, _=None):
        self._shell.input_bar.set_busy(True)

    def _on_failed(self, msg: str):
        self._shell.input_bar.set_busy(False)

    def send(self, text: str, images=None):
        if not text:
            return
        self._shell.timeline.add_widget(UserBubble(text, images))
        self._runtime.rpc.send_prompt(text, images=images)

    # ── Hooks for subclasses ──
    def build_left_panel(self) -> QtWidgets.QWidget: ...
    def collect_scene_info(self) -> dict: return {}
```

注意:TimelineView 需要暴露 `add_widget` 方法(若当前没有则补,见下条 note)。

- [ ] **Step 4:确认 TimelineView 有 add_widget 公开方法**

检查 `components/timeline_view.py`,若无 `add_widget(widget)` 则补:
```python
def add_widget(self, widget):
    """Insert a widget above the bottom stretch."""
    self._layout.insertWidget(self._layout.count() - 1, widget)
```

- [ ] **Step 5:运行测试**

Run: `python -m pytest tests/test_base_driver.py -v`
Expected: 2 passed

- [ ] **Step 6:Commit**

```bash
git add python3.11libs/edini/ui/chat/base_driver.py \
        python3.11libs/edini/ui/components/timeline_view.py \
        tests/test_base_driver.py
git commit -m "feat(chat): BaseChatDriver wires ChatRuntime to Shell components"
```

---

### Task 3.5:主窗口切换到 ChatWindowShell(scope=agent)

**Files:**
- Modify: `python3.11libs/edini/main_window.py`
- Modify: `python3.11libs/edini/ui/agent_panel.py`(瘦身)
- Test: 手动验证(主窗口视觉无变化)

**说明:** 这是主窗口"动手术"的关键一步。当前 `EdiniMainWindow._build_ui()` 直接构造三面板。改为实例化 `ChatWindowShell(scope=agent_scope)` 并把 `HistoryPanel` 作为 left_panel 传入。AgentPanel 的角色从"自己拥有 timeline/thinking/tool"退化为"驱动 shell 的胶水"(这部分逻辑已被 BaseChatDriver 接管)。

- [ ] **Step 1:定义 agent_scope**

在 `main_window.py` 加:
```python
def _make_agent_scope(self):
    from edini.ui.chat.scope import ScopeConfig
    return ScopeConfig(
        scope_id="agent",
        window_title="Edini Agent",
        accent_override=None,             # 跟随全局主题
        header_badge=None,
        left_panel_kind="global_sessions",
        show_change_tree=True,
        show_eval_button=True,
        show_attachment_bar=True,
        show_param_snapshot=False,
        scene_data_provider=self._collect_global_scene,
    )

def _collect_global_scene(self) -> dict:
    # 把原 context_panel.refresh_scene_info 的逻辑搬到这里,返回 dict
    ...
```

- [ ] **Step 2:_build_ui 改用 Shell**

把 `_build_ui` 里直接构造 splitter+三面板的代码替换为:
```python
from edini.ui.chat.window_shell import ChatWindowShell
self._shell = ChatWindowShell(self._make_agent_scope(), left_panel=self.history_panel)
self.setCentralWidget(self._shell)
# 暴露兼容引用(原代码各处用 self.agent_panel / self.context_panel)
self.agent_panel = self._shell  # 兼容期
self.context_panel = self._shell.context_panel
```

- [ ] **Step 3:把 ChatRuntime 连接迁到 Driver**

把 `_bind_events` 里直接连接 ChatRuntime→各 handler 的代码,改为实例化 `AgentDriver(BaseChatDriver)`(或直接用 BaseChatDriver + 在 main_window 里补 global-scene provider hook)。

- [ ] **Step 4:手动验证(主窗口)**

在 Houdini 中打开 Edini Agent 面板,验证:
- 三面板布局正确(左=历史,中=对话,右=status)
- 主题色正确(青色)
- 发送消息 → 流式渲染 → finalize markdown
- Thinking / Tool 卡片显示
- token 计数更新
- 会话切换/新建

Expected: 视觉和行为与重构前一致。

- [ ] **Step 5:运行所有测试**

Run: `python -m pytest tests/ -v 2>&1 | tail -10`
Expected: 全绿

- [ ] **Step 6:Commit**

```bash
git add python3.11libs/edini/main_window.py \
        python3.11libs/edini/ui/agent_panel.py
git commit -m "refactor(main-window): switch to ChatWindowShell + agent scope"
```

---

## 阶段 4:HDA 窗口迁移到新架构

### Task 4.1:ProjectChatDriver + HDA scope

**Files:**
- Modify: `python3.11libs/edini/project/panel/chat_dialog.py`
- Create: `python3.11libs/edini/project/panel/chat_driver.py`
- Test: `tests/test_project_chat_driver.py`

- [ ] **Step 1:写测试**

```python
"""ProjectChatDriver — node-level scene provider + version hook stubs."""
import sys
sys.path.insert(0, "python3.11libs")
from tests.qt_helpers import qapp
from edini.project.panel.chat_driver import ProjectChatDriver, make_hda_scope


def test_hda_scope_uses_orange():
    scope = make_hda_scope(core_path="/obj/geo1/build1", node_type="project_builder",
                            scene_provider=lambda: {})
    assert scope.accent_override == "#f59e0b"
    assert scope.scope_id == "project_hda"
    assert "build1" in scope.window_title or "/obj/geo1/build1" in scope.window_title
    assert scope.show_param_snapshot is True
    assert scope.show_attachment_bar is False


def test_hda_scope_header_badge_has_core_path():
    scope = make_hda_scope(core_path="/obj/x", node_type="t",
                            scene_provider=lambda: {})
    assert "/obj/x" in scope.header_badge
```

- [ ] **Step 2:运行,确认失败**

Run: `python -m pytest tests/test_project_chat_driver.py -v`
Expected: FAIL

- [ ] **Step 3:实现 ProjectChatDriver + make_hda_scope**

```python
"""ProjectChatDriver — HDA-specific driver. Node-level scene provider."""
from edini.ui.chat.base_driver import BaseChatDriver
from edini.ui.chat.scope import ScopeConfig


def make_hda_scope(core_path: str, node_type: str, scene_provider) -> ScopeConfig:
    return ScopeConfig(
        scope_id="project_hda",
        window_title=f"Project HDA · {core_path}",
        accent_override="#f59e0b",
        header_badge=f"🔧 {core_path}  [{node_type}]",
        left_panel_kind="node_versions",
        show_change_tree=True,
        show_eval_button=False,
        show_attachment_bar=False,
        show_param_snapshot=True,
        scene_data_provider=scene_provider,
    )


class ProjectChatDriver(BaseChatDriver):
    """HDA driver: node-level scene + version management hooks (Stage 5 fills)."""
    def __init__(self, runtime, shell, core_path: str):
        super().__init__(runtime, shell)
        self._core_path = core_path

    def collect_scene_info(self) -> dict:
        # 阶段 5 实现:从 HDA 节点读参数/子节点
        return {}
```

- [ ] **Step 4:运行测试**

Run: `python -m pytest tests/test_project_chat_driver.py -v`
Expected: 2 passed

- [ ] **Step 5:Commit**

```bash
git add python3.11libs/edini/project/panel/chat_driver.py \
        tests/test_project_chat_driver.py
git commit -m "feat(project-chat): ProjectChatDriver + HDA scope (orange accent)"
```

---

### Task 4.2:ProjectChatDialog 改用 ChatWindowShell + ChatRuntime

**Files:**
- Modify: `python3.11libs/edini/project/panel/chat_dialog.py`

- [ ] **Step 1:重写 chat_dialog.py**

```python
"""ProjectChatDialog — HDA chat window using ChatWindowShell.

Now full 3-panel: version list (left) | chat (center) | status+knowledge (right).
Uses ChatRuntime (no direct RpcClient signal wiring). Orange accent.
"""
from __future__ import annotations
from PySide6 import QtWidgets
from edini.ui.theme import apply_theme
from edini.ui.chat.window_shell import ChatWindowShell
from edini.ui.chat.chat_runtime import ChatRuntime
from edini.project.panel.chat_driver import ProjectChatDriver, make_hda_scope


class ProjectChatDialog(QtWidgets.QDialog):
    def __init__(self, core_path: str, node_type: str = "", parent=None):
        super().__init__(parent)
        self._core_path = core_path
        self._rpc = None
        self._runtime = None
        self._driver = None
        self.setWindowTitle(f"Edini — {core_path}")
        self.resize(1100, 720)   # 加宽以容纳三面板

        # 左侧版本面板占位(阶段 5 实现 NodeVersionList)
        self._left_placeholder = QtWidgets.QLabel("Versions\n(loading)")
        self._left_placeholder.setMinimumWidth(200)

        scope = make_hda_scope(core_path, node_type, self._collect_scene)
        self._shell = ChatWindowShell(scope, left_panel=self._left_placeholder)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._shell)
        apply_theme(self)

    def _collect_scene(self) -> dict:
        # 阶段 5:从 HDA 节点读真实数据
        return {"path": self._core_path}

    def _get_rpc(self):
        if self._rpc is not None:
            return self._rpc
        from edini.tool_executor import get_tool_executor
        get_tool_executor()
        from edini.rpc_client import RpcClient
        self._rpc = RpcClient(parent=self)
        self._rpc.status_changed.connect(self._on_rpc_status)
        self._rpc.start()
        return self._rpc

    def _on_rpc_status(self, status: str):
        if status == "connected" and self._runtime is None:
            rpc = self._get_rpc()
            self._runtime = ChatRuntime(rpc)
            self._driver = ProjectChatDriver(self._runtime, self._shell, self._core_path)
            if self._core_path:
                rpc.send_set_session_name(self._core_path)
            try:
                from edini.config import read_pi_settings
                s = read_pi_settings()
                p, m = s.get("defaultProvider", ""), s.get("defaultModel", "")
                if p and m:
                    rpc.send_set_model(p, m)
            except Exception:
                pass

    def closeEvent(self, event):
        if self._rpc is not None:
            try: self._rpc.stop()
            except Exception: pass
        super().closeEvent(event)


_active_dialogs: dict[str, ProjectChatDialog] = {}


def open_chat_for_core(core_path: str, node_type: str = "") -> None:
    import hou
    dlg = _active_dialogs.get(core_path)
    if dlg is None:
        dlg = ProjectChatDialog(core_path, node_type, parent=hou.qt.mainWindow())
        _active_dialogs[core_path] = dlg
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
```

- [ ] **Step 2:更新 make_project_hda.py 的调用**

`scripts/make_project_hda.py` 里 `open_chat` 回调改为传 node_type:
```python
# 原: hou.phm().open_chat()
# 新: hou.phm().open_chat()  (PythonModule 内部调 open_chat_for_core 时传 node_type)
```
检查 `open_chat` 函数实现,确保传 `node.type().name()`。

- [ ] **Step 3:删除旧 project_widget.py 的 _StreamBubble 引用**

`project_widget.py` 里若有 `from edini.ui.agent_panel import _StreamBubble` 改为从 `components.bubbles` import,或直接删(ProjectPanelWidget 的内嵌聊天可能已被 chat_dialog 取代,确认后处理)。

- [ ] **Step 4:手动验证(HDA 窗口)**

在 Houdini 中:创建 Project HDA → 点 💬 Chat 按钮 → 验证:
- 三面板布局(左=占位/中=对话/右=status)
- 橙色强调色(与主窗口青色明显区分)
- header 显示 core_path + 节点类型
- 发送消息 → 流式 → thinking 显示(新能力)→ tool 卡片(新能力)
- token 计数更新(新能力)

- [ ] **Step 5:运行测试**

Run: `python -m pytest tests/ -v 2>&1 | tail -10`
Expected: 全绿

- [ ] **Step 6:Commit**

```bash
git add python3.11libs/edini/project/panel/chat_dialog.py \
        python3.11libs/edini/project/panel/project_widget.py \
        scripts/make_project_hda.py
git commit -m "feat(project-chat): HDA dialog uses ChatWindowShell + ChatRuntime (3-panel, orange)"
```

---

## 阶段 5:HDA 版本管理 + 参数快照

### Task 5.1:版本名解析 + NodeVersionList

**Files:**
- Create: `python3.11libs/edini/ui/components/version_list.py`
- Create: `python3.11libs/edini/ui/components/version_naming.py`
- Test: `tests/test_version_naming.py`, `tests/test_version_list.py`

- [ ] **Step 1:写版本命名测试**

```python
"""Version name parse/format: core_path::vN."""
import sys
sys.path.insert(0, "python3.11libs")
from edini.ui.components.version_naming import (
    make_version_session_name, parse_version_session_name, next_version
)


def test_make_version_name():
    assert make_version_session_name("/obj/geo1/build1", 3) == "/obj/geo1/build1::v3"


def test_parse_versioned_name():
    assert parse_version_session_name("/obj/x::v5") == ("/obj/x", 5)


def test_parse_unversioned_returns_none_version():
    assert parse_version_session_name("/obj/x") == ("/obj/x", None)


def test_next_version_from_empty():
    assert next_version([]) == 1


def test_next_version_from_existing():
    assert next_version([1, 2, 4]) == 5


def test_next_version_handles_none():
    assert next_version([1, None, 3]) == 4
```

- [ ] **Step 2:运行,确认失败**

Run: `python -m pytest tests/test_version_naming.py -v`
Expected: FAIL

- [ ] **Step 3:实现 version_naming.py**

```python
"""Version session naming: core_path::vN separator scheme.

Pi sees only a session-name string; the ::vN suffix is our convention
for enumerating versions of a single HDA node's modeling attempts.
"""
SEP = "::v"


def make_version_session_name(core_path: str, version: int) -> str:
    return f"{core_path}{SEP}{version}"


def parse_version_session_name(name: str) -> tuple[str, int | None]:
    if SEP in name:
        path, vstr = name.rsplit(SEP, 1)
        try:
            return path, int(vstr)
        except ValueError:
            return name, None
    return name, None


def next_version(existing_versions: list[int | None]) -> int:
    nums = [v for v in existing_versions if v is not None]
    return max(nums) + 1 if nums else 1
```

- [ ] **Step 4:运行测试**

Run: `python -m pytest tests/test_version_naming.py -v`
Expected: 6 passed

- [ ] **Step 5:实现 NodeVersionList**

`components/version_list.py`:
```python
"""NodeVersionList — left panel showing a node's session versions."""
from PySide6 import QtCore, QtWidgets
from edini.ui.theme import fs


class _VersionItem(QtWidgets.QWidget):
    selected = QtCore.Signal(int)   # version number
    def __init__(self, version: int, summary: str, meta: str, current: bool = False):
        super().__init__()
        # ... 构造:版本号 + 当前标记 + 摘要 + meta,点击发 selected(version)


class NodeVersionList(QtWidgets.QWidget):
    version_created = QtCore.Signal(int)      # new version N
    version_selected = QtCore.Signal(int)     # switch to version N
    version_deleted = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: dict[int, _VersionItem] = {}
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        # [+ New Version] 按钮
        new_btn = QtWidgets.QPushButton("+ New Version")
        new_btn.clicked.connect(lambda: self.version_created.emit(self._next_version()))
        lay.addWidget(new_btn)
        self._list_container = QtWidgets.QVBoxLayout()
        self._list_container.addStretch(1)
        lay.addLayout(self._list_container)

    def set_versions(self, versions: list[dict]):
        """versions = [{version, summary, meta, current}, ...]"""
        # 清空重建
        for v in versions:
            item = _VersionItem(v["version"], v["summary"], v["meta"], v.get("current", False))
            item.selected.connect(self.version_selected.emit)
            self._items[v["version"]] = item
            self._list_container.insertWidget(self._list_container.count() - 1, item)

    def _next_version(self) -> int:
        return max(self._items.keys(), default=0) + 1

    def mark_current(self, version: int):
        for v, item in self._items.items():
            item.set_current(v == version)
```

- [ ] **Step 6:写 NodeVersionList 测试并运行**

```python
def test_version_list_emits_create(test):
    ...  # 见 test_version_list.py
```

Run: `python -m pytest tests/test_version_list.py tests/test_version_naming.py -v`
Expected: passed

- [ ] **Step 7:Commit**

```bash
git add python3.11libs/edini/ui/components/version_naming.py \
        python3.11libs/edini/ui/components/version_list.py \
        tests/test_version_naming.py tests/test_version_list.py
git commit -m "feat(components): NodeVersionList + version naming (core_path::vN)"
```

---

### Task 5.2:Pi sessions 扫描工具(节点版本)

**Files:**
- Create: `python3.11libs/edini/ui/version_scanner.py`
- Test: `tests/test_version_scanner.py`

- [ ] **Step 1:写测试**

```python
"""Version scanner: list Pi sessions for a given core_path."""
import sys, os, tempfile
sys.path.insert(0, "python3.11libs")
from edini.ui.version_scanner import scan_node_versions


def test_scan_finds_versioned_sessions(tmp_path, monkeypatch):
    # mock pi_sessions_root to tmp_path
    monkeypatch.setattr("edini.ui.version_scanner._pi_sessions_root", lambda: tmp_path)
    # 创建几个 fake session 文件,内容含 session name
    (tmp_path / "a.jsonl").write_text('{"sessionName": "/obj/x::v1"}\n')
    (tmp_path / "b.jsonl").write_text('{"sessionName": "/obj/x::v2"}\n')
    (tmp_path / "c.jsonl").write_text('{"sessionName": "/obj/other::v1"}\n')  # 不同节点

    versions = scan_node_versions("/obj/x")
    version_nums = [v["version"] for v in versions]
    assert 1 in version_nums and 2 in version_nums
    assert len(versions) == 2


def test_scan_returns_empty_when_no_match(tmp_path, monkeypatch):
    monkeypatch.setattr("edini.ui.version_scanner._pi_sessions_root", lambda: tmp_path)
    assert scan_node_versions("/obj/none") == []
```

- [ ] **Step 2:运行,确认失败**

Run: `python -m pytest tests/test_version_scanner.py -v`
Expected: FAIL

- [ ] **Step 3:实现 version_scanner.py**

```python
"""Scan Pi session files to enumerate a node's versions.

True source: ~/.pi/agent/sessions/<cwd-hash>/*.jsonl
We read each file's first line, parse sessionName, filter by core_path::vN prefix.
"""
import json
import os
from pathlib import Path
from edini.ui.components.version_naming import parse_version_session_name, SEP


def _pi_sessions_root() -> Path:
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or "~"
    return Path(home) / ".pi" / "agent" / "sessions"


def scan_node_versions(core_path: str, cwd: str | None = None) -> list[dict]:
    """Return [{version, summary, meta, session_file}] for versions of core_path.

    Scans all session dirs (or the cwd-specific one if given). meta = mtime/size.
    """
    root = _pi_sessions_root()
    if not root.exists():
        return []
    results = []
    search_dirs = [root / _cwd_hash(cwd)] if cwd else [d for d in root.iterdir() if d.is_dir()]
    for d in search_dirs:
        if not d.exists():
            continue
        for f in d.glob("*.jsonl"):
            session_name = _read_session_name(f)
            if session_name is None:
                continue
            path, ver = parse_version_session_name(session_name)
            if path == core_path and ver is not None:
                results.append({
                    "version": ver,
                    "summary": _read_first_user_msg(f),
                    "meta": _file_meta(f),
                    "session_file": str(f),
                })
    results.sort(key=lambda v: v["version"])
    return results


def _read_session_name(path: Path) -> str | None:
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                obj = json.loads(line)
                if "sessionName" in obj:
                    return obj["sessionName"]
    except Exception:
        return None
    return None


def _read_first_user_msg(path: Path) -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                obj = json.loads(line)
                if obj.get("role") == "user":
                    return str(obj.get("content", ""))[:60]
    except Exception:
        pass
    return ""


def _file_meta(path: Path) -> str:
    import time
    mtime = os.path.getmtime(path)
    size = path.stat().st_size
    t = time.strftime("%H:%M", time.localtime(mtime))
    return f"{t} · {size//1024}kb"


def _cwd_hash(cwd: str) -> str:
    # 复用 pi_sessions.py 的 _cwd_to_dirname 逻辑
    from edini.ui.pi_sessions import _cwd_to_dirname
    return _cwd_to_dirname(cwd)
```

- [ ] **Step 4:运行测试**

Run: `python -m pytest tests/test_version_scanner.py -v`
Expected: 2 passed

- [ ] **Step 5:Commit**

```bash
git add python3.11libs/edini/ui/version_scanner.py tests/test_version_scanner.py
git commit -m "feat(version-scanner): scan Pi sessions for node versions (true source)"
```

---

### Task 5.3:ProjectChatDriver 接入版本管理

**Files:**
- Modify: `python3.11libs/edini/project/panel/chat_driver.py`
- Modify: `python3.11libs/edini/project/panel/chat_dialog.py`

- [ ] **Step 1:在 ProjectChatDriver 加版本管理逻辑**

```python
class ProjectChatDriver(BaseChatDriver):
    def __init__(self, runtime, shell, core_path: str):
        super().__init__(runtime, shell)
        self._core_path = core_path
        self._current_version = 1
        self._init_version_list()

    def _init_version_list(self):
        from edini.ui.components.version_list import NodeVersionList
        from edini.ui.version_scanner import scan_node_versions
        # 替换 shell 的左侧占位
        self._version_list = NodeVersionList()
        self._version_list.version_created.connect(self._on_new_version)
        self._version_list.version_selected.connect(self._on_select_version)
        versions = scan_node_versions(self._core_path)
        self._version_list.set_versions(versions)
        # 替换 shell.left_panel(需 ChatWindowShell 支持 replace_left)
        self._shell.replace_left(self._version_list)

    def _on_new_version(self, version: int):
        from edini.ui.components.version_naming import make_version_session_name
        name = make_version_session_name(self._core_path, version)
        self._runtime.rpc.send_set_session_name(name)
        self._current_version = version
        self._shell.timeline.clear()
        self._version_list.mark_current(version)

    def _on_select_version(self, version: int):
        from edini.ui.components.version_naming import make_version_session_name
        name = make_version_session_name(self._core_path, version)
        self._runtime.rpc.send_set_session_name(name)
        self._current_version = version
        # 历史回灌:依赖 Pi messages_received(见 spec §6.4 降级)
        self._shell.timeline.clear()
        self._version_list.mark_current(version)
```

- [ ] **Step 2:给 ChatWindowShell 加 replace_left**

```python
def replace_left(self, new_widget):
    """Swap the left panel widget at runtime."""
    idx = self._splitter.indexOf(self._left_panel)
    self._splitter.replaceWidget(idx, new_widget)
    self._left_panel.setParent(None)
    self._left_panel.deleteLater()
    self._left_panel = new_widget
    self._left_panel.setObjectName("LeftPanel")
```

- [ ] **Step 3:给 TimelineView 加 clear 方法**

```python
def clear(self):
    """Remove all message widgets (keep bottom stretch)."""
    while self._layout.count() > 1:
        item = self._layout.takeAt(0)
        w = item.widget()
        if w:
            w.deleteLater()
```

- [ ] **Step 4:运行测试**

Run: `python -m pytest tests/test_project_chat_driver.py tests/test_window_shell.py -v`
Expected: passed

- [ ] **Step 5:Commit**

```bash
git add python3.11libs/edini/project/panel/chat_driver.py \
        python3.11libs/edini/ui/chat/window_shell.py \
        python3.11libs/edini/ui/components/timeline_view.py
git commit -m "feat(project-chat): version list wiring (new/switch/delete)"
```

---

### Task 5.4:ParamSnapshotPanel(HDA 专属)

**Files:**
- Create: `python3.11libs/edini/ui/components/param_snapshot.py`
- Test: `tests/test_param_snapshot.py`

- [ ] **Step 1:写测试**

```python
"""ParamSnapshotPanel — shows HDA params + diff on change."""
import sys
sys.path.insert(0, "python3.11libs")
from tests.qt_helpers import qapp
from edini.ui.components.param_snapshot import ParamSnapshotPanel


def test_snapshot_displays_params():
    p = ParamSnapshotPanel()
    p.set_params({"height": "5.0", "steps": "20", "width": "2.0"})
    text = p.params_text()
    assert "height" in text and "5.0" in text


def test_diff_highlights_changed():
    p = ParamSnapshotPanel()
    p.set_params({"height": "5.0", "steps": "20"})
    p.set_params({"height": "8.0", "steps": "20"})  # height changed
    diffed = p.changed_params()
    assert "height" in diffed
    assert "steps" not in diffed
```

- [ ] **Step 2:运行,确认失败**

Run: `python -m pytest tests/test_param_snapshot.py -v`
Expected: FAIL

- [ ] **Step 3:实现 ParamSnapshotPanel**

```python
"""ParamSnapshotPanel — HDA parameter tree + change diff (HDA-only widget)."""
from PySide6 import QtGui, QtWidgets
from edini.ui.theme import fs


class ParamSnapshotPanel(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._params: dict[str, str] = {}
        self._prev: dict[str, str] = {}
        self._changed: set[str] = set()
        self.setStyleSheet("QFrame { background:#0e0e15; border:1px solid #2a2a3c; border-radius:6px; }")
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        header = QtWidgets.QLabel("🔧 Parameters")
        header.setStyleSheet(f"font-size:{fs(11)};font-weight:600;color:#71717a;")
        lay.addWidget(header)
        self._tree = QtWidgets.QTreeWidget()
        self._tree.setHeaderLabels(["Param", "Value"])
        self._tree.setColumnWidth(0, 100)
        lay.addWidget(self._tree)

    def set_params(self, params: dict[str, str]):
        self._prev = dict(self._params)
        self._params = dict(params)
        self._changed = {k for k in params if self._prev.get(k) != params[k]}
        self._refresh()

    def _refresh(self):
        self._tree.clear()
        for k, v in sorted(self._params.items()):
            item = QtWidgets.QTreeWidgetItem([k, v])
            if k in self._changed:
                for col in range(2):
                    item.setForeground(col, QtGui.QColor("#f59e0b"))
            self._tree.addTopLevelItem(item)

    def params_text(self) -> str:
        return "\n".join(f"{k}: {v}" for k, v in sorted(self._params.items()))

    def changed_params(self) -> set[str]:
        return set(self._changed)
```

注意:`QtGui` 需 import。

- [ ] **Step 4:在 ChatWindowShell 接入 ParamSnapshot(条件渲染)**

修改 `_build_center`:当 `scope.show_param_snapshot` 为 True 时,在 tool_panel 下方加 ParamSnapshotPanel:
```python
if self._scope.show_param_snapshot:
    from edini.ui.components.param_snapshot import ParamSnapshotPanel
    self._param_snapshot = ParamSnapshotPanel()
    lay.addWidget(self._param_snapshot)
```

- [ ] **Step 5:运行测试**

Run: `python -m pytest tests/test_param_snapshot.py -v`
Expected: 2 passed

- [ ] **Step 6:Commit**

```bash
git add python3.11libs/edini/ui/components/param_snapshot.py \
        python3.11libs/edini/ui/chat/window_shell.py \
        tests/test_param_snapshot.py
git commit -m "feat(components): ParamSnapshotPanel with change diff (HDA-only)"
```

---

## 阶段 6:主窗口瘦身收尾 + 架构守卫

### Task 6.1:架构分层守卫测试

**Files:**
- Create: `tests/test_layering.py`

- [ ] **Step 1:写分层守卫测试**

```python
"""Architecture layering guard.

Components MUST NOT import rpc_client / chat / main_window.
ChatRuntime MUST NOT import components.
"""
import ast
import importlib
from pathlib import Path

ROOT = Path(__file__).parent.parent / "python3.11libs" / "edini"

BANNED_FOR_COMPONENTS = {"edini.rpc_client", "edini.rpc_client",
                          "edini.ui.chat", "edini.ui.chat.chat_runtime",
                          "edini.main_window"}
BANNED_FOR_CHAT_RUNTIME = {"edini.ui.components"}


def _imports_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
    return mods


def test_components_dont_import_rpc_or_chat():
    comp_dir = ROOT / "ui" / "components"
    for py in comp_dir.glob("*.py"):
        imps = _imports_in(py)
        bad = imps & BANNED_FOR_COMPONENTS
        assert not bad, f"{py.name} imports banned: {bad}"


def test_chat_runtime_doesnt_import_components():
    # chat_runtime 可能在 ui/chat/ 或 ui/
    for candidate in [ROOT / "ui" / "chat" / "chat_runtime.py",
                       ROOT / "ui" / "chat_runtime.py"]:
        if candidate.exists():
            imps = _imports_in(candidate)
            bad = imps & BANNED_FOR_CHAT_RUNTIME
            assert not bad, f"{candidate.name} imports banned: {bad}"
```

- [ ] **Step 2:运行**

Run: `python -m pytest tests/test_layering.py -v`
Expected: 2 passed(若失败,说明有违规 import,需修)

- [ ] **Step 3:Commit**

```bash
git add tests/test_layering.py
git commit -m "test(layering): architecture guard — no banned cross-layer imports"
```

---

### Task 6.2:ScopeConfig 唯一差异入口 grep 守卫

**Files:**
- Create: `tests/test_scope_discipline.py`

- [ ] **Step 1:写守卫**

```python
"""Scope discipline: no `if scope_id ==` branches inside components/.

Components must read ScopeConfig fields, never branch on scope_id string.
"""
import re
from pathlib import Path

COMP_DIR = Path(__file__).parent.parent / "python3.11libs" / "edini" / "ui" / "components"
SCOPE_BRANCH_RE = re.compile(r'if\s+.*scope_id\s*==|if\s+.*scope\.scope_id\s*==')


def test_no_scope_id_branches_in_components():
    offenders = []
    for py in COMP_DIR.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        if SCOPE_BRANCH_RE.search(text):
            offenders.append(py.name)
    assert not offenders, f"Components branch on scope_id: {offenders}"
```

- [ ] **Step 2:运行**

Run: `python -m pytest tests/test_scope_discipline.py -v`
Expected: passed

- [ ] **Step 3:Commit**

```bash
git add tests/test_scope_discipline.py
git commit -m "test(scope-discipline): guard against scope_id branching in components"
```

---

### Task 6.3:移除兼容别名 + agent_panel 瘦身

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py`
- Modify: `python3.11libs/edini/ui/components/bubbles.py`(移除 `_AiBubble = AiBubble` 等)
- Modify: `python3.11libs/edini/ui/context_panel.py`(确认 shim 还在被用,或删)
- Modify: `python3.11libs/edini/ui/chat_runtime.py`(确认 shim)

- [ ] **Step 1:grep 找出所有还在用旧名的引用**

Run: 
```bash
cd python3.11libs && grep -rn "_AiBubble\|_StreamBubble\|_UserBubble\|_ToolCardWidget\|_TimelineView" --include="*.py" | grep -v "components/" | grep -v "test"
```
列出仍引用旧私有名的文件。

- [ ] **Step 2:逐个改为公开名**

把 `_AiBubble` → `AiBubble`,`_UserBubble` → `UserBubble` 等(在非 components 文件里)。

- [ ] **Step 3:移除 bubbles.py 里的兼容别名**

删除 `_AiBubble = AiBubble`、`_UserBubble = UserBubble`、`_ToolCardWidget = ToolCardWidget`。

- [ ] **Step 4:验证 agent_panel.py 行数**

Run: `wc -l python3.11libs/edini/ui/agent_panel.py`
Expected: ≤ 800 行(目标)。若超出,识别可进一步删的残留(已迁走的类的注释/空 section header)。

- [ ] **Step 5:运行全测试**

Run: `python -m pytest tests/ -v 2>&1 | tail -10`
Expected: 全绿

- [ ] **Step 6:Commit**

```bash
git add -A
git commit -m "refactor(cleanup): remove compat aliases, slim agent_panel to <800 lines"
```

---

### Task 6.4:验收清单手动验证

- [ ] **Step 1:HDA 窗口验收(对照 spec §13)**

在 Houdini 中打开 Project HDA → 💬 Chat,逐项验证:
1. ☐ 三面板布局(左=版本列表 / 中=对话+thinking+tool+参数快照 / 右=ContextPanel+Knowledge)
2. ☐ token 计数、模型配置、thinking 过程、tool calls 可见
3. ☐ 橙色强调色(主窗口青色,一眼可分辨)
4. ☐ header 显示 core_path + 类型徽章
5. ☐ 左侧可新建/切换/删除版本
6. ☐ 参数快照面板显示参数 + diff 高亮

- [ ] **Step 2:主窗口验收**

打开 Edini Agent,验证:
1. ☐ 三面板布局不变
2. ☐ 主题色跟随全局设置
3. ☐ 发送/流式/工具/thinking/stats 全部正常
4. ☐ 会话切换/新建/删除正常

- [ ] **Step 3:并排对比验收**

同时打开主窗口 + HDA 窗口,验证:
1. ☐ 一眼可分辨(青 vs 橙)
2. ☐ 切换全局主题时,主窗口变色,HDA 不变

- [ ] **Step 4:全测试绿**

Run: `python -m pytest tests/ -v`
Expected: 全绿

- [ ] **Step 5:Commit 验收记录**

```bash
git commit --allow-empty -m "test: acceptance verified — unified chat window architecture complete"
```

---

## 完成标准

- [ ] HDA 窗口具备完整三面板(版本/对话+能力/状态+知识区)
- [ ] HDA 显示 token/模型/thinking/tool/参数快照
- [ ] HDA 固定橙色,主窗口跟随全局,并排可分辨
- [ ] HDA 版本管理(新建/切换/删除)
- [ ] `agent_panel.py` ≤ 800 行,主窗口行为不变
- [ ] `test_layering.py` 绿(components 无跨层 import)
- [ ] `test_scope_discipline.py` 绿(组件无 scope_id 分支)
- [ ] 全部单元/集成测试通过
