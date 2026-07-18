"""会话模式持久化与应用服务。

Task 1 (计划 2026-07-17-platform-and-routing) 引入的会话模式：
- ``yunhe_default``：默认云合调度，每轮最多委派一个 Agent。
- ``agent_locked``：用户主动锁定的子 Agent 会话。
- ``news_analysis_locked``：仅由新闻分析服务在内部创建的研判锚点会话。
"""

from application.session.schema import SessionMode, SessionRecord, UserSessionMode
from application.session.service import SessionService

__all__ = [
    "SessionMode",
    "SessionRecord",
    "SessionService",
    "UserSessionMode",
]
