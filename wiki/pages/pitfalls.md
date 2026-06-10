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

- **分类**: Python/PySide6
- **优先级**: 高
- **状态**: 已修复

时间线使用 QTextBrowser + setHtml 流式更新（每 80 字符一次）：① setHtml 重建整个 HTML 文档 DOM，性能差 ② actionTriggered 信号在部分 Qt 版本不可靠 ③ blockSignals + setValue + 比例计算存在异步布局竞态 ④ _flush_thinking_buf 清空 _current_text 导致气泡只显示新 chunk。
**解决**：重构为 QScrollArea + 独立 Widget 架构：_UserBubble / _AiBubble (QLabel RichText) / _Separator / _ErrorBanner。滚动改用 rangeChanged + valueChanged + _pinned_to_bottom 标志位。流式文本用 _streaming_full_text 永不清空的累加器。气泡用 Expanding sizePolicy + layout margin 填满窗口。

## 参考

- [架构地图](architecture.html) — 了解系统边界避免踩坑
- [工具清单](tools.html) — 16 个工具的正确使用方式

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
