from __future__ import annotations

import json
import logging
import re

from domain.user.emotion.schema import EmotionResult, EmotionType, EMOTION_STRATEGIES
from infrastructure.llm.openai import OpenAILLM

logger = logging.getLogger(__name__)

_EMOTION_KEYWORDS: dict[EmotionType, list[str]] = {
    EmotionType.ANGRY: [
        "太差", "垃圾", "骗人", "投诉", "恶心", "离谱", "过分",
        "受不了", "忍不了", "气死", "愤怒", "荒谬", "欺骗",
        "差评", "黑心", "坑人",
    ],
    EmotionType.ANXIOUS: [
        "急", "着急", "怎么办", "什么时候", "多久", "等不了",
        "催", "赶紧", "快点", "急用", "来不及",
    ],
    EmotionType.DISAPPOINTED: [
        "失望", "不如预期", "没想到", "太遗憾", "可惜",
        "不满意", "不够好", "差强人意",
    ],
    EmotionType.SATISFIED: [
        "满意", "不错", "很好", "谢谢", "感谢", "好评",
        "点赞", "棒", "优秀",
    ],
}

_EMOTION_SYSTEM = """你是客服情感分析器。分析用户消息中的情绪状态。
仅返回 JSON：
{
  "emotion": "angry" | "anxious" | "disappointed" | "satisfied" | "neutral",
  "score": 0.0-1.0,
  "confidence": 0.0-1.0,
  "keywords": ["触发情感的关键词"]
}
规则：
- score 表示情绪强度，0.0 最弱，1.0 最强
- 仅输出 JSON
"""


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


class EmotionDetector:
    def __init__(self, llm: OpenAILLM | None = None) -> None:
        self._llm = llm

    async def detect(self, message: str) -> EmotionResult:
        keyword_result = self._keyword_detect(message)
        if keyword_result and keyword_result.confidence >= 0.7:
            return keyword_result

        if self._llm is None:
            return keyword_result or EmotionResult(
                emotion=EmotionType.NEUTRAL,
                score=0.0,
                confidence=0.3,
            )

        try:
            text = await self._llm.complete(
                system=_EMOTION_SYSTEM,
                messages=[{"role": "user", "content": message}],
            )
            data = _extract_json(text)
        except Exception:
            return keyword_result or EmotionResult(
                emotion=EmotionType.NEUTRAL, score=0.0, confidence=0.3
            )

        try:
            emotion = EmotionType(data.get("emotion", "neutral"))
        except ValueError:
            emotion = EmotionType.NEUTRAL

        score = float(data.get("score", 0.5))
        confidence = float(data.get("confidence", 0.5))
        keywords = [str(k) for k in data.get("keywords", []) if str(k).strip()]

        strategy = EMOTION_STRATEGIES.get(emotion, EMOTION_STRATEGIES[EmotionType.NEUTRAL])

        from core.metrics.collector import record_emotion
        record_emotion(emotion.value)

        return EmotionResult(
            emotion=emotion,
            score=score,
            confidence=confidence,
            keywords=keywords,
            response_style=strategy["response_style"],
            raw_output=text,
        )

    def _keyword_detect(self, message: str) -> EmotionResult | None:
        lowered = message.lower()
        best_emotion: EmotionType | None = None
        best_score = 0
        matched_keywords: list[str] = []

        for emotion_type, keywords in _EMOTION_KEYWORDS.items():
            matches = [kw for kw in keywords if kw in lowered]
            if len(matches) > best_score:
                best_score = len(matches)
                best_emotion = emotion_type
                matched_keywords = matches

        if best_emotion is None or best_score == 0:
            return None

        strategy = EMOTION_STRATEGIES.get(best_emotion, EMOTION_STRATEGIES[EmotionType.NEUTRAL])
        confidence = min(0.6 + best_score * 0.15, 0.95)
        score = min(0.5 + best_score * 0.2, 1.0)

        return EmotionResult(
            emotion=best_emotion,
            score=score,
            confidence=confidence,
            keywords=matched_keywords,
            response_style=strategy["response_style"],
        )
