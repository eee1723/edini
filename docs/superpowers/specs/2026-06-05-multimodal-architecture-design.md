# 多模态架构设计 — Edini 视觉能力完整链路

> 2026-06-05 | 第十三阶段：多模态扩展深化

## 1. 目标

为 Edini 构建完整的多模态能力——用户可通过截图、拖拽、粘贴、文件选择 4 种渠道向 AI 提供图片，AI 通过 pi-visionizer 视觉代理自动调用 Qwen-VL Max 描述图片内容，再由 DeepSeek 主模型基于文本描述进行推理回复。

## 2. 方案选择

| 方案 | 描述 | 选择 |
|---|---|---|
| A | 最小扩展：修 bug + 线性加功能 | ❌ agent_panel.py 已 900+ 行，继续膨胀不可维护 |
| B | MediaManager + VisionPipeline 分层 | ✅ 遵循现有分层模式，职责清晰 |
| C | pi-visionizer 中心化 | ❌ UI 控制权交给 Node.js 端，不适合 Houdini 深度绑定场景 |

## 3. 新增模块架构

```
python3.11libs/edini/
├── media_manager.py        # NEW — 图片输入统一管理
│   ├── MediaSource (Enum)  # VIEWPORT | DRAG_DROP | CLIPBOARD | FILE_PICK | TOOL
│   ├── MediaItem (dataclass)
│   ├── capture_viewport()  # 从 viewport.py 迁入，三级降级修复
│   ├── from_files(paths)   # 文件选择 → list[MediaItem]
│   ├── from_clipboard()    # 粘贴板读取 → MediaItem | None
│   ├── from_drop(mime)     # 拖拽 QMimeData → list[MediaItem]
│   └── validate(item)      # 大小/mimeType/base64 校验
│
├── ui/
│   ├── agent_panel.py      # 改动 — 接入 MediaManager + 附件预览栏
│   ├── image_attachment.py # NEW — ImageAttachmentWidget (缩略图 120×68 + ✕ 删除)
│   └── vision_overlay.py   # NEW — VisionDescriptionBubble (时间线中可折叠描述气泡)

pi-extensions/pi-visionizer/
└── src/
    ├── config.ts           # 改动 — 默认视觉模型改为 aliyun/qwen-vl-max
    └── index.ts            # 改动 — context hook 写入 vision-description custom entry
                             #         并通过 extension_ui_request 通知 Edini
```

### 3.1 模块职责边界

| 模块 | 职责 | 禁止 |
|---|---|---|
| media_manager.py | 图片获取（截屏/选择/粘贴/拖拽）、格式归一化、缩略图生成 | 不涉及 UI 渲染 |
| image_attachment.py | 待发送图片的缩略图预览 + 删除按钮 | 不处理 Houdini API |
| vision_overlay.py | 时间线中渲染 VisionDescriptionBubble | 不发起 RPC |
| agent_panel.py | 接入 MediaManager 信号、附件栏布局 | 不直接调用 hou |
| pi-visionizer/ | 图片→文字描述代理、session custom entry 写入 | 不直接操作 Houdini |

## 4. 完整数据流

```
用户操作 (截图/拖拽/粘贴/选文件)
    │
    ▼
MediaManager — 归一化为 MediaItem { base64, mimeType, source, thumbnail, filename }
    │
    ▼
ImageAttachmentWidget — 附件预览栏 (最多 5 张, 缩略图 120×68)
    │ 用户点"发送"
    ▼
RpcClient.send_prompt(text, images=[{ type:"image", data:base64, mimeType }])
    │  stdin/stdout JSON-RPC
    ▼
Pi Agent Core → context hook 拦截
    │
    ▼
pi-visionizer:
  ├─ 检测 image content block
  ├─ 调用 Qwen-VL Max (aliyun API)
  ├─ 替换 image block → [Image Description: ...]
  ├─ 写入 session custom entry (vision-description)
  └─ extension_ui_request 通知 Edini
    │
    ▼
Edini UI 渲染:
  ├─ UserBubble (含已发送缩略图)
  ├─ VisionDescriptionBubble (可折叠, 显示 Qwen-VL 描述文本)
  └─ AiBubble (DeepSeek 流式回复)
```

