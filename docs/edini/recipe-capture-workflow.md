# Recipe 捕获工作流 — 从手工子网到 edini 可读的参考样本

> **核心定位**：recipe 是给 edini 的**参考样本**，不是死模板。捕获把
> 你搭好的子网序列化成 `recipe.json`，其中 `python_script` 字段是一段
> 可读的 Python 还原代码。edini 读这段代码学习节点语法和你的约定，
> 然后用自己的判断重建——它的能力不被 recipe 限死。

---

## 一、一次性安装：给 HDA 加「捕获」按钮

只需做一次。在 Houdini Python Shell（Windows > Python Shell）里运行：

```python
import sys
sys.path.insert(0, r"E:\edini\python3.11libs")
import importlib
import scripts.rebuild_hda_with_button as b
importlib.reload(b)
print(b.main())
```

成功输出：
```
OK: 'Capture All Recipes' button added to edini_recipe_manager and saved to
.../otls/edini_recipe_manager.hda.
```

之后 `edini_recipe_manager` HDA 的参数面板上会出现 **Capture All Recipes** 按钮。
该按钮已随 `.hda` 持久化，换场景/重启 Houdini 都在。

> 如果还没创建 recipe manager HDA，先在 edini 里让 LLM 建：
> 「创建 recipe manager HDA」（调 `create_recipe_manager`），或参考
> `recipe-library-getting-started.md`。

---

## 二、加新 recipe 的标准流程

每个 recipe 都是一个叶子 subnet（内部是真实 SOP 节点网络）。

1. **dive 进 HDA**：双击 `/obj/edini_recipe_manager1`，进入内部。
2. **建/选分类容器**：在对应的分类 subnet（如 `procedural_modeling`）下，
   新建一个 subnet 作为叶子，命名清晰（如 `tube_along_curve`）。
3. **双击进叶子，搭内部网络**：用真实的 SOP 节点搭出效果。
   （可参考 `scripts/build_recipes_standalone.py` 的 build_* 函数。）
4. **写 Notes**（选中叶子 subnet，按 C）—— **强制契约**，格式：
   ```
   功能：<这个 recipe 做什么>
   用途：<适用场景>
   输入：<第N输入是什么>
   重要参数：<逗号分隔的内部参数名>  ← 这些会被标记为 author-marked
   不要用于：<什么情况该用别的 recipe>
   ```
   `重要参数` 里列出的参数名，在生成的 python_script 里会带
   `# author-marked` 注释，是给 edini 的核心信号。
5. **改你要的参数**：调整你真正在意的那些（如 `endcaptype=1` 封端、
   `rad` 管径）。**不需要 promote 参数**——捕获会自动用 manifest 对比
   默认值，记录所有 current != default 的参数。
6. **回到 HDA 顶层，点 Capture All Recipes 按钮**。
   弹窗显示捕获数量 + 跳过项（Notes 为空会跳过）。

完成后，新 recipe 立即可被 edini 检索：`recipe_list(query="...")`。

---

## 三、edini 怎么用 recipe

edini（LLM）的工作流，由 `recipe-library` skill 驱动：

1. **搜** `recipe_list(query="tube")` → 得到匹配 recipe 的摘要。
2. **读** `recipe_read(recipe_id)` → 重点看 `python_script` 字段：
   ```python
   def build_tube_along_curve(parent):
       path_line = parent.createNode('line', 'path_line')
       section = parent.createNode('circle', 'section')
       sweep1 = parent.createNode('sweep::2.0', 'sweep1')
       sweep1.parm('endcaptype').set(1)  # author-marked
       sweep1.parm('surfacetype').set(2)  # author-marked
       ...
   ```
   - `# author-marked` = 你在 Notes 里标注的关键参数
   - 节点类型用的是正确版本名（`sweep::2.0` 不是 `sweep`）
   - 连接关系一目了然
3. **学，然后自己重建**：edini 可以原样用这段脚本、修改它、或只借鉴
   节点搭配方式，用 `houdini_run_python_sandbox` 搭出用户真正要的东西。
   **recipe 是参考，不是枷锁。**

---

## 四、为什么不需要「暴露参数 / Promote Parameter」

旧设计要求把参数 promote 到 subnet 顶层才能被 override。新设计里：

- **edini 自己重建**，不依赖机械 override，所以不需要 promote。
- **modified 参数自动捕获**：捕获时用 manifest 对比默认值，
  `current != default` 的参数全部记录（这就是"用户修改过的参数"）。
- **`重要参数` 标注是核心信号**：在 Notes 里列出的参数名，
  在 python_script 里被 `# author-marked` 高亮，edini 一眼看出你的意图。

> `exposed_parms` 字段仍保留（兼容 `recipe_rebuild` 的快速还原路径），
> 但不再是 edini 的主路径。如果你 promote 了参数，它照样会被捕获。

---

## 五、验证捕获质量

捕获后，在 edini 里检查：

```
recipe_read("sopnet.Procedural_Modeling.tube_along_curve")
```

看 `nodes[].changed_params`——应该只有**真正改过的**参数（manifest 对比
修复后，噪音从 100+ 降到个位数）。如果某个节点 changed_params 还是一大堆，
通常是 manifest 里缺该节点类型的默认值（少见，可跑
`scripts/generate_node_parms_manifest.py` 重新生成）。

`python_script` 应该干净可读：marked 参数突出，噪音参数（tx=0、空字符串、
folder 折叠状态）被过滤。

---

## 六、维护：manifest 更新

manifest（`python3.11libs/edini/data/node_parms_manifest.json`）是节点参数
默认值的快照，捕获靠它判断"哪些参数被改过"。Houdini 大版本升级后，
新节点的默认值可能变化。重新生成（在 Houdini 里）：

```python
# 见 scripts/generate_node_parms_manifest.py 顶部注释
hython scripts/generate_node_parms_manifest.py
```

提交更新后的 manifest，然后重新捕获现有 recipe 即可。

---

## 附：数据结构（recipe.json）

| 字段 | 给谁用 | 说明 |
|---|---|---|
| `python_script` | **edini（主路径）** | 可读还原代码，参考素材 |
| `notes` / `function` / `avoid` | edini | 意图元数据，决定何时用 |
| `nodes[]` / `changed_params` | recipe_rebuild / verify | 机械还原路径（可选） |
| `marked_params` | edini | Notes 里"重要参数"标注的，python_script 里 `# author-marked` |
| `vex_snippets` | edini | wrangle 节点的 VEX 代码（python_script 里内联） |
| `exposed_parms` | recipe_rebuild overrides | promote 的参数（兼容旧路径） |
