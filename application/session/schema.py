"""会话模式相关的类型与数据结构。

P7 引入：``SessionMode`` / ``UserSessionMode`` 由 ``domain.user.session.modes``
定义，本模块重新导出以保持向后兼容（``application.session`` 历史调用方不变）。
新代码应直接 ``from domain.user.session.modes import SessionMode``。
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.user.session.modes import SessionMode, UserSessionMode

__all__ = ["SessionMode", "UserSessionMode", "SessionRecord"]


@dataclass(frozen=True)
class SessionRecord:
    """持久化的会话模式记录。

    所有用户拥有的资源在应用服务层执行对象级授权；未授权统一返回 404。
    `locked_agent_id` 在 ``agent_locked`` 模式下指向用户选择的子 Agent，
    在 ``news_analysis_locked`` 模式下固定为 ``"news"``。
    `news_id` 仅在 ``news_analysis_locked`` 模式下非空，作为新闻研判锚点。
    """

    session_id: str
    user_id: str
    mode: SessionMode
    locked_agent_id: str | None
    news_id: str | None
