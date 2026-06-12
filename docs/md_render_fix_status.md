# MD 渲染修复 — 最终状态

## 已完成
- [x] 用 **mistune 3.2.1** 替代手写正则 Markdown 渲染器
- [x] 自定义 `_DarkRenderer` 注入暗色主题 inline style
- [x] `_format_lite` = `_format_full`，流式/最终渲染 **像素级一致**
- [x] GFM 完整支持：table, strikethrough, task_lists
- [x] 新增支持：h4-h6, blockquote, image, strikethrough, task list
- [x] 代码块正确 HTML 转义（单次）
- [x] 数学表达式不再误判斜体
- [x] 未闭合代码块正确处理
- [x] 57 项测试全部通过

## 新增支持的语法（之前不支持）
| 语法 | 示例 |
|------|------|
| h4-h6 | `#### Title` |
| 引用块 | `> quote` |
| 图片 | `![alt](url)` |
| 删除线 | `~~text~~` |
| 任务列表 | `- [ ] todo` / `- [x] done` |
| 嵌套引用 | `> level1 >> level2` |

## 文件变更
- `python3.11libs/edini/ui/agent_panel.py` — 新增 `_DarkRenderer` 类, `_md_parser` 实例; 重写 `_format_lite` / `_format_full`
- `tests/test_md_render.py` — 57 项全面测试

## 依赖
- `mistune >= 3.0` (pip install mistune)
