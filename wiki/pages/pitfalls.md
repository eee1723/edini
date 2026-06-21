# ⚠️ 踩坑记录

> Edini 开发过程中的踩坑记录，避免重复犯错。支持按分类/优先级/状态筛选。

## 已记录的问题

### Houdini Python 环境隔离

- **分类**: Python/PySide6
- **优先级**: 高
- **状态**: 信息

Houdini 自带 Python 解释器，路径与系统 Python 隔离。`pip install` 对 Houdini 内运行的代码无效。
**解决**：所有依赖必须安装在 `python3.11libs/` 目录下，该目录会被加入 sys.path。

```bash
pip install mistune --target "E:/edini/python3.11libs" --no-deps
```

当前外部依赖：`mistune`（零依赖、纯 Python Markdown 渲染器）。PySide6 由 Houdini 自带，

### QThread 与 Houdini 主线程

- **分类**: Python/PySide6
- **优先级**: 高
- **状态**: 信息

Houdini 的 hou 模块只能在主线程调用。RpcClient 使用 QThread 管理 Pi 子进程的 stdin/stdout 读取，
但所有 UI 操作和 hou API 调用必须在主线程。`ToolExecutor` 的 HTTP server 使用 daemon thread，
接收到工具调用请求后，实际执行仍在主线程（通过 hou 模块自动排队）。
**注意**：`RpcClient` 的信号通过 Qt 的 queued connection 自动跨线程安全。

### npm 全局路径在 Houdini 中不可见

- **分类**: 部署/安装
- **优先级**: 中
- **状态**: 已修复

Houdini 启动时不会继承完整的用户 PATH，npm 全局安装的 `pi` 命令可能找不到。
**解决**：`config.py` 中的 `_find_pi()` 函数实现三级查找：
1. `EDINI_PI_PATH` 环境变量
2. Windows `%APPDATA%/npm/pi.cmd`
3. `shutil.which("pi")` 兜底

### 手写正则 Markdown 渲染器的不稳定性

- **分类**: Python/PySide6
- **优先级**: 高
- **状态**: 已修复 (2026-06-10)

**症状**：
- 代码块 `<>&` 被双重 HTML 转义（`html.escape` 全文转义 + 提取后再转义）
- 数学表达式 `5 * 3 * 2` 被误判为斜体
- 流式阶段 `_format_lite` 只做 `\n→<br>`，块级语法完全不解析
- 流式 vs 最终渲染布局不一致

**根因**：手写 ~250 行正则表达式实现 Markdown→HTML 转换，
代码块提取在 `html.escape` 之后导致双重转义，italic 正则不区分语义/算术 `*`。

**解决**：用 **mistune 3.2.1** 替换手写渲染器。自定义 `_DarkRenderer` 继承 `HTMLRenderer`，
注入暗色主题 inline style。`_format_lite` = `_format_full` = `mistune.html(text)`，
流式/最终渲染 pixel 级一致。新增支持：h4-h6、引用块、图片、删除线、任务列表。

```python
import mistune
from mistune import HTMLRenderer

class _DarkRenderer(HTMLRenderer):
    def paragraph(self, text):
        return f'<p style="margin:6px 0;">{text}</p>'
    # ... 覆盖所有 tag 方法注入暗色 style

_md_parser = mistune.create_markdown(
    renderer=_DarkRenderer(), escape=True, hard_wrap=True,
    plugins=['table', 'strikethrough', 'task_lists'],
)
```

### TypeBox 参数校验 vs houp API 类型

- **分类**: TypeScript
- **优先级**: 低
- **状态**: 信息

TypeBox 定义的参数类型（如 `Type.String()`）与 Python houp API 的期望类型不完全对应。
例如：整数参数在 TypeBox 是 `Type.Number()`，但需要确保不传递浮点数给需要整数的参数。
**解决**：工具设计上保持参数类型宽松（`Type.Unknown()` 用于 set_param value），
让 Python 端做最终的类型转换和校验。

### Type.Tuple 的 JSON Schema 触发智谱 400（兼容性炸弹）

