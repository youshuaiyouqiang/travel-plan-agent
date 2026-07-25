# application/builtin_agents/ — 模块记忆

## 职责定位
内置智能体的声明式配置与加载器：以 YAML 定义 4 个内置 Agent（云合调度员、新闻、旅行、学术），新增 Agent 只需加 YAML 文件不改代码。

## 关键文件
- `loader.py`：`BuiltinAgentLoader`，扫描目录下 `*.yaml` 并映射为 `AgentConfig`。
- `yunhe.yaml`：云合调度员——意图识别、委派路由、通用兜底对话。
- `news.yaml`：新闻 Agent——热点解读、交叉验证、证据编排（锚定 news_id）。
- `travel.yaml`：旅行 Agent——行程规划、草稿/确认存档流程。
- `academic.yaml`：学术 Agent——论文检索、引用分析、学术写作辅助。
- `__init__.py`：包占位。

## 业务边界要点
- 单个 YAML 加载失败仅记录日志不中断启动；目录缺失返回空列表。
- Agent 的工具白名单在 YAML 中声明，由工具策略层强制执行（如学术 Agent 拿不到 web_search）。
