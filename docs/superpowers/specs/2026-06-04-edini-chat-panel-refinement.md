# Edini 对话面板优化设计（完整版）

> 日期: 2026-06-04
> 状态: 已确认
> 基于: 2026-06-03-edini-ui-redesign-design.md
> 本次新增: 消息时间线架构 / 字体统一 / Session 系统 / 设置改进 / Viewport 截图 / Copy 按钮 / 状态栏

---

## 一、设计目标

在已有三栏布局框架（History | Chat Timeline | Context）基础上，补充和细化以下方面：

1. **消息时间线信息架构** — Thinking/Tool 双层折叠，Pi CLI 风格
2. **字体和间距统一** — 全局统一字号规范，紧凑呼吸感排版
3. **会话独立管理** — 每个 Session 独立上下文，“新建/切回”模式
4. **摘要压缩** — ctx ≥ 60% 自动压缩，重建上下文用摘要 + 最近 N 轮
5. **Copy 按钮和右键菜单** — 代码块一键复制、消息右键操作
6. **设置对话框改进** — Provider 下拉 + Model 历史记忆 + 实时预览
7. **Viewport 截图** — 输入框截图附件，vision-capable 模型支持
8. **Theme/Font 生效保证** — 修复当前设置不生效问题

---

## 二、三栏布局总览

```
┌──────┬─────────────────────────────┬──────────────┐
│ Ses- │        Timeline             │   Context    │
│ sions│                             │              │
│      │ [当前会话标识行]              │ ┌Pi Status──┐│
│ 240px│ ── 消息时间线 ──             │ │● Connected││
│      │  [用户消息]                  │ │DS/DS-chat ││
│      │  [AI 响应单元]               │ │Tokens/Cost││
│      │    ▸ Thinking (折叠)        │ │Ctx ██ 42% ││
│      │    ▸ 🔧 tool (折叠)         │ └───────────┘│
│      │    最终回复...              │ ┌Scene──────┐│
│      │  ─────────────────          │ │HIP: test  ││
│      │  输入框 + 📷截图  [发送]     │ │Nodes: 14  ││
│      │                             │ └───────────┘│
└──────┴─────────────────────────────┴──────────────┘
```

- 左侧 Sessions：240px，不可折叠，不可拉伸
- 中间 Timeline：自适应，可拉伸
- 右侧 Context：340px，不可折叠，不可拉伸

---

## 三、消息时间线信息架构

### 3.1 核心原则：双层折叠

每条 AI 回复是一个**可展开单元**。Thinking 默认折叠，Tool Call 默认折叠，最终回复始终可见。

### 3.2 消息单元结构

```
┌─────────────────────────────────────────────────┐
│  👤 用户消息（右对齐，蓝色底）                     │
│  右键 → 编辑 / 删除                               │
├─────────────────────────────────────────────────┤
│  🤖 AI 响应单元（左对齐，暗底）                    │
│                                                   │
│  ▸ Thinking (3 steps) · 1.2k tokens    [折叠]    │
│  ▸ 🔧 houdini_create_node              [折叠]    │
│  ▸ 🔧 houdini_set_param                [折叠]    │
│                                                   │
│  ── 最终回复 ──                                  │
│  我已创建了 smoke 模拟网络...                     │
│  ```vex                                          │
│  @Cd = noise(@P);                      [📋 复制] │
│  ```                                             │
│                                                   │
│  右键 → [📋 复制全部] [🔄 重新运行]                │
│                                                   │
│  ── 本轮耗时 3.2s · 总计 4,123 tokens ────────── │
└─────────────────────────────────────────────────┘
```

### 3.3 Thinking 展开态

```
  ▾ Thinking (3 steps) · 1.2k tokens
  │  ┌──────────────────────────────────────────┐
  │  │ 1. 用户想要创建烟雾模拟，需要先确定使用   │
  │  │    Pyro FX 还是 Volume 方法...            │
  │  │                                          │
  │  │ 2. 考虑到是初学者场景，应该用 Pyro Solver │
  │  │    预设，减少参数配置...                  │
  │  │                                          │
  │  │ 3. 确认后调用 houdini_create_node 创建    │
  │  │    pyro 节点...                          │
  │  └──────────────────────────────────────────┘
  │  [📋 复制思考过程]
```

### 3.4 Tool Call 展开态

