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
- **状态**: 已修复（2026-07-03 彻底修复）

`get_node_info` 遍历 `node.parms()` 时对所有参数调用 `p.eval()`。Ramp 类型参数（如 polybevel::3.0 的 `profileramp`）的 `eval()` 返回 `hou.Ramp`，不可 JSON 序列化，导致**整个节点信息响应**（不仅 ramp 参数）在 `tool_executor._send_json` 的 `json.dumps` 处崩溃，agent 连节点结构都看不到，被迫绕道 sandbox 探查。
**解决（2026-07-03）**：新增 `_serialize_parm_value(parm, value)`，检测 `parm.parmTemplate().type().name() == "Ramp"` 时返回结构化描述 `{"__type__":"ramp","keys":[...],"values":[...]}`（用 `ramp.keys()`/`ramp.values()`），其余类型走 `_json_safe`（处理 vector/enum，兜底 str）。此前虽有一个 `_json_safe` 兜底函数，但 `get_node_info` 路径**从未调用它**——本次才接上。测试：mock ramp parm 断言可 JSON 序列化。

### query_parms 与 create_node 版本不一致（参数名错配）

- **分类**: 架构
- **优先级**: 高
- **状态**: 已修复（2026-07-03）

`query_parms("polybevel")`（读 manifest）和 `create_node("polybevel")`（调 Houdini）对同一个裸名解析到**不同版本**：create_node 建 `polybevel::3.0`（Houdini 最新默认），query_parms 却返回 manifest 里独立的裸名旧条目（beveltype/relinset，~1.0 时代）。agent 拿到的参数名配不上它创建的节点 → 全部 not found → 反复试错（polybevel 这一项就浪费 30+ 次调用）。
**根因**：`_resolve_node_type_in_manifest` 先用裸名 `node_types.get("polybevel")` 命中旧条目直接返回，永远走不到后面的「最高版本」逻辑（对 polybevel 是死代码）。manifest 里三个条目（bare / ::2.0 / ::3.0）是**三套完全不同的参数**。
**解决**：① `node_parms` 命中后若存在真实 hou 且解析为裸名，用 `hou.nodeType(...).namespaceOrder()[0]`（= create_node 内部同一套解析）校正到 Houdini 实际默认版本；② 离线兜底：裸名有版本化兄弟时优先返回最高版本；③ `_node_parms_live` 返回 `nt.name()`（解析后版本名）。原则：**以 create_node 为准**，query 主动询问 Houdini 它会建哪个版本。

### design_params 只存 JSON 不落 spare parm（ch() 链断裂）

- **分类**: Project HDA
- **优先级**: 高
- **状态**: 已修复（2026-07-03）

`project_build_scaffold` 把 `design_params` 写进 `__edini_state` JSON 后就**完全忽略**它们——只循环 components，从不创建真实 spare parm。但 `add_design_param` 的 docstring 和 state.py 注释都**声称**「parm 在 build_scaffold 期间创建在 core 上」。文档承诺、代码未兑现。后果：agent 用 `ch('../../width')` 引用 → width 不存在 → 几何静默归零（bounds=0）→ 反复试错手动补建（又踩 sandbox）。
**解决**：`build_project_scaffold` 新增第四遍 `_ensure_design_params(core_node, design_params)`：把每个 `{name,label,default,min,max}` 实例化为 core 的真实 Float spare parm（`hou.FloatParmTemplate` + `addSpareParmTuple`，幂等——已存在则跳过）。真机 hython 验证：`ch('../../width')` = 1.2（非 0），幂等不重复。

### 视觉验证噪声（capture_review + describe_image 误判）

- **分类**: 多模态
- **优先级**: 中
- **状态**: 已修复（2026-07-03，默认关闭）

