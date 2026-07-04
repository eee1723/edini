# 统一对话窗口架构设计 — 主 Agent 窗口与 Project HDA 窗口共享组件库

- **状态:** Draft(待用户审阅)
- **日期:** 2026-07-05
- **作者:** Edini Pipeline
- **关联文件:**
  - `python3.11libs/edini/ui/main_window.py`(`EdiniMainWindow`,1213 行)
  - `python3.11libs/edini/ui/agent_panel.py`(`AgentPanel`,1951 行)
  - `python3.11libs/edini/ui/context_panel.py`(`ContextPanel`,265 行)
  - `python3.11libs/edini/ui/chat_runtime.py`(`ChatRuntime`,59 行)
  - `python3.11libs/edini/ui/theme.py`(4 主题色)
  - `python3.11libs/edini/ui/history_panel.py`(`HistoryPanel`,177 行)
  - `python3.11libs/edini/project/panel/chat_dialog.py`(`ProjectChatDialog`,189 行)
  - `python3.11libs/edini/project/panel/project_widget.py`(`_StreamBubble` + `_InputDialog`,461 行)

---

## 1. 问题陈述(第一性原理)

### 1.1 表层需求

- 程序化建模对话窗口(`ProjectChatDialog`)目前"太简陋":无三面板、无 token 计数、无模型配置、无 thinking/tool 可见性。
- 需要参照主 Agent 对话窗口(`EdiniMainWindow`)的三面板形式重做,但保留差异化。
- 左侧不需要全部历史会话,只保留**当前 HDA 任务下的对话轮次**(多版本)。
- 中间区尽量与主窗口一致。
- 右侧保留 token 计数与模型配置 status,并作为**将来的知识图谱空间**。
- 两个窗口要同步演进、保持差异、易于维护、不能混乱。

### 1.2 深层问题(根因)

两个对话窗口本质上是**同一件事的两个实例** —— 都是人↔Pi Agent 的对话,只是作用域不同(全局会话 vs 某个 HDA 节点的会话)。但当前代码把它们当成两个独立项目在写:

1. **无共享抽象**:主窗口 1951 行单文件 `AgentPanel` 把所有组件塞在一起;HDA 窗口靠 `from edini.ui.agent_panel import _TimelineView, _UserBubble` 这种**直接 import 私有类**来"复用"。主窗口一改,私有类就脱钩。
2. **能力不对称**:主窗口有 token 计数/模型配置/thinking/tool cards/knowledge zone/eval;HDA 窗口什么都没有。但 HDA 任务恰恰更需要 status(每节点独占 Pi 子进程,token 消耗更难追踪)。
3. **左侧面板语义错位**:主窗口左侧是"全部历史会话",HDA 窗口的作用域是"这一个 HDA 节点的对话版本",语义完全不同。
4. **RPC 适配分裂**:主窗口用 `ChatRuntime` 适配 RPC 信号;HDA 窗口直连 `RpcClient` 的 `text_delta/agent_finished/status_changed`,手写一遍且没接 thinking/stats/tool。

### 1.3 目标(第一性原理表述)

> 抽出一个**共享的对话窗口骨架**(组件库 + 装配器 + 单一 RPC 适配层),让两个实例在共享 90% 能力的同时,各自表达那 10% 的差异(作用域、左侧语义、右侧未来用途、视觉身份)。

---

## 2. 决策清单(用户已确认)

| # | 决策 | 选择 |
|---|------|------|
| D1 | 复用方式 | **组件库 + 组合**(非继承、非单窗口切换) |
| D2 | 交互一致性 | 交互逻辑通用化,UI 外观差异化 |
| D3 | HDA 左侧语义 | **该节点的多个 session/版本**(节点级版本管理) |
| D4 | 右侧构成 | 共享 `ContextPanel`(status 卡)+ Knowledge Zone 占位(将来升级图谱) |
| D5 | 视觉差异维度 | 强调色不同 + header 徽章不同 + 中间区能力侧重不同(不做密度/尺寸差异) |
| D6 | 能力侧重 | 主=通用对话/探索/多会话;HDA=建模聚焦(但**保留 thinking**,否则以为卡住) |
| D7 | 重构粒度 | **渐进式抽取** `AgentPanel`(不一次性重写) |
| D8 | RPC 适配 | HDA 窗口**接入 ChatRuntime**(消除直连) |
| D9 | HDA 建模色 | **Houdini 橙 #f59e0b**(固定,不受全局主题切换影响) |
| D10 | 参数快照面板 | **现在做基础版**(HDA 专属中间区能力) |
| D11 | 主窗口范围 | 主窗口**同步瘦身**到 ~600-800 行 |
| D12 | 版本命名 | `core_path::vN` 分隔符 |
| D13 | 版本清单存储 | (iii) 扫描 Pi sessions 目录为真源 + (i) 节点 userData 缓存 |
| D14 | 业务胶水 | `BaseChatDriver` 组合 + 模板方法(非 QWidget 继承) |

