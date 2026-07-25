"""新闻研判上下文（证据卡片 + 未核实线索）prompt 构造器。

设计要点：
- 接收 :class:`NewsAnalysisResponse`（``NewsAnalysisService.analyze`` 输出），
  把 ``evidence_cards`` 与 ``unverified_leads`` 拼装成可注入 user message 的
  prompt 段，置于 :mod:`anchor_prompt` 之后、用户问题之前。
- ``evidence_cards`` 中的 ``status`` 显式标注（``verified`` / ``conflicted``），
  便于新闻 Agent 在工作流中区分对待。
- 证据或线索为空时输出显式"暂无可用证据"占位，避免 Agent 误以为注入被截断。
- 业务红线：不输出新闻全文，不在 prompt 中嵌入任何用户身份/会话信息。
"""

from __future__ import annotations

from application.news.models import NewsAnalysisResponse

EVIDENCE_HEADER = "[证据卡片]"
LEADS_HEADER = "[未核实线索]"
NO_EVIDENCE_PLACEHOLDER = "（暂无证据或线索）"


def build_empty_evidence_block() -> str:
    """生成"证据 + 线索"两段占位，供 ``analysis is None`` 降级路径使用。

    始终同时输出 ``[证据卡片]`` 与 ``[未核实线索]`` 两段占位，避免新闻 Agent
    误判为"注入未完成"而向用户反问索取证据。
    """
    return (
        f"{EVIDENCE_HEADER}\n  {NO_EVIDENCE_PLACEHOLDER}\n\n"
        f"{LEADS_HEADER}\n  {NO_EVIDENCE_PLACEHOLDER}"
    )


def _format_evidence_card(index: int, card) -> str:
    """格式化单张证据卡片。"""
    return (
        f"  {index}. [{card.status}] 来源：{card.source_name}\n"
        f"     URL：{card.url}\n"
        f"     claim：{card.claim}"
    )


def _format_lead(index: int, lead) -> str:
    """格式化单条未核实线索。"""
    return (
        f"  {index}. 来源：{lead.source_name}\n"
        f"     URL：{lead.url}\n"
        f"     claim：{lead.claim}"
    )


def build_evidence_block(response: NewsAnalysisResponse) -> str:
    """拼装"证据卡片 + 未核实线索"prompt 段。

    输出结构：
        [证据卡片]
          1. [verified] 来源：xxx
             URL：xxx
             claim：xxx
          ...
        [未核实线索]
          1. 来源：xxx
             URL：xxx
             claim：xxx
          ...

    即便 ``evidence_cards`` 和 ``unverified_leads`` 都为空，也**必须同时输出两段
    占位**（``[证据卡片] / 暂无证据或线索`` 与 ``[未核实线索] / 暂无证据或线索``）。
    这样新闻 Agent 不会把"占位"误读为"注入未完成"，从而避免向用户反问索取证据。
    """
    sections: list[str] = []
    if response.evidence_cards:
        lines = [EVIDENCE_HEADER]
        for idx, card in enumerate(response.evidence_cards, start=1):
            lines.append(_format_evidence_card(idx, card))
        sections.append("\n".join(lines))
    else:
        sections.append(f"{EVIDENCE_HEADER}\n  {NO_EVIDENCE_PLACEHOLDER}")

    if response.unverified_leads:
        lines = [LEADS_HEADER]
        for idx, lead in enumerate(response.unverified_leads, start=1):
            lines.append(_format_lead(idx, lead))
        sections.append("\n".join(lines))
    else:
        sections.append(f"{LEADS_HEADER}\n  {NO_EVIDENCE_PLACEHOLDER}")

    return "\n\n".join(sections)