```
  ▾ 🔧 houdini_create_node
  │  参数:
  │  ┌──────────────────────────────────────────┐
  │  │ {                                         │
  │  │   "node_type": "pyro",                   │
  │  │   "parent_path": "/obj"                  │
  │  │ }                                         │
  │  └──────────────────────────────────────────┘
  │  结果: ✅ 成功创建 /obj/pyro_sim
  │  [📋 复制参数]
```

### 3.5 Copy 按钮规则

| 位置 | 行为 |
|------|------|
| 代码块右上角 | `📋` 按钮，点击复制该块代码到剪贴板 |
| AI 气泡右键 | "复制全部"菜单项，复制完整 AI 回复文本 |
| Thinking 展开区域 | "复制思考过程"按钮 |
| Tool 展开区域 | "复制参数 JSON"按钮 |
| 用户消息右键 | "编辑" / "删除" |

### 3.6 智能滚动

- 用户在底部：AI 输出时自动跟随滚动
- 用户手动上滚查看历史：停止自动滚动
- 用户回到底部：恢复自动跟随
- 判断阈值：距底部 < 50px 视为在底部

---

## 四、字体和间距统一规范

### 4.1 字体大小（全局统一）

| 元素 | 字号 | 字色 |
|------|------|------|
| 用户消息气泡 | 12pt | #e5e5eb on 蓝底 |
| AI 最终回复文字 | 12pt | #e5e5eb on 暗底 |
| Thinking 内容文字 | 11pt | #71717a |
| Tool 参数/结果 | 11pt | #94a3b8 |
| 折叠标题行 | 11pt | #a1a1aa |
| 系统分隔线 | 10pt | #52525b |
| 输入框 | 13pt | #e5e5eb |
| Session 列表项 | 12pt | #a1a1aa |
| Session 列表副标题 | 11pt | #71717a |
| Context 卡片标题 | 11pt bold | #71717a |
| Context 卡片标签 | 11pt | #a1a1aa |
| Context 卡片值 | 11pt | #e5e5eb |
| Context 进度条文字 | 10pt | #a1a1aa |
| 状态栏 | 11pt | #71717a |

### 4.2 间距系统

| 间距项 | 值 |
|------|------|
| 消息气泡之间 | 6px |
| 消息气泡内 padding | 8px 12px |
| Thinking 块 padding | 4px 8px |
| Tool 块 padding | 4px 8px |
| 分隔线上下间距 | 10px |
| 折叠标题与内容之间 | 4px |
| Context 卡片之间 | 8px |
| Context 卡片内 padding | 8px |

---

## 五、会话管理系统

### 5.1 核心原则

- **本地存储永远完整** — 所有消息 JSON 文件一条不丢
- **压缩只影响发给 Pi 的上下文** — compressed_summary 只是缓存
- **切换会话 = 重建上下文** — 摘要 + 最近 N 轮发给 Pi

### 5.2 会话生命周期

```
新建 ──→ 活跃 ──→ 切到其他 ──→ 休眠 ──→ 切回 ──→ 活跃
         │                     │
         │ 每轮追加消息        │ 若 ctx ≥ 60%
         │ ctx 监控中          │ → 生成 compressed_summary
         │                     │ → messages 数组不动
         ↓                     ↓
      session.json         session.json
      (完整记录)           (完整记录 + 摘要缓存)
```

### 5.3 存储格式

```json
{
  "session_id": "uuid-v4",
  "title": "Pyro 烟雾模拟",
  "created_at": "2026-06-04T10:00:00Z",
  "updated_at": "2026-06-04T10:30:00Z",
  "compressed_summary": "用户要求创建烟雾模拟，经过多轮迭代...",
  "compressed_at": "2026-06-04T10:15:00Z",
  "compressed_round": 8,
  "messages": [
    {
      "role": "user",
      "content": "创建烟雾效果",
      "timestamp": "2026-06-04T10:00:00Z"
    },
    {
      "role": "assistant",
      "content": "我来帮你创建烟雾模拟网络...",
      "thinking": [
        {"step": 1, "text": "用户想要创建烟雾模拟..."},
        {"step": 2, "text": "应该使用 Pyro Solver 预设..."},
        {"step": 3, "text": "确认后调用创建节点..."}
      ],
      "tools": [
        {
          "name": "houdini_create_node",
          "call_id": "t1",
          "args": {"node_type": "pyro", "parent_path": "/obj"},
          "result": {"success": true, "path": "/obj/pyro_sim"}
        }
      ],
      "timestamp": "2026-06-04T10:00:15Z",
      "token_count": 1234,
      "duration_ms": 3200
    }
  ]
}
```