---

## 3. 架构总览(方案 A:扁平组件库 + Window 装配器)

### 3.1 分层与不变量

```
┌─────────────────────────────────────────────────────────┐
│  components/  (纯叶子组件,无会话语义,无 RPC 依赖)         │
│  TimelineView / AiBubble / ThinkingPanel / ToolPanel /   │
│  ChangeTree / InputBar / ParamSnapshot / NodeVersionList │
└──────────────▲──────────────────────────────────────────┘
               │ Qt signals (append_chunk / set_usage / ...)
┌──────────────┴──────────────────────────────────────────┐
│  chat/  (装配层)                                          │
│  ChatRuntime  ←→  BaseChatDriver  ←→  ChatWindowShell    │
│  ScopeConfig                                             │
└──────────────▲──────────────────────────────────────────┘
               │ 各自实例化,注入 scope 与 RpcClient
   ┌───────────┴───────────────┐
   │                           │
┌──┴──────────────┐  ┌─────────┴─────────────┐
│ EdiniMainWindow │  │ ProjectChatDialog     │
│ + AgentDriver   │  │ + ProjectChatDriver   │
│ scope=agent     │  │ scope=project_hda     │
│ 共享 RPC        │  │ 每节点独占 RPC        │
│ 左=全局会话     │  │ 左=节点版本           │
└─────────────────┘  └───────────────────────┘
```

**关键不变量(贯穿所有阶段,lint 守卫):**

1. `components/` 永远不 import `RpcClient` / `ChatRuntime` / `edini.ui.chat`。
2. `ChatRuntime` 永远不 import `components`(只发信号,不感知 UI)。
3. 两个窗口在阶段 4 后都不直接订阅 `RpcClient` 信号(只经 `ChatRuntime`)。
4. 任何"主窗口/HDA 不同"的逻辑必须经 `ScopeConfig`,禁止散落 `if scope_id` 判断(grep 守卫)。

### 3.2 数据流(单向、单一适配层)

```
RpcClient (Pi 子进程, stdin/stdout JSON-RPC)
    │ 15+ 原始信号 (text_delta, thinking_delta, tool_call, ...)
    ▼
ChatRuntime (唯一 RPC→UI 翻译层)
    │ UI 友好信号 (stream_chunk, thinking_chunk, tool_started, stats_updated, ...)
    ▼
BaseChatDriver.(子类 AgentDriver / ProjectChatDriver)
    │ 调用组件方法
    ▼
components/ (纯展示)
```

---

## 4. 目录结构

### 4.1 新建 `edini/ui/components/` — 纯叶子组件库

每个文件单一职责、无业务耦合、无 Pi 会话语义。组件只接受数据/信号,不持有会话状态。

```
python3.11libs/edini/ui/components/
├── __init__.py
├── timeline_view.py        # _TimelineView 抽出:可滚动气泡容器 + 自动跟随
├── markdown.py             # _DarkRenderer + _format_lite + _format_full
├── bubbles.py              # AiBubble(合并 _AiBubble + _StreamBubble)
├── thinking_panel.py       # 折叠的 Thinking(n) 面板
├── tool_panel.py           # _ToolCardWidget + Tool Calls(n) 折叠面板
├── change_tree.py          # ChangeTreeWidget(undo/redo 轮次 + 节点导航)
├── attachments.py          # ImageAttachmentWidget(多模态图片预览栏)
├── input_bar.py            # 输入框 + 多模态工具栏 + 执行/Abort + IME popout(_InputDialog 迁入)
├── version_list.py         # NodeVersionList(HDA 左侧:节点版本列表)
└── param_snapshot.py       # ParamSnapshotPanel(HDA 专属:参数快照 + diff)
```

### 4.2 新建 `edini/ui/status/` — 右侧 status 子系统(数据驱动)