- **分类**: TypeScript / 模型兼容性
- **优先级**: 高
- **状态**: 已修复 (2026-06-16)

**症状**：
- `picli`（独立 CLI）用 `zai-coding-cn/glm-5.1/5.2`（智谱 coding plan）完全正常；
- Edini（Houdini RPC，带全部 Houdini 工具）同样切换到 GLM 模型后，**每次请求都返回 `400 API 调用参数有误，请检查文档。`**。
- 与 API key、套餐订阅、并发、请求体大小、工具数量、thinking/tool_stream/stream_options 全部无关（逐一用 curl 复现验证过，智谱 API 本身全盘接受）。

**根因**：
TypeBox 的 `Type.Tuple([Type.Number(), Type.Number()])` 生成的是**旧版 JSON Schema 的 tuple 写法**：
```json
{"type":"array","items":[{"type":"number"},{"type":"number"}],"additionalItems":false}
```
注意 `items` 是一个 **schema 数组**（已废弃形式，新版规范应改用 `prefixItems`）。
智谱 coding plan API 的参数校验器对这种 `items: 数组` 形式直接判错返回 400。OpenAI、DeepSeek 等接受这个写法，所以平时测不出问题。

Edini 当时有两个工具用了 `Type.Tuple`（`houdini_capture_review` 和 `houdini_capture_component_detail` 的 `resolution` 参数）。picli 没有这类 schema 所以一直正常——这解释了为什么「同一套 Pi 后端、同一个 key，picli 行而 Edini 不行」。

**验证方法**（已证）：用 TypeBox 真实输出 + curl 直发智谱 →
- `Type.Tuple`（items 数组形式）→ **400**
- `Type.Record`（patternProperties）、`Type.Union`+`const`（anyOf）→ 200
- 改 `Type.Array(Type.Number())` / `prefixItems` / object → 全部 200

**解决**：把两处 `Type.Tuple([Type.Number(), Type.Number()])` 改成 `Type.Array(Type.Number())`，对应 TS 类型 `[number, number]` → `number[]`。语义不变（仍是 `[width, height]`）。

**⚠️ 开发准则（适用所有要接智谱 / 严格 OpenAI 兼容 API 的工具）**：
1. **禁用 `Type.Tuple`**——它生成废弃的 `items: 数组` 写法。固定长度数组用 `Type.Array(Type.X())`，必要时在 description 里说明顺序。
2. 定义新工具后，**务必用目标 provider（尤其智谱 coding plan）实测一次**，不要只靠 OpenAI/DeepSeek 验证。校验严格度：智谱 > DeepSeek > OpenAI。
3. 排查 provider 报 400 时，先隔离测试「是否带了某个特定工具的 schema」——用二分法逐步移除工具，定位到具体的 schema。
4. 复现脚本模板见 `wiki/raw` 或本节验证方法：构造 payload → curl 直发 `https://open.bigmodel.cn/api/coding/paas/v4/chat/completions`。

### subprocess stdout 阻塞风险

- **分类**: JSON-RPC
- **优先级**: 高
- **状态**: 已修复

子进程 stdout 读取使用同步迭代 `for line in self._process.stdout`，
如果 Pi 进程异常退出但 stdout 未关闭，QThread 可能永远阻塞。
**解决**：添加 `_should_stop` 标志 + 循环内检查，`stop()` 时先 terminate 再 kill 兜底。

### 工具执行器的线程安全

- **分类**: 部署/安装
- **优先级**: 中
- **状态**: 信息

`ToolExecutor` 使用 Python `HTTPServer` + daemon thread。`HTTPServer` 本身是单线程的，
每个请求在同一个线程顺序处理。Houdini 的 hou API 可以从任何线程调用（内部有 GIL 保护，
hou 模块会调度到主线程）。但要注意长时间运行的 Python 脚本可能阻塞工具执行器响应。

### settings.json 的位置和权限

- **分类**: 部署/安装
- **优先级**: 低
- **状态**: 信息

API key 存储在 `edini/settings.json` 中（与代码同目录），通过 `.gitignore` 防止提交。
Windows 下通常无障碍，但 macOS/Linux 如果 Houdini 包安装在系统目录可能有写权限问题。
**改进方向**：考虑使用 Houdini 用户 prefs 目录或系统 keyring。

