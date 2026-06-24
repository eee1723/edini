# 🤖 Agent 交接文档

> **用途**：让新 Agent 或开发者在 Edini 仓库里快速上手。

**最后更新**：2026-06-24（recipe_rebuild 4 bug 修复 + 架构清理：harness.py 死代码删除 + edini-context system prompt 更新）
**当前阶段**：Recipe Library 核心 + 递归树抓取 + VEX 配方 + **recipe_rebuild 真实 Houdini 验证通过** + 旧程序化死代码清理完成
**下一步**：给高价值配方补 Notes → 实现 Dashboard HDA（scan_tree + Qt 树面板）
**工作分支**：`master`

---

## 🔴 最重要：2026-06-23 架构转向（必读）

### 发生了什么

旧的程序化建模管道（提示词驱动 + validate_recipe/build_procedural_asset/G1-G3 闸门）
**已完全关闭并备份**。根因：LLM 对 Houdini 不熟，靠提示词规则无论写多细还是会出错。

### 两件大事

**1. 关闭程序化建模（已备份，可恢复）**
- 7 个 skill + 5 个 Python 模块 + 23 个测试 → `_disabled_backup/procedural-modeling/`
- tool_executor.py 移除 4 个工具注册（build_procedural_asset/validate_recipe/rebuild_component/houdini_variant_scatter）
- harness.ts 移除 3 个 TS 工具定义
- 恢复方式：见 `python3.11libs/edini/tool_executor.py` 顶部 NOTE 注释

**2. 新建 Recipe Library（核心完成 + schema v2 + 真实验证）**
- `python3.11libs/edini/recipe_library.py`（~900 行）：**5 个工具**
  - `recipe_capture(subnet_path, ...)` — 捕获 subnet 内部网络→配方 JSON（支持 kind/tree_path/vex_snippets）
  - `recipe_capture_tree(root_path)` — **递归扫整棵分类树，自动抓所有叶子 subnet**（一次抓完用户手搭的分类树）
  - `recipe_list(query, category, kind)` — 查询索引（按关键词/分类/kind 检索，支持 tree_path 组件命中）
  - `recipe_read(recipe_id)` — 读完整配方（含 vex_snippets 代码）
  - `recipe_rebuild(recipe_id, parent_path, overrides)` — 拓扑排序重建+内置验证+还原 VEX snippet
- **配方 JSON schema v2**：nodes（相对名 inputs）/ changed_params / marked_params / exposed_parms / **kind**（network|vex）/ **tree_path**（分类面包屑）/ **vex_snippets**（wrangle 代码+runover）
- subnet Notes 强制非空作元数据（功能/重要参数/不要用于）；tree_capture 时空 Notes 自动生成
- `pi-extensions/edini-tools/tools/recipe.ts`：5 工具 TS 定义
- `skills/recipe-library/SKILL.md`：自动注册的轻量 skill（含 tree capture + 两 kind 说明）
- `tests/test_recipe_library.py`：30 测试 + 2 subtests，全绿

### 当前状态

- **35 recipe 测试全绿**（30 schema v2 + 5 新增回归：dopnet 分类层下钻、multiparm 名字归一化、scalar/list 默认值比较、ramp dict 往返、harness 死代码移除后无回归）。完整套件 **300 passed**。
- **47 个工具注册**（recipe 5 个 + 共享工具保留）
- **2 个 skill**（grill-me + recipe-library）
- **recipe_rebuild 真实 Houdini 端到端验证通过**：Base_Sweep（spiral+circle→sweep）重建成功，`verify.ok=True, mismatches=[]`。修复 4 个真实 bug：①dopnet 分类层不下钻（noise_forece 抓不到）②rebuild 用 subnet 容器致 SOP 节点创建失败（改用 geo）③multiparm 实例名 vs manifest 模板名不匹配（heightprofile2pos vs #pos）④Ramp 序列化为字符串 + scalar/list 默认值不等。
- **架构清理完成（2026-06-24）**：
  - `harness.py` 4644→**1810 行**（删 2834 行死代码：build_procedural_asset/rebuild_component/build_variant_scatter/validate_recipe_tool 整条 builder 链 + _validate_recipe/_build_*_component/_safe_create_node 等），7 个共享工具 import 不变、功能不变
  - `edini-context/index.ts` system prompt 从「强制 build_procedural_asset」改为「recipe-library 优先 + 通用几何验证」
  - `node_utils.py`/`mock_hou.py` 移除过时的 procedural-modeling-bugs.md/build_procedural_asset 引用
  - 2 个纯 vexlib 手动脚本移到 `_disabled_backup/procedural-modeling/tests/`
  - commit `ce7431b`（4 bug 修复）+ 后续清理 commit
- **配方库配方是 Houdini 本地产物**（随 .hip 存，不随 git）—— 新环境需在 Houdini 里重抓。

### 下一步该做什么

