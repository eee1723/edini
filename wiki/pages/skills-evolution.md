# 🧠 知识 → Skills 演化

> **灵感来源**: [Hivemind](https://x.com/kimmonismus/status/2064001045391462907) — Continual Learning for AI Coding Agents
> **创建日期**: 2026-06-09
> **状态**: 规划中

## 背景

Hivemind 的核心理念：**从每个 AI 编程代理的操作轨迹（traces）中提取可复用技能（skills），跨代理共享**。它支持 Claude Code、Codex、Cursor、Hermes、Pi 等多个 agent。

**Edini 已经实现了这个思路的 80%**：

| Hivemind 概念 | Edini 现状 |
|---------------|-----------|
| Traces 收集 | ✅ Pi session `.jsonl` 记录完整对话+工具调用 |
| 知识提取 | ✅ `ReflectWorker` — LLM 分析对话 → 提取知识 |
| 知识存储 | ✅ 两层架构：`rules.json`（铁律）+ `entries.json`（知识库） |
| 去重 | ✅ Jaccard 相似度 + LLM 合并 |
| 注入未来会话 | ✅ `edini-context` 注入铁律；`edini_search_knowledge` 工具查询 |
| 跨 agent 共享 | ❌ 目前仅限 Edini/Pi 内部 |

## 现有数据流

```
对话结束
    │
    ▼
ReflectWorker (QThread 后台)
    │
    ├─ 读取 Pi session .jsonl
    ├─ 加载当前知识库（rules + entries）
    ├─ 构建 prompt（上下文 + 提取标准 + 去重要求）
    ├─ HTTP POST → LLM API
    ├─ 解析 JSON 响应 → 知识条目
    ├─ Jaccard 去重 → 标记 merge
    └─ emits: reflection_done(items)
         │
         ▼
KnowledgeZone（右面板）
    ├─ 展示提取结果 → 用户逐条 ✓✕
    └─ accept → rules.json / entries.json
         │
         ▼
下次会话
    ├─ edini-context 自动注入铁律到 system prompt
    └─ edini_search_knowledge 工具随时查询知识库
```

## 升级目标：Knowledge → Pi Skills

### 目标数据流

```
对话结束
    │
    ▼
ReflectWorker (增强版)
    │
    ├─ 读取 Pi session .jsonl
    ├─ 加载当前知识库 + 现有 skills
    ├─ 构建 prompt（增加 skill 提取维度）
    ├─ HTTP POST → LLM API
    ├─ 解析 JSON 响应 → knowledge 条目 + skill 条目
    ├─ Jaccard 去重
    └─ emits: reflection_done(knowledge_items, skill_items)
         │
         ▼
KnowledgeZone
    ├─ 知识条目 → rules.json / entries.json（现有逻辑）
    └─ Skill 条目 → skills/<name>/SKILL.md（新增）
         │
         ▼
下次 Pi 启动
    └─ 自动加载 skills/ 目录 → 改变 agent 行为
```

### 关键差异

| 维度 | 当前 Knowledge | 升级后 Skills |
|------|---------------|--------------|
| **格式** | JSON（rules.json / entries.json） | Markdown（SKILL.md） |
| **注入方式** | 系统提示注入 / 工具查询 | Pi 原生 skill 加载机制 |
| **内容** | 知识点（避坑、技巧、配置） | 可执行工作流（多步骤操作指南） |
| **粒度** | 1-3 句话描述 | 完整的操作步骤文档 |
| **生命周期** | 永久积累 | 有淘汰机制（使用效果追踪） |

## 实现方案

### P0: 优化现有 ReflectWorker 提取质量（小改动）

**不做新功能，先把现有系统调到最佳状态。**

- 调优提取 prompt 的过滤条件
- 增加"提取后验证"：对提取的知识做二次 LLM 校验
- 统计分析：哪些类型的知识被实际查询到（通过 search_knowledge 调用日志）

### P1: 增加 Skill 提取维度（中等改动）

#### 1. 扩展 ReflectWorker prompt

在 `_REFLECT_PROMPT` 中增加 skill 提取模板：

```python
## Skill 提取（可选）
如果对话中出现了可复用的工作流程（不只是知识点），提取为 Pi skill：

{
  "type": "skill",
  "name": "houdini-vdb-erosion-workflow",
  "description": "Use when creating VDB erosion effects with boolean operations",
  "content": "# VDB Erosion Workflow\n## Steps\n1. ...\n## Pitfalls\n- ..."
}

条件：
- 包含 3 步以上的确定性工作流
- 涉及多个节点连接模式
- 不依赖于具体场景，是通用的操作流程
- 有经验的 Houdini 用户也会受益
```

#### 2. knowledge_store.py 增加 skill 持久化

```python
def _skills_dir() -> Path:
    """Skills → Edini 的 skills/ 目录（Pi 自动加载）"""
    project_skills = Path(os.environ.get("EDINI_PROJECT_DIR", ".")) / "skills"
    project_skills.mkdir(parents=True, exist_ok=True)
    return project_skills

def add_skill(name: str, description: str, content: str) -> Path:
    """写入 SKILL.md 到 skills 目录"""
    skill_dir = _skills_dir() / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{content}",
        encoding="utf-8"
    )
    return skill_path
```

#### 3. 利用 Pi 已有的 skill 加载机制

Pi 已有 `skills/README.md` 和 `--no-skills` 配置，会自动加载 `skills/` 目录下的 `.md` 文件。**不需要改 Pi 代码**，只需把提取的 skills 写入 `skills/` 目录。

#### 4. 输出解析扩展

```python
# parse_extraction_response 的 _normalize_items 中增加:
if item_type == "skill":
    valid.append({
        "type": "skill",
        "name": item.get("name", ""),
        "description": item.get("description", ""),
        "content": item.get("content", ""),
    })
```

### P2: 跨 Agent 共享（大改动 — 真正的 Hivemind）

#### 方案 A: Git Repo 同步

```
~/.pi/agent/edini-knowledge/   ← 本地知识库
~/.pi/agent/edini-skills/      ← 本地 skills
        ↕ git push/pull
github.com/team/edini-shared/  ← 团队共享仓库
```

- 每次 `accept_extracted` 后自动 commit + push
- Pi 启动时 pull 最新
- 团队成员自动获得所有人的知识和 skills

#### 方案 B: SaaS API

- 部署一个轻量 API 服务（FastAPI）
- `POST /knowledge` 提交、`GET /knowledge` 拉取
- 支持多团队、多项目隔离
- 可以给其他 agent（Claude Code、Cursor 等）提供同样的接口

### P3: 反馈循环 — Skill 使用效果追踪

#### 目标

不是所有提取的 skill 都有用。需要一个反馈循环来淘汰低质量 skill。

#### 机制

```
Skill 被加载 → Pi 使用了 skill 中的步骤 → 标记"被使用"
    │
    ▼
30 天内从未被使用的 skill → 标记"待淘汰"
    │
    ▼
淘汰前再做一次 LLM 评估：是否还有价值？
    │
    ▼
确认淘汰 → 移出 skills/ → 归档到 skills-archive/
```

#### 追踪方式

- **被动追踪**：在 `edini-context` 中注入一个 `_skill_used` 工具，agent 使用 skill 后调用
- **主动追踪**：每次 session 结束后，扫描 agent 的工具调用序列，匹配 skill 中提到的节点/操作

## 最小可行验证（1-2 小时）

不改 ReflectWorker，先手动验证 concept：

```python
# scripts/knowledge_to_skills.py
"""把 knowledge entries 中的工作流类条目导出为 Pi skills"""
from pathlib import Path
from edini.ui.knowledge_store import load_entries

count = 0
for entry in load_entries():
    if entry["category"] == "工作流" and len(entry["content"]) > 50:
        skill_name = entry["title"].replace(" ", "-").lower()
        path = Path("skills") / skill_name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"---\nname: {skill_name}\n"
            f"description: Use when {entry['title']} - {entry['content'][:100]}\n---\n\n"
            f"# {entry['title']}\n\n{entry['content']}\n",
            encoding="utf-8"
        )
        count += 1

print(f"Exported {count} skills")
```

运行后重启 Pi，验证 skill 是否被自动加载。

## Edini vs Hivemind 特殊优势

Edini 有一些 Hivemind 不具备的独特优势：

1. **Houdini 领域特异性** — 知识提取聚焦在 3D/VFX 领域，提取质量更高
2. **工具调用结构化** — 22 个 Houdini 工具的调用是结构化数据，比纯文本 traces 更容易分析
3. **评估系统闭环** — 5 维度评估 → 低分会话自动触发知识提取，形成自我改进循环
4. **变更树** — 每轮操作都有 snapshot/diff，可以精确追踪 agent 做了什么
5. **本地运行** — 不依赖 SaaS，数据完全在用户控制下

## 参考资料

- [Hivemind 推文](https://x.com/kimmonismus/status/2064001045391462907) — 灵感来源
- [Pi Skills 文档](../skills/README.md) — Pi skill 加载机制
- [Pi writing-skills](https://github.com/obra/superpowers/skills/writing-skills/) — Skill 编写规范
- [Knowledge Store](../python3.11libs/edini/ui/knowledge_store.py) — 两层知识存储实现
- [ReflectWorker](../python3.11libs/edini/ui/reflect_worker.py) — AI 反思引擎

---

*本页面由 AI Agent 维护。记录 Hivemind 式持续学习的演化路线。*