```
python3.11libs/edini/ui/status/
├── __init__.py
├── context_panel.py        # ContextPanel 迁入:status 卡 + scene 卡 + knowledge 占位卡
├── scene_card.py           # Scene 卡(从 ContextPanel 拆出,数据注入,去 hou.pwd() 硬依赖)
└── knowledge_zone.py       # KnowledgeZone 迁入(现状占位 → 将来图谱)
```

**关键改动:** `ContextPanel` 重构为**数据驱动**。去掉 `refresh_scene_info()` 里对 `hou.pwd()` 的硬依赖,改成 `set_scene_info(dict)`。两个窗口各自组装数据传入:
- 主窗口:全局场景(`hou.pwd()` / `hou.selectedNodes()` / `hipFile.name()`)
- HDA 窗口:节点级数据(当前 HDA 的 `core_path` / 参数快照 / 子节点数 / 依赖节点)

### 4.3 新建 `edini/ui/chat/` — 装配层

```
python3.11libs/edini/ui/chat/
├── __init__.py
├── chat_runtime.py         # ChatRuntime 迁入(增强 3 个透传信号)
├── scope.py                # ScopeConfig 数据类(差异化的唯一入口)
├── window_shell.py         # ChatWindowShell 组合器(三面板 splitter + accent override)
└── base_driver.py          # BaseChatDriver 模板方法
```

### 4.4 现有窗口瘦身目标

| 文件 | 现行 | 重构后 |
|------|------|--------|
| `main_window.py` (1213) | 直接构造三面板 | 实例化 `ChatWindowShell(scope=agent_scope)` + 全局会话业务胶水 |
| `agent_panel.py` (1951) | 全塞一起 | ~600-800 行,只剩"通用对话"业务胶水(连 ChatRuntime→更新组件) |
| `chat_dialog.py` (189) | slim QDialog, import 私有类 | 实例化 `ChatWindowShell(scope=hda_scope)` + 节点版本管理业务 |

---

## 5. 核心组件设计

### 5.1 `AiBubble`(合并 `_AiBubble` + `_StreamBubble`)

消除两个 bubble 类的分裂。统一状态机:

```python
class AiBubble(QFrame):
    """流式 AI 气泡。流式期纯文本追加(O(1)),完成期一次 markdown 全量渲染。"""
    def __init__(self, format_mode="full"): ...
    def append_chunk(self, text: str):
        # 流式期:Qt.PlainText 追加,O(1),不触发 markdown 重解析
    def finalize(self):
        # 完成期:一次 mistune 全量渲染(setHtml)
```

**背景:** `_AiBubble.update_streaming` 当前是 O(n²) 全量重解析(每个 chunk 都重新跑 mistune),会卡 Houdini 主线程。`_StreamBubble` 是为绕开此问题的纯文本实现。合并后,主窗口也获得流式性能优化。

**兼容期:** 阶段 1 末保留 `_AiBubble = AiBubble` / `_StreamBubble = AiBubble` 别名,确保遗漏的旧 import 不炸,下一阶段移除。

### 5.2 `ScopeConfig` — 差异化的唯一入口

```python
@dataclass(frozen=True)
class ScopeConfig:
    """描述一个对话窗口的作用域身份。组件内部代码相同,差异只在此配置。"""
    scope_id: str                       # "agent" / "project_hda"
    window_title: str                   # "Edini Agent" / "Project HDA · {node}"
    accent_override: str | None         # None=跟随全局主题 / "#f59e0b"=HDA 固定橙
    header_badge: str | None            # None / "🔧 core_path: /obj/geo1/build1"
    left_panel_kind: str                # "global_sessions" / "node_versions"
    show_change_tree: bool              # True / True(建模必需)
    show_eval_button: bool              # True / False
    show_attachment_bar: bool           # True / False(HDA 聚焦建模)
    show_param_snapshot: bool           # False / True(HDA 专属)
    scene_data_provider: Callable[[], dict]  # 各自实现,返回 scene dict
```

**守卫:** 任何 `if scope.scope_id == ...` 出现在组件内部都视为违规。组件只读配置字段,不分支判断。

**`scene_data_provider` 返回的 scene dict 字段约定**(两个 provider 必须遵循同一 schema,`SceneCard.set_scene_info(dict)` 按此读取):

