# infrastructure/mcp/servers/chrome-devtools/ — 模块记忆

## 职责定位
Chrome DevTools 浏览器自动化 MCP 服务声明：截图、点击、页面内容提取。**当前仅有目录声明，无内置 adapter**，工具查询会显示 `adapter_available=False`。

## 关键文件
- `SERVER_METADATA.json`：服务元数据。
- `INSTRUCTIONS.md`：依赖与工具说明。
- `tools/`：三个工具声明（见其 memory.md）。

## 业务边界要点
- 前置依赖 playwright + chromium；要可执行需在 `mcp/runtime.py` 登记 adapter 或接外部 MCP 客户端。
