# 🤖 Agent 交接文档

> **用途**：让新 Agent 或开发者在 Edini 仓库里快速上手。

**最后更新**：2026-06-04（第七阶段：知识沉淀系统）
**当前阶段**：知识沉淀系统完成 · Thinking 独立面板 · Windows 部署配置
**下一阶段**：工具执行反馈（viewport 高亮节点）→ 单元测试
**工作分支**：`main`

## 一句话总结

Edini 是 Houdini 21 的 AI 助手：Python/PySide6 面板 → JSON-RPC 进程通信 → Pi Agent AI 后端 → 16 个 Houdini 工具。当前全部基础架构已就绪，待 Houdini 实机验证。

## 当前能做什么

- ✅ **UI 层**：完整的 PySide6 聊天面板（流式文本、工具卡片、设置对话框、状态栏、暗色模式）
- ✅ **通信层**：JSON-RPC stdin/stdout 协议 (QThread 管理 Pi 子进程)
- ✅ **工具层**：16 个 Houdini 操作全部实现 (node_utils.py + HTTP 工具执行器)
- ✅ **扩展层**：Pi 扩展 (16 tools TypeBox 注册 + 系统提示注入)
- ✅ **部署**：install.py · setup_pi.bat · settings.json 配置持久化
- ✅ **模型**：DeepSeek V3 (默认) · DeepSeek R1 (推理模式)

## 关键文件速查

| 文件 | 作用 | 关键点 |
|------|------|------|
| `python3.11libs/edini/config.py` | 配置中心 | `_find_pi()` 三级查找 · settings.json · env var · knowledge_enabled |
| `python3.11libs/edini/ui/main_window.py` | 主窗口 | 三栏布局 · 信号绑定 · 知识提取流程 · 轮次计时器 |
| `python3.11libs/edini/ui/agent_panel.py` | 对话面板 | 时间线 + Thinking 独立面板(_ThinkingPanelWidget) + Tool Call 面板 · 流式渲染 |
| `python3.11libs/edini/rpc_client.py` | Pi 通信 | `RpcClient` → QThread → `_RpcWorker` · JSON-RPC · 会话 RPC · 通知分流 · CREATE_NO_WINDOW |
| `python3.11libs/edini/tool_executor.py` | 工具执行 | `HTTPServer` on daemon thread · 16 `TOOL_HANDLERS` · `/execute` + `/health` |
| `python3.11libs/edini/node_utils.py` | Houdini 操作 | 纯 houp API · 16 个 handler 函数 |
| `python3.11libs/edini/__init__.py` | 入口 | `create_panel()` / `createPanel()` |
| `python3.11libs/edini/ui/knowledge_store.py` | 知识存储 | JSON CRUD · `_extract_json_array` 平衡括号 · parse_agent_response |
| `python3.11libs/edini/ui/knowledge_dialog.py` | 知识管理 | 弹窗 · 分类筛选 · 删除 · 清空 |
| `python3.11libs/edini/ui/context_panel.py` | 右侧面板 | Pi Status · Scene · Knowledge · 通知 · 轮次计时 |
| `python3.11libs/edini/ui/history_panel.py` | 会话列表 | 浏览模式 · 选中高亮 · 右键删除 |
| `pi-extensions/edini-tools/` | Pi 工具 | `index.ts` 注册 16 tools · `forwardTool()` HTTP 转发 |
| `pi-extensions/edini-context/index.ts` | 系统提示 | `before_agent_start` hook 注入 Houdini 上下文 + 知识库 JSON 读取 |
| `scripts/install.py` | 安装 | Houdini 包注册 · MainMenuCommon.xml hconfig |
| `MainMenuCommon.xml` | 菜单 | Edini > Open Chat Panel / Settings |

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
pi --mode rpc --no-session \
   -e pi-extensions/edini-tools/index.ts \
   -e pi-extensions/edini-context/index.ts
```

- `--mode rpc`: JSON-RPC stdin/stdout 协议
- `--no-session`: 每次对话独立，不持久化上下文
- `-e`: 加载扩展文件

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

1. **无自动化测试** — 所有功能手动验证
2. **无工具执行反馈** — 节点创建后不会在 viewport 高亮
3. **无嵌入式 Panel** — 当前为独立浮动窗口，未注册为 Houdini Pane Tab
4. **知识沉淀依赖 AI 反思质量** — JSON 格式偶有偏差需手动修正

## 常见开发任务

### 添加新工具
1. 在 `node_utils.py` 添加 handler 函数（返回 `{success, ...}` 或 `{success:false, error:"msg"}`）
2. 在 `tool_executor.py` 的 `TOOL_HANDLERS` 注册
3. 在 `pi-extensions/edini-tools/tools/` 添加 TypeBox schema + `forwardTool()` 调用
4. 在 `index.ts` 的 `allTools` 数组注册
5. 运行 `python wiki/scripts/build.py` 更新工具清单

### 添加新的 AI Provider
1. 在 `~/.pi/agent/models.json` 添加 provider 配置
2. 更新 `edini/panel.py` 中 SettingsDialog 的 provider 下拉列表
3. 更新 panel 中 model switch UI

### 调试通信问题
1. 查看 Houdini Console 的 stderr 输出（Pi 进程的 stderr 被重定向到父进程）
2. 检查 Pi 进程是否正常启动：`pi --mode rpc --no-session` 手动运行
3. 检查工具执行器：`curl http://127.0.0.1:9876/health`