```python
{
    "hip":      str | None,   # hip 文件名(主窗口填;HDA 可填同一 hip 或 None)
    "path":     str | None,   # 主窗口=hou.pwd().path(); HDA=core_path
    "selected": str | None,   # 主窗口=选中节点名; HDA=当前 HDA 节点名+类型
    "nodes":    str | None,   # 主窗口="N here / M total"; HDA="该HDA子节点数"
    # HDA 专属字段(主窗口留空):
    "node_type":    str | None,   # HDA 节点类型,如 "project_builder::2.3"
    "params_summary": str | None, # HDA 参数摘要(供 status 卡显示;详细在 ParamSnapshotPanel)
}
```

未知字段被 `SceneCard` 忽略(向前兼容,将来加图谱字段不破坏)。`None` 值时该行显示 "—"。

### 5.3 `ChatWindowShell` — 组合器(非继承基类)

```python
class ChatWindowShell(QWidget):
    """三面板对话窗口骨架。组合器:接受 scope + 三个面板构造器。"""
    def __init__(self, scope: ScopeConfig, parent=None):
        # QSplitter(horizontal): left | center | right
        # accent override(若 scope.accent_override)通过 objectName 局部样式表
        # header(scope.window_title + scope.header_badge)
        # center: TimelineView + ThinkingPanel + ToolPanel + ChangeTree(可选) + InputBar
        # right: ContextPanel
    # 暴露子组件引用供 driver 连接信号:
    @property
    def timeline(self) -> TimelineView: ...
    @property
    def thinking_panel(self) -> ThinkingPanel: ...
    @property
    def tool_panel(self) -> ToolPanel: ...
    @property
    def context_panel(self) -> ContextPanel: ...
    @property
    def input_bar(self) -> InputBar: ...
```

### 5.4 `BaseChatDriver` — 业务胶水(组合 + 模板方法)

```python
class BaseChatDriver(QObject):
    """连接 ChatRuntime 与 ChatWindowShell 一组组件的通用业务胶水。

    普通 QObject(非 QWidget 基类),持有 runtime + shell 两个对象。
    共性(流式/工具/thinking/stats/发送/中断)在此;子类重写 4 个 hook。
    """
    def __init__(self, runtime: ChatRuntime, shell: ChatWindowShell):
        self._runtime = runtime
        self._shell = shell
        self._bind_runtime()

    def _bind_runtime(self):
        r, s = self._runtime, self._shell
        r.stream_chunk.connect(s.timeline.append_ai_chunk)
        r.thinking_chunk.connect(s.thinking_panel.append)
        r.tool_started.connect(s.tool_panel.on_tool_started)
        r.tool_completed.connect(s.tool_panel.on_tool_completed)
        r.completed.connect(self._on_turn_done)
        r.stats_updated.connect(s.context_panel.set_usage)
        r.status_changed.connect(s.context_panel.set_pi_status)
        r.started.connect(s.input_bar.set_busy)
        r.failed.connect(self._on_failed)

    def send(self, text: str, images=None):
        self._shell.timeline.add_user_bubble(text, images)
        self._runtime.rpc.send_prompt(text, images=images)

    # ── 子类 hook(默认空,HDA/Agent 各自覆盖)──
    def _build_left_panel(self) -> QWidget: ...           # 主=会话列表, HDA=版本列表
    def _collect_scene_info(self) -> dict: ...            # 主=hou全局, HDA=节点级
    def _on_session_changed(self, session_id: str): ...   # 切换会话/版本
```

### 5.5 `ChatRuntime` 增强

补 3 个透传信号(不改现有信号):

```python
class ChatRuntime(QObject):
    # ... 现有信号 ...
    status_changed = Signal(str)       # 新:透传连接状态
    models_received = Signal(dict)     # 新:透传可用模型列表
    session_switched = Signal(str)     # 新:透传会话切换

    def _bind(self):
        # ... 现有绑定 ...
        self._rpc.status_changed.connect(self.status_changed)
        self._rpc.models_received.connect(self.models_received)
        self._rpc.session_switched.connect(self.session_switched)

    @property
    def rpc(self):  # 新:driver 需要主动调用 send_prompt 等
        return self._rpc
```

---

## 6. HDA 版本管理(左侧 NodeVersionList)

### 6.1 版本命名

```
会话名 = f"{core_path}::v{N}"
例:  /obj/geo1/project_build1::v1
     /obj/geo1/project_build1::v2
```

