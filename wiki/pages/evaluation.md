# 📐 智能体评估系统 — 设计理念

> **最后更新**：2026-06-08 &nbsp;|&nbsp; **状态**：设计阶段 · 待实现 &nbsp;|&nbsp; **版本**：v1 初版

## 为什么需要评估系统

智能体（Agent）不同于传统软件——它的输出是非确定性的。同一个 prompt 在不同模型、不同配置下可能产生完全不同的结果。评估系统是让智能体从"可用"进化到"可靠"的核心工具。

对于 Edini 来说，评估系统解决三个关键问题：

1. **可见性** — 每次对话 agent 做了什么？调了哪些工具？参数填错了没有？
2. **可衡量性** — 如何客观知道这次比上次好？改 prompt 后到底进步了还是退步了？
3. **可改进性** — 如果出了问题，怎么快速定位是工具描述的问题、参数提取的问题、还是 prompt 的问题？

**核心理念：** 评估系统不是为了打分而打分，而是为了给每一轮的修改提供一个客观的 benchmark。没有评估系统的 AI 产品，改进就是摸黑走路。

## 设计哲学

### 1. 分而治之（Dimension First）

一个 agent 的表现不是单一维度能衡量的。我们把评估拆成 5 个正交维度，每个维度独立评分：

| 维度 | 考查什么 | 类型 | 为什么独立 |
|------|---------|------|-----------|
| 工具准确度 | 选对的工具 + 填对的参数 | LLM-as-Judge | 工具调用是 agent 的核心能力 |
| 任务完成度 | 用户的目标是否达成 | LLM-as-Judge | 这是用户关心的最终结果 |
| 效率 | 是否走了最短路径 | 确定性计算 | 绕路浪费时间和 token |
| 可靠性 | 工具调用无错误率 | 确定性计算 | 频繁报错说明基础逻辑有问题 |
| 成本 | token + 延迟开销 | 确定性计算 | 性能再好也要考虑经济性 |

**为什么权重不同？** 工具准确度和任务完成度各占 30%，因为它们直接决定了用户体验。效率和可靠性各 15%，成本 10%——这和用户说出"帮我创建个烟雾模拟"时的期望是一致的：先做对、做成就行，效率可以逐步优化。

### 2. 确定性优先，Judge 辅助

能写代码算的，绝不用 LLM：

- **可靠性** = 成功调用数 / 总调用数 —— 纯数学
- **效率** = 最小步数 / 实际步数 —— 对比同类任务的最优记录
- **成本** = 基于同类任务百分位的评分 —— 统计计算

只有**需要理解语义**的场景才用 LLM-as-Judge：
- 这个 tool 选得合理吗？（要考虑用户意图）
- 这个任务完成了吗？（要考虑 Houdini 场景的上下文）

**Judge 采样策略：** 第一次评分 100% 跑，后续 50% 采样。因为大部分时候 agent 的表现是稳定的，全量评 Judge 是浪费 token——用采样发现问题趋势就够了。

### 3. JSONL 即真理源（Immutability of Logs）

```
JSONL (原始数据) ──只读──► LogParser ──► Evaluator ──► SQLite (评估缓存)
                                      ▲                      │
                                      └── 可重建（删了重评）──┘
```

- Pi 的 JSONL 会话文件是唯一权威源，**不往里写任何评估数据**
- SQLite 只是评估视图缓存——删了可以从 JSONL 重建
- 这意味着未来的评估方法可以升级，历史数据不会被污染

### 4. 闭环反思（Agent Self-Reflection）

评估系统不仅给开发者看，也给 agent 自己看。`edini_get_eval_stats` 工具让 agent 在对话中查询自己的历史评分：

- **看到薄弱维度** → 比如 tool_accuracy 低，接下来会更仔细地提取参数
- **看到高频错误** → 知道自己经常在什么场景出问题，主动避免
- **看到趋势** → 知道最近的修改方向是对是错

这形成了一个"执行 → 评估 → 反思 → 改进"的自我优化循环。

### 5. 迭代演进

评估系统本身也需要迭代。v1 的目标是：

- 先跑通基础流水线（Log → Score → UI）
- 用确定的评估维度积累数据
- 有了数据后再优化权重和 Judge 提示词