视觉验证循环（capture_review 截图 + describe_image 用 3D prompt 判断）在建模任务中制造**误判噪声**：视觉模型报告「少一条腿」（实为俯视图遮挡）、「腿不一样高」（投影错觉），agent 花轮次去怀疑几何、改节点类型，最终判断是误判。对「4 个点/几何库存已确认存在」的情况，像素证据劣于数值/拓扑证据。
**解决**：新增 `settings.json` 的 `visual_verification_enabled`（默认 `false`）。Python `config.py` 经 `EDINI_VISUAL_VERIFICATION` env 传给 TS 扩展，四处门控：edini-context（系统提示的 Visual Verification Rules / 工作流第 4-5 步 / 参考图指令 / PROCEDURAL_VERIFY_PROMPT）、edini-tools（注册时过滤 capture_review）、pi-visionizer（整块 describe_image 注册）、tool_executor（防御纵深）。每处标 `[VISUAL-VERIFY-GATE]`。**可逆**：设 true 重启即恢复。视觉验证的重新设计留待后续。

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

### 安全闸过度矫正：堵洞时封死了正门（LLM agent 契约设计）

- **分类**: 平台契约 / agent 行为
- **优先级**: 高
- **状态**: 已修复（三轮迭代）

为防止 agent 覆盖 `tag_component` snippet 静默删 `edini_world_axis`，把整个节点锁死成 `__edini_axis_bake`（默认硬编码 `{0,1,0}`）。但 backrest 是 Z 朝向，baked 成 Y → `verify_orientation` 90° 失败，agent 尝试编辑节点（被 guard 拒）、传 `construction_axis`（被后端忽略）、最终放弃。**模型无法通过 commit gate**。
**根因**：安全闸设计只做了"拒绝错误行为"，没做"开放正确通道"——把唯一能设轴的地方封死了。
**解决**：① 把 per-component 朝向轴提升为**声明层字段**（`axis: "Z"`），scaffold 据此烘焙正确向量，agent 改数据不改代码；② `verify_orientation` 的 `construction_axis` 参数真正生效（per-check 覆盖）。
**第一性原理教训**：对 LLM agent，契约强制优先级 = **不可绕过的结构 > 拒绝 > 默认值**。默认值（可变状态 + 全量覆盖语义）最脆弱——agent 的"设 component_id"心智 ≠ API 的"重写整个 snippet"语义，默认值被无声擦除。设计安全闸时务必问：**"agent 合理需要改的东西，我留了正门吗？"** 详见 progress.md 第四十一阶段 + project-component-foundation.md「组件朝向轴」节。

### 测试污染：`edini.*` 模块全局清空破坏 UI 类身份

- **分类**: 测试/隔离
- **优先级**: 高
- **状态**: 已修复 (2026-07-06)

**症状**：装上 PySide6 后，`test_base_driver`（3 个 bubble 测试）+ `test_project_chat_driver_is_subclass` 在**全套件**下稳定失败，单文件跑全过。`issubclass(ProjectChatDriver, BaseChatDriver)` 为 False，`findChildren(UserBubble)` 找不到刚创建的 widget。

**根因**：多个测试（test_assembly_builder / test_node_utils / test_config / test_capture_tools / test_capture_component_detail / test_verify_orientation）为了在 mock hou 下重新加载某个特定模块，用了反模式：

```python
for _m in list(sys.modules):
    if _m.startswith("edini"):        # ← 清空所有 edini.* 模块
        del sys.modules[_m]
```

这会顺带清掉无关的 `edini.ui.components.bubbles` / `edini.ui.chat.base_driver`。后续测试重新 `import` 时模块文件被**重新执行**，生成**新的类对象**（`id(OldUserBubble) != id(NewUserBubble)`，尽管 `__module__` 相同）。用旧类创建的 widget，对新类做 `isinstance` / `findChildren` 全部失败 → flaky 但稳定失败。

**关键诊断技巧**：用 `builtins.exec` 包一层，计数目标模块的**实际执行次数**（正常应=1，被污染时>1）。`sys.modules.__delitem__` 监控无效——Python 3.12+ 的 importlib 内部绕过了它。

**解决**：
1. `tests/conftest.py` 提供 `reload_edini_modules(*names)` helper，只清**指定**模块及其子模块，绝不波及 UI/chat。
2. 所有 `startswith("edini")` 全局清理改为 `reload_edini_modules("edini.node_utils")` 等精准调用。
3. 顺带清理 18 个测试文件里冗余的 `sys.path.insert(0, "python3.11libs")`（conftest.py 已统一处理路径；冗余 insert 会干扰 import 解析）。