- `::vN` 作为版本分隔符,Pi 侧无感知(它只看到一个 session 名字符串)
- 新建版本 = 启动新 Pi session + 命名 `::v{N+1}`
- 切换版本 = `rpc.send_set_session_name(f"{core_path}::v{N}")`

### 6.2 版本清单存储(iii 真源 + i 缓存)

| 层 | 位置 | 角色 |
|----|------|------|
| 真源 | Pi sessions 目录 | 扫描 `core_path::` 前缀过滤,列表的唯一事实来源 |
| 缓存 | HDA 节点 userData(`edini_versions` 键) | 加速列表渲染,失效时回扫真源 |

**理由:** Pi sessions 目录是唯一真源,扫描它不会出现"清单和实际 session 不一致"。但扫描可能慢,所以用节点 userData 做缓存,失效时回扫。节点删除则版本丢失(可接受 —— 节点都没了,版本无意义)。

### 6.3 NodeVersionList 列表项

```
┌──────────────────────────┐
│ v2  ◀ 当前               │   ← 版本号 + 当前标记
│ "创建一个螺旋楼梯"        │   ← 首条用户消息摘要
│ 14:32 · 1.2k tok         │   ← 时间 + token 累计
├──────────────────────────┤
│ v1                       │
│ "做一个基础盒子"          │
│ 14:05 · 0.8k tok         │
└──────────────────────────┘
```

**操作:**
- `[+ New Version]`:创建 `::v{N+1}` 新 session,清空 timeline,聚焦输入
- 单击版本:切换 session → `rpc.send_set_session_name(f"{core_path}::v{N}")` → 回灌历史
- 右键菜单:重命名 / 删除 / 复制为新建版本(基于该版本首条 prompt 开新 session)

### 6.4 历史回灌风险(已知)

切换到已有版本 session 用 `send_set_session_name`,**Pi 是否回灌该 session 的历史消息需在实现时验证**(当前 HDA 窗口刻意不调 `send_new_session`,会冲掉 pi-visionizer 上下文)。

**降级方案:** 若 Pi 不支持历史回灌,版本切换 = "只切换后续对话上下文,timeline 显示空 + 提示『历史未加载,可在 Pi 端查看』",不阻塞主体功能。

---

## 7. 视觉差异化机制

### 7.1 强调色局部 override(通过 objectName 限定作用域)

```python
# ChatWindowShell 构造时
if scope.accent_override:
    self.setObjectName(f"ChatShell_{scope.scope_id}")
    self.setStyleSheet(_accent_scope_stylesheet(scope.accent_override, self.objectName()))
```

`_accent_scope_stylesheet(accent, oid)` 只覆盖 accent 相关选择器,用 `#oid ...` 前缀锁定作用域,不污染主窗口:

```css
#ChatShell_project_hda QSplitter::handle:hover { background-color:#f59e0b; }
#ChatShell_project_hda QListWidget::item:selected { border-left:2px solid #f59e0b; color:#f59e0b; }
#ChatShell_project_hda QProgressBar::chunk { background-color:#f59e0b; }
```

