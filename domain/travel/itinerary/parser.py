from __future__ import annotations

import json
import logging
import re
from typing import Any

from infrastructure.llm.openai import OpenAILLM
from domain.travel.itinerary.schema import Itinerary, DayPlan, Activity

logger = logging.getLogger(__name__)

_PARSE_SYSTEM_PROMPT = """你是一个旅行行程解析器。你的任务是将用户提供的旅行行程文本解析为结构化的JSON数据。

严格按照以下格式输出，不要输出任何其他内容：

```json
{
  "title": "行程标题，如：成都5日游",
  "destination": "目的地城市",
  "start_date": "开始日期，格式YYYY-MM-DD",
  "end_date": "结束日期，格式YYYY-MM-DD",
  "budget": "预算概要，如：约5000元/人",
  "days": [
    {
      "date": "日期，格式YYYY-MM-DD",
      "title": "当日主题，如：初识成都·宽窄巷子",
      "summary": "当日行程概要，30字以内",
      "activities": [
        {
          "time_slot": "时间段，如：09:00-11:00",
          "title": "活动名称，如：宽窄巷子漫步",
          "location": "具体地点，如：成都市青羊区宽窄巷子",
          "description": "活动描述，50字以内",
          "image_url": "",
          "cost": 0,
          "tips": "实用小贴士，20字以内"
        }
      ]
    }
  ]
}
```

注意：
1. 每个活动的时间段要合理，不要重叠
2. cost字段为数字，单位为元，0表示免费或未知
3. image_url留空，由系统后续填充
4. tips要实用，如"建议早到避开人流"、"需提前预约"等
5. 只输出JSON，不要输出任何解释文字"""


class ItineraryParser:
    def __init__(self, llm: OpenAILLM | None = None) -> None:
        self._llm = llm or OpenAILLM()

    async def parse(
        self,
        raw_content: str,
        user_id: str = "",
        session_id: str = "",
    ) -> Itinerary | None:
        try:
            result = await self._llm.complete_json(
                system=_PARSE_SYSTEM_PROMPT,
                user=f"请解析以下旅行行程：\n\n{raw_content}",
            )
        except Exception:
            logger.warning("Itinerary parsing LLM call failed", exc_info=True)
            return None

        if not result or "days" not in result:
            logger.warning("Itinerary parsing returned invalid result: %s", str(result)[:200])
            return None

        try:
            return self._build_itinerary(result, user_id, session_id, raw_content)
        except Exception:
            logger.warning("Failed to build itinerary from parsed result", exc_info=True)
            return None

    def _build_itinerary(
        self,
        data: dict[str, Any],
        user_id: str,
        session_id: str,
        raw_content: str,
    ) -> Itinerary:
        days = []
        for di, day_data in enumerate(data.get("days", [])):
            activities = []
            for ai, act_data in enumerate(day_data.get("activities", [])):
                act = Activity(
                    activity_index=ai,
                    time_slot=str(act_data.get("time_slot", "")),
                    title=str(act_data.get("title", "")),
                    location=str(act_data.get("location", "")),
                    description=str(act_data.get("description", "")),
                    image_url=str(act_data.get("image_url", "")),
                    cost=float(act_data.get("cost", 0)),
                    tips=str(act_data.get("tips", "")),
                )
                activities.append(act)
            day = DayPlan(
                day_index=di,
                date=str(day_data.get("date", "")),
                title=str(day_data.get("title", "")),
                summary=str(day_data.get("summary", "")),
                activities=activities,
            )
            days.append(day)

        return Itinerary(
            user_id=user_id,
            session_id=session_id,
            title=str(data.get("title", "")),
            destination=str(data.get("destination", "")),
            start_date=str(data.get("start_date", "")),
            end_date=str(data.get("end_date", "")),
            budget=str(data.get("budget", "")),
            raw_content=raw_content,
            status="confirmed",
            days=days,
        )

    @staticmethod
    def parse_simple(raw_content: str) -> Itinerary | None:
        lines = raw_content.strip().split("\n")
        title = ""
        destination = ""
        days: list[DayPlan] = []
        current_day: DayPlan | None = None
        day_index = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            day_match = re.match(
                r"(?:第\s*[一二三四五六七八九十\d]+\s*天|Day\s*\d+)[：:.\s]*(.*)",
                stripped,
                re.IGNORECASE,
            )
            if day_match:
                if current_day:
                    days.append(current_day)
                current_day = DayPlan(
                    day_index=day_index,
                    title=stripped,
                    summary=day_match.group(1).strip()[:30],
                )
                day_index += 1
                continue

            act_match = re.match(
                r"(?:(\d{1,2}:\d{2})\s*[-–—~至到]\s*(\d{1,2}:\d{2})\s*[：:.\s]*)?(.+)",
                stripped,
            )
            if act_match and current_day:
                time_start = act_match.group(1) or ""
                time_end = act_match.group(2) or ""
                time_slot = f"{time_start}-{time_end}" if time_start else ""
                act_title = act_match.group(3).strip()
                if len(act_title) > 2:
                    act = Activity(
                        activity_index=len(current_day.activities),
                        time_slot=time_slot,
                        title=act_title[:50],
                    )
                    current_day.activities.append(act)

            if not title and ("行程" in stripped or "旅游" in stripped or "游" in stripped):
                title = stripped[:30]

            if not destination:
                dest_match = re.search(
                    r"(?:去|到|前往)\s*([^\s,，。！？、]+?)(?:旅游|玩|出差|度假|吧|呢|的)",
                    stripped,
                )
                if dest_match:
                    destination = dest_match.group(1).strip()
                else:
                    dest_match2 = re.search(
                        r"^([\u4e00-\u9fff]{2,4}?)(?:旅游|行程|攻略|自由行)",
                        stripped,
                    )
                    if dest_match2:
                        destination = dest_match2.group(1).strip()

        if current_day:
            days.append(current_day)

        if not days:
            return None

        return Itinerary(
            title=title or "旅行行程",
            destination=destination,
            days=days,
            status="planning",
            raw_content=raw_content,
        )
