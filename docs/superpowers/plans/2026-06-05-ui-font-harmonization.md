# UI 字体协调优化 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 Edini UI 字号层级（4层），修复文字裁切问题，确保 fs() 缩放全局生效

**Architecture:** 逐文件修改字号和固定尺寸。4层体系：header(fs13) / body(fs12) / detail(fs11) / caption(fs10)。取消 fs(9)，所有固定高度/宽度改为与字号关联。

**Tech Stack:** PySide6, Qt Stylesheets, Python

---

### Task 1: 修复 history_panel.py 硬编码 pt → fs()

**Files:**
- Modify: `python3.11libs/edini/ui/history_panel.py`

- [ ] **Step 1: 导入 fs 并修改 title 和样式**

```python
# In history_panel.py — change title and all inline styles:

# Import (add fs to import):
from edini.ui.theme import fs

# In __init__, change title:
title.setStyleSheet(f"font-size:{fs(13)};font-weight:700;color:#e5e5eb;")

# In __init__, change session_list stylesheet:
# "font-size: 12pt;" → f"font-size:{fs(12)};"

# In add_session, change title_label:
title_label.setStyleSheet(f"font-size:{fs(12)};color:#e5e5eb;font-weight:600;border:none;")

# In add_session, change meta_label:
meta_label.setStyleSheet(f"font-size:{fs(11)};color:#71717a;border:none;")

# In add_session, change updated_label:
updated_label.setStyleSheet(f"font-size:{fs(10)};color:#52525b;border:none;")
```

- [ ] **Step 2: 视觉验证**

