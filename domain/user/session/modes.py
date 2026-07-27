"""会话模式枚举 — P7 从 ``application.session.schema`` 迁移到 domain 层。

迁移原因：``domain.agent.orchestrator`` 之前 ``from application.session.schema import SessionMode``，
违反 ``domain_no_application`` 架构规则。会话模式是核心领域概念（描述会话与子 Agent 的关系），
必须由 domain 定义；application 层可重新导出但不得拥有。
"""

from __future__ import annotations

from typing import Literal

# 全部会话模式：包含内部使用的 news_analysis_locked。
SessionMode = Literal["yunhe_default", "agent_locked", "news_analysis_locked"]

# 用户 API 可设置的模式：news_analysis_locked 只能由新闻分析服务在内部创建。
UserSessionMode = Literal["yunhe_default", "agent_locked"]