**第一性原理教训**：模块重载是**全局副作用**，不是测试的私事。`del sys.modules[...]` 清一个就够时，绝不要用 `startswith` 清一族——你不知道会殃及谁。隔离要**最小权限**：只动你真正需要重绑定的那个模块。

### Python 3.14 + Windows subprocess WinError 6 句柄竞争

- **分类**: 测试/环境
- **优先级**: 高
- **状态**: 已修复 (2026-07-06)

**症状**：`test_project_hython.py` 的 18 个 hython subprocess 测试**高频 flaky**——同样命令连跑 5 次，失败数 6/0/18/9/5 不等。报错固定在 `subprocess._make_inheritable` → `OSError: [WinError 6] 句柄无效`。git bash 与 cmd.exe 下都能复现。

**根因**：CPython 3.14 在 Windows 创建子进程时，要把父进程的 stdio 句柄标记为可继承。当 `subprocess.run(..., capture_output=True)` 不显式指定 `stdin`，子进程默认继承父进程的 stdin 句柄——这个句柄的 `DuplicateHandle` 调用存在竞争窗口（pytest 的 capture 机制会反复重配 sys.stdin/stdout/stderr，使句柄状态更脆弱），间歇性抛 WinError 6。

**解决**：所有 `subprocess.run` 调用显式加 `stdin=subprocess.DEVNULL`——消除父 stdin 句柄继承这个竞争源。修复后 hython 测试连跑 5 次 100% 全绿。

**注意**：这是 CPython 在 Windows 的已知类问题（多个 issue 描述 subprocess 句柄竞争），3.14 仍未根治。任何在 Windows + Python 3.14 下用 `subprocess.run(capture_output=True)` 跑外部进程的代码都应加 `stdin=DEVNULL`。

### HDA 对话框 disconnected：缺进程组隔离，Pi 被控制台事件击杀

- **分类**: JSON-RPC / Windows 子进程
- **优先级**: 高
- **状态**: 已修复 (2026-07-07，第四十二阶段)

**症状**：Project HDA 对话框打开后，Pi Status 从 Connecting 一闪到 Connected，然后约 2 秒后掉到 Disconnected，反复如此。Pi 能成功启动并加载扩展（"Edini tools loaded"），但很快死亡，且 **stderr 完全为空**——不像 Pi 自己报错，倒像被外部力量杀掉。

**根因**：`rpc_client.py` 启动 Pi 子进程时用了 `CREATE_NO_WINDOW`（隐藏控制台窗口），但**没有 `CREATE_NEW_PROCESS_GROUP`**。后果：Pi 共享 Houdini 的控制台会话（console session）。Houdini 内部产生的任何控制台控制事件（Ctrl-C 类信号，很多内部操作会触发）会**级联到共享同一会话的 Pi 子进程**，以 `STATUS_CONTROL_C_EXIT`（`0xC000013A`，十进制 exit code **3221225786**）终止它。

关键诊断信号：
- exit code = `3221225786`（`0xC000013A`）= 控制信号终止，**不是** Pi 自己 exit(1) 之类的主动退出
- **无 stderr**（不是 Pi 报错，是被外部信号杀的）
- 启动后 ~2s 死亡（取决于 Houdini 何时产生第一个控制事件）
- 扩展能正常加载（emit "connected"），死亡发生在加载完成之后

**诊断方法**：新建的 `diagnose_rpc.py` 模拟 RpcClient 启动流程，捕获 Pi 的 stdout/stderr/exit code，精确识别 `0xC000013A` 控制事件击杀。stdout 读取放后台线程（避免 `readline()` 在 Pi 安静等待 stdin 时永久阻塞——脚本自身的坑）。

