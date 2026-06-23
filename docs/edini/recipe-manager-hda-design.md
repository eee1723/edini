# Edini Recipe Manager — 设计方案 v2（定稿）

> 状态：定稿 · 日期：2026-06-23
> v1 用 HDA 原生参数面板（multiparm 模拟树）→ v2 改为**自写 Qt 树控件**，
> 配合 HDA 内部的**递归 subnet 树**，结构即分类，可无限扩展方向。

## 0. 一句话定位

**`edini_recipe_manager`** 是 `/obj` 里一个不锁定内容的主 HDA。
- **内部**：递归 subnet 树（容器 subnet 套叶子 subnet）——结构本身就是分类树
- **外部**：自写 Qt 树控件面板（QTreeView）——真正的可视化树，可展开/拖拽/右键
- **驱动**：PythonModule + recipe_library，按钮和 LLM 共享同一套逻辑

## 1. 三层架构

```
┌──────────────────────────────────────────────────────────────┐
│  Qt 树面板（edini.ui.recipe_tree_window）                      │
│  ┌────────────────────────────────────────┐                   │
│  │ 📊 统计: 12 配方 / 10 已验证           │                   │
│  │ 🔍 [搜索框]                            │                   │
│  │ ─────────────────────────────────────  │                   │
│  │ ▼ 📁 procedural_modeling       [➕][⚙] │                   │
│  │   ▼ 📁 wheels                 [➕][⚙] │  ← 容器 subnet   │
│  │     • tube_along_curve    ok   [✓][⟳][✎] ← 叶子 subnet   │
│  │     • wheel_spoked        ok   [✓][⟳][✎]                  │
│  │   • copy_to_points        ok   [✓][⟳][✎]                  │
│  │ ▶ 📁 fx                                │  ← 将来的方向     │
│  │ ▶ 📁 materials                          │                  │
│  └────────────────────────────────────────┘                   │
│                  │ 按钮/双击                                   │
└──────────────────┼───────────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  HDA: /obj/edini_recipe_manager（不锁定内容）                  │
│  │                                                            │
│  ├─ procedural_modeling/  (subnet 容器)                       │
│  │   ├─ wheels/           (subnet 容器)                       │
│  │   │   ├─ wheel_spoked  (subnet 叶子 = 一个 recipe)          │
│  │   │   └─ wheel_basic   (subnet 叶子)                        │
│  │   ├─ tube_along_curve  (subnet 叶子)                        │
│  │   └─ copy_to_points    (subnet 叶子)                        │
│  ├─ fx/                  (subnet 容器，将扩展)                 │
│  └─ materials/           (subnet 容器，将扩展)                 │
│                                                              │
│  规则：容器 subnet 不含几何，只组织结构；                       │
│        叶子 subnet 内部是真正的节点配方。                       │
└──────────────────────────────────────────────────────────────┘
                   │
                   ▼  PythonModule 调用
┌──────────────────────────────────────────────────────────────┐
│  recipe_library.py（现有，不改核心）                           │
│  recipe_capture / recipe_rebuild / recipe_list(递归)          │
└──────────────────────────────────────────────────────────────┘
```

## 2. 已确认决策（v2 关键变化）

| 决策 | v1 | v2（定稿） |
|---|---|---|
| **内部结构** | 平铺 subnet | **递归 subnet 树**（容器套叶子） |
| **分类机制** | Tab 文件夹（固定） | **结构即分类**（subnet 嵌套 = 分类树，用户/LLM 共建） |
| **仪表盘** | HDA multiparm 模拟 | **自写 Qt QTreeView**（真树，拖拽/折叠/右键） |
| **扩展性** | 固定方向 | **无限**（加新方向 = 加个容器 subnet） |
| **subnet 载体** | HDA 内部 | 不变 |
| **按钮驱动** | PythonModule 调 recipe_library | 不变 |

## 3. 容器 vs 叶子的判定

HDA 内部每个节点都是 subnet，但要区分两类：

| 类型 | 判定 | 作用 | Notes 写法 |
|---|---|---|---|
| **容器** | `children()` 全是 subnet（无叶子/SOP） | 组织分类树 | `功能：分类容器` |
| **叶子** | `children()` 含非 subnet 节点（SOP 等） | 一个 recipe 配方 | `功能：<具体功能>` |