**后续可能的方向：**
- 用实际用户反馈校准 Judge 模型（Human-in-the-loop）
- 基于评估数据做主动学习（哪些 session 最需要人工审阅）
- 评估结果反哺到知识系统（自动提取"铁律"）
- AB 实验框架（同时跑两个模型配置，对比评分）

## 数据流详解

```
┌─────────────────────────────────────────────────────────────┐
│                  数据流（离线+在线结合）                       │
└─────────────────────────────────────────────────────────────┘

在线路径（对话进行中）:
  User Input
    ▼
  Pi Agent ──thinking──► tool call ──► tool result ──► response
    │                                                           │
    └──────────── JSONL append (自动) ───────────────────────────┘

离线路径（对话结束后）:
  JSONL
    ▼
  LogParser ──► StructuredSession
    ▼
  EvaluatorPipeline
    ├── ReliabilityEval (确定性)
    ├── EfficiencyEval (确定性)
    ├── CostEval (确定性)
    ├── ToolAccuracyEval (LLM-as-Judge, 50% 采样)
    └── TaskCompletionEval (LLM-as-Judge, 50% 采样)
    ▼
  SQLite EvalStore
    ├── sessions 表
    ├── tool_calls 表
    ├── judge_logs 表
    └── daily_aggregates 表
    ▼
  EvalDashboard (PySide6 Tab)
    开发者查看评分 + 趋势 + 详情
    ▼
  edini_get_eval_stats (Pi Tool)
    Agent 自省查询
```

## SQLite Schema 设计说明

sessions 表的设计目标是一个会话一行，既存评分也存元数据，方便 UI 做列表展示和排序：

- `total_score` 是加权总和，但 `tool_accuracy` 等原始维度也保留——UI 可以展示雷达图、用户也可以自定义权重
- `judge_logs` 表是个"黑匣子"——存下每次 Judge 调用的完整 prompt 和 response，用来调试 Judge 本身的质量
- `daily_aggregates` 是预聚合——UI 的趋势图不需要每次扫描全表

## 评估维度的计算方法

### 效率（Efficiency）

```
efficiency = min(1.0, optimal_steps / actual_steps)
```

其中 `optimal_steps` 取最近 50 个同类任务的最小步数。同类任务按第一个工具调用分类（如 `houdini_create_node` 开头的是一类）。

### 可靠性（Reliability）

```
reliability = successful_tool_calls / total_tool_calls
```

工具调用超时（>30s）也视为失败。

### 成本（Cost）

```
cost = clamp(0.0, 1.0, 1.0 - (total_tokens - p10_tokens) / (p90_tokens - p10_tokens))
```

p10/p90 基于同类任务的历史百分位。没有历史数据时用固定基线。

## LLM-as-Judge 的质量控制

Judge 本身也是 LLM，也会有偏见和不稳定。我们通过以下方式控制：

1. **仅 Judge 需要理解语义的维度** — 确定性计算不需要 Judge
2. **结构化输出** — 强制 JSON 格式，带 score + reason，方便程序解析和人工核验
3. **Judge 日志** — 每次 Judge 调用都记录完整 prompt 和 response，可以审计 Judge 质量
4. **未来扩展** — 可以引入人类标注者对 Judge 结果做抽样验证，计算 precision/recall

## 与现有系统的关系

| 现有系统 | 关系 |
|---------|------|
| Pi JSONL sessions | 数据源（只读） |
| pi_sessions.py | LogParser 可复用部分解析逻辑 |
| knowledge 系统 | 未来可将评估中发现的模式错误自动提取为铁律 |
| Houdini scene | 评估不直接接触场景，只分析 JSONL 记录的工具调用 |
| pi-visionizer | Judge 可复用 vision model 作为更强评估模型 |

## 实测结果（2026-06-08）

在 8 个真实 Houdini 对话上运行了完整评估流程：

