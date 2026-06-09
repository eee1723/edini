# 🤖 Agent 交接文档

> **用途**：让新 Agent 或开发者在 Edini 仓库里快速上手。

**最后更新**：2026-06-09（第二十一阶段：知识反思面板 + 去重）
**当前阶段**：156 单元测试 · ReflectWorker 后台反思 · Jaccard 去重
**下一阶段**：Houdini Pane Tab 嵌入 · 场景感知
**工作分支**：`master`

## 一句话总结

Edini 是 Houdini 21 的 AI 助手：Python/PySide6 面板 → JSON-RPC 进程通信 → Pi Agent AI 后端 → 22 个 Houdini 工具。知识沉淀采用两层架构（铁律 + 知识库），对话结束后 ReflectWorker 后台反思 → KnowledgeZone 面板确认 → 自动去重合并。

## 当前能做什么

- ✅ **UI 层**：完整的 PySide6 聊天面板（流式文本、Thinking 面板、Tool Call 面板、知识确认区、Settings 双标签）· 4 层统一字号体系 (fs13/fs12/fs11/fs10) · 全局 fs() 缩放 · 零文字裁切
- ✅ **通信层**：JSON-RPC stdin/stdout 协议 (QThread 管理 Pi 子进程) · 会话 RPC
- ✅ **工具层**：22 个 Houdini 操作全部实现 (node_utils.py + HTTP 工具执行器)
- ✅ **扩展层**：Pi 扩展 (22 tools TypeBox 注册 + 铁律上下文注入 + edini_search_knowledge 知识检索)
- ✅ **知识层**：铁律 (≤20, rules.json) + 知识库 (entries.json) · AI 反思 · 用户确认
- ✅ **部署**：install.py · setup_pi.bat · settings.json 配置持久化
- ✅ **变更树**：SnapshotEngine 快照 Diff · QTreeWidget 面板（按轮次，可点击跳转 viewport）· Undo/Redo 栈（每轮一个事务，整轮撤销/恢复）· 对话中自动折叠/对话结束自动展开 · shelf tool 预设自动应用
- ✅ **测试**：Mock Hou 模块 + 156 单元测试（node_utils 48 + config 21 + knowledge_store 33 + dedup 12 + reflect_worker 9）
- ✅ **模型**：DeepSeek V3 (默认) · DeepSeek R1 (推理模式) · Anthropic Claude · 35 内置供应商自动同步

## 关键文件速查

| 文件 | 作用 | 关键点 |
|------|------|------|
| `python3.11libs/edini/config.py` | 配置中心 | `_find_pi()` 三级查找 · settings.json · env var · knowledge_enabled |
| `python3.11libs/edini/ui/main_window.py` | 主窗口 | 三栏布局 · 信号绑定 · 知识提取流程（反思→解析→确认→存储）· 轮次计时器 |
| `python3.11libs/edini/ui/agent_panel.py` | 对话面板 | QScrollArea Widget 时间线（_UserBubble / _AiBubble / _Separator / _ErrorBanner）+ Thinking 面板 + Tool Call 面板 + 知识确认区 · QLabel 流式更新 · linkActivated Copy · _pinned_to_bottom 智能滚动 · TypeToggleBadge |
| `python3.11libs/edini/rpc_client.py` | Pi 通信 | `RpcClient` → QThread → `_RpcWorker` · JSON-RPC · 会话 RPC · extension_info 信号 · CREATE_NO_WINDOW |
| `python3.11libs/edini/tool_executor.py` | 工具执行 | `HTTPServer` on daemon thread · 22 `TOOL_HANDLERS` · `/execute` + `/health` |
| `python3.11libs/edini/node_utils.py` | Houdini 操作 | 纯 houp API · create_node 含 namespace 解析 + shelf tool 预设 · 22 个 handler 函数 |
| `python3.11libs/edini/ui/snapshot_engine.py` | 场景快照 | snapshot(root) → 全节点状态 dict · diff(before, after) → 结构化变更 · restore(before, after) → 三阶段节点级回滚 · _filter_descendants 过滤内部子节点 |
| `python3.11libs/edini/ui/change_tree_widget.py` | 变更树面板 | QTreeWidget 按轮次分组 · 创建/修改/删除三级树 · 节点路径可点击跳转 viewport · 参数折叠（≤2全显/3+摘要）· 撤销/重做按钮 · 对话中自动折叠 · undo_round_requested / redo_requested / node_path_requested 信号 |
| `python3.11libs/edini/__init__.py` | 入口 | `create_panel()` / `createPanel()` |
| `python3.11libs/edini/ui/knowledge_store.py` | 知识存储 | 两层 CRUD（rules.json + entries.json）· `parse_extraction_response`（代码块提取/单引号/尾逗号修复）· `find_similar`/`merge_entry` 去重合并 · MAX_RULES=20 |
| `python3.11libs/edini/ui/knowledge_dialog.py` | 知识管理 | 双标签弹窗（铁律/知识库）· 搜索/分类筛选 · 增删改 · 启用禁用 |
| `python3.11libs/edini/ui/knowledge_zone.py` | Knowledge Zone | 右侧面板可折叠浏览 + 反思结果展示 · 条目确认/拒绝 · 合并标注 |
| `python3.11libs/edini/ui/reflect_worker.py` | 反思引擎 | QThread 后台 HTTP 调 LLM · 读 session JSONL · 去重分类 · 5 列供应商 URL |
| `python3.11libs/edini/ui/dedup.py` | 去重模块 | Jaccard 相似度（中英文字符分词）· `classify_items`（new/merge 分类） |
| `python3.11libs/edini/ui/context_panel.py` | 右侧面板 | Pi Status (含 Tools + Round 计时) · Scene · KnowledgeZone |
| `python3.11libs/edini/ui/history_panel.py` | 会话列表 | 浏览模式 · 选中高亮 · 右键删除 · 回到当前 |
| `python3.11libs/edini/ui/settings_dialog.py` | 设置 | General + Knowledge 双标签 · Provider/Model/API Key/外观 · 知识开关/统计/管理 |
| `python3.11libs/edini/ui/pi_sessions.py` | 会话读取 | 直接读 pi JSONL 文件获取会话列表和消息 |
| `pi-extensions/edini-tools/` | Pi 工具 | `index.ts` 注册 22 tools · `forwardTool()` HTTP 转发 · `edini_search_knowledge` 知识检索 |
| `pi-extensions/edini-context/index.ts` | 系统提示 | `before_agent_start` hook 注入 Houdini 上下文 + 读取 rules.json 注入铁律 |
| `scripts/install.py` | 安装 | Houdini 包注册 · MainMenuCommon.xml hconfig |
| `MainMenuCommon.xml` | 菜单 | Edini > Open Chat Panel / Settings |

