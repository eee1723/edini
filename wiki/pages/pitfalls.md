# ⚠️ 踩坑记录

> Edini 开发过程中的踩坑记录，避免重复犯错。支持按分类/优先级/状态筛选。

## 已记录的问题

### Houdini Python 环境隔离

- **分类**: Python/PySide6
- **优先级**: 高
- **状态**: 信息

Houdini 自带 Python 解释器，路径与系统 Python 隔离。`pip install` 对 Houdini 内运行的代码无效。
**解决**：所有依赖必须在 Houdini Python 环境中可用。PySide6 由 Houdini 自带，markdown 包不直接使用（Panel 自处理 Markdown→HTML），
Pi 作为外部 Node.js 进程独立运行。配置文件使用标准库 json/os/pathlib，无外部 PyPI 依赖。

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

### TypeBox 参数校验 vs houp API 类型

- **分类**: TypeScript
- **优先级**: 低
- **状态**: 信息

TypeBox 定义的参数类型（如 `Type.String()`）与 Python houp API 的期望类型不完全对应。
例如：整数参数在 TypeBox 是 `Type.Number()`，但需要确保不传递浮点数给需要整数的参数。
**解决**：工具设计上保持参数类型宽松（`Type.Unknown()` 用于 set_param value），
让 Python 端做最终的类型转换和校验。

### Pi --no-session 模式限制

- **分类**: Pi
- **优先级**: 中
- **状态**: 信息

使用 `--no-session` 模式表示每次对话完全独立，不支持上下文延续。
这对简单操作友好（避免上下文膨胀），但对需要多步操作的复杂工作流不友好。
**权衡**：当前策略优先保证可预测性，后续可考虑开启 session 模式加上 max_turns 限制。

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

## 参考

- [架构地图](architecture.html) — 了解系统边界避免踩坑
- [工具清单](tools.html) — 16 个工具的正确使用方式