**解决**：启动 Pi 时 `creationflags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP`。`CREATE_NEW_PROCESS_GROUP` 让 Pi 进入独立进程组，免受父侧（Houdini）控制台事件波及。`stop()` 用 `TerminateProcess`（`.terminate()`/`.kill()`）终止，是强制终止不依赖控制台事件，对新进程组依然有效。

顺带修复一个相关的设计缺陷：`_RpcWorker.run()` 主循环在 Pi 进程退出后原先**不 emit 任何状态**，UI 会永远卡在虚假的 "connected"（进程已死但 UI 不知道）。现在 Pi 非主动停止退出时 emit `disconnected` + 带 exit code 的错误信息，用户能看到真实原因。

**教训**：
1. **Windows 子进程隔离不只是隐藏窗口**。`CREATE_NO_WINDOW` 只管"看不看见"，`CREATE_NEW_PROCESS_GROUP` 才管"接不接收父进程的控制信号"。GUI 进程（Houdini/Electron 等）派生长驻子进程时，两者都要——否则父进程的任何控制台事件（哪怕不是真 Ctrl-C）都会波及子进程。详见 [Node.js child_process docs](https://nodejs.org/api/child_process.html) 的 detached 说明。
2. **exit code 是死因的直接证据**。`0xC000013A` 精确指向"控制信号终止"，而非"Pi 崩溃"。排查子进程死亡，先看 exit code 的十六进制——它能区分"自杀/他杀/意外"。
3. **子进程死亡要反馈到 UI**。RPC worker 的读取循环在进程退出后必须 emit 状态，否则 UI 卡在假连接，用户发消息无响应却以为还连着。

### forwardTool 无错误处理：网络抖动抛成裸 "fetch failed"

- **分类**: TypeScript / 工具层
- **优先级**: 高
- **状态**: 已修复 (2026-07-07，第四十二阶段)

**症状**：建模会话日志里，3 次 `houdini_connect_nodes` 调用返回 `[houdini_connect_nodes] fetch failed`（裸字符串，无结构化信息）。agent 无法判断是该重试、改参数、还是 Houdini 挂了，只能放弃或乱试。

**根因**：9 个工具文件（scene/query/script/harness/recipe/rooted/project/knowledge/eval）各自复制粘贴了一份完全相同的 `forwardTool`，**完全无 try/catch**：

```typescript
async function forwardTool(toolName, params) {
  const response = await fetch(TOOL_URL, {...});  // ← 网络抖动直接抛
  const result = await response.json();
  return { content: [...], details: result };
}
```

Node 的 fetch 在 socket 级失败（ECONNRESET/ECONNREFUSED/超时）时 reject 一个 TypeError，message 通常是 "fetch failed"——对 agent 毫无信息量。复制粘贴 9 份意味着修一处要改 9 处。

**解决**：抽出唯一共享的 `pi-extensions/edini-tools/tools/_shared.ts`，提供带完整错误处理的 `forwardTool`：try/catch + 瞬时错误（网络/5xx/429）重试 2 次（退避 150ms）+ 30s 超时（AbortController）+ 结构化错误体 `{success:false, error, hint, transient, retryable}`。agent 看到的是"这是瞬时错误，重试即可"的明确指引，而非裸字符串。9 个工具文件删掉本地副本，统一 import 共享版本。

**教训**：
1. **代理转发层必须有错误处理**。代理（proxy）工具的价值是"把远程调用的复杂性封装成干净的本地接口"——裸抛远程错误违背了这个价值。至少要：捕获 → 分类（瞬时 vs 永久）→ 结构化 → 带恢复指引。
2. **复制粘贴是技术债的温床**。9 份相同的 forwardTool 意味着同样的 bug 要修 9 次，且极易漏改。一旦发现第二份相同的实现，就该立刻抽共享模块。

### create_node 不返回参数名，agent 被迫猜（length vs dist）

- **分类**: 工具层 / agent 效率
- **优先级**: 高
- **状态**: 已修复 (2026-07-07，第四十二阶段)

**症状**：建模日志里，模型给 line SOP 写 `houdini_set_param(leg_template, "length", ...)`，失败（"parameter 'length' not found"）→ query_parms 才发现真名是 `dist` → 修复。这一个参数名来回浪费 5 轮调用。根因：`houdini_create_node` 只返回 path/name/type，agent 只能凭记忆猜参数名，而 Houdini 参数名跨版本会变（失效）。

**根因**：工具设计缺陷——创建节点后不暴露该节点的参数清单。agent 不得不额外调一次 `query_parms`（读 manifest），而 manifest 还可能和实际创建的版本漂移（polybevel 的 beveltype vs offset 问题是前车之鉴，见上一个 pitfall）。

**解决**：`create_node` 返回值增加 `parms` 字段，含该节点的真实参数清单（`{name, type, components?, menu?}`）。新增 `_node_parm_inventory(node)` 辅助函数，双路径：优先 `node.type().parmTemplateGroup()`（真实 hou，完整含 type/menu/components，从刚创建的实际节点读，无版本漂移），回退 `node.parms()`（已物化参数，覆盖 mock/特殊节点）。60 项截断保护，完全 best-effort，任何失败降级为空 list + note，绝不阻塞 create。更新 `houdini_create_node` 工具描述告知 agent 用 `parms.list`。

**教训**：**工具的返回值要带着 agent 下一步需要的信息**。创建节点后，agent 立即要做的就是设参数——那就该在创建的返回值里给出参数名，省掉一个来回。`query_parms` 是"创建前的查询"，`create_node` 的返回值是"创建后的实证"，两者互补，但后者更准（反映实际实例化的版本）。

### 误判 "platform bug" 前先读源码（output_index 误判事件）

- **分类**: 诊断方法 / 方法论
- **优先级**: 高
- **状态**: 教训 (2026-07-07，双建模会话日志诊断)

**症状**：分析桌子建模日志时，第一版诊断断言"**scaffold 默认 `output_index=0` 接错**，shelf 的 4 个输入被连到 legs 的几何体输出而非锚点云"。基于这个误判，最初的改进方向指向"修 scaffold 的 output_index 逻辑"。

**根因**：诊断没有落到代码行号。读 `python3.11libs/edini/project/builder.py` 的 `_ensure_input_scaffold` 后**证伪**：

```python
# builder.py:282-292
from_port = in_entry.get("port")     # 来自声明的 ports.in[].port
...
subnet.setInput(i, upstream, from_port)   # 用的是声明的 port，不是默认 0
```

日志里 shelf 的 scaffold 声明 `"port": 1` 是**正确的**，scaffold 也确实按 `from_port=1` 接了。**scaffold 没有 output_index bug。** 真实根因是模型侧：不信任已正确接好的脚手架 → 对子网内部 filter 节点重连失败 → 退到 sandbox setInput 断链 → 自己删 filter 链退回 Object Merge 硬编码（10 分钟挣扎，全程是模型行为，非平台 bug）。

**解决**：诊断必须以代码行号为锚。详见 [会话日志第一性原理诊断](session-logs-analysis.md) 的"关键修正"一节。

**教训（立为规矩）**：**凡断言"平台 X 行为错误"，必须先 grep 到对应源码行号佐证，否则一律先归为"模型行为/文档缺口"排除。** 第一性原理分析若不落到代码，会把"模型行为"误判成"平台 bug"，导致整层改进方向错位——这次的误判差点让改进方向去动一个本来正确的 `setInput` 调用。**诊断的下一个问题永远是"这个行为在源码哪一行？"**

### 程序化建模的五个真实失败模式（双日志实证）

- **分类**: project-modeling / 诊断
- **优先级**: 高
- **状态**: 已诊断 / 待修复 (2026-07-07，A/B/C 路线图待实施)

**症状**：分析桌子（3 组件）+ 公路车（7 组件）两份真实建模会话日志，归纳出五个系统性缺陷。不是偶发，是结构性反复。

**五个缺陷（各一句话，详见 [诊断深度页](session-logs-analysis.md)）**：

1. **接线错觉**（违背"依赖显式声明"）—— scaffold 接对了，但模型不信任 + 重连机制不安全 → 自己破坏契约退回硬编码。根因是 scaffold 不回报接线 ground-truth。**→ Layer A 改进**。
2. **Python SOP 知识缺口系统性复发**（违背"单元可读可改"）—— `return` outside function ×6+、`addAttrib` 须先于 `setAttribValue` ×2、`createPoint` 签名错、`ch` vs `hou.ch`、`node.geometry()` 是输出非输入。skill 把组件生成器写法完全交给即兴发挥。**→ Layer B 改进**。
3. **锚点测量全是 bbox 派生 → 参数化只是表象**（违背"坐标可参数化"）—— bike 的 frame 四锚点全用 `bbox_face_center`，frame 是单一合并网格，bbox 面中心 ≠ 真实 dropout/头管/五通。改 `frame_scale` 轮子不跟真实 dropout 走。`vex_strategies.py` 无 `by_name`/named-marker 策略。**→ Layer C1 改进**。
4. **promote_params 返回 0 是 workflow 设计矛盾**（违背"完成有判据"）—— promote 只提升 subnet spare parm，但 SKILL 教模型用绝对 ch() 直引 core，从不建 subnet spare parm → promote 永远 0 → 死重量。副作用：绝对路径让组件不可迁移。**→ 待规划**。
5. **bike 跳过参数联动验证**（违反 skill 自己的 premature-done 诫令）—— 桌子验证了 length 1.2→1.5，bike 零扰动验证就声明完成。`overall_ok` 不证明参数化成立。现有工具无扰动测试。**→ Layer C2 改进**。

**根因**：这五个缺陷的共同源头是"**程序化建模的核心契约（live 参数化 + 组件协作 + 完成判据）在 prompt 层和 platform 层都还不够硬**"。skill 已有四诫，但对应的平台层执行（scaffold 回报 / Python SOP 模板 / named-marker 锚点 / 扰动验证门）尚未到位。

**解决（A/B/C 路线图，本轮未实施）**：A=scaffold 回报接线 ground-truth（杠杆最高）；B=Python SOP 组件模板（纯 prompt）；C=named-marker 锚点 + `verify_parametric` 扰动验证门（最治本）。每层配 hython 真机铁证。详见 [诊断深度页](session-logs-analysis.md) 的"后续路线图"一节。

**教训**：**模型越复杂，脆性越大**。下一阶段重心不该是"做更复杂的模型"，而是把这五个底层契约修硬——否则公路车这种 7 组件 DAG 会比桌子的 3 组件链更脆。

### 原型层谎报 success：未知 parm 静默 no-op + 多点锚点只命名 [0]

- **分类**: 程序化管线 / 原型层
- **优先级**: 高
- **状态**: 已修复 (2026-07-08，archetype-fixes)

**症状**：键盘会话里 `project_emit_component(copy_array, leaf.size=[...])` 返回 `success:true`，但 leaf box 停在 1×1×1（尺寸没应用）；`grid_on_face` 发了 75 个锚点，下游 keys 只收到 1 个 → 只出 1 个键。两次都要 agent 手动补丁（手补 set_params_batch / 手补命名 wrangle）才救回来。

**根因（两个独立静默失效，同 commit 修）**：
1. **P0-2**：`_set_archetype_parm`（builder.py:975）遇未知 parm `if p is None: return` —— box 没有 "size" parm（只有 sizex/y/z），copy_array 把 `leaf.params.size=[...]` 透传过来被静默吞掉，且不处理 list 值。emit_component 照样返回 `success:true`。**最危险的失败模式：报成功却没生效。**
2. **P0-1**：`add_anchors`/`emit_markers`（builder.py:759/897）收尾只 `setpointattrib(__newpts[0], name)` —— 多点策略（grid/pickets/cells/shelf）往 `__newpts` 加 N 点，只命名第一个。端口按 `@name` 过滤 → 下游 1/N。单点策略（bbox_corner）N=1 意外能用，掩盖了 bug。

**解决**：
1. P0-2：`_set_archetype_parm` 重写为委托 `node_utils._apply_one_param`（手搓路径 set_param/set_params_batch 的同一套 dispatch）—— 自动获得向量→parmTuple、表达式→setExpression、未知 parm "did you mean" 报错。失败 raise → emit_component 返回清晰 `{success:False}`。**第一性原理：一套设参真相，原型与手搓同等能力。**
2. P0-1：`foreach (int __pt; __newpts) setpointattrib(...)` 全部命名。

**教训**：**生成器（archetype/builder）的契约是"比手搓更可靠"，否则就是负价值**。静默 no-op + 谎报 success 是生成器头号大忌——比报错坏得多（agent 信任 success，不会复查）。任何"找不到就 return"的 helper 用在生成器里都要换成 raise。配套测试矩阵必须覆盖"多点"场景（此前只测单点策略，盲区）。实测是唯一铁证：4 个真实 Pi 会话才把这俩挖出来。

### 设计好的节流被静默禁用（dead-code _flush_stream）

- **分类**: UI / 性能
- **优先级**: 高
- **状态**: 已修复 (2026-07-08，archetype-fixes)

**症状**：Houdini 里开着 edini 对话面板 + agent 跑建模任务时，UI 严重卡顿；关掉面板就明显好转。

**根因**：流式渲染本有节流设计（`_stream_flush_timer` / `STREAM_FLUSH_INTERVAL_MS=80` / `_flush_stream`），但 `_flush_stream` 被改成了 **no-op**（注释 "No-op in widget mode — updates happen in append_stream_chunk"），render 挪到了 `append_stream_chunk` 里**逐 token eager** 调 `bubble.update_streaming(full_text)` → `QLabel.setText(整段增长文本)` → Qt 每 token 重排整段（O(N)/token）。配合 agent 同主线程跑图变更工具（见「QThread 与 Houdini 主线程」「工具执行器的线程安全」），开面板 = 两个主线程消费者抢一个线程。

**解决**：**不是新增节流，是重新接上一根被拔掉的线**。`append_stream_chunk` 只 buffer + 起单次定时器；`_flush_stream`（定时器回调）真正渲染，~12 次/秒而非逐 token。`finish_streaming` 在一次性 markdown 渲染前补 flush 防尾部丢失。零新 API、不碰 Houdini 全局状态、复用既有设施。删死常量 `STREAM_FLUSH_CHARS`。

**教训**：**改实现时把旧机制留成 no-op 而非删除，是隐形债**。后人（包括自己）看到 `_stream_flush_timer` 还以为节流在工作，实则死代码。要么彻底删，要么留醒目注释。逐 token 重排这种累积性能成本，单元测覆盖不到，只能靠真机实测发现。

### HTTP 响应写未容忍客户端超时断连 → ConnectionAbortedError 级联

- **分类**: 工具执行器 / 并发
- **优先级**: 中
- **状态**: 已修复 (2026-07-08，archetype-fixes)

**症状**：Houdini 控制台刷 `ConnectionAbortedError: [WinError 10053]` traceback，源自 `tool_executor.do_POST → _send_json → end_headers → wfile.write`。

**根因**：Pi 客户端 `forwardTool` 有 30s 超时（见「forwardTool 无错误处理：网络抖动抛成裸 fetch failed」）。慢 tool（如 `verify_robust` 7×3=21 次强制 cook 在主线程争用下）超 30s → 客户端关 socket → server 算完写响应时撞已关闭连接 → `ConnectionAbortedError`。级联：结果写失败被 `do_POST` 的 `except Exception` 捕获 → 又写错误响应 → 又失败 → 未捕获 → traceback。对正确性无害（客户端已重试 `attempts:3` 并成功），纯噪音。

**解决**：`_write_response` 统一发送，吞掉 `BrokenPipeError`/`ConnectionAbortedError`/`ConnectionResetError`。客户端已走，无可送达。

**教训**：**服务端响应写必须容忍客户端先行断开**（超时/取消/换页都常见）。裸写不加 try/except，一次客户端超时就刷一个吓人 traceback，还级联成双重失败。慢 tool 本身要治（绑到节流 + 后续 manual-update），但响应层的健壮性是独立的底线。