### 4.1 附件预览栏布局

```
┌─────────────────────────────────────────────────────────┐
│ 📸 vp_2026.jpg  ✕   📁 ref.png  ✕   📋 paste.png  ✕     │  ← ImageAttachmentWidget
│ [120×68缩略图]      [120×68缩略图]    [120×68缩略图]     │
├─────────────────────────────────────────────────────────┤
│ 📷  ⌨  📁  [请输入操作...                              ] 发送 │  ← 输入栏
└─────────────────────────────────────────────────────────┘
```

- 来源图标: 📸截图 / 📁文件 / 📋粘贴
- 超过 5 张：拒绝新图片，提示"最多 5 张图片"
- 发送后自动清空
- 无附件时完全隐藏 (0 高度)

### 4.2 视觉描述气泡

```
┌────────────────────────────────────────────┐
│ 👁️ 图片描述 · qwen-vl-max · 2.3s  ▲ 收起  │  ← 头部
├────────────────────────────────────────────┤
│ The viewport shows a 3D scene with:        │
│ - Smoke simulation, density appears low    │
│ - Wireframe overlay visible on left side   │
│ - Timeline shows frame 42 of 240           │
│                                            │
│ 📸 查看原图                                 │
└────────────────────────────────────────────┘
```

- 默认展开
- 折叠后: `👁️ 图片描述 · qwen-vl-max · 2.3s ▼ 展开`
- "查看原图" → 在系统默认图片查看器中打开 base64 渲染的临时图片
- 失败时: `👁️ 图片分析失败: API error (401): ...`

### 4.3 AI 工具主动读图

pi-visionizer 已注册 `describe_image` 工具，AI 可主动调用：
```
AI: "让我先看看渲染结果"
  → tool_call: describe_image({ path: "render/result.jpg" })
    → Qwen-VL 描述 → AI 基于描述继续推理
```
结果在 Tool Card 中展示，无需额外 UI。

## 5. MediaManager 详细设计

### 5.1 数据结构

```python
class MediaSource(Enum):
    VIEWPORT = "viewport"
    DRAG_DROP = "drag"
    CLIPBOARD = "paste"
    FILE_PICK = "pick"
    TOOL = "tool"

@dataclass
class MediaItem:
    base64: str          # 无 data: 前缀
    mime_type: str       # "image/jpeg" | "image/png" | ...
    source: MediaSource
    filename: str        # "viewport_20260605.jpg" | "ref_texture.png"
    thumbnail: str | None  # 120px 宽等比缩放, JPEG q=30
    file_path: str | None  # 文件选择/拖拽源路径, paste/screenshot 为 None
    size_bytes: int
```

### 5.2 核心方法

| 方法 | 输入 | 输出 | 校验 |
|---|---|---|---|
| `capture_viewport()` | 无 | `MediaItem \| None` | 大小 >0 |
| `from_files(paths)` | `list[str]` | `list[MediaItem]` | ≤5MB, 图片扩展名 |
| `from_clipboard()` | 无 | `MediaItem \| None` | QImage.isNull() |
| `from_drop(mime_data)` | QMimeData | `list[MediaItem]` | 过滤非图片 URL |
| `validate(item)` | MediaItem | `(bool, str)` | ≤5MB, mimeType 合法 |

### 5.3 Viewport 截图修复 — 三级降级

当前 `capture_viewport()` 返回 None。修复采用三级降级策略：