**结果:** 主窗口跟随全局主题(默认青);HDA 窗口固定橙(#f59e0b),不受全局切换影响。切换全局主题时,主窗口变色,HDA 窗口不变,两者始终可分辨。

### 7.2 Header 徽章

```
主窗口:  🔵 Edini Agent
HDA 窗口:🟠 Project HDA  /obj/geo1/build1   [builder v2.3]
                          └─core_path───┘  └─节点类型chip─┘
```

### 7.3 能力侧重矩阵(中间区)

通过 `ScopeConfig` 开关控制,组件本身不变:

| 能力 | 主窗口 | HDA 窗口 | 开关 |
|------|:------:|:--------:|------|
| Thinking 面板 | ✓ | ✓ | 始终开 |
| Tool Calls 面板 | ✓ | ✓ | 始终开 |
| ChangeTree | ✓ | ✓ | 始终开(建模必需) |
| 多模态附件栏 | ✓ | ✗ | `show_attachment_bar` |
| Eval 按钮 | ✓ | ✗ | `show_eval_button` |
| 参数快照面板 | ✗ | ✓ | `show_param_snapshot`(HDA 专属) |

### 7.4 ParamSnapshotPanel(HDA 专属)

显示当前 HDA 的参数键值树 + 本轮对话中参数变更 diff(配合 `change_tree` 的参数级追踪,对接 `python3.11libs/edini/project/state.py`)。这是主窗口没有的、HDA 独有的中间区能力,体现"建模聚焦"。

---

## 8. 渐进式迁移顺序(6 个阶段)

每阶段独立可交付、可回滚、可验证。绝不允许"半重构"中间态。

### 阶段 0 — 现状基线 + 测试快照
- 写主窗口关键交互冒烟测试(发送/流式/工具/thinking/stats)
- HDA 窗口冒烟测试(发送/流式/关闭)
- **产出:** pytest 绿色基线,后续每阶段必须保持绿

### 阶段 1 — 抽取叶子组件(无行为变化)
- `components/timeline_view.py` ← 抽 `_TimelineView`
- `components/markdown.py` ← 抽 `_DarkRenderer/_format_*`
- `components/bubbles.py` ← 合并 `_AiBubble` + `_StreamBubble` → `AiBubble`(纯文本流式优化并入)
- `components/thinking_panel.py` / `tool_panel.py` / `change_tree.py` / `attachments.py` / `input_bar.py`
- `agent_panel.py` 改为 import 这些组件,**行为完全不变**
- 末尾保留 `_AiBubble = AiBubble` 别名
- **验证:** 阶段 0 冒烟测试全绿;主窗口视觉无变化

### 阶段 2 — status 子系统数据驱动化
- `status/scene_card.py` ← 拆出,去 `hou.pwd()` 硬依赖,改 `set_scene_info(dict)`
- `status/context_panel.py` ← 迁入,调 `scene_card.set_scene_info`
- `status/knowledge_zone.py` ← 迁入
- `main_window` 注入全局 scene provider
- **验证:** 主窗口场景卡仍显示正确

### 阶段 3 — ChatRuntime 增强 + Shell + ScopeConfig
- `chat_runtime.py` 补 `status_changed/models_received/session_switched` 透传 + `rpc` property
- `chat/scope.py` ← `ScopeConfig`
- `chat/window_shell.py` ← 三面板 splitter + accent override
- `chat/base_driver.py` ← `BaseChatDriver`
- 主窗口切换到 `ChatWindowShell(scope=agent_scope)`
- **验证:** 主窗口三面板布局、主题色、能力与之前一致;冒烟测试绿

### 阶段 4 — HDA 窗口迁移到新架构
- `ProjectChatDialog` 改为实例化 `ChatWindowShell(scope=hda_scope, accent=#f59e0b)`
- 接入 `ChatRuntime`(替换直连 `RpcClient` 信号)
- `ProjectChatDriver(BaseChatDriver)` ← 节点级 scene provider
- 消除 `chat_dialog.py` 对 `_StreamBubble/_InputDialog` 的私有 import
- `_InputDialog` 迁入 `components/input_bar.py`
- **HDA 窗口获得:** thinking/tool/stats/change_tree/ContextPanel
- **验证:** HDA 冒烟测试 + 新能力可见;主窗口不受影响

### 阶段 5 — HDA 版本管理 + 参数快照(差异化能力)
- `components/version_list.py` ← `NodeVersionList`
- Pi sessions 扫描工具(`core_path::vN` 前缀过滤)
- `ProjectChatDriver` 版本切换逻辑
- `components/param_snapshot.py` ← `ParamSnapshotPanel`(对接 `project/state.py`)
- **验证:** 版本新建/切换/删除;参数快照显示 + diff 高亮

### 阶段 6 — 主窗口瘦身收尾 + 守卫
- `agent_panel.py` 移除残留私有类、别名
- 加 `tests/test_layering.py`(import 静态检查:components 不准 import rpc/chat)
- 加 grep 守卫:组件内禁 `if scope_id`
- **验证:** `agent_panel.py` 行数降到 ~600-800;全测试绿

---

## 9. 测试策略

### 9.1 测试金字塔

```
┌─────────────────────────────────────┐
│ 手动验收(主+HDA 窗口并排截图对比)   │  ← 每阶段末尾
├─────────────────────────────────────┤
│ 集成测试(Qt信号链: Runtime→Driver)  │  ← pytest + QtBot
├─────────────────────────────────────┤
│ 单元测试(纯组件:Bubble/Scope/版本名)│  ← pytest 无需 Qt 事件循环
└─────────────────────────────────────┘
```

### 9.2 单元测试(无 Qt 事件循环,纯逻辑)
- `AiBubble.append_chunk/finalize` 状态机(纯文本期 vs markdown 期)
- `ScopeConfig` 序列化、accent override 计算
- 版本名解析 `parse_version_name("/obj/x::v3") → ("path", 3)`
- `ContextPanel.set_scene_info(dict)` 数据映射(不依赖 hou)
- markdown renderer 输入输出对(快照测试)

### 9.3 集成测试(用 QtBot 驱动信号)
- `ChatRuntime` 信号透传(RpcClient mock → ChatRuntime → 验证 emitted)
- `BaseChatDriver._bind_runtime` 连接正确(stream_chunk → timeline.append_ai_chunk 等)
- 版本切换流程(新建 vN+1 → session 名正确 → 切换回 vN)

### 9.4 冒烟测试(Houdini 内,hou 可用)
- 主窗口:打开 → 发送 → 收流式 → 工具卡片出现 → thinking 显示 → 关闭
- HDA 窗口:打开 → 发送 → 收流式 → thinking 显示(新能力) → stats 更新(新能力) → 关闭

### 9.5 回归保护
阶段 0 的冒烟测试快照是基线。**每个阶段结束前必须全绿才能合并。**

---

## 10. 工程纪律(防混乱)

- **每个组件一个 PR** — 阶段 1 的每个文件单独 PR,易审易回滚
- **禁止跨层 import** — `tests/test_layering.py` 跑 import 静态检查:
  - `components/` 不准 import `edini.rpc_client` / `edini.ui.chat`
  - `ChatRuntime` 不准 import `edini.ui.components`
- **ScopeConfig 是唯一差异入口** — grep 守卫:组件内禁 `if scope_id`
- **bubble 合并兼容期** — 阶段 1 末保留别名一阶段,阶段 6 移除

---

## 11. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|:----:|:----:|------|
| 阶段 1 合并 bubble 引入流式/markdown/IME 回归 | 中 | 高 | 先纯搬迁不改,合并作为阶段 1 最后子步;阶段 0 冒烟测试把关 |
| 阶段 3 主窗口切换 Shell 破布局 | 中 | 中 | 只换装配方式,布局参数 1:1 从旧代码搬入 Shell;阶段 0 冒烟测试 |
| 阶段 4 HDA 接 ChatRuntime 行为变 | 低 | 中 | HDA 原本能力极简,接入后只增不减;冒烟测试保证原路径不破 |
| 阶段 5 版本切换历史回灌不确定 | 中 | 中 | 降级方案(§6.4)已备;版本管理 UI 独立于主对话路径 |
| Houdini Python Panel 抢键盘致 IME 失效 | 已知 | 中 | `_InputDialog` popout 机制保留并迁入 `input_bar.py`,两窗口共用 |
| HDA 每节点独占 Pi 子进程,多开资源占用 | 已知 | 中 | 维持现状(决策 #11);窗口关闭时 `rpc.stop()`,已实现 |

---

## 12. 非目标(明确排除)

- ❌ 不重写 Pi 通信协议或 RpcClient
- ❌ 不改 Pi sessions 存储格式(只读扫描)
- ❌ 不实现知识图谱可视化(只占位)
- ❌ 不统一为单窗口(明确保留两个独立窗口)
- ❌ 不引入继承式 QWidget 基类
- ❌ 不做密度/尺寸差异化(保持两窗口视觉密度一致)
- ❌ 不在本次实现 eval 面板的 HDA 版本

---

## 13. 验收标准

1. HDA 窗口具备三面板布局(左=版本列表 / 中=对话+thinking+tool+change_tree+参数快照 / 右=ContextPanel+Knowledge 占位)
2. HDA 窗口显示 token 计数、模型配置、thinking 过程、tool calls
3. HDA 窗口固定橙色强调色,主窗口跟随全局主题,两者并排一眼可分辨
4. HDA 窗口 header 显示节点路径 + 类型徽章
5. HDA 左侧可新建/切换/删除版本(`core_path::vN`)
6. HDA 参数快照面板显示当前参数 + 本轮 diff
7. `agent_panel.py` ≤ 800 行,主窗口行为与重构前一致(冒烟测试绿)
8. `components/` 零 `rpc_client`/`chat` import(layering 测试绿)
9. 组件内零 `if scope_id` 分支(grep 守卫绿)
10. 全部单元/集成/冒烟测试通过

---

## 14. 后续(本 spec 之后)

本 spec 经用户审阅通过后,转入 **writing-plans** skill 制定详细实现计划(TDD 任务拆解)。
