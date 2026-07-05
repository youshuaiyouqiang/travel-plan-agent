from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from domain.travel.intent.travel_schema import (
    TravelIntentType,
    INTENT_TOOL_HINTS,
    INTENT_RAG_KEYWORDS,
)
from infrastructure.llm.openai import OpenAILLM

logger = logging.getLogger(__name__)

_TRAVEL_PATTERNS: dict[TravelIntentType, list[str]] = {
    TravelIntentType.TRIP_PLANNING: [
        "想去",
        "计划去",
        "帮我规划",
        "行程",
        "几天",
        "旅游攻略",
        "怎么安排",
        "旅行计划",
        "出游",
        "度假",
        "出发地",
        "目的地",
        "出发日期",
        "返程",
        "人数",
        "成人",
        "老人",
        "儿童",
        "总预算",
        "偏好",
        "日游",
        "天行程",
        "晚行程",
    ],
    TravelIntentType.DESTINATION_SEARCH: [
        "去哪玩",
        "推荐目的地",
        "适合去哪",
        "有什么好玩的",
        "旅游地点",
        "景点推荐",
        "小众目的地",
    ],
    TravelIntentType.FLIGHT_SEARCH: [
        "机票",
        "航班",
        "飞机",
        "特价机票",
        "直飞",
        "转机",
        "廉价航空",
        "机票价格",
    ],
    TravelIntentType.HOTEL_SEARCH: [
        "酒店",
        "住宿",
        "民宿",
        "旅馆",
        "住哪",
        "青旅",
        "度假村",
        "公寓",
    ],
    TravelIntentType.ATTRACTION_SEARCH: [
        "景点",
        "打卡",
        "必去",
        "网红",
        "地标",
        "博物馆",
        "主题公园",
        "自然风光",
    ],
    TravelIntentType.WEATHER_CHECK: [
        "天气",
        "气温",
        "下雨",
        "穿什么",
        "冷不冷",
        "热不热",
        "防晒",
        "雨季",
    ],
    TravelIntentType.BUDGET_CALC: [
        "预算",
        "花费",
        "多少钱",
        "费用",
        "贵不贵",
        "穷游",
        "性价比",
        "人均",
    ],
    TravelIntentType.ITINERARY_ADJUST: [
        "改行程",
        "换计划",
        "调整",
        "取消",
        "延期",
        "改签",
        "退订",
        "不满意",
        "不太满意",
        "换个方案",
        "重新规划",
        "重新安排",
        "换一个",
        "不好",
    ],
    TravelIntentType.ITINERARY_CONFIRM: [
        "满意",
        "就这样",
        "确认",
        "没问题",
        "好的就这样",
        "ok",
        "OK",
        "确认行程",
        "生成概览",
        "生成行程概览",
    ],
    TravelIntentType.VISA_INFO: [
        "签证",
        "护照",
        "入境",
        "免签",
        "落地签",
        "签证材料",
        "签证费用",
    ],
    TravelIntentType.FOOD_RECOMMEND: [
        "美食",
        "餐厅",
        "小吃",
        "吃什么",
        "特色菜",
        "米其林",
        "夜市",
        "当地美食",
    ],
    TravelIntentType.TRAVEL_TIPS: [
        "注意事项",
        "避坑",
        "贴士",
        "攻略",
        "禁忌",
        "安全",
        "防骗",
    ],
    TravelIntentType.CURRENCY_CONVERT: [
        "汇率",
        "换汇",
        "货币",
        "人民币",
        "美元",
        "欧元",
        "日元",
        "泰铢",
    ],
    TravelIntentType.TRAVEL_COMPANION: [
        "结伴",
        "同行",
        "拼团",
        "找人",
        "一起",
        "组队",
    ],
    TravelIntentType.EMERGENCY_HELP: [
        "紧急",
        "求助",
        "丢失",
        "被盗",
        "大使馆",
        "报警",
        "急救",
        "领事馆",
    ],
}