| 会话 | 工具数 | 成功率 | 工具准确度 | 任务完成度 | 总分 |
|------|--------|--------|-----------|-----------|------|
| 场景分析 | 8 | 88% | 0.30 | 0.00 | 0.300 |
| 节点调试+分析 | 34 | 79% | 0.20 | 0.00 | 0.183 |
| 节点分析+创建HDA | 85 | 82% | 0.30 | 0.90 | 0.485 |
| 节点分析 | 20 | 65% | 0.30 | 0.00 | 0.195 |
| 场景检查+节点信息 | 12 | 92% | 0.00 | 0.00 | 0.190 |
| 创建HDA打包工具 | 35 | 71% | 0.30 | 0.00 | 0.201 |
| 创建HDA+配置 | 17 | 94% | 0.30 | 0.00 | 0.273 |
| HDA开发+创建节点 | 37 | 87% | 0.00 | 0.00 | 0.142 |

**关键发现：**

1. **确定性维度（Reliability/Efficiency/Cost）工作稳定** — 纯数学计算，零成本
2. **LLM-as-Judge 需要合适的模型** — deepseek-v4-pro 的推理模式（reasoning_tokens）会隐藏输出的可见内容，导致 JSON 无法解析。改用 deepseek-chat（v4-flash）后正常工作
3. **Task Completion 评分有区分度** — 唯一一个实际完成任务的会话（HDA 创建）获得 0.9 分，其余探索性会话得 0.0
4. **Tool Accuracy 偏保守** — 因为 Pi RPC JSONL 不存储 tool 参数，Judge 看到空 params 会降低评分
5. **效率评分在当前启发式下偏低** — 长会话（35+ calls）cost=0.0，需要基于任务类型的百分位基线来改进

**下一步：**
- 将 Judge 采样率设为 50% 以控制成本
- 接入 Anthropic Claude 做 Judge（更擅长结构化输出）
- 优化效率/evaluation 计算使用百分位基线
- 添加自定义 Judge 模型配置

## 经验教训

### DeepSeek V4 Pro 的 reasoning_tokens 问题

DeepSeek V4 Pro 使用 reasoning_tokens 来存储思考过程。当模型需要输出 JSON 时，如果 prompt 不够明确，模型会在 reasoning_tokens 中做推理而不输出可见内容。

**解决方案：**
1. 添加明确的 system prompt "Output ONLY valid JSON"
2. 使用 `deepseek-chat`（v4-flash）作为 Judge 模型，它不隐藏输出
3. 备选方案：从 `reasoning_content` 字段中搜索 JSON 模式

### Pi RPC JSONL 格式

Pi 的 RPC 模式（`--mode rpc`）产生的 JSONL 格式与标准 Pi 格式不同：
- 工具调用结果以 `role="toolResult"` 的消息条目存储
- 工具名称在 `message.toolName` 字段
- 参数不单独存储（只存在结果 JSON 中）

这意味着 LogParser 不能依赖 `params` 字段来判断参数正确性，只能从结果内容中提取信息。

### Python 3.11 f-string 限制

Python 3.11（Houdini 使用的版本）不允许在 f-string 表达式中使用反斜杠转义。以下写法会报错：

```python
# Python 3.12+ OK
f"{'{\"score\": 0.5}'}"

# Python 3.11 需要改为
_json_example = '{"score": 0.5}'
f"{_json_example}"
```

同样地，`\u2014`（em dash）在 f-string 中也不允许，需要提取为模块级常量 `_EM_DASH = "\u2014"` 再引用。

### Pi RPC 事件时序

Pi 的 RPC 模式发送独立事件流。`agent_end`（对话完成）和 `session_switched`（回话路径确认）是两个独立事件，可能以任意顺序到达。在首次对话中，`agent_end` 通常先于 `session_switched` 到达。

这意味着在 `_on_agent_done` 中不能假设 `_current_session_path` 已经可用。需要延迟触发评估：

```python
if not self._current_session_path:
    # 等待 session_switched 信号
    self._rpc_client.session_switched.connect(self._on_deferred_eval)
else:
    self.agent_panel.finish_streaming()  # 立即评估
```

## 变更日志

| 日期 | 变更 |
|------|------|
| 2026-06-08 | 端到端调试完成：6 个 bug 修复后评估系统可正常运行 |
| 2026-06-08 | 实测阶段：修复 LogParser 兼容 Pi RPC 格式，对接真实 Judge API，优化 JSON 解析逻辑 |
| 2026-06-08 | 初版设计：5 维度评估 + SQLite + UI Dashboard + AgentEval 工具 |
