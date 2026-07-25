# domain/feedback/ — 模块记忆

## 职责定位
对话质量反馈领域层：持久化 👍/👎 评分与质量问题，作为产品迭代数据来源。

## 关键文件
- `repository.py`：`FeedbackRepository`——建表并持久化 `quality_issues`（rating、issue_type、comment、agent_id、message_snippet 等）；提供记录、按用户列出、按评分计数。
- `__init__.py`：包占位。

## 业务边界要点
- 评分枚举：`good`/`bad`；问题类型：`inaccurate`/`tool_error`/`delegation_error`/`other`。
- `message_snippet` 截断至 500 字符入库。

## 技术债
⚠️ 直接 `from infrastructure.persistence.database import get_connection` 建表读写，违反 domain 分层约束。