_TRAVEL_CLASSIFY_SYSTEM = """你是智能旅行规划助手的意图分类器。
分析用户的旅行请求，返回严格 JSON：
{
  "intent": "意图类型（见下方列表）",
  "goal": "用户目标的简洁描述",
  "confidence": 0.0-1.0,
  "rag_keywords": ["用于知识库检索的关键词（最多3个）"],
  "modification_scope": "local_reorder|partial_research|full_research|",
  "affected_categories": ["hotel|poi|flight|train|route|weather"],
  "target_plan": "plan1|plan2|"
}
意图类型列表：
- trip_planning: 整体行程规划（包含多天安排）
- destination_search: 目的地推荐和搜索
- flight_search: 机票/航班查询
- hotel_search: 酒店/住宿搜索
- attraction_search: 景点/打卡地搜索
- weather_check: 天气/气候查询
- budget_calc: 预算/费用计算
- itinerary_adjust: 行程调整/改签
- itinerary_confirm: 用户确认满意当前行程方案（如"满意""可以""确认""就这样""没问题"等肯定回复）
- visa_info: 签证/入境信息
- food_recommend: 美食/餐厅推荐
- travel_tips: 旅行注意事项/攻略
- currency_convert: 汇率/货币换算
- travel_companion: 结伴/拼团
- emergency_help: 紧急求助
- general_chat: 闲聊/其他

当 intent 为 itinerary_adjust 时，额外返回以下字段：
- modification_scope: 修改范围判断
  - "local_reorder": 仅调整行程安排，不需要重新搜索。例："太赶了""轻松一点""第一天和第二天换一下""少去一个景点"
  - "partial_research": 需要重新搜索特定类别，但其他数据不变。例："酒店便宜点"→ hotel / "换个景点"→ poi / "能坐飞机去吗"→ flight
  - "full_research": 核心参数变了（出发地/目的地/日期/天数/人数），所有数据需重搜。例："改到下周出发""不去成都了去重庆""玩5天不是3天"
  - 如果不是 itinerary_adjust 意图，modification_scope 设为空字符串
- affected_categories: 受影响的类别列表（如 ["hotel"]、["flight", "hotel"]）
  如果 modification_scope 为 "full_research"，affected_categories 可为空数组
- target_plan: 被修改的是哪个方案
  - "plan1": 方案一（景点打卡型）
  - "plan2": 方案二（经济实惠型）
  - "": 无法确定或两个都要改

规则：
- 涉及多天安排 → trip_planning
- 明确问机票/航班 → flight_search
- 问去哪玩/推荐 → destination_search
- 用户对已生成的行程表示满意、确认、肯定 → itinerary_confirm
- ⚠️【极其重要】用户只是在回答问题或确认某个参数（如"是的，从南昌出发""对，3个人""好的，6月5号"），不是在确认行程方案！这些应归类为 trip_planning，绝对不能归类为 itinerary_confirm！只有当助手已经生成了完整的文字行程方案并询问"您满意吗"之后，用户回复"满意""可以""就这样"等，才是 itinerary_confirm
- 用户想修改行程 → itinerary_adjust
- ⚠️【极其重要】用户表示不满意、需要调整、想换方案（如"不满意""不太满意""需要调整""换个方案""重新规划"），应归类为 itinerary_adjust，绝对不能归类为 budget_calc 或其他意图！
- 仅输出 JSON"""


@dataclass
class TravelIntentResult:
    intent: TravelIntentType
    goal: str
    confidence: float = 0.5
    tool_hints: list[str] = field(default_factory=list)
    rag_keywords: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)
    detected_destination: str = ""
    raw_output: str = ""
    # ★ 多方案修改元数据
    modification_scope: str = ""  # "local_reorder" | "partial_research" | "full_research" | ""
    affected_categories: list[str] = field(default_factory=list)  # ["hotel", "poi"] 等
    target_plan: str = ""  # "plan1" | "plan2" | ""


