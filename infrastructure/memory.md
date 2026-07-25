# infrastructure/ — 模块记忆

## 职责定位
基础设施层（DDD 最外圈）：SQLite 持久化、LLM 适配、限流缓存、MCP 工具代理、Skill 系统、工具执行框架、新闻抓取适配、密码安全。所有外部 I/O 集中于此。

## 子目录
- `cache/`：Redis/内存限流器。
- `external/`：空占位包（外部集成实际分散在 tools/adapters、mcp/servers、skills/builtin）。
- `llm/`：OpenAI 兼容 LLM 客户端 + FallbackLLM 降级链。
- `mcp/`：MCP 目录扫描 + 代理运行时；`servers/` 下 5 个服务声明。
- `news/`：新闻来源抓取适配器（按域名分发）。
- `persistence/`：SQLite 连接管理、迁移跟踪、各领域 Repository、健康检查。
- `security/`：bcrypt/PBKDF2 密码哈希。
- `skills/`：Skill Provider 与内置 Skill（高德、飞猪、和风天气等）。
- `tools/`：工具核心框架（注册表/策略/执行器）与外部服务适配器。

## 业务边界要点
- SQL 必须参数化；动态表名只能来自硬编码白名单。
- 抓取层绝不返回新闻全文；LLM 调用全链路写审计。
- 新增外部依赖应经端口/应用服务注入 domain，不让 domain 反向依赖本层（现状有违规，见 domain/memory.md）。
