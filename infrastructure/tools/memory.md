# infrastructure/tools/ — 模块记忆

## 职责定位
工具核心框架：工具定义、注册、安全策略、异步执行，是所有 Agent 工具调用的统一总线。

## 关键文件
- `base.py`：`ToolSpec` / `Tool` 定义，含渐进式披露 tier、skill_binding、mcp_source 属性。
- `registry.py`：名称 → 工具的注册与查询。
- `catalog.py`：spec 只读视图。
- `policy.py`：安全策略——硬编码拦截高危 shell 命令、禁写 `/etc/`、高风险操作需确认、频率限制、按 Agent 过滤工具白名单（`filter_allowed_tools`）。
- `executor.py`：异步执行器，落地 DENY/CONFIRM/UNKNOWN 决策与审计日志。
- `__init__.py`：包占位。

## 业务边界要点
- shell 黑名单（`rm -rf /`、`mkfs` 等）+ 风险命令需用户确认；写文件禁 `/etc/`。
- 每工具限流：30 次/分、200 次/时。
- Agent 工具白名单在此强制：`academic` 限 arXiv/论文工具（无 web_search），`news` 限新闻检索/来源库/交叉验证工具。
- 工具执行全程写审计（domain/shared/audit）。
