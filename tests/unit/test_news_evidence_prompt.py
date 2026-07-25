"""新闻研判证据 prompt 构造器的单元测试。

覆盖范围：
- ``build_evidence_block``：当 evidence_cards 与 unverified_leads 均为空时输出
  "暂无证据或线索"占位；只有 verified / conflicted 卡片时正确格式化并标注
  status；只有 leads 时格式化 lead 行；混合时按"证据卡片 → 未核实线索"顺序。
- 业务红线：格式化结果中不含新闻全文字段；call/URL 等来源信息保留以便追溯。
- ``build_news_full_context``：完整上下文包含"新闻锚点 → 证据 → 线索 → 用户问题"四段；
  ``analysis=None`` 时降级为"暂无证据或线索"占位；用户原文 verbatim 保留。
"""

from __future__ import annotations

from application.news.anchor_prompt import (
    ANCHOR_HEADER,
    USER_QUESTION_HEADER,
    build_news_anchor_message,
    build_news_anchor_prompt,
    build_news_full_context,
)
from application.news.evidence_prompt import (
    EVIDENCE_HEADER,
    LEADS_HEADER,
    NO_EVIDENCE_PLACEHOLDER,
    build_empty_evidence_block,
    build_evidence_block,
)
from application.news.models import (
    EvidenceCard,
    NewsAnalysisResponse,
    NewsAnchor,
    NewsItem,
    UnverifiedLead,
)


def _anchor() -> NewsAnchor:
    return NewsAnchor(
        news_id="news-1",
        title="某热点事件",
        source="某权威来源",
        url="https://example.com/news-1",
        summary="简短摘要",
        published_at="2026-07-25T10:00:00Z",
    )


def _item() -> NewsItem:
    return NewsItem(
        id="news-1",
        title="某热点事件",
        source="某权威来源",
        url="https://example.com/news-1",
        summary="简短摘要",
        published_at="2026-07-25T10:00:00Z",
    )


# ---------------------------------------------------------------------------
# build_evidence_block
# ---------------------------------------------------------------------------


class TestBuildEvidenceBlock:
    def test_no_evidence_or_leads_emits_placeholder(self):
        response = NewsAnalysisResponse(
            anchor=_anchor(),
            question="q",
            evidence_cards=[],
            unverified_leads=[],
            summary="",
        )
        block = build_evidence_block(response)
        # 两段都输出占位：避免 Agent 误判注入未完成而反问用户
        assert EVIDENCE_HEADER in block
        assert LEADS_HEADER in block
        assert NO_EVIDENCE_PLACEHOLDER in block
        # 占位不包含任何具体 claim
        assert "claim" not in block
        # 两段都带占位
        assert block.count(NO_EVIDENCE_PLACEHOLDER) == 2
        # 顺序：证据 → 线索
        assert block.index(EVIDENCE_HEADER) < block.index(LEADS_HEADER)

    def test_verified_card_is_formatted_with_status(self):
        response = NewsAnalysisResponse(
            anchor=_anchor(),
            question="q",
            evidence_cards=[
                EvidenceCard(
                    source_id="src-a",
                    source_name="src-a",
                    url="https://a.example/x",
                    claim="已核实说法",
                    status="verified",
                )
            ],
            unverified_leads=[],
            summary="",
        )
        block = build_evidence_block(response)
        assert EVIDENCE_HEADER in block
        assert "[verified]" in block
        assert "来源：src-a" in block
        assert "URL：https://a.example/x" in block
        assert "claim：已核实说法" in block
        # 单条 enabled 来源未触发 conflicted
        assert "[conflicted]" not in block

    def test_conflicted_card_status_is_preserved(self):
        response = NewsAnalysisResponse(
            anchor=_anchor(),
            question="q",
            evidence_cards=[
                EvidenceCard(
                    source_id="src-a",
                    source_name="src-a",
                    url="https://a/x",
                    claim="说法 A",
                    status="conflicted",
                ),
                EvidenceCard(
                    source_id="src-b",
                    source_name="src-b",
                    url="https://b/x",
                    claim="说法 B",
                    status="conflicted",
                ),
            ],
            unverified_leads=[],
            summary="",
        )
        block = build_evidence_block(response)
        assert "[conflicted]" in block
        # 两条 card 都被编号列出
        assert "1. [conflicted]" in block
        assert "2. [conflicted]" in block

    def test_unverified_lead_section_present_when_leads_exist(self):
        response = NewsAnalysisResponse(
            anchor=_anchor(),
            question="q",
            evidence_cards=[],
            unverified_leads=[
                UnverifiedLead(
                    source_name="X 平台",
                    url="https://x/post",
                    claim="未核实消息",
                )
            ],
            summary="",
        )
        block = build_evidence_block(response)
        assert LEADS_HEADER in block
        assert "来源：X 平台" in block
        assert "URL：https://x/post" in block
        assert "claim：未核实消息" in block
        # 没有证据卡片时仍输出 evidence 段（占位）
        assert EVIDENCE_HEADER in block

    def test_mixed_cards_and_leads_both_sections_present(self):
        response = NewsAnalysisResponse(
            anchor=_anchor(),
            question="q",
            evidence_cards=[
                EvidenceCard(
                    source_id="src-a",
                    source_name="src-a",
                    url="https://a/x",
                    claim="已核实",
                    status="verified",
                )
            ],
            unverified_leads=[
                UnverifiedLead(
                    source_name="X 平台",
                    url="https://x/p",
                    claim="线索",
                )
            ],
            summary="",
        )
        block = build_evidence_block(response)
        assert EVIDENCE_HEADER in block
        assert "claim：已核实" in block
        assert LEADS_HEADER in block
        assert "claim：线索" in block
        # 顺序：证据 → 线索
        assert block.index(EVIDENCE_HEADER) < block.index(LEADS_HEADER)

    def test_no_full_text_field_leaks(self):
        response = NewsAnalysisResponse(
            anchor=_anchor(),
            question="q",
            evidence_cards=[
                EvidenceCard(
                    source_id="src",
                    source_name="src",
                    url="https://x/y",
                    claim="a",
                    status="verified",
                )
            ],
            unverified_leads=[],
            summary="",
        )
        block = build_evidence_block(response)
        for forbidden in ("full_text", "body", "content", "全文"):
            assert forbidden not in block