启动 Edini，检查历史面板的 session 标题、消息数、日期显示是否完整，拖动字体缩放滑块验证。

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/history_panel.py
git commit -m "fix: history panel uses fs() for font scaling"
```

---

### Task 2: 统一 theme.py 全局样式表

**Files:**
- Modify: `python3.11libs/edini/ui/theme.py`

- [ ] **Step 1: 调整 QStatusBar 和 QCheckBox 字号**

在 `build_stylesheet()` 中修改：

```css
/* QStatusBar: fs(11) → fs(10) */
QStatusBar      {{ background-color:#0a0a10; color:#6a6e76; border-top:1px solid #1e1e2c; font-size:{fs(10)}; padding:0 8px; }}

/* QCheckBox: fs(11) → fs(10) */
QCheckBox       {{ color:#8a8f98; font-size:{fs(10)}; spacing:6px; }}
```

- [ ] **Step 2: 视觉验证**

检查状态栏文字显示完整，checkbox 标签不被裁切。

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/theme.py
git commit -m "fix: theme QStatusBar/QCheckBox use fs(10)"
```

---

### Task 3: 优化 agent_panel.py 字号和固定尺寸

**Files:**
- Modify: `python3.11libs/edini/ui/agent_panel.py`

- [ ] **Step 1: 修改代码块字号为 fs()**

在 `_format_message` 函数中，将 `font-size:10pt` 和 `font-size:11pt` 改为使用 `fs()`：

```python
# Code block Copy button:
f'font-size:{fs(10)};'

# Code block pre:
f'font-size:{fs(11)};'

# Inline code:
f'font-size:{fs(11)};'
```

- [ ] **Step 2: 修改 Thinking 面板折叠样式字号**

```python
def _thinking_collapsed_style() -> str:
    # fs(11) → fs(10)
    return (
        f'color:#a1a1aa;font-size:{fs(10)};cursor:pointer;'
        ...
    )

def _thinking_expanded_style() -> str:
    # fs(11) → fs(10)
    return (
        f'color:#71717a;font-size:{fs(10)};display:block;'
        ...
    )
```

- [ ] **Step 3: 修改 TypeToggleBadge fs(9) → fs(10), 放宽宽度**

```python
class _TypeToggleBadge(QtWidgets.QLabel):
    def __init__(self, ...):
        ...
        self.setFixedWidth(40)  # was 36

    def _update_style(self):
        ...
        self.setStyleSheet(
            f"color:{color};font-size:{fs(10)};font-weight:600;"  # was fs(9)
            ...
        )
```

- [ ] **Step 4: 修改知识卡片分类标签 fs(9) → fs(10), 放宽宽度**

在 `_make_knowledge_card` 中：

```python
cat_label.setStyleSheet(f"color:#71717a;font-size:{fs(10)};border:none;")  # was fs(9)
cat_label.setFixedWidth(40)  # was 32
```

- [ ] **Step 5: 视觉验证**

启动 Edini，发送一条含代码块的回复，验证代码字号正常。打开知识提取面板，检查徽章"铁律"/"知识"文字不溢出。

- [ ] **Step 6: Commit**

```bash
git add python3.11libs/edini/ui/agent_panel.py
git commit -m "fix: agent_panel font sizes unified, code blocks use fs()"
```

---

### Task 4: 调整 change_tree_widget 固定高度

**Files:**
- Modify: `python3.11libs/edini/ui/change_tree_widget.py`

- [ ] **Step 1: 修改 COLLAPSED_H 和 EXPANDED_H**

```python
COLLAPSED_H = 24   # was 22
EXPANDED_H = 280   # was 260
```

- [ ] **Step 2: 视觉验证**

检查变更树面板折叠时标题栏不裁切，展开时内容区域充裕。

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/ui/change_tree_widget.py
git commit -m "fix: change_tree panel heights accommodate font scaling"
```

---

### Task 5: 优化 context_panel.py 卡片布局

**Files:**
- Modify: `python3.11libs/edini/ui/context_panel.py`

- [ ] **Step 1: 卡片标题 fs(11) → fs(12)**

```python
def _make_card(title: str, parent=None) -> tuple[...]:
    ...
    header.setStyleSheet(f"font-size:{fs(12)};font-weight:600;color:#71717a;border:none;")
    ...
```

- [ ] **Step 2: 放宽 _card_row 的标签宽度**

```python
def _card_row(label: str, value_widget: ...):
    ...
    lbl.setFixedWidth(56)  # was 50
    ...
```

- [ ] **Step 3: 视觉验证**

检查 Pi Status / Scene / Knowledge 三张卡片的标题和行标签无裁切。

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/ui/context_panel.py
git commit -m "fix: context_panel card header fs(12), wider label columns"
```

---

### Task 6: 统一 knowledge_dialog.py 字号

**Files:**
- Modify: `python3.11libs/edini/ui/knowledge_dialog.py`

- [ ] **Step 1: _KnowledgeTab 中搜索/过滤/列表/选项卡 提升字号**

```python
# 搜索框: fs(11) → fs(12)
self._search.setStyleSheet(f"""
    QLineEdit {{
        ...
        font-size: {fs(12)};
    }}
""")

# 分类过滤: fs(11) → fs(12)
self._category_filter.setStyleSheet(f"""
    QComboBox {{
        ...
        font-size: {fs(12)};
    }}
""")

# 列表: fs(11) → fs(12)
self._list.setStyleSheet(f"""
    QListWidget {{
        ...
        font-size: {fs(12)};
    }}
""")

# 详情区域: 保持 fs(11)

# 选项卡: fs(11) → fs(12)
self._tabs.setStyleSheet(f"""
    ...
    QTabBar::tab {{
        ...
        font-size: {fs(12)};
    }}
""")
```

- [ ] **Step 2: _ItemEditDialog 对话框标签/输入框 fs(11) → fs(12)**

```python
def _apply_styles(self):
    s = f"""
        ...
        QLabel {{ color: #a1a1aa; font-size: {fs(12)}; }}
        QLineEdit, QPlainTextEdit, QComboBox {{
            ...
            font-size: {fs(12)};
        }}
    """
```

- [ ] **Step 3: 视觉验证**

打开知识管理对话框，检查列表项、搜索框、选项卡标签文字完整。

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/ui/knowledge_dialog.py
git commit -m "fix: knowledge_dialog uses fs(12) for primary text"
```

---

### Task 7: 最终集成验证

- [ ] **Step 1: 全部字号验证**

在 Edini Settings 中将 Font 依次设为 0.8、1.0、1.2、1.4，检查：
- 历史面板 session 标题和元数据
- 聊天气泡（用户/AI）
- 代码块（~/```）
- 思考面板折叠头
- 工具调用卡片
- 知识提取徽章和分类标签
- Pi Status / Scene / Knowledge 卡片
- 变更树折叠头和树节点
- 知识管理对话框

- [ ] **Step 2: 无裁切**

确认所有可见文字完整显示，无一被裁切边缘。

- [ ] **Step 3: 最终 Commit**

```bash
git add -A
git commit -m "chore: UI font harmonization — verified across 0.8-1.4 scale"
```
