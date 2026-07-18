"""会话模式相关的类型与数据结构。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# 全部会话模式：包含内部使用的 news_analysis_locked。
SessionMode = Literal["yunhe_default", "agent_locked", "news_analysis_locked"]

# 用户 API 可设置的模式：news_analysis_locked 只能由新闻分析服务在内部创建。
UserSessionMode = Literal["yunhe_default", "agent_locked"]


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
