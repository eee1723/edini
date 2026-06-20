---
name: procedural-modeling
description: Use when a Houdini procedural asset design has been approved and implementation begins. Routes to the correct specialized skill based on which pipeline phase you are in. NOT for design brainstorming (use edini-brainstorm first).
license: MIT
---

# Procedural Modeling — Pipeline Router

轻量路由。不包含规则，只判断当前阶段并指向正确的专用技能。

## 管道阶段判断

```
                    ┌─────────────────┐
                    │ 有 Recipe？      │
                    └────────┬────────┘
                             │
                  ┌──────────▼──────────┐
                  │ validate_recipe     │
                  │ 全部通过？           │
                  └──────┬─────┬───────┘
                     YES  │     │ NO
                          │     └──→ 加载 recipe-authoring
                  ┌───────▼───────┐
                  │ 所有组件       │
                  │ build 通过？   │
                  └───────┬───────┘
                     YES  │     │ NO
                          │     └──→ 加载 component-building
                  ┌───────▼───────┐
                  │ assemble 完成？│
                  └───────┬───────┘
                     YES  │     │ NO
                          │     └──→ 加载 assembly-wiring
                  ┌───────▼───────┐
                  │ test_params   │
                  │ 全部通过？     │
                  └───────┬───────┘
                     YES  │     │ NO
                          │     └──→ 加载 parametric-testing
                  ┌───────▼───────┐
                  │ commit_sandbox│
                  └───────────────┘
```

## 哪个技能用于哪个阶段？

| 阶段 | 信号 | 加载的技能 |
|---|---|---|
| 设计 | 用户说"做一个..." | `edini-brainstorm` |
| 写 Recipe | 设计已批准，无 Recipe | `recipe-authoring` |
| 验证 Recipe | `validate_recipe` 返回错误 | `recipe-authoring` |
| 构建组件 | 验证通过，组件未构建 | `component-building` |
| 组装 | 所有组件 passed，未组装 | `assembly-wiring` |
| 验证 | 组装完成，未验证 | `verification` |
| 参数测试 | 验证通过，未测试边界 | `parametric-testing` |
| 提交 | 全部通过 | 直接 `commit_sandbox` |

## 参考索引（按需加载）

| 需要什么？ | 读取 |
|---|---|
| 参数名参考（H21 验证过的） | [references/parm-reference.md](references/parm-reference.md) |
| 常见陷阱 | [references/pitfalls.md](references/pitfalls.md) |
| Builder schema + construction axis | [references/declarative-builder.md](references/declarative-builder.md) |
| 验证协议 + 调试纪律 | [references/verification-protocol.md](references/verification-protocol.md) |
| 原生模板（hub/spoke/pedal/...） | [scripts/prebuilt-templates.md](scripts/prebuilt-templates.md) |
| VEXlib 使用指南 | [scripts/vexlib-usage.md](scripts/vexlib-usage.md) |
| Recipe 填写模板 | [scripts/recipe-template.md](scripts/recipe-template.md) |

## 关键规则（来自旧版，保持不变）

1. **永远不要使用 `houdini_run_python`** — 已从工具注册表中移除。使用 `build_component(network_mode=true)`。
2. **在设置任何 parm 之前查询参数名** — 使用 `query_parms(type)`。自动目录是权威来源。
3. **用 `@component_id` 标记每个几何组件** — 在创建几何体之前声明。
4. **靠构造保证封闭性，不靠缠绕** — Sweep(endcaptype=1) / PolyExtrude(output_back=1)。
