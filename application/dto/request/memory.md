# application/dto/request/ — 模块记忆

## 职责定位
所有 API 请求体的 Pydantic 校验模型，按资源域分文件。

## 关键文件
- `agent.py`：创建/更新自定义 Agent。
- `auth.py`：注册/登录请求。
- `chat.py`：聊天请求（不含 user_id/agent_id，身份由服务端认证上下文决定）。
- `feedback.py`：反馈评分（rating 与 issue_type 限枚举）。
- `geocode.py`：批量/国际地理编码请求。
- `itinerary.py`：行程增改/确认/分享。
- `news.py`：新闻收藏（红线：不存全文，仅元数据）。
- `travel.py`：草稿创建/编辑/应用提议（`extra="forbid"` 防注入）。
- `__init__.py`：聚合导出。

## 业务边界要点
- 多处 `extra="forbid"`：拒绝未声明字段，防止客户端注入 user_id、locked_agent_id 等敏感参数。
- 新闻收藏 DTO 明确不接收新闻正文字段。