1. **给高价值配方补 Notes**（最优先，需真实 Houdini）
   - 给 Base_Sweep / noise_forece 等选中 subnet → 按 `C` 写 `功能：...` + `重要参数：...` → `recipe_capture` 重抓
   - Notes 是搜索质量的根本——auto-generated 占位文本搜索效果差

2. **验证 recipe_rebuild**（补完 Notes 后）
   - 聊天面板发「用 tube 配方重建一个」测真实重建
   - 重点验：exposed_parms override 生效、vex_snippet 还原、verify.mismatches 为空

3. **实现 Dashboard HDA**（验证后）
   - 设计文档：`docs/edini/recipe-manager-hda-design.md`
   - 阶段 1：scan_tree + create_recipe_manager（递归读 HDA 内部 subnet 树）
   - 阶段 3：Qt 树面板（recipe_tree_window.py，QTreeView）
   - 关键技术点：createDigitalAsset(save_as_locked=False) + PythonModule 调 recipe_library

## 关键文件速查（新增 Recipe Library 部分）

| 文件 | 作用 |
|------|------|
| `python3.11libs/edini/recipe_library.py` | **Recipe Library 核心**：4 工具 + 配方 schema + 拓扑排序重建 |
| `pi-extensions/edini-tools/tools/recipe.ts` | 4 recipe 工具的 TS 定义（LLM 接口） |
| `skills/recipe-library/SKILL.md` | recipe-library skill（自动注册） |
| `tests/test_recipe_library.py` | 20 测试（捕获/重建/索引/notes 校验） |
| `docs/edini/recipe-manager-hda-design.md` | Dashboard HDA 设计文档（定稿） |
| `docs/edini/recipe-library-testing.md` | 真实 Houdini 测试指南 |
| `docs/edini/recipe-library-getting-started.md` | 搭建第一个配方指南 |
| `_disabled_backup/procedural-modeling/` | 旧程序化建模完整备份（7 skill + 5 模块 + 23 测试） |

---

## 历史记录（2026-06-09 之前，保留作参考）

> 以下是架构转向前的交接记录，程序化建模部分已废弃（备份在 _disabled_backup/）。

## 第二十一阶段修复记录（Houdini 实测后修复 4 个 bug）

1. `RpcClient` 缺 `thinking_delta`/`tool_result`/`extension_info` 等 6 个信号 — Phase 20 sync 覆盖了完整版
2. `_on_change_undo`/`_redo`/`_node_requested` 3 个方法误删 — 字节替换时范围过大
3. `PROJECT_ROOT` 差一级，Pi 找不到扩展 — `config.py` 在 `python3.11libs/edini/` 时 parent.parent 是 `python3.11libs/` 而非 `edini/`
4. `config.py` 缺 `get_pi_ai_providers` 等 6 个桥接函数 — Phase 19 代码在 sync 中丢失

**经验教训**：`edini/` 和 `python3.11libs/edini/` 是两个独立的安装路径，同步时不能简单覆盖，需要双向对比确保功能完整。最好用 `diff` 对比后再合并。

## Procedural Harness Handoff (2026-06-12)

- Worktree: `E:/edini/.worktrees/procedural-harness`
- Branch: `codex/procedural-harness`
- Current HEAD: `0930850 fix(harness): sanitize output diagnostics path`
- Base plan: `docs/superpowers/plans/2026-06-11-edini-procedural-harness.md`
- Design spec: `docs/superpowers/specs/2026-06-11-edini-procedural-harness-design.md`
- Status: Phase B procedural harness is implemented, documented, and final-review approved after two JSON-safety fixes.
- Scope landed: live procedural sandbox, diagnostics before retry/delete, structural verification, commit/discard lifecycle, safe flipbook viewport capture, Pi harness tools, procedural-modeling skill guidance, and ladder regression coverage.
- Phase C path preserved: harness results include `job_id`, `execution_mode`, diagnostics bundles, JSON-safe result payloads, and artifact-shaped fields so an external worker can replace live sandbox execution later.
- Final focused verification: `python -m pytest tests/test_node_utils.py tests/test_procedural_harness.py tests/test_tool_executor_harness.py tests/test_capture_tools.py tests/test_pi_harness_tools.py -q` -> `111 passed, 743 warnings`.
- Compile/read checks passed: Python `py_compile` for harness/node_utils/tool_executor source/runtime copies, Pi TS file readability check, and source/runtime copy comparisons.
- Full-suite blocker: `python -m pytest tests -q` still has one unrelated failure, `tests/test_config.py::TestGetPiEnv::test_vision_env_not_set_when_configured`, where `VISIONIZER_PROVIDER` is `openai` but the test expects `None`.
- Diff check: the procedural harness branch does not modify `edini/config.py`, `python3.11libs/edini/config.py`, or `tests/test_config.py`; do not mix that config behavior decision into the harness commits unless explicitly choosing to resolve the blocker.
- Next continuation step: decide/fix the config test behavior, rerun full verification, then use the finishing branch workflow to choose merge, PR, keep-as-is, or discard.

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