### 5.4 上下文重建（切回旧会话时）

```
切回 Session-A → 用户发送新 prompt
                      │
                      ▼
            compressed_summary 存在？
            │
     YES ───┤                        NO
     │                                │
     ▼                                ▼
  Pi system context:            Pi system context:
  [摘要文本] +                  messages 全部内容 +
  messages 最后 6 轮 +          当前 prompt
  当前 prompt
```

**N=6 轮**：保留最近 6 轮对话可见性，加上摘要覆盖早期内容。无兜底逻辑——相信 60% 触发足够。

### 5.5 摘要压缩流程（ctx ≥ 60%）

```
1. Pi 报告 contextUsage >= 60%
2. 提取前 8 轮完整消息（用户/AI/thinking/tools）
3. 构造内部压缩 prompt：
   "请用 200 字以内摘要以下对话的关键信息和已完成的工作..."
4. 将结果写入 compressed_summary 字段
5. 更新 compressed_at / compressed_round
6. messages 数组完整保留，不删除任何条目
7. UI 上左侧会话列表显示"已压缩"标记
```

### 5.6 左侧 Sessions 面板

```
┌──────────────────────────┐
│ Sessions                 │
│ [+ 新建会话]              │
│                          │
│ ▸ ● 烟雾模拟              │  ← 当前活跃，青色高亮
│   创建: 6/4 10:00        │
│   更新: 6/4 10:30        │
│   8 轮                    │
│ ─────────────────────────│
│   火焰特效                │  ← 历史会话，灰色
│   创建: 6/4 09:15        │
│   更新: 6/4 09:45        │
│   12 轮 · 已压缩          │
│ ─────────────────────────│
│   粒子散布                │
│   创建: 6/3 16:00        │
│   更新: 6/3 17:20        │
│   5 轮                    │
│ ─────────────────────────│
│   基础建模                │
│   创建: 6/2 14:00        │
│   更新: 6/2 14:30        │
│   3 轮                    │
│                          │
│ (双击重命名 / 右键删除)    │
└──────────────────────────┘
```

| 操作 | 行为 |
|------|------|
| 点击历史会话 | 切换到该会话，时间线刷新为该会话消息 |
| 当前会话高亮 | 左侧青色竖线 + 名称加粗 |
| 双击会话名 | 内联重命名 |
| 右键菜单 | 重命名 / 删除 |
| [+ 新建] 按钮 | 创建新会话，自动激活 |
| 已压缩标记 | 显示"已压缩"灰色小字 |

### 5.7 Timeline 顶部当前会话标识

```
┌─────────────────────────────────┐
│ ● 烟雾模拟  │  6/4 10:00 创建    │
│ 8 轮对话    │  6/4 10:30 更新    │
└─────────────────────────────────┘
  ── 消息时间线 ──
```

---

## 六、Context Panel（右侧）

### 6.1 卡片式分组

```
┌────────────────────────────┐
│ Context                    │
│                            │
│ ┌─── Pi Status ──────────┐│
│ │ ● Connected             ││
│ │ deepseek / deepseek-chat││
│ │                         ││
│ │ Tokens                  ││
│ │ In: 234  Out: 1,532     ││
│ │ Total: 1,766            ││
│ │ Cost           $0.003   ││
│ │ Context ████░░░░ 42%    ││
│ └─────────────────────────┘│
│                            │
│ ┌─── Scene ───────────────┐│
│ │ HIP    scene_v3.hip     ││
│ │ Path   /obj/geo1        ││
│ │ Sel    /obj/geo1/pyro   ││
│ │ Type   pyro             ││
│ │ Nodes  14               ││
│ │       [⟳ Refresh]       ││
│ └─────────────────────────┘│
└────────────────────────────┘
```

### 6.2 卡片视觉

- QFrame 包裹，`border: 1px solid #2a2a3c`，`border-radius: 6px`
- 标题在卡片内顶部，`11pt bold #71717a`
- 内容用最小化 QFormLayout 或 标签-值 对
- 卡片间距 8px

### 6.3 数据刷新策略

| 数据 | 刷新方式 |
|------|---------|
| Pi 连接状态 | `status_changed` 事件即时 |
| Provider/Model | `set_model` 后即时 |
| Token/Cost/Context | `agent_finished` 时 `send_get_stats()` |
| 场景信息 | `agent_finished` 时 + QTimer 每 5 秒 |

---

## 七、输入框与发送

### 7.1 基础布局