### Houdini 版本兼容性

- **分类**: 部署/安装
- **优先级**: 中
- **状态**: 信息

`install.py` 硬编码查找 `Documents/houdini21.0` 或 `houdini21.5`。
未来 Houdini 版本更新需要更新路径。
**建议**：扫描 `Documents/` 下所有 `houdini*` 目录，选择最新版本。

### 知识提取 JSON 解析

- **分类**: 知识沉淀
- **优先级**: 中
- **状态**: 已修复

AI 反思返回的 JSON 格式不稳定：可能包裹在 ```json 代码块中、使用单引号、带尾逗号。
旧解析器只用 bracket balancing + json.loads，解析失败率高。
**解决**：多级修复 — 代码块提取 → 单引号转换 → 尾逗号移除 → 双重修复组合。
提取响应不再渲染进时间线（get_raw_stream_text + cancel_current_stream），
避免 HTML 解析脆弱导致时间线消失。

### 3 位 hex 颜色导致 UI 崩溃

- **分类**: Python/PySide6
- **优先级**: 中
- **状态**: 已修复

`_lighter("#555", 0.15)` 中 `int(h[5:7], 16)` 对 3 位 hex 缩写解析失败。
**解决**：添加 `_expand_hex()` 函数，自动将 `#RGB` 展开为 `#RRGGBB`。

### 图片缓存写入竞态：agent_done 先于 session_switched

- **分类**: 图片/缓存
- **优先级**: 高
- **状态**: 已修复 (2026-06-10)

**症状**：发送图片后，当前对话能看到缩略图和识别描述，但切换到历史记录后图片完全消失。检查磁盘发现 `edini_images/<session_id>/manifest.json` 不存在。

**根因**：Pi 的 `agent_end` 事件和 `session_switched` 响应的到达顺序不保证。在新会话中，`agent_end` 经常先于 `session_switched` 到达 Edini。旧代码在 `_on_agent_done` 中无条件清零 `_pending_images` 和 `_pending_cache_meta`。当 `_on_pi_session_switched` 后到达时，pending 数据已被清空，`_flush_pending_image_cache()` 跳过写入。

**解决**：
1. `_on_agent_done` / `_on_abort_request` / `_on_error` 中，只在 `session_path` 已确认时才清零 pending 数据
2. 如果 `session_path` 仍为空，保留 pending 数据等待 `_on_pi_session_switched` 处理
3. `_on_pi_session_switched` 写入缓存后显式清零 pending
4. 新增 `_flush_pending_image_cache()` 统一方法，避免内联代码重复

关键时序：
```
_on_agent_done   → flush(空路径跳过) → session_path为空? → 保留pending
_on_pi_session_switched → 设置session_path → flush(写入!) → 清零pending
```

### setSpareParmGroup 在 H21 非 HDA 节点静默失败

- **分类**: Houdini API / Procedural Harness
- **优先级**: 高
- **状态**: 已修复 (2026-06-16，第三十阶段)

**症状**：声明式 builder build 的资产，`params_summary` 里所有参数 `installed=false`，最终交付文案被迫写"参数暂时固化在代码里"。component 代码用 `hou.ch("../wheelbase")` 读不到值。
**根因**：`_install_spare_params` 用全新空 `ParmTemplateGroup` 调 `root.setSpareParmGroup(group)`。该 API 在 H21 的非 HDA 节点（如 geo 容器）上受限会抛异常，但被 `except Exception: pass` 吞掉，`installed` 恒为 `False`，参数永不落地。
**解决**：改用 Houdini 官方 read-merge 文件夹参数模式（H21 兼容、merge-safe）：`ptg = root.parmTemplateGroup()` 读现有（保留 Transform 等默认文件夹）→ `FolderParmTemplate("edini_params")` 装参数 → `setParmTemplateGroup(ptg)` 写回。主路径 `setParmTemplateGroup` → 失败回退 `setSpareParmGroup` → 仍失败才降级 `installed=False`+warning。真实 Houdini 21.0.440 验证 5/5 参数 `installed=true`。
**教训**：泛化的 `except Exception: pass` 会吞掉真正失败，让"参数没挂上"变成静默降级。关键路径应把异常转成可观测信号（warning + installed 标志），而非静默吞。

