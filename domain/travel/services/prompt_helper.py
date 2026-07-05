from __future__ import annotations

import logging
from typing import Any

from domain.memory.manager import DualLayerMemoryManager
from domain.travel.services.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class PromptHelper:
    # 需要的 _FIELD_LABELS 子集，从 CacheManager 引用
    _FIELD_LABELS = CacheManager._FIELD_LABELS

    def __init__(self, *, dual_memory: DualLayerMemoryManager) -> None:
        self._dual_memory = dual_memory

    def build_missing_info_context(
        self,
        ops_result: Any,
        dual_memory_context: str,
        user_id: str | None,
    ) -> str:
        if not ops_result or not hasattr(ops_result, "missing_info"):
            return ""
        missing = ops_result.missing_info
        if not missing:
            return ""

        parts: list[str] = []

        missing_labels = [self._FIELD_LABELS.get(f, f) for f in missing]
        parts.append(f"用户缺少以下关键信息：{'、'.join(missing_labels)}")
        parts.append("请友好地提醒用户补充这些信息，同时可以提供一些目的地相关的推荐来增加互动性。")

        destination = getattr(ops_result, "detected_destination", "")
        if destination:
            parts.append(f"用户已提供目的地：{destination}")
            parts.append(
                f"请利用你对{destination}的了解，主动推荐该地的特色景点、美食、文化活动等，"
                f"让用户在补充信息的同时对旅行产生期待。"
            )

        if dual_memory_context and user_id:
            preference_memories = self._dual_memory.get_long_term_memories(user_id)
            preference_items = [m for m in preference_memories if m.category == "preference"]
            if preference_items:
                prefs = "、".join(m.content for m in preference_items[:5])
                parts.append(
                    f"用户偏好（请据此推荐）：{prefs}"
                )
                parts.append(
                    "当你基于用户偏好做出推荐时，请在推荐后面用【基于记忆：偏好内容】标注依据，"
                    "例如：推荐青岛啤酒博物馆【基于记忆：喜欢文化类景点】"
                )

            stm_list = self._dual_memory.get_short_term_memories(user_id)
            stm_prefs = [m for m in stm_list if m.category == "preference"]
            if stm_prefs:
                prefs = "、".join(m.content for m in stm_prefs[:3])
                if not preference_items:
                    parts.append(f"用户近期偏好（请据此推荐）：{prefs}")
                    parts.append(
                        "当你基于用户偏好做出推荐时，请在推荐后面用【基于记忆：偏好内容】标注依据"
                    )

            experience_items = [m for m in preference_memories if m.category == "experience"]
            stm_exp = [m for m in stm_list if m.category == "experience"]
            all_exp = experience_items + stm_exp
            if all_exp:
                exp_texts = []
                for e in all_exp[:3]:
                    tag = "✓" if e.experience_tag == "success" else "✗"
                    exp_texts.append(f"{tag} {e.content}")
                parts.append(f"用户旅行经验：{'、'.join(exp_texts)}")
                parts.append(
                    "当你基于用户经验调整推荐时，请用【基于记忆：经验内容】标注依据"
                )

        return "\n".join(parts)

    def build_clarification_question(self, ops_result: Any) -> str:
        """根据 missing_info 构建友好的追问问题，在进入 ReAct 前调用。

        一次性问完所有缺失信息，避免多轮追问。
        """
        destination = getattr(ops_result, "detected_destination", "")
        missing = ops_result.missing_info

        # 如果目的地也缺失，优先问目的地（最关键信息）
        if "destination" in missing:
            return "请问您想去哪个城市旅行？"

        # 目的地已知，一次性问完所有缺失信息
        destination = destination or "目的地"
        question_parts: list[str] = []

        for field in missing:
            label = self._FIELD_LABELS.get(field, field)
            if field == "origin":
                question_parts.append(f"从哪个城市出发")
            elif field == "duration":
                question_parts.append(f"计划旅行几天")
            elif field == "dates":
                question_parts.append(f"大概什么时候出发")
            elif field == "budget":
                question_parts.append(f"预算大概是多少")
            else:
                question_parts.append(f"补充一下{label}")

        if len(question_parts) == 1:
            return f"好的，您想去{destination}旅行。请问{question_parts[0]}？"
        else:
            items = "、".join(question_parts)
            return f"好的，您想去{destination}旅行。请问{items}？"