## 知识沉淀系统架构

```
对话结束
  ↓ knowledge_enabled?
AI 反思（提取 prompt：只记录会重复犯的错）
  ↓
JSON 解析（代码块提取 → 单引号修复 → 尾逗号修复 → json.loads）
  ↓ 有内容
时间线底部弹出知识确认区
  · 每条显示：铁律/知识徽章（可点击切换）| 分类 | 标题 | 内容 | ✓ ✕
  · 全部接受 / 全部放弃 按钮
  ↓ 用户确认
铁律 → rules.json (≤20条，超限淘汰最旧)
知识 → entries.json (无上限)

存储路径：~/.pi/agent/edini-knowledge/
├── rules.json    ← 铁律层（每次会话注入 system prompt）
└── entries.json  ← 知识库层（细节知识，可检索）
```

## 启动命令

```bash
# 1. 安装 Pi
npm install -g @earendil-works/pi-coding-agent

# 2. 安装 Edini 到 Houdini
python scripts/install.py

# 3. 在 Houdini Python Shell
from edini import createPanel
panel = createPanel()
panel.show()

# 4. 点击 ⚙ 设置 API Key
```

## Pi 启动参数

```
pi --mode rpc \
   -e pi-extensions/edini-tools/index.ts \
   -e pi-extensions/edini-context/index.ts
```

- `--mode rpc`: JSON-RPC stdin/stdout 协议
- `-e`: 加载扩展文件
- Pi 以 `cwd=HIP目录` 启动，session JSONL 按项目归档

## 环境变量

| 变量 | 作用 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key（Edini 自动传递） |
| `EDINI_API_KEY` | 覆盖 settings.json 中的 api_key |
| `EDINI_MODEL_PROVIDER` | 覆盖 provider 设置 |
| `EDINI_MODEL_ID` | 覆盖 model_id 设置 |
| `EDINI_TOOL_PORT` | 工具执行器端口（默认 9876） |
| `EDINI_PI_PATH` | 指定 Pi 可执行文件路径 |

## 当前限制

1. **无嵌入式 Panel** — 当前为独立浮动窗口，未注册为 Houdini Pane Tab

## 常见开发任务

### 添加新工具
1. 在 `node_utils.py` 添加 handler 函数（返回 `{success, ...}` 或 `{success:false, error:"msg"}`）
2. 在 `tool_executor.py` 的 `TOOL_HANDLERS` 注册
3. 在 `pi-extensions/edini-tools/tools/` 添加 TypeBox schema + `forwardTool()` 调用
4. 在 `index.ts` 的 `allTools` 数组注册

### 添加新的 AI Provider
1. 在 `~/.pi/agent/models.json` 添加 provider 配置
2. 更新 `settings_dialog.py` 中 PROVIDERS 列表

### 调试通信问题
1. 检查 Pi 进程是否正常启动
2. 检查工具执行器：`curl http://127.0.0.1:9876/health`
3. 查看 Pi 子进程 stderr（pipe 到父进程）