### 几何健康检查 degenerate 误报（0.5·|cross|² 单位错误）

- **分类**: Houdini API / Procedural Harness
- **优先级**: 高
- **状态**: 已修复 (2026-06-16，第三十阶段)

**症状**：`inspect_geometry_health` 报 `degenerate_prims: 1228`，但 agent 手算发现这些 fan-cap 三角形面积 2e-4（远超退化阈值），是误报。把 n-gon cap 改成 fan-cap 后误报数反而从 238 涨到 1228，逼 agent 花 3 轮思考自证清白、触发无谓 rebuild。
**根因**：退化检测把 `0.5·|cross|²`（cross 是两边向量的叉积，`|cross|` = 2·面积，所以 `0.5·|cross|²` = `2·area²`，**不是**面积）与 `1e-7` 比，等效面积阈值 ~7e-5；且只取前 3 个顶点。合法 fan-cap 三角（面积 2e-4 → `2·area²`=8e-8 < 1e-7）被误报。fan-cap 把 1 个 n-gon 拆成 N 个小三角，每个 `2·area²` 更小，误报数暴涨。
**解决**：改用 `prim.intrinsicValue("measuredarea")`（Houdini 原生真实多边形面积，含 n-gon），异常时回退修正后的 shoelace（遍历全部顶点对中心做扇形面积求和）。阈值 `1e-7` 现在真的是面积阈值。真实 Houdini 实测合法三角 measuredarea=2e-4 不再误报。
**教训**：手写几何数学（叉积/面积）极易单位搞错（`|cross|` vs `|cross|²` vs `0.5·|cross|²`）；优先用 Houdini 内禀值（`intrinsicValue`）这类原生 API，它已封装好正确语义。注释里写"对于 >3 顶点仍可靠"的断言要有测试覆盖，否则像这个 bug 一样潜伏。

- **分类**: Python/PySide6
- **优先级**: 高
- **状态**: 已修复

时间线使用 QTextBrowser + setHtml 流式更新（每 80 字符一次）：① setHtml 重建整个 HTML 文档 DOM，性能差 ② actionTriggered 信号在部分 Qt 版本不可靠 ③ blockSignals + setValue + 比例计算存在异步布局竞态 ④ _flush_thinking_buf 清空 _current_text 导致气泡只显示新 chunk。
**解决**：重构为 QScrollArea + 独立 Widget 架构：_UserBubble / _AiBubble (QLabel RichText) / _Separator / _ErrorBanner。滚动改用 rangeChanged + valueChanged + _pinned_to_bottom 标志位。流式文本用 _streaming_full_text 永不清空的累加器。气泡用 Expanding sizePolicy + layout margin 填满窗口。

## 参考

- [架构地图](architecture.html) — 了解系统边界避免踩坑
- [工具清单](tools.html) — 30+ 个工具的正确使用方式

### H21 parm 参数名变更（2026-06-21 验证）

- **分类**: Houdini 操作 / H21 兼容
- **优先级**: 高
- **状态**: 已修复

H21 多个 SOP 节点的参数命名与旧版不同：
- `box` 用 `sizex/sizey/sizez`（独立 Float）而非单 `size` 向量；parmTemplate 层面有 `size`(Float,3-comp) 但 `node.parm("size")` 返回 None，必须用 `parmTuple("size")` 或单独设 `sizex/sizey/sizez`
- `xform` 用 `t`（3-float translate）而非 `tx/ty/tz`
- `attribwrangle.class` menu 排序变化：H21 = detail(0)/primitive(1)/point(2)/vertex(3)/number(4)。旧硬编码 `class=2` 误选中 point 模式而非 detail
- `sweep::2.0` 默认 `surfaceshape=input` 需要 input-1 横截面几何体；设为 `tube` 才自动生成管状横截面
- `circle` 用 `radx/rady` 而非 `rad`
**解决**：`_set_parm_safe` 自动检测多分量值走 `parmTuple`；VEX wrangle 改用字符串 token `"detail"`；sweep recipe 加 `surfaceshape: "tube"`。Phase A 参数目录校验在 cook 前拦截不存在的参数名。

