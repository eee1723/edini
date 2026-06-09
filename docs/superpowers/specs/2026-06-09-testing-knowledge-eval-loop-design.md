# 第二十阶段：测试基建 + 知识检索闭环 + 评估联动

> **状态**: 已批准 — 2026-06-09

## 目标

为 Edini 建立可信赖的质量基础，并打通三个核心闭环：
1. **测试闭环** — node_utils / config / tool_executor 的脱机单元测试
2. **知识检索闭环** — Agent 通过 `edini_search_knowledge` 工具检索知识库
3. **评估→知识联动** — 低分会话自动触发知识提取

## 背景

项目已完成 19 个阶段，功能丰富但测试严重不足（仅 2 个弱测试文件）。知识库的 `search_entries()` 函数已实现但 Agent 无法调用。评估系统的结果未被用来改善知识沉淀。

## 架构

### 1. Mock Hou 模块

创建 `tests/mock_hou.py` — 一个轻量的 `hou` 模块替代品，支持：
- `hou.node("/obj")` → 返回 MockNode 树
- MockNode.children() / .createNode() / .destroy() / .parm() / .set() / .eval()
- `hou.nodeTypeCategories()` → 返回预设节点类型
- `hou.selectedNodes()` → 可配置返回值
- `hou.hipFile.name()` → 可配置

测试通过 `sys.modules["hou"] = mock_hou` 注入，让 node_utils 在无 Houdini 环境下跑。

### 2. edini_search_knowledge 工具

- **Pi 扩展**: `pi-extensions/edini-tools/tools/knowledge.ts` — 注册 `edini_search_knowledge` 工具
- **Python handler**: `python3.11libs/edini/tool_executor.py` 新增 `edini_search_knowledge` → 调用 `knowledge_store.search_entries()`
- 工具参数：`query` (string), `category` (optional), `limit` (optional, default 10)
- 返回：匹配的知识条目列表（title, content, category, tags）

### 3. 评估→知识联动

- 评估完成后，检查 `total_score < 0.5` 的低分会话
- 自动调用知识提取 prompt（复用已有的 `parse_extraction_response`）
- 生成候选条目，存入 entries.json（标记 `auto_extracted: true`）
- 下次会话时 Agent 可通过 `edini_search_knowledge` 查到这些经验

### 4. Handoff 文档更新

- 同步 handoff.md 到第十九阶段内容

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `tests/mock_hou.py` | 新建 | Mock hou 模块，支持所有 22 个 node_utils 函数的测试 |
| `tests/test_node_utils.py` | 新建 | 22 个 handler 的单元测试 |
| `tests/test_config.py` | 新建 | config.py 的测试（路径查找、读写 JSON、迁移） |
| `tests/test_tool_executor.py` | 新建 | HTTP 端点测试（mock node_utils） |
| `tests/test_knowledge_store.py` | 新建 | knowledge_store 的 CRUD + search + parse 测试 |
| `pi-extensions/edini-tools/tools/knowledge.ts` | 新建 | edini_search_knowledge Pi 工具定义 |
| `pi-extensions/edini-tools/index.ts` | 修改 | 注册 knowledge 工具 |
| `python3.11libs/edini/tool_executor.py` | 修改 | 新增 `edini_search_knowledge` handler |
| `wiki/pages/handoff.md` | 更新 | 同步到第十九阶段 |
| `wiki/pages/progress.md` | 更新 | 新增第二十阶段条目 |

## 测试策略

所有测试在无 Houdini 环境下运行（纯 Python 3.11 + pytest）：
1. Mock `hou` 模块提供节点树模拟
2. Mock `hou` 的 node type categories 提供搜索目标
3. Config 测试使用 tempdir 隔离文件系统
4. Tool executor 测试使用 subprocess 启动 HTTP server + requests
5. Knowledge store 测试使用 tempdir 隔离

## 成功标准

- [ ] `pytest tests/` 全部通过，≥30 个测试用例
- [ ] node_utils 的 22 个 handler 各有 ≥1 个测试
- [ ] `edini_search_knowledge` 工具注册并可调用
- [ ] 评估低分会话可自动提取知识条目
- [ ] handoff.md 更新到第十九阶段
