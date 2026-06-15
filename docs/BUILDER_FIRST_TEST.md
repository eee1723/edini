# Builder 首次实测指令（A 站验证）

> **前置确认（人类做）**：已重启 Houdini / Pi 扩展，使新的
> `houdini_build_procedural_asset` 工具被加载。在 Houdini Python shell 里
> 跑 `import edini.harness; print(hasattr(edini.harness, 'build_procedural_asset'))`
> 应返回 `True`；如果 `False`，说明 python3.11libs/edini 没更新（检查
> $HOUDINI_PATH 是否指向本仓库的 python3.11libs）。

## 目的
最小可证伪测试：用声明式 builder 建一个**单组件**（无 Copy-to-Points）的
资产，端到端跑通 build → diagnostics → commit 全链路。这能验证 builder
基础设施（sandbox 创建、python SOP cook、component_id 检查、structure
gate、commit gate）在真实 Houdini 里全部正常，且复用了现有 gate 无需改动。

## 发给 agent 的 prompt（直接复制）

---

用 `houdini_build_procedural_asset` 工具，提交下面这份最小 recipe，建一个
单组件资产。然后报告结果。**不要 commit**——先 build，把结果完整报给我。

recipe 内容：
- asset_name: "builder_smoke"
- components（只 1 个）：
  - id: "frame"
  - code: 一段单 SOP python，生成一个 box（用 hou 几何 API 手建 8 点 12
    三角面，或 createPolygon 拼 6 个四边形面），每个 prim 都 tag
    `component_id="frame"`。必须先 `geo.addAttrib(hou.attribType.Prim,
    "component_id", "")` 再建几何。
  - anchors: [] （空，直接进 merge）
- 不加 orientation_asserts（单组件无朝向需求）
- 不加 postprocess

调用 build 工具后，把你返回结果里的这些字段**逐条**报给我（每个一行）：
1. `success`（应为 true）
2. `build_mode`（应为 "recipe"）
3. `output_node`（应以 /OUT 结尾）
4. `components_built`（应为 ["frame"]）
5. `component_id_check`（missing 应为 []，ok 应为 ["frame"]）
6. `structural_checks`（point_count 应 > 0，bounds_nonzero 应为 true）
7. `structure_advisory.passed`（应为 true——单组件不被判 monolithic）

如果 `success` 是 false，把 `error` 和 `traceback` 完整贴给我，不要自行
重试或修改 recipe。我在看哪一环挂了。

---

## 人类验收清单（agent 报完结果后核对）

| 检查项 | 期望 | 挂了说明 |
|---|---|---|
| `success` | true | builder 基础设施有问题（sandbox 创建/cook/拼装） |
| `output_node` 以 `/OUT` 结尾 | 是 | OUT 节点没建出来 |
| `component_id_check.ok` 含 "frame" | 是 | 组件代码没正确 tag component_id（Prim 属性） |
| `component_id_check.missing` | [] | 同上 |
| `structural_checks.point_count` > 0 | 是 | 几何没生成 |
| `structure_advisory.passed` | true | 不该发生——单组件不是 monolithic；若 false 是 gate 误判 |
| Houdini 网络编辑器里 `/obj/edini_sandbox_.../` 下有 frame_python + merge_all + OUT | 是 | 节点没建对 |

## 全过之后（第二阶段）

最小案例过了，再跑**二组件 + 1 stamp**验证 Copy-to-Points 真实 stamping
（这是 mock 覆盖不到的核心环节）。那个 prompt 我会在第一阶段结果回来后
给你——因为它依赖第一阶段确认的基础设施是好的。
