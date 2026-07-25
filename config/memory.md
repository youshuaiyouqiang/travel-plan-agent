# config/ — 模块记忆

## 职责定位
配置层：应用配置定义与环境变量模板，全局 `Settings` 的唯一来源。

## 关键文件
- `settings.py`：基于 pydantic-settings 的 `Settings`——统一读取 `YUNHE_` 前缀环境变量；覆盖 LLM、数据目录、日志、审计、Agent 运行参数、安全策略（allow_shell/shell_timeout）、Redis/限流、监控端口、管理员账号、运行环境；派生路径 `builtin_agents_dir`/`skills_dir`/`mcp_servers_dir`；末尾实例化全局 `settings`。
- `.env.example`：开发环境变量模板。
- `__init__.py`：包占位。

## 业务边界要点
- 敏感值全部来自 `.env`（不入库），`settings.py` 本身不含密钥。
- `admin_username` 为空时管理员 API 不可用；生产环境必须配置且启动 fail-fast。
- ⚠️ 安全隐患：`config/.env.example` 中曾发现真实形态密钥明文（高德/飞猪等），应替换为纯占位符；`allow_shell=true`、`log_level=DEBUG` 为宽松默认值，生产需收紧。
