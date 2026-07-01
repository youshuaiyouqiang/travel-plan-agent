from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EmotionType(str, Enum):
    ANGRY = "angry"
    ANXIOUS = "anxious"
    SATISFIED = "satisfied"
    NEUTRAL = "neutral"
    DISAPPOINTED = "disappointed"


@dataclass
class EmotionResult:
    emotion: EmotionType
    score: float
    confidence: float = 1.0
    keywords: list[str] = field(default_factory=list)
    response_style: str = "neutral"
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_output: str = ""


EMOTION_STRATEGIES: dict[EmotionType, dict[str, Any]] = {
    EmotionType.ANGRY: {
        "priority": "high",
        "response_style": "empathetic",
        "system_prompt_suffix": (
            "用户当前情绪较为激动，请使用安抚性语言，"
            "先表达理解和歉意，再提供解决方案。"
            "避免使用命令式语气，多用\"我们\"代替\"你\"。"
        ),
    },
    EmotionType.ANXIOUS: {
        "priority": "high",
        "response_style": "reassuring",
        "system_prompt_suffix": (
            "用户当前情绪较为焦虑，请提供明确的时间线和进度信息，"
            "使用确定性的语言，避免模糊表达。"
        ),
    },
    EmotionType.DISAPPOINTED: {
        "priority": "medium",
        "response_style": "apologetic",
        "system_prompt_suffix": (
            "用户对服务感到失望，请先承认问题并道歉，"
            "然后提供具体的改进措施或补偿方案。"
        ),
    },
    EmotionType.SATISFIED: {
        "priority": "normal",
        "response_style": "confirming",
        "system_prompt_suffix": "",
    },
    EmotionType.NEUTRAL: {
        "priority": "normal",
        "response_style": "neutral",
        "system_prompt_suffix": "",
    },
}
