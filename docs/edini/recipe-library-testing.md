# Recipe Library — 测试方法 & HDA 创建

> 本文档讲清两件事：
> 1. **HDA 怎么创建**（适配 recipe 方案——内容不锁定，LLM 可读）
> 2. **怎么测试 recipe 链路**（subnet 直连 → HDA 包装，3 种粒度）

---

## 一、HDA 怎么创建

### 核心认知：为什么默认 HDA 不适合 recipe

Houdini 的 `createDigitalAsset()` 默认 `save_as_locked=True`——创建后内部节点被
**锁成黑盒**，`subnet.children()` 返回空，LLM 读不到配方。你的方案要求内部透明，
所以必须让 HDA **不锁定**。

### 方式 A：subnet 直接捕获（推荐起步，无需 HDA）

`recipe_capture` 工具读的是 `subnet.children()`，**普通 subnet 也能捕获**。
HDA 不是必需的——它只是「带版本管理 + 仪表盘的 subnet 包装」。

```
普通 subnet  → recipe_capture → recipe.json   ✅ 完全可用
HDA（unlocked）→ recipe_capture → recipe.json  ✅ 也能用，多版本管理
```

**起步就用 subnet**，等配方稳定、需要版本管理时再升级成 HDA。

### 方式 B：创建不锁定的 HDA（手动，Houdini UI）

这是最可靠的方式——在 UI 里建，控制每个选项：

1. 在 `/obj` 搭好你的 subnet（内部节点 + 参数 + Notes）
2. 右键 subnet → **Create Digital Asset**
3. 弹窗里：
   - **Operator Name**: `tube_along_curve`（全小写下划线）
   - **Operator Label**: `Tube Along Curve`
   - **Save to Library**: 选一个 .hda 文件路径
   - ⚠️ **取消勾选 "Save Contents as Locked"**（关键！）
4. 点 Accept

创建后验证不锁定：右键 HDA 节点应该能看到 **"Allow Editing of Contents"**
（如果显示 "Lock Contents" 说明已经是 unlock 状态，符合预期）。

### 方式 C：用 Edini 工具创建（自动，需改 create_hda）

现有 `create_hda` 工具调 `createDigitalAsset()` 不传 `save_as_locked`，默认锁定。
要支持不锁定，需要小改 `node_utils.py` 的 `create_hda`：

```python
# 当前（锁定）:
node.createDigitalAsset(name=hda_name, hda_file_name=save_path, description=hda_label)

# 改为（不锁定）:
node.createDigitalAsset(
    name=hda_name, hda_file_name=save_path, description=hda_label,
    save_as_locked=False,   # ← 关键：内容不锁定，LLM 可读内部节点
)
```

> 如果你要走这条自动路径，告诉我，我改 `create_hda` 加一个
> `save_as_locked=False` 参数（默认 False 适配 recipe 方案）。

### 方式 D：已有锁定的 HDA，事后 unlock

如果 HDA 已经建好了且是锁定的：

```python
# 在 Houdini Python 里：
node = hou.node("/obj/my_hda")
# 方法1：通过 definition
definition = node.type().definition()
definition.setLocked(False)  # 或用 unlock API
# 方法2：UI 右键 → Allow Editing of Contents
```

---

## 二、怎么测试 recipe 链路

### 测试粒度（从简到全）

| 粒度 | 载体 | 验证什么 | 适合谁 |
|---|---|---|---|
| **1. 自动化测试** | mock_hou | 捕获/重建/索引逻辑（无 Houdini） | 已完成，20 测试全绿 |
| **2. subnet 直连** | 普通 subnet | 真实 hou 的 children/parms/promote 检测 | **你现在该做这步** |
| **3. HDA 包装** | 不锁定 HDA | HDA 实例的 children 读取 | 配方稳定后再验 |

### 测试 1：自动化测试（已通过，无需 Houdini）

```bash
cd E:\edini
python -m pytest tests/test_recipe_library.py -v
```

这覆盖了核心逻辑（notes 校验、changed/default 判定、拓扑排序、相对名 inputs、
索引重建、隔离）。20 个测试全绿，证明逻辑正确。

### 测试 2：subnet 直连（真实 Houdini，推荐现在做）

**目标**：验证真实 hou API 的边界（promote 参数检测、input connectors、
manifest 默认值对比）。

#### 步骤 1：启动 Houdini + Edini

1. 打开 Houdini 21
2. 菜单 **Edini → Open Chat Panel**（`Alt+Shift+E`）
3. 等待「Edini tools loaded」通知

#### 步骤 2：手动搭一个简单 subnet

