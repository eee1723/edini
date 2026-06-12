# 🧪 Procedural Harness

> 最后更新：2026-06-12 ｜ 状态：Phase B 已合入 `master` ｜ 目标：让程序化建模先进入可诊断、可验证、可回滚的沙盒流程。

## 这批解决了什么

Procedural Harness 是 Edini 给 Houdini 程序化建模加上的一层执行护栏。它不再让 AI 一上来就用 `houdini_run_python` 在用户的 live scene 里直接试错，而是要求先创建 `/obj/edini_sandbox_*` 沙盒节点，把生成结果、诊断、结构验证和最终提交拆成清晰步骤。

这批主要落地了：

| 能力 | 内容 | 观察点 |
|------|------|--------|
| Live sandbox | `houdini_run_python_sandbox` 创建唯一 job id 和沙盒根节点 | 新资产应先出现在 `/obj/edini_sandbox_*` 下 |
| JSON-safe result | Houdini 节点对象、集合、递归对象会转成安全 JSON | tool result 不应因为对象不可序列化而崩掉 |
| Diagnostics | `houdini_collect_diagnostics` 收集节点错误、警告、参数、几何统计、bounds | 失败后应先看到诊断，而不是马上删除节点 |
| Structural verify | `houdini_verify_asset` 检查 `min_points`、`min_prims`、`bounds_nonzero`、node errors | commit 前应有结构证据 |
| Lifecycle | `houdini_commit_sandbox` / `houdini_discard_sandbox` 管理沙盒去留 | 通过后改名提交，废弃时显式删除 |
| Safe capture | `houdini_capture_review` 支持多视角接触表截取 | 截图失败时应干净报告，不探索 Qt 私有接口 |
| Skill guidance | `procedural-modeling` 明确要求 harness-first | 生成程序化资产时不应优先 raw run |
| Pi tools | Pi extension 暴露 harness tool schema | Agent 可直接选择 sandbox/verify/commit/diagnostics 工具 |

## 标准测试流程

1. 让 Agent 创建一个明确的程序化资产，例如 ladder、parametric stair、scatter pattern 或 L-system tree。
2. 观察它是否先调用 `houdini_run_python_sandbox`，并返回 `job_id`、`execution_mode: live_sandbox`、`root_path`。
3. 如果生成失败，观察是否保留失败沙盒，并调用 `houdini_collect_diagnostics` 读取错误、警告、traceback 或几何状态。
4. 如果生成成功，观察是否调用 `houdini_verify_asset`，至少检查非空几何和非零 bounds。
5. 结构检查通过后，再观察是否调用 `houdini_capture_review` 做视觉确认。
6. 用户确认或结果足够明确后，再调用 `houdini_commit_sandbox` 把沙盒改成最终资产名。
7. 不需要的沙盒应通过 `houdini_discard_sandbox` 清理。

## 手测时重点盯什么

### 应该出现的好信号

- 工具调用顺序是 sandbox → diagnostics/verify → safe capture → commit/discard。
- 失败节点没有被立即删除，能在 Houdini 里看到失败现场。
- tool result 里包含 `root_path`、`job_id`、`diagnostics`、`geometry.point_count`、`geometry.prim_count`、`bounds.size`。
- Agent 在切换 Python SOP / VEX / node network 策略前，会先解释诊断结果。
- `houdini_run_python` 的使用变少，只在专家调试或非程序化资产任务里出现。
- 截图失败时返回明确错误和阶段信息，不尝试 `QtWidgets`、viewport internals 或 main window 探测。

### 需要警惕的坏信号

- 一开始就 raw `houdini_run_python`，并直接改 live scene。
- Python SOP 或 VEX cook 失败后，Agent 先删节点或立刻换方案，没有诊断。
- commit 前没有 point/primitive/bounds 结构验证。
- tool result 里出现 JSON serialization error、circular reference、node object repr 崩溃。
- `commit_on_success` 被误理解成自动提交，但实际没有调用 `houdini_commit_sandbox`。
- final node 重名时没有说明 `replace_existing` 策略。
- 截图失败后开始探索 Qt widget、desktop pane internals 或 unsupported HOM API。

## 互动手测清单

可打开这个单文件 HTML 来做手测记录：

[Procedural Harness 手测清单](../../docs/procedural_harness_test_guide.html)

清单包含 19 个测试项，覆盖基础生成、失败诊断、结构验证、生命周期、skill 行为和安全截图。每项有“通过 / 失败 / 未测”状态、备注框、localStorage 保存和报告导出。

## 代码入口

| 区域 | 文件 |
|------|------|
| Harness 实现 | `edini/harness.py`、`python3.11libs/edini/harness.py` |
| Tool executor 注册 | `edini/tool_executor.py`、`python3.11libs/edini/tool_executor.py` |
| Pi tool schema | `pi-extensions/edini-tools/tools/harness.ts` |
| Pi tool index | `pi-extensions/edini-tools/index.ts` |
| Skill 指南 | `skills/procedural-modeling/SKILL.md` |
| Skill 预览 | `skills/procedural-modeling/preview.html` |
| Ladder 回归说明 | `docs/harness_ladder_regression.md` |
| 互动清单 | `docs/procedural_harness_test_guide.html` |
| 单测 | `tests/test_procedural_harness.py`、`tests/test_tool_executor_harness.py`、`tests/test_pi_harness_tools.py` |

## 当前限制

- Phase B 仍运行在 live Houdini 进程内，不能提供 OS 级 crash isolation。
- `commit_on_success` 当前只记录请求状态，不自动 commit；正式提交仍应显式调用 `houdini_commit_sandbox`。
- 结构验证是通用的 point/primitive/bounds 检查，不理解每一种资产的语义完整性。
- Phase C 才会把高风险程序化 job 移到外部 worker。

## 验证状态

最近主线合并后的验证结果：

```text
python -m pytest
216 passed, 5043 warnings

python -m compileall -q python3.11libs/edini edini
passed
```