### menuItems() 返回字符串列表而非对象（H21）

- **分类**: Houdini API
- **优先级**: 中
- **状态**: 已修复

`pt.menuItems()` 在 H21 返回 `tuple[str]`，不是对象列表。旧代码调 `mi.label()` 出错被静默吞掉，导致菜单项列表为空。
**解决**：直接用 `list(pt.menuItems() or [])`。

### parmTemplateType.name 不含括号

- **分类**: Houdini API
- **优先级**: 高
- **状态**: 已修复

`pt.type().name` 返回 bound method 对象而非类型名字符串。正确调用是 `pt.type().name()`。
此 bug 导致参数目录中所有 type 字段存储为 `<bound method EnumValue.name of parmTemplateType.Float>` 而非 `"Float"`，Menu 验证完全失效。

### Python createNode 不会应用 Tab 菜单预设

- **分类**: Houdini 操作
- **优先级**: 高
- **状态**: 已修复

Tab 菜单创建节点时（如 copytopoints::2.0）会执行 shelf tool 脚本中的后处理操作（如 `pressButton('resettargetattribs')`），但 Python `createNode()` 只创建裸节点，不执行这些脚本。导致节点参数与 Tab 菜单创建的不一致。
**解决**：`create_node()` 现在会 ① 用 `namespaceOrder()` 自动解析全限定名（如 copytopoints → copytopoints::2.0），② 创建后查找匹配的 shelf tool 脚本，提取并执行其中的 `pressButton()` / `parm().set()` 调用。



### Ramp 参数导致 JSON 序列化崩溃

- **分类**: Houdini 操作
- **优先级**: 高
- **状态**: 已修复

 遍历  时对所有参数调用 。Ramp 类型参数 (hou.Ramp) 不可 JSON 序列化，导致整个工具调用失败。
**解决**：新增  函数，先用  检查类型。检测到 hou.Ramp 时返回结构化描述 (keys/positions/basis)，而非尝试序列化原始对象。同样的保护覆盖 hou.Data 和其他不可序列化类型。

### Pi 工具注册与 Python Handler 不同步

- **分类**: 架构
- **优先级**: 高
- **状态**: 已修复

、、 在 TypeScript (scene.ts) 中定义并注册，但 Python 后端 (tool_executor.py) 缺少对应 handler。Agent 调用时返回 "Unknown tool" 错误。
**解决**：在 node_utils.py 中添加完整实现，在 tool_executor.py 的 TOOL_HANDLERS 中注册 lambda handler。两端的工具注册必须同步。

### QMetaObject.invokeMethod 不支持 lambda (PySide6)

- **分类**: Python/PySide6
- **优先级**: 中
- **状态**: 已修复

PySide6 的  第二个参数必须是方法名字符串，不支持 lambda 函数。从后台线程跨线调用 UI 更新时，PySide6 报 Type error。
**解决**：全部改用 ，这是 PySide6 中跨线程回调的标准做法。

### API Key 环境变量始终映射为 DEEPSEEK_API_KEY

- **分类**: 配置
- **优先级**: 高
- **状态**: 已修复

 中无论用户选择哪个 provider，API Key 都设为 。当用户选择智谱 (zhipu) 时，扩展查找  为空，Pi 无法认证，实际仍用 DeepSeek。
**解决**：新增  函数，映射 provider → 环境变量名 (zhipu→ZHIPU_API_KEY, google→GEMINI_API_KEY 等)。同时保留 DEEPSEEK_API_KEY 作为兜底。

### 快照 diff 包含 Houdini 内部自动子节点

- **分类**: 变更树
- **优先级**: 中
- **状态**: 已修复

创建节点时 Houdini 会自动生成内部子节点（如 geo 容器内的 file1），变更树不应列出这些。
**解决**：`_filter_descendants()` 在 diff 结果中过滤掉具有祖先在同类别中的子节点路径。