在 Edini 聊天里说：

> 在 /obj 下创建一个 subnet 叫 test_tube，里面放一个 curve 节点叫 guide，
> 一个 sweep::2.0 节点叫 sweep1，把 guide 连到 sweep1 的第0输入，设 sweep1
> 的 endcaptype 为 1

或者你自己在 Houdini UI 里搭。

#### 步骤 3：写 Notes（强制）

选中 `test_tube` subnet，按 `C` 打开 Notes，写：

```
功能：测试用管材配方
重要参数：endcaptype
```

#### 步骤 4：捕获

在 Edini 聊天：

> 捕获 /obj/test_tube 到配方库

工具调用 `recipe_capture(subnet_path="/obj/test_tube")`。

**看返回**：
- `success: true` → 检查 `E:\edini\recipes\test_tube\recipe.json` 生成
- `success: false` → 看错误（最常见：Notes 空/占位、节点路径错）

#### 步骤 5：读配方验证

> 读取 test_tube 配方的详情

`recipe_read(recipe_id="test_tube")`。

**重点检查 recipe.json 的 nodes 字段**：
- `guide` 节点：type 是否正确
- `sweep1` 节点：`changed_params` 是否含 `endcaptype: 1`
- `sweep1.inputs`：`{"0": "guide"}` —— 相对名引用
- `marked_params`：含 `endcaptype`（因为 Notes 标了）

#### 步骤 6：重建（核心测试）

> 用 test_tube 配方在 /obj 重建一个实例

`recipe_rebuild(recipe_id="test_tube", parent_path="/obj", name="test_tube_rebuilt")`。

**看返回**：
- `success: true` + `verify.ok: true` → 完美
- `verify.mismatches` 非空 → 读具体哪个节点/参数对不上

#### 步骤 7：人工对比

在 Houdini 里对比 `test_tube` 和 `test_tube_rebuilt`：
- 内部节点结构一致？
- 连线一致？
- endcaptype 都是 1？

### 测试 3：HDA 包装（配方稳定后）

subnet 直连验证通过后，把 subnet 升级成不锁定 HDA（方式 B），重跑步骤 4-7。
验证 HDA 实例的 `.children()` 也能被正确捕获。

---

## 三、常见测试问题排查

### 捕获失败：Notes 相关

| 错误 | 原因 | 解决 |
|---|---|---|
| `Notes 为空` | subnet 没写 Notes，或写在内部节点上 | 选中 subnet 本身写 Notes |
| `占位文本` | Notes 是 "todo"/"notes" 等占位词 | 写真实功能说明 |
| `太短` | Notes 少于 4 字符 | 写详细点 |

### 捕获成功但 changed_params 空

→ 所有参数都等于 manifest 默认值。这是**正确行为**。如果你想强制记录某参数，
在 Notes 加 `重要参数：<parm名>`，它会进 `marked_params`。

### 捕获成功但 exposed_parms 空

→ promote 的参数没被检测到。recipe_capture 通过识别 subnet 顶层 parm 的
**channel reference 表达式**（`ch("../inner/parm")`）来判断 promote。

排查：
- 确认你用的是 **Promote Parameter**（右键 → Promote），不是手动加 parm
- 在 Houdini 里检查提升的 parm 是否有 expression（右键 parm → Expression）

### 重建 verify.mismatches 非空

| mismatch | 原因 | 解决 |
|---|---|---|
| `node.parm: parm missing` | 重建的节点类型没这 parm | 检查 manifest 是否缺该节点类型 |
| `expected X, got Y` | 参数没设上 | 可能是 multiparm/需要 pressButton |

### 重建后连线缺失

→ 配方的 `inputs` 用相对名，但重建时上游节点名对不上。检查 recipe.json 的
`nodes[].inputs` 是否正确引用了内部节点名。

---

## 四、快速验证清单

跑通后，确认这些关键点都 OK：

- [ ] `recipe_capture` 能读真实 subnet 的子节点（不是空）
- [ ] `changed_params` 正确区分改过的参数（不是全空也不是全记录）
- [ ] `marked_params` 记录了 Notes 标的参数（即使等于默认）
- [ ] `inputs` 是相对名（`{"0": "guide"}`），不是绝对路径
- [ ] `recipe_rebuild` 能在新位置重建出结构一致的 subnet
- [ ] `verify.ok` 为 true（参数回读一致）
- [ ] `recipe_list` 能查到捕获的配方
- [ ] HDA（不锁定）的捕获结果与 subnet 一致（如果你测了 HDA）

任何一项不过，把 recipe.json 和错误信息发我，我据此调整。