`scan_tree()` 递归遍历时按这个规则判型，Qt 树据此渲染（容器是文件夹图标，叶子是配方图标）。

> 边界：一个 subnet 如果既有子 subnet 又有 SOP 节点 → 当叶子处理（它是个自包含配方）。

## 4. 数据流（v2）

```
真相源 = HDA 内部的递归 subnet 树
                 │
        scan_tree() 递归读取
                 │
        ┌────────┴────────┐
        ▼                 ▼
   Qt 树面板显示      recipe_list(递归) 供 LLM
   (用户操作)         (LLM 逐层 dive 查找)
        │
        │ 捕获/重建
        ▼
   recipe.json 派生缓存（recipes/ 目录）
   ← 仅用于 LLM 跨场景检索 + 重建历史快照
```

**关键**：subnet 树是 source of truth。recipe.json 是缓存，丢了能从 subnet 重建。
LLM 的 `recipe_list` 改为**直接读 HDA 内部 subnet 树**（递归），不再只读 index.json。

## 5. Qt 树控件规格（edini.ui.recipe_tree_window）

照 `windows.py` 的浮动面板模式（`hou.qt.mainWindow()` 父窗口，PySide6）。

```
RecipeTreeWindow(QtWidgets.QWidget)
├─ 顶栏
│   ├─ QLabel 统计（总配方数 / 已验证 / 错误数）
│   ├─ QLineEdit 搜索框（实时过滤树）
│   └─ QPushButton「扫描刷新」
│
├─ QTreeView（核心）
│   ├─ 数据模型：QStandardItemModel
│   │   列：[图标+名称] [路径] [节点数] [状态] [操作]
│   ├─ 容器行：文件夹图标，双击 dive 进 Houdini 该 subnet
│   ├─ 叶子行：配方图标，右侧按钮组
│   │   [✓ 检查] 重建测试 + diff，更新状态列
│   │   [⟳ 重建] 重建到 /obj（target_parent 可配）
│   │   [✎ 编辑] dive 进该 subnet
│   ├─ 右键菜单
│   │   容器：新建子分类 / 新建配方 / 重命名 / 删除
│   │   叶子：检查 / 重建 / 编辑 / 捕获到库 / 删除
│   └─ 拖拽：移动 subnet 改分类（改 parent）
│
└─ 底栏
    └─ QPlainTextEdit 选中配方的 Notes 预览（只读）
```

**树数据来源**：`recipe_library.scan_tree(hda_path)` 递归读 HDA 内部 subnet，
返回嵌套结构：

```python
{
    "name": "edini_recipe_manager",
    "type": "container",
    "children": [
        {"name": "procedural_modeling", "type": "container",
         "children": [
             {"name": "wheels", "type": "container",
              "children": [
                  {"name": "wheel_spoked", "type": "leaf",
                   "path": "/obj/.../procedural_modeling/wheels/wheel_spoked",
                   "node_count": 5, "status": "ok", "notes": "..."},
              ]},
             {"name": "tube_along_curve", "type": "leaf", ...},
         ]},
    ]
}
```

## 6. 新增/改动清单

### 新增（Python）
| 文件 | 作用 |
|---|---|
| `recipe_library.py` 加 `scan_tree(hda_path)` | 递归读 HDA 内部 subnet 树（区分容器/叶子） |
| `recipe_library.py` 加 `create_recipe_manager(parent, name)` | 一键创建主 HDA（不锁定，含初始结构） |
| `recipe_library.py` 改 `recipe_list` | 支持 `hda_path` 参数，从 subnet 树递归查（不只读 index.json） |
| `edini/ui/recipe_tree_window.py` | Qt 树控件面板 |
| `edini/ui/windows.py` 加 `open_recipe_tree()` | 树面板入口（仿 open_chat_window） |

### 新增（Houdini 集成）
| 项 | 作用 |
|---|---|
| `MainMenuCommon.xml` 加菜单项 | Edini → Open Recipe Tree（Alt+Shift+R） |

### 新增（工具）
| 工具 | 作用 |
|---|---|
| `recipe_manager_create` | 一键建主 HDA |
| `recipe_tree_scan` | 手动触发扫描（也可按钮调） |
| `recipe_tree_open` | 打开 Qt 树面板 |

### 复用（不改）
`recipe_capture` / `recipe_read` / `recipe_rebuild` 核心逻辑不变，Qt 按钮调它们。