def _extract_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned.strip())
    except Exception:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except Exception:
                return {}
        else:
            return {}
    return data if isinstance(data, dict) else {}


class TravelIntentClassifier:
    def __init__(self, llm: OpenAILLM | None = None) -> None:
        self._llm = llm

    _FAST_CHAT = {"你好", "hello", "hi", "谢谢", "thanks", "收到", "嗯", "哦", "哈", "嘿"}

    async def classify(
        self, message: str, conversation_history: list[dict[str, str]] | None = None
    ) -> TravelIntentResult:
        stripped = message.strip().lower()
        if stripped in self._FAST_CHAT or len(stripped) <= 1:
            return TravelIntentResult(
                intent=TravelIntentType.GENERAL_CHAT,
                goal=message[:100],
                confidence=0.9,
                tool_hints=[],
                rag_keywords=[],
                missing_info=[],
                detected_destination="",
            )

        keyword_result = self._keyword_classify(message, conversation_history)
        # P2-10：阈值 0.7 → 0.85，降低关键词误判为旅行意图的概率。
        if keyword_result and keyword_result.confidence >= 0.85:
            return keyword_result

        if self._llm is None:
            return keyword_result or TravelIntentResult(
                intent=TravelIntentType.GENERAL_CHAT,
                goal=message[:100],
                confidence=0.3,
            )

        try:
            text = await self._llm.complete(
                system=_TRAVEL_CLASSIFY_SYSTEM,
                messages=[{"role": "user", "content": message}],
            )
            data = _extract_json(text)
        except Exception:
            return keyword_result or TravelIntentResult(
                intent=TravelIntentType.GENERAL_CHAT,
                goal=message[:100],
                confidence=0.3,
            )

        try:
            intent = TravelIntentType(data.get("intent", "general_chat"))
        except ValueError:
            intent = TravelIntentType.GENERAL_CHAT

        return TravelIntentResult(
            intent=intent,
            goal=str(data.get("goal", message[:100])),
            confidence=float(data.get("confidence", 0.5)),
            tool_hints=INTENT_TOOL_HINTS.get(intent, []),
            rag_keywords=data.get("rag_keywords", INTENT_RAG_KEYWORDS.get(intent, [])),
            missing_info=self._check_missing_info(message, intent, conversation_history),
            detected_destination=self._extract_destination(message),
            raw_output=text,
            # ★ 多方案修改元数据
            modification_scope=str(data.get("modification_scope", "")),
            affected_categories=[str(c) for c in data.get("affected_categories", [])],
            target_plan=str(data.get("target_plan", "")),
        )

    _CONFIRM_KEYWORDS = {"满意", "就这样", "确认", "没问题", "好的就这样", "ok", "OK", "确认行程"}
    _CONFIRM_EXACT = {"行", "可以", "好的", "是的", "没错"}
    _NEGATION_WORDS = {"不太满意", "不满意", "不好", "不行", "不可以", "不太行", "不够好"}

    def _keyword_classify(
        self, message: str, conversation_history: list[dict[str, str]] | None = None
    ) -> TravelIntentResult | None:
        lowered = message.lower()
        stripped = message.strip()

        has_negation = any(neg in stripped for neg in self._NEGATION_WORDS)

        if len(stripped) <= 10 and not has_negation:
            is_confirm = False
            for kw in self._CONFIRM_KEYWORDS:
                if kw in stripped.lower():
                    is_confirm = True
                    break
            if not is_confirm and stripped.strip() in self._CONFIRM_EXACT:
                is_confirm = True
            if is_confirm:
                return TravelIntentResult(
                    intent=TravelIntentType.ITINERARY_CONFIRM,
                    goal=message[:100],
                    confidence=0.85,
                    tool_hints=INTENT_TOOL_HINTS.get(TravelIntentType.ITINERARY_CONFIRM, []),
                    rag_keywords=INTENT_RAG_KEYWORDS.get(TravelIntentType.ITINERARY_CONFIRM, []),
                    missing_info=[],
                    detected_destination="",
                )

        best_intent: TravelIntentType | None = None
        best_count = 0
        matched: list[str] = []

        for intent_type, keywords in _TRAVEL_PATTERNS.items():
            matches = [kw for kw in keywords if kw in lowered]
            effective_count = len(matches)
            if intent_type == TravelIntentType.ITINERARY_CONFIRM and effective_count > 0:
                if has_negation:
                    effective_count = 0
                else:
                    effective_count += 2
            if effective_count > best_count:
                best_count = effective_count
                best_intent = intent_type
                matched = matches

        if best_intent is None or best_count == 0:
            return None

        confidence = min(0.6 + len(matched) * 0.15, 0.95)

        return TravelIntentResult(
            intent=best_intent,
            goal=message[:100],
            confidence=confidence,
            tool_hints=INTENT_TOOL_HINTS.get(best_intent, []),
            rag_keywords=INTENT_RAG_KEYWORDS.get(best_intent, []),
            missing_info=self._check_missing_info(message, best_intent, conversation_history),
            detected_destination=self._extract_destination(message),
        )

    def _check_missing_info(
        self, message: str, intent: TravelIntentType, conversation_history: list[dict[str, str]] | None = None
    ) -> list[str]:
        return self._regex_missing_info(message, intent, conversation_history=conversation_history)

    async def check_missing_info_with_context(
        self,
        message: str,
        intent: TravelIntentType,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> list[str]:
        if self._llm is None:
            return self._regex_missing_info(message, intent)

        if not conversation_history:
            conversation_history = [{"role": "user", "content": message}]

        required_fields = {
            TravelIntentType.TRIP_PLANNING: ["destination", "duration", "dates"],
            TravelIntentType.FLIGHT_SEARCH: ["origin", "destination", "dates"],
            TravelIntentType.HOTEL_SEARCH: ["destination", "dates"],
            TravelIntentType.ATTRACTION_SEARCH: ["destination"],
            TravelIntentType.WEATHER_CHECK: ["destination"],
            TravelIntentType.BUDGET_CALC: ["destination", "duration"],
        }

        fields = required_fields.get(intent, [])
        if not fields:
            return []

        field_labels = {
            "destination": "目的地",
            "origin": "出发地",
            "duration": "旅行天数",
            "dates": "出发日期",
            "budget": "预算",
        }
        field_desc = "、".join(field_labels.get(f, f) for f in fields)

        system = (
            "你是旅行信息完整性检查器。根据对话历史判断用户是否已提供所有必要信息。\n"
            f"需要检查的字段：{field_desc}\n"
            "仅返回 JSON：\n"
            "{\n"
            '  "missing": ["缺失的字段名列表"],\n'
            '  "reasoning": "简短判断理由"\n'
            "}\n"
            "规则：\n"
            "- 中文数字也算（三天=3天，五日=5天）\n"
            "- 相对时间也算（下个月、下周、五一、暑假）\n"
            "- 对话历史中提到的信息也算已提供\n"
            "- 如果信息足够，返回空列表\n"
            "- 仅输出 JSON"
        )

        history_text = "\n".join(
            f"{turn.get('role', 'user')}: {turn.get('content', '')}" for turn in conversation_history[-6:]
        )

        # 正则检查作为回退基准，LLM 失败时返回正则结果
        regex_fallback = self._regex_missing_info(message, intent, conversation_history=conversation_history)

        try:
            text = await self._llm.complete(
                system=system,
                messages=[{"role": "user", "content": f"对话历史：\n{history_text}\n\n请检查缺失信息。"}],
            )
            data = _extract_json(text)
            missing = data.get("missing", [])
            result = [str(m) for m in missing if str(m) in fields]
            logger.info(
                "LLM missing_info check: fields=%s missing=%s reasoning=%s", fields, result, data.get("reasoning", "")
            )
            return result
        except Exception as e:
            logger.warning("LLM missing_info check failed, falling back to regex: %s", e)
            return regex_fallback

    _DESTINATION_PATTERNS = [
        r"(?:去|到|飞|前往)\s*([^\s,，。！？、]+?)(?:旅游|玩|出差|度假|吧|呢|啊|。|，|$)",
        r"(?:目的地|去的地方|想去)\s*(?:是|:|：)?\s*([^\s,，。！？、]+)",
    ]

    _KNOWN_DESTINATIONS = {
        "云南",
        "昆明",
        "大理",
        "丽江",
        "西双版纳",
        "香格里拉",
        "北京",
        "上海",
        "广州",
        "深圳",
        "成都",
        "杭州",
        "南京",
        "武汉",
        "西安",
        "重庆",
        "长沙",
        "厦门",
        "三亚",
        "海口",
        "桂林",
        "阳朔",
        "西藏",
        "拉萨",
        "新疆",
        "乌鲁木齐",
        "青岛",
        "大连",
        "苏州",
        "黄山",
        "九寨沟",
        "张家界",
        "凤凰古城",
        "峨眉山",
        "稻城亚丁",
        "泰国",
        "日本",
        "韩国",
        "新加坡",
        "马来西亚",
        "越南",
        "巴厘岛",
        "马尔代夫",
        "普吉岛",
        "东京",
        "大阪",
        "京都",
        "首尔",
        "曼谷",
    }

    def _extract_destination(self, message: str) -> str:
        for dest in self._KNOWN_DESTINATIONS:
            if dest in message:
                return dest

        for pattern in self._DESTINATION_PATTERNS:
            match = re.search(pattern, message)
            if match:
                candidate = match.group(1).strip()
                if candidate and len(candidate) <= 10:
                    return candidate

        return ""

    def _regex_missing_info(
        self, message: str, intent: TravelIntentType, conversation_history: list[dict[str, str]] | None = None
    ) -> list[str]:
        combined = message
        if conversation_history:
            # 拼接历史消息和当前消息，确保当前消息的内容也被检查
            combined = " ".join(turn.get("content", "") for turn in conversation_history) + " " + message
        compacted = re.sub(r"(\d)\s+(天|日|号|月|晚|人)", r"\1\2", combined)
        missing: list[str] = []
        if intent == TravelIntentType.TRIP_PLANNING:
            if not re.search(
                r"去|到|飞|前往|云南|北京|上海|成都|三亚|西藏|新疆|杭州|西安|厦门|桂林|丽江|大理|昆明|西双版纳|香格里拉|目的地",
                compacted,
            ):
                missing.append("destination")
            if not re.search(
                r"从|出发|南京|北京|上海|广州|深圳|成都|杭州|合肥|武汉|长沙|重庆|昆明|厦门|青岛|大连|苏州", compacted
            ):
                missing.append("origin")
            if not re.search(r"\d+天|[一两三四五六七八九十]+天|几天|多久|日游|\d+晚", compacted):
                missing.append("duration")
            if not re.search(
                r"\d+月|\d+号|\d+日|什么时候|何时|下周|下月|五一|十一|暑假|寒假|春节|国庆|出发日期|日期|明天|后天|大后天|这周末|本周末|下周末|今天|今晚",
                compacted,
            ):
                missing.append("dates")
        elif intent == TravelIntentType.FLIGHT_SEARCH:
            if not re.search(r"从|出发|南京|北京|上海|广州|深圳|成都|杭州|合肥", compacted):
                missing.append("origin")
            if not re.search(r"到|去|飞|前往|云南|昆明|三亚|成都|西安|杭州", compacted):
                missing.append("destination")
            if not re.search(
                r"\d+月|\d+号|\d+日|什么时候|何时|下周|下月|出发日期|明天|后天|大后天|这周末|本周末|下周末|今天|今晚",
                compacted,
            ):
                missing.append("dates")
        elif intent == TravelIntentType.HOTEL_SEARCH:
            if not re.search(r"去|到|在|云南|昆明|三亚|成都|西安|杭州", compacted):
                missing.append("destination")
            if not re.search(
                r"\d+月|\d+号|\d+日|什么时候|何时|入住|下周|下月|出发日期|明天|后天|大后天|这周末|本周末|下周末|今天|今晚",
                compacted,
            ):
                missing.append("dates")
        elif intent == TravelIntentType.ATTRACTION_SEARCH:
            if not re.search(r"去|到|在|云南|昆明|三亚|成都|西安", combined):
                missing.append("destination")
        elif intent == TravelIntentType.WEATHER_CHECK:
            if not re.search(r"去|到|在|云南|昆明|三亚|成都|西安", combined):
                missing.append("destination")
        elif intent == TravelIntentType.BUDGET_CALC:
            if not re.search(r"去|到|飞|前往|云南|昆明|三亚|成都|西安", combined):
                missing.append("destination")
            if not re.search(r"\d+天|[一两三四五六七八九十]+天|几天|多久", combined):
                missing.append("duration")
        return missing

    def to_intent_result(self, result: TravelIntentResult) -> Any:
        from domain.shared.types import IntentResult, IntentType

        mapping: dict[TravelIntentType, IntentType] = {
            TravelIntentType.TRIP_PLANNING: IntentType.TASK,
            TravelIntentType.DESTINATION_SEARCH: IntentType.TASK,
            TravelIntentType.FLIGHT_SEARCH: IntentType.TASK,
            TravelIntentType.HOTEL_SEARCH: IntentType.TASK,
            TravelIntentType.ATTRACTION_SEARCH: IntentType.TASK,
            TravelIntentType.WEATHER_CHECK: IntentType.TASK,
            TravelIntentType.BUDGET_CALC: IntentType.TASK,
            TravelIntentType.ITINERARY_ADJUST: IntentType.TASK,
            TravelIntentType.ITINERARY_CONFIRM: IntentType.TASK,
            TravelIntentType.VISA_INFO: IntentType.QUERY,
            TravelIntentType.FOOD_RECOMMEND: IntentType.QUERY,
            TravelIntentType.TRAVEL_TIPS: IntentType.QUERY,
            TravelIntentType.CURRENCY_CONVERT: IntentType.QUERY,
            TravelIntentType.TRAVEL_COMPANION: IntentType.QUERY,
            TravelIntentType.EMERGENCY_HELP: IntentType.TASK,
            TravelIntentType.GENERAL_CHAT: IntentType.CHAT,
        }

        task_intents = {
            TravelIntentType.TRIP_PLANNING,
            TravelIntentType.DESTINATION_SEARCH,
            TravelIntentType.FLIGHT_SEARCH,
            TravelIntentType.HOTEL_SEARCH,
            TravelIntentType.ATTRACTION_SEARCH,
            TravelIntentType.WEATHER_CHECK,
            TravelIntentType.BUDGET_CALC,
            TravelIntentType.ITINERARY_ADJUST,
            TravelIntentType.ITINERARY_CONFIRM,
            TravelIntentType.EMERGENCY_HELP,
        }

        fast_reply_intents = {
            TravelIntentType.GENERAL_CHAT,
        }

        legacy_type = mapping.get(result.intent, IntentType.QUERY)
        force_tool = result.intent in task_intents
        fast_reply = result.intent in fast_reply_intents

        return IntentResult(
            intent=legacy_type,
            goal=result.goal,
            fast_reply=fast_reply,
            force_tool=force_tool,
            tool_hints=result.tool_hints,
        )