1. **saveImage（主方案）**: `viewport.saveImage(buf, "JPEG", width=1280, height=720)` — 需 Commercial license
2. **grabFrameBuffer（降级）**: `viewport.grabFrameBuffer().image()` → QImage → save to JPEG — 某些 Houdini 版本可用
3. **flipbook 单帧（终局降级）**: 通过 `hou.flipbook()` 或 `viewport.flipbook()` 输出单帧到临时目录 → `os.path.join(tempfile.gettempdir(), "edini_viewport.jpg")` → 读文件 → base64 编码 → 删除

三级都失败则返回 None，UI 显示 ❌ 闪烁 1.5s 并提示"截图失败: 当前 Houdini 环境不支持视口截图"。

### 5.4 拖拽事件整合

PySide6 的 `dragEnterEvent`/`dropEvent` 可能被 Houdini 原生拖拽吞掉。解决方案：
- 在输入框 `QPlainTextEdit` 上 `installEventFilter`
- 仅拦截含图片 MIME (`image/*` 文件 URL) 的事件
- 不含图片 MIME → `event.ignore()`，让 Houdini 原生处理

### 5.5 缩略图生成

```python
def _make_thumbnail(full_base64: str, mime_type: str) -> str:
    """生成 120px 宽的 JPEG 缩略图, quality=30."""
    img = QImage()
    img.loadFromData(base64.b64decode(full_base64))
    scaled = img.scaledToWidth(120, Qt.SmoothTransformation)
    buf = io.BytesIO()
    scaled.save(buf, "JPEG", quality=30)
    return base64.b64encode(buf.getvalue()).decode("ascii")
```

## 6. pi-visionizer 改动

### 6.1 默认视觉模型

`config.ts`:
```typescript
export const DEFAULT_VISION_MODEL: VisionizerConfig = {
  provider: "aliyun",
  modelId: "qwen-vl-max",
};
```

### 6.2 context hook 增强

在 `index.ts` 的 context hook 中，处理完图片描述后：

```typescript
// 收集描述结果
const descriptions: Array<{
  mimeType: string;
  description: string;
  model: string;
  elapsedMs: number;
}> = [];

// 每张图片处理完:
const start = Date.now();
const result = await describeImage(...);
descriptions.push({
  mimeType,
  description: result.description || `[Error: ${result.error}]`,
  model: "aliyun/qwen-vl-max",
  elapsedMs: Date.now() - start,
});

// 全部处理完后:
ctx.sessionManager.appendEntry({
  type: "custom",
  customType: "vision-description",
  data: { timestamp: Date.now(), descriptions },
});

// 通知 Edini:
await pi.sendUiRequest({
  method: "notify",
  notifyType: "info",
  message: JSON.stringify({
    event: "vision_description",
    descriptions,
  }),
});
```

### 6.3 Edini 接收流程

`rpc_client.py` 中已有 `extension_ui_request` → `extension_info` signal。在 `agent_panel.py` 中监听：

```python
# agent_panel.py
self._runtime.extension_info → 检测 JSON 中的 event: "vision_description"
  → 解析 descriptions 列表
  → 创建 VisionDescriptionBubble 插入时间线
```

## 7. 新增 UI 组件

### 7.1 ImageAttachmentWidget

- 继承 `QWidget`
- 水平 `QHBoxLayout`，子项为每个附件的图片卡片
- 每个卡片: `QVBoxLayout` { QLabel(缩略图 120×68), QLabel(文件名 + 来源图标) } + QPushButton("✕")
- 信号: `attachment_removed(int index)`, `attachments_changed()`
- 公共方法: `add(MediaItem) → bool`, `remove(int)`, `clear()`, `items() → list[MediaItem]`

### 7.2 VisionDescriptionBubble

- 继承 `QFrame`
- 可折叠: QPushButton("▲ 收起") → 隐藏内容区, 显示一行摘要
- 内容区: QLabel(描述文本, WordWrap, TextSelectableByMouse)
- 静态方法: `create_vision_bubble(descriptions) → VisionDescriptionBubble`
- 失败变体: 红色边框 + 错误信息

## 8. Agent Panel 改动汇总

