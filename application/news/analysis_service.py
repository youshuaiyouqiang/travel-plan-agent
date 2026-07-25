"""Task 2 — 新闻研判分析服务。

设计要点：
- ``NewsAnalysisService.analyze`` 接收 ``NewsAnchor`` 与用户问题，调用
  ``EvidenceProvider`` 取证，按来源当前状态分类为证据卡片或未核实线索。
- 正式证据卡片（``evidence_cards``）只能由 ``enabled`` 来源支撑。
- 多个 ``enabled`` 来源 claim 不同 → 全部标记为 ``conflicted``。
- ``pending`` / ``lead_only`` / ``rejected`` / ``blocked`` / 未知来源 →
  归入 ``unverified_leads``。
- 来源状态在研判时实时查询，避免来源审核状态变更后证据状态过期。
"""

from __future__ import annotations

import logging
from typing import Protocol

from application.news.models import (
    Evidence,
    EvidenceCard,
    NewsAnalysisResponse,
    NewsAnchor,
    SourceStatus,
    UnverifiedLead,
)
from application.news.source_service import SourceService

logger = logging.getLogger(__name__)

# 这些状态的来源只能作为 unverified_leads，不能支撑正式结论。
_LEAD_STATUSES: frozenset[SourceStatus] = frozenset(
    {"pending", "lead_only", "rejected", "blocked", "needs_review"}
)


class EvidenceProvider(Protocol):
    """证据提供者协议。

    实现方需提供 ``get_evidence(anchor) -> list[Evidence]``；可以是
    LLM 抽取、检索器、人工录入或测试替身。返回顺序不影响分类结果。
    """

    def get_evidence(self, anchor: NewsAnchor) -> list[Evidence]:  # pragma: no cover - 协议定义
        ...


def _normalize_claim(claim: str) -> str:
    """归一化 claim 用于冲突比较：去首尾空白、统一全角标点。"""
    text = (claim or "").strip()
    if not text:
        return ""
    # 简单归一化：替换常见全角标点为半角，避免格式差异被误判为冲突。
    fullwidth = {"。": ".", "，": ",", "；": ";", "：": ":", "？": "?", "！": "!"}
    for ch, half in fullwidth.items():
        text = text.replace(ch, half)
    return text


class NewsAnalysisService:
    """新闻研判分析服务。"""

    def __init__(
        self,
        sources: SourceService,
        evidence_provider: EvidenceProvider,
    ) -> None:
        self._sources = sources
        self._evidence_provider = evidence_provider

    def analyze(
        self, context: NewsAnchor, question: str
    ) -> NewsAnalysisResponse:
        """对指定锚点执行研判，返回结构化证据卡片与未核实线索。"""
        evidence_list = self._evidence_provider.get_evidence(context)
        enabled_evidence: list[Evidence] = []
        leads: list[UnverifiedLead] = []

        for evidence in evidence_list:
            source = self._sources.get_source_by_id(evidence.source_id)
            if source is not None and source.status == "enabled":
                enabled_evidence.append(evidence)
            else:
                leads.append(
                    UnverifiedLead(
                        source_name=evidence.source_name,
                        url=evidence.url,
                        claim=evidence.claim,
                    )
                )

        # 冲突检测：多个 enabled 来源 claim 归一化后不同 → 全部 conflicted。
        distinct_claims = {
            _normalize_claim(ev.claim) for ev in enabled_evidence if ev.claim.strip()
        }
        is_conflicted = len(distinct_claims) > 1

        cards = [
            EvidenceCard(
                source_id=ev.source_id,
                source_name=ev.source_name,
                url=ev.url,
                claim=ev.claim,
                status="conflicted" if is_conflicted else "verified",
            )
            for ev in enabled_evidence
        ]

        summary = self._build_summary(question, cards, leads)
        return NewsAnalysisResponse(
            anchor=context,
            question=question,
            evidence_cards=cards,
            unverified_leads=leads,
            summary=summary,
        )

    def _build_summary(
        self,
        question: str,
        cards: list[EvidenceCard],
        leads: list[UnverifiedLead],
    ) -> str:
        """构造简短摘要；不暴露内部堆栈或敏感细节。"""
        verified = sum(1 for c in cards if c.status == "verified")
        conflicted = sum(1 for c in cards if c.status == "conflicted")
        parts: list[str] = []
        if verified:
            parts.append(f"{verified} 条已核实证据")
        if conflicted:
            parts.append(f"{conflicted} 条冲突证据")
        if leads:
            parts.append(f"{len(leads)} 条未核实线索")
        evidence_desc = "、".join(parts) if parts else "暂无可用证据"
        return f"基于{evidence_desc}回答：{question}"