## 7. scan_tree 算法（核心）

```python
def scan_tree(root_path):
    """递归读 subnet 树。返回嵌套 dict。"""
    node = hou.node(root_path)
    if node is None:
        return None
    children = node.children()
    has_leaf = any(_is_leaf(c) for c in children)
    is_leaf = _is_leaf(node) and not (children and all(_is_container(c) for c in children))

    entry = {
        "name": node.name(),
        "path": node.path(),
        "type": "leaf" if is_leaf else "container",
        "notes": node.comment() or "",
        "children": [],
    }
    if is_leaf:
        entry["node_count"] = len(children)
        entry["status"] = "unverified"  # 由 check 更新
    for c in children:
        entry["children"].append(scan_tree(c.path()))
    return entry

def _is_leaf(subnet):
    """叶子 = 含非 subnet 节点（SOP 等）。容器 = 全是 subnet。"""
    kids = subnet.children()
    return any(c.type().category().name() != "Object" or
               c.type().name() not in ("subnet", "geo") for c in kids) if kids else True
```

> `_is_leaf` 的精确判定需要在真实 Houdini 验证（subnet 内 SOP 的 category）。

## 8. create_recipe_manager 流程

```python
def create_recipe_manager(parent_path="/obj", name="edini_recipe_manager"):
    """一键创建主 HDA + 初始结构。"""
    parent = hou.node(parent_path)
    subnet = parent.createNode("subnet", name)
    subnet.setComment("Edini Recipe Manager — 配方仓库与仪表盘")
    # 创建初始分类容器
    for cat in ("procedural_modeling",):
        cat_subnet = subnet.createNode("subnet", cat)
        cat_subnet.setComment("分类容器：程序化建模配方")
    # 打包成 HDA（不锁定！）
    hip_dir = hou.hipFile.dirName() or hou.homeHoudiniDirectory()
    hda_path = f"{hip_dir}/{name}.hda"
    subnet.createDigitalAsset(
        name=name, hda_file_name=hda_path,
        description="Edini Recipe Manager",
        save_as_locked=False,   # ← 关键：不锁定，内部可读可改
    )
    return {"success": True, "hda_path": subnet.path(), "hda_file": hda_path}
```

## 9. 实现顺序（小步验证）

| 阶段 | 产出 | 验收（需真实 Houdini） |
|---|---|---|
| **1. scan_tree + create_recipe_manager** | 能建 HDA + 递归读树 | HDA 创建，scan 返回正确结构 |
| **2. recipe_list 递归支持** | LLM 能查树 | recipe_list(hda_path=...) 返回嵌套结果 |
| **3. Qt 树面板骨架** | 树能显示 HDA 内部结构 | 打开面板见树，容器/叶子区分 |
| **4. 按钮接线** | 检查/重建/编辑可用 | 点按钮调 recipe_library |
| **5. 右键菜单 + 拖拽** | 新建/移动 subnet | 能加分类、移动配方 |
| **6. LLM 工具接线** | recipe_manager_create/tree_scan/tree_open | LLM 能建 HDA、打开面板 |

每阶段独立可验证。阶段 1 是地基，必须先在真实 Houdini 跑通。

## 10. 与 LLM 的关系

LLM 有两条路用这套系统：

**A. 直接调工具**（无 GUI）：
```
recipe_list(hda_path="/obj/edini_recipe_manager", query="tube")
  → 递归搜树，返回匹配的叶子配方
recipe_rebuild("tube_along_curve", "/obj", overrides={...})
  → 重建到场景
```

**B. 引导用户用 GUI**：
LLM 在聊天里说「请在 Recipe Manager 面板里检查 tube_along_curve」，
用户点按钮。LLM 读 recipe_library 状态判断结果。

两条路共享同一套 recipe_library 核心。

## 11. 待真实 Houdini 验证的风险点

| 风险 | 验证方式 |
|---|---|
| `createDigitalAsset(save_as_locked=False)` 的确切行为 | 建后检查 children() 可读 |
| 容器/叶子判定（subnet 内 SOP 的 category） | dive 进 subnet 查 node.type().category() |
| Qt 树面板在 Houdini 里的浮动行为 | 仿 open_chat_window 测 |
| 递归 subnet 的 dive 路径 | 确认 hou.node 深层路径可访问 |
