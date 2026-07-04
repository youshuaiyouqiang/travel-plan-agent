from __future__ import annotations
import logging
from collections.abc import AsyncGenerator

from domain.travel.core import Agent
from domain.agent.base import BaseAgent

logger = logging.getLogger(__name__)


class TravelAgent(BaseAgent):
    """旅行规划智能体 — 包装现有 Agent，附加操作建议。

    现有 Agent 的所有旅游逻辑、工具、记忆、Prompt 全部保留。
    本类只做三件事：
    1. 委托 chat/chat_stream 给现有 Agent
    2. 从回复中提取行程 ID，生成"进入行程规划"的跳转建议
    3. 自动注入多方案锚点（不依赖 LLM，保障前端渲染）

    【商用注意】行程 ID 提取不应依赖正则匹配自由文本（脆弱、易误匹配）。
    正确做法是让底层 Agent 在生成行程后，通过结构化字段返回 itinerary_id，
    而不是从回复文本中正则提取。本类提供两种方案的过渡实现：
    - 优先读取 result 中的结构化字段（result["itinerary_id"]）
    - 兜底用正则（仅作为过渡，后续应废弃）
    """

    # ★ 多方案锚点常量 — 后端保障注入，不依赖 LLM
    _MULTI_PLAN_ANCHOR = "<!--MULTI_PLAN:plan1=sightseeing,plan2=budget-->"
    _SINGLE_PLAN_ANCHOR = "<!--MULTI_PLAN:plan1=sightseeing-->"
    # 检测多方案的信号词
    _PLAN2_SIGNALS = ["方案二", "经济实惠", "方案2", "省钱方案"]
    _PLAN1_SIGNALS = ["方案一", "景点打卡", "方案1"]

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

    @classmethod
    def _inject_multi_plan_anchor(cls, reply: str) -> str:
        """后端保障注入多方案锚点。

        不依赖 LLM 遵循锚点注入指令——检测回复中的方案信号词，
        自动在末尾追加锚点。如果 LLM 已注入则不重复。
        """
        # 已有锚点则跳过
        if "<!--MULTI_PLAN:" in reply:
            return reply

        # 必须包含方案一才注入（否则不是行程方案回复）
        has_plan1 = any(sig in reply for sig in cls._PLAN1_SIGNALS)
        if not has_plan1:
            return reply

        has_plan2 = any(sig in reply for sig in cls._PLAN2_SIGNALS)
        # 注入锚点（独占一行，放在回复最末尾）
        anchor = cls._MULTI_PLAN_ANCHOR if has_plan2 else cls._SINGLE_PLAN_ANCHOR
        return reply.rstrip() + "\n" + anchor

    def _extract_actions(self, reply: str, structured_data: dict | None = None) -> list[dict]:
        """从回复中提取行程 ID，生成跳转建议。

        优先使用结构化数据（商用推荐），兜底用正则（过渡方案）。
        支持多方案 plan_type 标记。
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
            # ★ 提取 plan_type，用于前端展示方案标签
            plan_type = ""
            if structured_data:
                plan_type = str(structured_data.get("plan_type", ""))

            action: dict = {
                "type": "navigate",
                "label": "进入完整行程规划",
                "path": f"/agent/travel/itinerary/{itinerary_id}",
                "agent": "travel",
                "description": "查看地图、编辑行程、管理花费、上传相册",
            }
            if plan_type:
                action["plan_type"] = plan_type
            actions.append(action)

        return actions

    async def chat(self, *, session_id: str, message: str, user_id: str | None = None, **kwargs) -> dict:
        result = await self._agent.chat(session_id=session_id, message=message, user_id=user_id)

        # ★ 后端保障注入多方案锚点
        reply = result.get("reply", "")
        reply_with_anchor = self._inject_multi_plan_anchor(reply)
        if reply_with_anchor != reply:
            result["reply"] = reply_with_anchor

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

        # 委托流式输出，同时从 done event 中提取结构化 itinerary_id（P1-13）
        reply_text = ""
        structured_itinerary_id: str | None = None
        got_done = False
        async for event in self._agent.chat_stream(session_id=session_id, message=message, user_id=user_id):
            # 拦截 done 事件，在锚点注入后再发射
            if event.get("type") == "done":
                got_done = True
                data = event.get("data")
                if isinstance(data, dict):
                    structured_itinerary_id = data.get("itinerary_id") or None
                # 先不发 done，等锚点注入
                continue
            yield event
            if event.get("type") == "chunk":
                reply_text += event.get("data", "")

        # ★ 后端保障注入多方案锚点（通过额外的 chunk 事件发送）
        anchor_to_inject = self._inject_multi_plan_anchor(reply_text)
        if anchor_to_inject != reply_text:
            # 锚点被追加了，把增量发出去
            added = anchor_to_inject[len(reply_text):]
            if added:
                yield {"type": "chunk", "data": added}
                reply_text = anchor_to_inject

        # 现在发 done 事件
        if got_done:
            yield {"type": "done", "data": "completed"}

        # 流结束后发操作建议：优先用结构化 itinerary_id，避免正则误匹配
        structured_data = {"itinerary_id": structured_itinerary_id} if structured_itinerary_id else None
        actions = self._extract_actions(reply_text, structured_data=structured_data)
        if actions:
            yield {"type": "actions", "data": actions}
