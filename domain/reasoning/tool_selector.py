from __future__ import annotations

from infrastructure.tools.base import ToolSpec


class ToolSelector:
    """根据用户消息和上下文，自动推荐应披露的工具。

    复用 MCPCatalog.select_tool_refs 的打分机制，推广到所有工具类别。
    双轨披露机制：
    1. 自动推荐（被动）：每轮根据用户消息自动推荐 top-N 相关工具
    2. 主动拉取（主动）：LLM 通过 load_skill_detail / load_tool_detail 主动拉取
    """

    def select(
        self,
        message: str,
        all_specs: list[ToolSpec],
        already_disclosed: set[str] | None = None,
        limit: int = 3,
    ) -> list[ToolSpec]:
        """选择 top-N 相关工具，排除已披露的。

        Args:
            message: 用户消息
            all_specs: 所有可用工具规格
            already_disclosed: 已披露的工具名集合
            limit: 最多推荐的工具数
        """
        disclosed = already_disclosed or set()
        scored: list[tuple[int, ToolSpec]] = []
        for spec in all_specs:
            if spec.name in disclosed:
                continue
            score = self._score(spec, message)
            if score > 0:
                scored.append((score, spec))
        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:limit]]

    def _score(self, spec: ToolSpec, message: str) -> int:
        """对单个工具与用户消息的匹配程度打分。"""
        score = 0
        msg_lower = message.lower()

        # 工具名命中（最高权重）
        if spec.name.lower() in msg_lower:
            score += 8

        # 披露关键词命中
        for kw in spec.disclosure_keywords:
            if kw.lower() in msg_lower:
                score += 4

        # category 命中
        if spec.category.lower() in msg_lower:
            score += 2

        # description 关键词部分匹配
        desc_lower = spec.description.lower()
        for word in msg_lower.split():
            if len(word) >= 2 and word in desc_lower:
                score += 1

        return score

    def select_by_category(
        self,
        category: str,
        all_specs: list[ToolSpec],
        already_disclosed: set[str] | None = None,
    ) -> list[ToolSpec]:
        """按类别筛选工具。"""
        disclosed = already_disclosed or set()
        return [s for s in all_specs if s.name not in disclosed and s.category.lower() == category.lower()]