```
┌──────────────────────────────────────────┐
│  [描述你的任务...]             [仅对话 ☐] │
│                                     [执行] │
└──────────────────────────────────────────┘

热键:
  Enter → 发送（切换至 Ctrl+Enter 换行）
  无 modifier → 发送
  Ctrl+Enter → 输入框内换行
  Esc → 中止当前 AI 回复
```

### 7.2 Viewport 截图附件

```
┌──────────────────────────────────────────┐
│  [描述你的任务...]                        │
│                                          │
│  ┌──────────────────┐                    │
│  │ [Viewport 缩略图] │  ← 160x90 缩略图   │
│  └──────────────────┘                    │
│         [✕ 移除]                         │
│                                          │
│  [📷 截取]  [仅对话 ☐]  [执行]            │
└──────────────────────────────────────────┘
```

**交互流程:**

1. 用户点击 `📷 截取` → 调用 Houdini Viewport 截图 API
2. 输出 JPEG → base64，尺寸 1280x720，质量 85%
3. 在输入框上方显示 160x90 缩略图 + `[✕ 移除]`
4. 发送时图片以 `images` 数组附加到 prompt
5. 模型要求: vision-capable（Claude / GPT-4o 等）
6. 非 vision 模型（DeepSeek-V3）时隐藏截取按钮

**实现参考:**

```python
def capture_viewport() -> bytes:
    """截取当前 viewport 返回 JPEG bytes."""
    import hou
    desktop = hou.ui.curDesktop()
    viewport = desktop.paneTabOfType(hou.paneTabType.SceneViewer)
    if viewport:
        img = viewport.flipbookSettings().stash()
        # 或 viewport.saveImage() 写入临时文件
        return img
    return None
```

---

## 八、设置对话框

### 8.1 布局

```
┌──────────────────────────────────────────┐
│ Settings                              ✕  │
├──────────────────────────────────────────┤
│                                          │
│  Provider                                │
│  ┌─────────────────────────────────────┐ │
│  │ deepseek                     ▾     │ │  ← 下拉框
│  │  · anthropic                       │ │
│  │  · openai                          │ │
│  │  · google                          │ │
│  └─────────────────────────────────────┘ │
│                                          │
│  Model Name                              │
│  ┌─────────────────────────────────────┐ │
│  │ deepseek-chat                ▾     │ │  ← 可输入 + 下拉历史
│  │  · deepseek-chat  (上次)           │ │
│  │  · deepseek-reasoner               │ │
│  └─────────────────────────────────────┘ │
│                                          │
│  → deepseek / deepseek-chat              │
│                                          │
│  API Key                                 │
│  ┌─────────────────────────────────────┐ │
│  │ ●●●●●●●●●●●●●●        [👁 显示]    │ │
│  └─────────────────────────────────────┘ │
│                                          │
│  Appearance                              │
│  Theme: [北极青 ▾]  Font: [1.0 ▾]       │
│  (保存后即时生效 ✓)                       │
│                                          │
│              [取消]  [保存]               │
└──────────────────────────────────────────┘
```

### 8.2 Model 历史记忆

- `model_history.json` 存储用户输入过的 model name 列表
- Provider 切换时，从历史中过滤出该 provider 的常用 model
- 保留最近 10 条历史

### 8.3 设置生效保证

| 设置项 | 保存后操作 | 验证方式 |
|--------|-----------|---------|
| Provider | `send_set_model()` | 右侧 Context Panel 更新 Model 显示 |
| Model Name | `send_set_model()` | 同上 |
| API Key | `restart()` Pi 进程 | Pi Status 变为 "Connected" |
| Theme 颜色 | `window.setStyleSheet()` 全量刷新 | UI 即时变色 |
| Font Scale | `window.setStyleSheet()` 全量刷新 | UI 即时变字号 |

**实现要点:**
- SettingsDialog 保存时 emit signal → MainWindow 接收
- MainWindow 调用 `theme.refresh_window_theme(self)` 强制重绘
- 配置同时写入 `settings.json`（theme_color, font_scale）

---

## 九、状态栏

```
┌─────────────────────────────────────────────────────────────────┐
│ ● Connected │ DS / deepseek-chat │ Nodes:14 │ Tok:1,234 / $0.01 │ HIP: scene_v1.hip
└─────────────────────────────────────────────────────────────────┘
```