# ---------------------------------------------------------------------------
# build_empty_evidence_block
# ---------------------------------------------------------------------------


class TestBuildEmptyEvidenceBlock:
    def test_always_emits_both_section_placeholders(self):
        """无论是否真的有证据/线索，都同时输出两段占位。"""
        block = build_empty_evidence_block()
        assert EVIDENCE_HEADER in block
        assert LEADS_HEADER in block
        assert block.count(NO_EVIDENCE_PLACEHOLDER) == 2
        # 顺序：证据 → 线索
        assert block.index(EVIDENCE_HEADER) < block.index(LEADS_HEADER)

    def test_no_full_text_field_leaks(self):
        block = build_empty_evidence_block()
        for forbidden in ("full_text", "body", "content", "全文"):
            assert forbidden not in block


# ---------------------------------------------------------------------------
# build_news_full_context
# ---------------------------------------------------------------------------


class TestBuildNewsFullContext:
    def test_full_context_contains_all_four_sections(self):
        response = NewsAnalysisResponse(
            anchor=_anchor(),
            question="q",
            evidence_cards=[
                EvidenceCard(
                    source_id="src",
                    source_name="src",
                    url="https://x",
                    claim="已核实",
                    status="verified",
                )
            ],
            unverified_leads=[
                UnverifiedLead(source_name="X 平台", url="https://x", claim="线索")
            ],
            summary="",
        )
        result = build_news_full_context(_item(), "请分析影响", response)
        # 四段都在，且顺序为：锚点 → 证据 → 线索 → 用户问题
        assert "[新闻锚点]" in result
        assert "标题：某热点事件" in result
        assert EVIDENCE_HEADER in result
        assert LEADS_HEADER in result
        assert "[用户问题]" in result
        assert "请分析影响" in result
        assert result.index("[新闻锚点]") < result.index(EVIDENCE_HEADER)
        assert result.index(EVIDENCE_HEADER) < result.index(LEADS_HEADER)
        assert result.index(LEADS_HEADER) < result.index("[用户问题]")
        assert result.index("[用户问题]") < result.index("请分析影响")

    def test_analysis_none_uses_placeholder(self):
        result = build_news_full_context(_item(), "请分析影响", None)
        assert "[新闻锚点]" in result
        assert EVIDENCE_HEADER in result
        assert NO_EVIDENCE_PLACEHOLDER in result
        assert LEADS_HEADER in result
        assert "请分析影响" in result

    def test_user_message_preserved_verbatim(self):
        response = NewsAnalysisResponse(
            anchor=_anchor(), question="q", evidence_cards=[], unverified_leads=[], summary=""
        )
        user_text = "  请详细分析  政策影响  \n第二行  "
        result = build_news_full_context(_item(), user_text, response)
        assert result.endswith(user_text)

    def test_no_full_text_field_leaks(self):
        result = build_news_full_context(_item(), "q", None)
        for forbidden in ("full_text", "body", "content", "全文"):
            assert forbidden not in result
