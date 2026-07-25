# application/session/ — 模块记忆

## 职责定位
会话模式持久化与所有权校验应用服务：管理三种会话模式（yunhe_default / agent_locked / news_analysis_locked）的创建、读取与切换规则。

## 关键文件
- `schema.py`：`SessionMode` / `UserSessionMode` / `SessionRecord` 数据类。
- `service.py`：`SessionService`——创建/读取/更新会话模式，`require_owned` 校验会话归属。
- `__init__.py`：导出模式类型与 `SessionService`。

## 业务边界要点
- 用户 API 禁止直接设置 `news_analysis_locked`：该模式只能由新闻研判服务内部创建（服务内二次防御）。
- `agent_locked` 必须指定白名单内的 `locked_agent_id`（默认 travel/academic；yunhe 与 news 不可被手动锁定）。
- `yunhe_default` 不允许携带 locked_agent_id 或 news_id。
- 非归属会话统一 404。