| 字段 | 数据来源 |
|------|---------|
| Pi 连接状态 | `status_changed` 事件 |
| Provider / Model | settings.json |
| Nodes 计数 | `node_utils.get_scene_info()` |
| Token / Cost | `send_get_stats()` → `stats_updated` |
| HIP 文件 | `hou.hipFile.name()` |

---

## 十、热键绑定

| 热键 | 作用域 | 行为 |
|------|--------|------|
| `Alt+Shift+E` | Houdini 全局 | 打开/切换到 Edini 面板 |
| `Enter` | 输入框 | 发送消息 |
| `Ctrl+Enter` | 输入框 | 换行 |
| `Esc` | 全局 | 中止当前 AI 回复 |

---

## 十一、实施阶段

### Phase A: 当前面板紧急修复（先行）

必须先修复当前 panel.py 中 Theme/Font 设置不生效问题，确保现有用户不受影响。

- [ ] config.py 存储 theme_color / font_scale
- [ ] SettingsDialog 保存后 emit signal
- [ ] MainWindow 接收 signal → refresh_window_theme()

### Phase B: 消息时间线重构（核心）

- [ ] agent_panel.py 替代旧的 QScrollArea + QLabel 方式
- [ ] QTextBrowser 实现双层折叠（Thinking/Tool）
- [ ] Markdown 完整渲染（代码块 + 高亮）
- [ ] Copy 按钮和右键菜单
- [ ] 智能滚动
- [ ] 字体/间距按规范统一

### Phase C: Session 系统

- [ ] session_store.py：JSON 文件读写
- [ ] Sessions 面板：列表 + CRUD + 高亮当前
- [ ] 上下文重建：摘要 + 最近 N 轮
- [ ] 摘要压缩：ctx ≥ 60% 触发
- [ ] Timeline 顶部当前会话标识

### Phase D: Context + Settings + 输入增强

- [ ] Context Panel 卡片式重构（Pi Status + Scene）
- [ ] Settings 对话框改进（Provider 下拉 + Model 历史）
- [ ] Viewport 截图功能
- [ ] 输入框附件系统
- [ ] 状态栏信息完善

### Phase E: 打磨

- [ ] Theme/Font 设置生效全面验证
- [ ] 热键在 Houdini 中注册
- [ ] Abort 反馈完善
- [ ] 实机 Houdini 21 验证

---

## 十二、与已有三栏设计的整合

本次优化基于 `2026-06-03-edini-ui-redesign-design.md` 的三栏框架，补充/修改以下文件：

### 新增/修改文件

| 文件 | 变化 |
|------|------|
| `edini/ui/agent_panel.py` | 重大重写：双层折叠、QTextBrowser、Copy、智能滚动 |
| `edini/ui/session_store.py` | 增强：摘要压缩、上下文重建逻辑 |
| `edini/ui/history_panel.py` → `sessions_panel.py` | 重命名+增强：会话列表带时间/轮数/压缩标记 |
| `edini/ui/context_panel.py` | 重构：卡片式分组 |
| `edini/ui/settings_dialog.py` | 重写：Provider 下拉 + Model 历史 + 实时预览 |
| `edini/ui/main_window.py` | 适配：信号连接、Theme 刷新、Session 切换 |
| `edini/ui/windows.py` | 不变 |
| `edini/ui/theme.py` | 增强：字体大小常量、间距常量、强制刷新函数 |
| `edini/ui/plan_progress_widget.py` | 不变 |
| `edini/ui/change_tree_widget.py` | 不变 |
| `edini/ui/hotkey.py` | 新增：热键注册 |
| `edini/config.py` | 增强：theme_color、font_scale、model_history |

### 文件重命名

- `history_panel.py` → `sessions_panel.py`（语义更准确）

---

## 十三、设计决策记录

| 决策 | 选项 | 理由 |
|------|------|------|
| Thinking/Tool 展示 | 双层折叠（默认折叠） | 不混乱，信息可选可见 |
| 间距风格 | 中等型（10-14px 间距） | 有呼吸感但不浪费空间 |
| 上下文重建 | 摘要 + 最近 6 轮 | 利用缓存摘要，避免重复生成 |
| 摘要触发阈值 | ctx ≥ 60% | 用户选择，足够保守 |
| 兜底策略 | 无 | 60% 触发足够覆盖边界情况 |
| Session 管理位置 | 左侧独立面板 | 与 Context 解耦，结构清晰 |
| Model 配置方式 | Provider 下拉 + Model 输入+历史 | 像 Pi CLI 一样简洁 |

---

> 完整版。待用户确认后进入 writing-plans 阶段。