| 改动点 | 描述 |
|---|---|
| 附件栏 | 输入框上方嵌入 `ImageAttachmentWidget`，无附件时隐藏 |
| 按钮栏 | 新增 📁 (选择文件) 按钮，屏截图按钮 → 拖拽区 → 粘贴监听 |
| 发送逻辑 | `_on_send()` 合并附件栏图片 + 截图数据 → `images=[...]` |
| 拖拽过滤 | 输入框 `installEventFilter`，仅拦截图片拖拽 |
| 粘贴处理 | 输入框 `keyPressEvent` 或剪贴板监听 → Cmd/Ctrl+V 时检查图片 |
| 视觉描述 | 监听 `extension_info` signal → 解析 `vision_description` → 渲染气泡 |
| 原图查看 | VisionDescriptionBubble 中"查看原图"按钮逻辑 |

## 9. 配置简化

**双 Key 场景**：用户主模型用 DeepSeek（通过 `$DEEPSEEK_API_KEY`），视觉模型用 Qwen-VL（通过 `$DASHSCOPE_API_KEY`）。

- **主模型 API Key**: 在 Edini Settings 中设置（现有字段）
- **视觉 API Key**: 利用 models.json 中 aliyun 已配置的 `$DASHSCOPE_API_KEY` 环境变量，用户需在系统环境变量或 `.env` 中设置
- pi-visionizer 通过 `ctx.modelRegistry.getApiKeyAndHeaders(visionModel)` 自动读取 Key，无需 Edini 额外传递

**后续优化**：可在 Settings Dialog 的 General 标签中增加"视觉 API Key"字段，覆盖环境变量，方便用户在 UI 中管理（本次不实现，留作 P3 优化项）。

## 10. 边界与约束

| 约束 | 值 | 说明 |
|---|---|---|
| 附件上限 | 5 张 | 避免 token 超限 |
| 图片大小上限 | 5 MB | 与 pi-visionizer describe_image 工具一致 |
| 截图分辨率 | 1280×720 | JPEG q=85 |
| 缩略图尺寸 | 120×68 | JPEG q=30 |
| 视觉 API 超时 | 30s | pi-visionizer 已配置 |
| Qwen-VL contextWindow | 32768 tokens | models.json 配置 |

## 11. pi-visionizer 改动细节

### 11.1 视觉模型认证

pi-visionizer 调用 `ctx.modelRegistry.getApiKeyAndHeaders(visionModel)` 获取 aliyun/qwen-vl-max 的 API Key。需要确保 models.json 中 aliyun provider 配置了正确的 `apiKey: "$DASHSCOPE_API_KEY"` 环境变量引用。

### 11.2 图片发送格式确认

Edini 端 `send_prompt` 发送的 image 格式：
```json
{ "type": "image", "data": "<base64>", "mimeType": "image/jpeg" }
```
pi-visionizer 的 `isImageBlock()` 检查 `block.type === "image" && typeof block.data === "string"` — 格式匹配。

## 12. 现有文件改动清单

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `python3.11libs/edini/media_manager.py` | NEW | 图片输入统一管理 |
| `python3.11libs/edini/ui/image_attachment.py` | NEW | 附件预览组件 |
| `python3.11libs/edini/ui/vision_overlay.py` | NEW | 视觉描述气泡 |
| `python3.11libs/edini/ui/agent_panel.py` | MODIFY | 接入 Management + 附件栏 + 视觉描述 |
| `python3.11libs/edini/ui/viewport.py` | MODIFY/REMOVE | capture_viewport 迁出到 media_manager.py |
| `python3.11libs/edini/rpc_client.py` | MODIFY | 透传 extension_ui_request 中的 vision_description JSON 到新 signal `vision_description` |
| `pi-extensions/pi-visionizer/src/config.ts` | MODIFY | 默认视觉模型改为 aliyun/qwen-vl-max |
| `pi-extensions/pi-visionizer/src/index.ts` | MODIFY | context hook 写入 vision-description entry + 通知 |
