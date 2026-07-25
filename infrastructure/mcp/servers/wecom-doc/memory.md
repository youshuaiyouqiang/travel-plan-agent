# infrastructure/mcp/servers/wecom-doc/ — 模块记忆

## 职责定位
企业微信集成 MCP 服务声明（创建待办、发送消息）。**当前仅有目录声明，无内置 adapter**。

## 关键文件
- `INSTRUCTIONS.md`：依赖说明。
- `tools/`：两个工具声明（见其 memory.md）。

## 业务边界要点
- 需环境变量 `WECOM_CORP_ID` / `WECOM_CORP_SECRET` / `WECOM_AGENT_ID`；凭证不得进入日志或仓库。
