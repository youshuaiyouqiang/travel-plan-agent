# infrastructure/mcp/servers/tencent-docs/ — 模块记忆

## 职责定位
腾讯文档读写 MCP 服务声明（搜索/创建文档）。**当前仅有目录声明，无内置 adapter**。

## 关键文件
- `INSTRUCTIONS.md`：依赖说明。
- `tools/`：两个工具声明（见其 memory.md）。

## 业务边界要点
- 需环境变量 `TENCENT_DOCS_APP_ID` / `TENCENT_DOCS_APP_SECRET` 凭证；凭证不得进入日志或仓库。
