from __future__ import annotations
import logging
from collections.abc import AsyncGenerator

from domain.agent.travel_core import Agent
from domain.agent.base import BaseAgent

logger = logging.getLogger(__name__)


class TravelAgent(BaseAgent):
    """旅行规划智能体 — 包装现有 Agent，附加操作建议。

    现有 Agent 的所有旅游逻辑、工具、记忆、Prompt 全部保留。
    本类只做两件事：
    1. 委托 chat/chat_stream 给现有 Agent
    2. 从回复中提取行程 ID，生成"进入行程规划"的跳转建议

    【商用注意】行程 ID 提取不应依赖正则匹配自由文本（脆弱、易误匹配）。
    正确做法是让底层 Agent 在生成行程后，通过结构化字段返回 itinerary_id，
    而不是从回复文本中正则提取。本类提供两种方案的过渡实现：
    - 优先读取 result 中的结构化字段（result["itinerary_id"]）
    - 兜底用正则（仅作为过渡，后续应废弃）
    """

    def __init__(self, agent: Agent) -> None:
        self._agent = agent

    def __getattr__(self, name: str):
        """委托未定义的公共方法到底层 Agent（会话/调试/记忆等），保持向后兼容。"""
        if name.startswith('_'):
            raise AttributeError(name)
        return getattr(self._agent, name)

    @property
    def name(self) -> str:
        return "travel"

    @property
    def description(self) -> str:
        return (
            "旅行规划助手。处理行程规划、景点推荐、机票酒店搜索、"
            "地图导航、花费统计、相册管理、旅行记忆等所有旅行相关需求。"
        )

    def _extract_actions(self, reply: str, structured_data: dict | None = None) -> list[dict]:
        """从回复中提取行程 ID，生成跳转建议。

        优先使用结构化数据（商用推荐），兜底用正则（过渡方案）。
        """
        actions = []
        itinerary_id = None

        # 方案 1（推荐）：从结构化字段获取 — 需要底层 Agent 配合
        if structured_data and structured_data.get("itinerary_id"):
            itinerary_id = structured_data["itinerary_id"]

        # 方案 2（过渡兜底）：从文本中正则提取 — TODO 后期废弃
        if not itinerary_id:
            import re
            # 仅在明确包含"行程概览已生成"等关键词时才提取，降低误匹配
            if '行程概览已生成' in reply or 'itinerary_id' in reply:
                match = re.search(r'([a-f0-9]{16})', reply, re.IGNORECASE)
                if match:
                    itinerary_id = match.group(1)

        if itinerary_id:
            actions.append({
                "type": "navigate",
                "label": "进入完整行程规划",
                "path": f"/agent/travel/itinerary/{itinerary_id}",
                "agent": "travel",
                "description": "查看地图、编辑行程、管理花费、上传相册",
            })

        return actions

    async def chat(self, *, session_id: str, message: str, user_id: str | None = None, **kwargs) -> dict:
        result = await self._agent.chat(session_id=session_id, message=message, user_id=user_id)

        # 附加激活态和操作建议
        result["active_agent"] = "travel"
        result["agent_actions"] = self._extract_actions(
            result.get("reply", ""),
            structured_data=result,  # 传入完整 result，提取结构化字段
        )

        return result

    async def chat_stream(self, *, session_id: str, message: str, user_id: str | None = None, **kwargs) -> AsyncGenerator[dict, None]:
        # 先发路由事件
        yield {"type": "route", "data": "travel"}

        # 委托流式输出
        reply_text = ""
        async for event in self._agent.chat_stream(session_id=session_id, message=message, user_id=user_id):
            yield event
            if event.get("type") == "chunk":
                reply_text += event.get("data", "")

        # 流结束后发操作建议
        actions = self._extract_actions(reply_text)
        if actions:
            yield {"type": "actions", "data": actions}
