"""新闻锚点与完整研判上下文 prompt 构造器的单元测试。

覆盖范围：
- ``build_news_anchor_prompt``：包含 ``[新闻锚点]`` 头、按顺序输出各字段；空
  ``summary`` 不渲染"摘要"行；空 ``published_at`` 显示"未知"。
- ``build_news_anchor_message``：锚点块在前，``[用户问题]`` 段在后；不修改用户原文。
- ``build_news_full_context``：完整上下文包含"锚点 → 证据 → 线索 → 用户问题"四段；
  ``analysis=None`` 时输出"暂无证据或线索"占位；用户原文 verbatim 保留。
- 业务红线：构造出的 prompt 中不应包含新闻全文字段（仅元数据）。
"""

from __future__ import annotations

from application.news.anchor_prompt import (
    ANCHOR_HEADER,
    USER_QUESTION_HEADER,
    build_news_anchor_message,
    build_news_anchor_prompt,
    build_news_full_context,
)
from application.news.evidence_prompt import EVIDENCE_HEADER, LEADS_HEADER
from application.news.models import (
    EvidenceCard,
    NewsAnalysisResponse,
    NewsAnchor,
    NewsItem,
    UnverifiedLead,
)


# ---------------------------------------------------------------------------
# build_news_anchor_prompt
# ---------------------------------------------------------------------------


class TestBuildNewsAnchorPrompt:
    def test_includes_anchor_header_and_all_fields(self):
        anchor = NewsItem(
            id="news-1",
            title="测试热点",
            source="测试来源",
            url="https://example.com/news-1",
            summary="测试摘要",
            published_at="2026-07-25T00:00:00Z",
        )
        prompt = build_news_anchor_prompt(anchor)

        assert prompt.startswith(ANCHOR_HEADER)
        assert "标题：测试热点" in prompt
        assert "来源：测试来源" in prompt
        assert "链接：https://example.com/news-1" in prompt
        assert "摘要：测试摘要" in prompt
        assert "发布时间：2026-07-25T00:00:00Z" in prompt
        assert prompt.index("标题：") < prompt.index("来源：")
        assert prompt.index("来源：") < prompt.index("链接：")
        assert prompt.index("链接：") < prompt.index("发布时间：")

    def test_omits_summary_line_when_empty(self):
        anchor = NewsItem(
            id="news-2",
            title="无摘要热点",
            source="源",
            url="https://example.com/n2",
            summary="",
            published_at="2026-07-25T00:00:00Z",
        )
        prompt = build_news_anchor_prompt(anchor)
        assert "摘要：" not in prompt
        assert "标题：无摘要热点" in prompt

    def test_uses_unknown_when_published_at_empty(self):
        anchor = NewsItem(
            id="news-3",
            title="无时间热点",
            source="源",
            url="https://example.com/n3",
            summary="",
            published_at="",
        )
        prompt = build_news_anchor_prompt(anchor)
        assert "发布时间：未知" in prompt

    def test_does_not_contain_full_text_field(self):
        anchor = NewsItem(
            id="news-4",
            title="锚点",
            source="源",
            url="https://example.com/n4",
            summary="摘要",
            published_at="2026-07-25T00:00:00Z",
        )
        prompt = build_news_anchor_prompt(anchor)
        for forbidden in ("full_text", "body", "content", "全文"):
            assert forbidden not in prompt


# ---------------------------------------------------------------------------
# build_news_anchor_message
# ---------------------------------------------------------------------------


class TestBuildNewsAnchorMessage:
    def test_concatenates_anchor_and_user_message(self):
        anchor = NewsItem(
            id="news-1",
            title="热点",
            source="源",
            url="https://example.com/n1",
            summary="摘要",
            published_at="2026-07-25T00:00:00Z",
        )
        result = build_news_anchor_message(anchor, "请分析这条新闻的影响")

        assert result.startswith(ANCHOR_HEADER)
        assert "标题：热点" in result
        assert USER_QUESTION_HEADER in result
        assert "请分析这条新闻的影响" in result
        assert result.index(ANCHOR_HEADER) < result.index(USER_QUESTION_HEADER)
        assert result.index(USER_QUESTION_HEADER) < result.index("请分析")

    def test_preserves_user_message_verbatim(self):
        anchor = NewsItem(
            id="news-1",
            title="热点",
            source="源",
            url="https://example.com/n1",
            summary="",
            published_at="",
        )
        user_text = "  保留首尾空白与换行\n第二行  "
        result = build_news_anchor_message(anchor, user_text)
        assert result.endswith(user_text)

    def test_handles_empty_user_message(self):
        anchor = NewsItem(
            id="news-1",
            title="热点",
            source="源",
            url="https://example.com/n1",
            summary="摘要",
            published_at="2026-07-25T00:00:00Z",
        )
        result = build_news_anchor_message(anchor, "")
        assert ANCHOR_HEADER in result
        assert USER_QUESTION_HEADER in result


# ---------------------------------------------------------------------------
# build_news_full_context
# ---------------------------------------------------------------------------


def _anchor() -> NewsAnchor:
    return NewsAnchor(
        news_id="news-1",
        title="热点",
        source="源",
        url="https://example.com/n1",
        summary="摘要",
        published_at="2026-07-25T00:00:00Z",
    )


def _item() -> NewsItem:
    return NewsItem(
        id="news-1",
        title="热点",
        source="源",
        url="https://example.com/n1",
        summary="摘要",
        published_at="2026-07-25T00:00:00Z",
    )


class TestBuildNewsFullContext:
    def test_full_context_contains_all_sections(self):
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
        result = build_news_full_context(_item(), "请分析", response)
        assert ANCHOR_HEADER in result
        assert EVIDENCE_HEADER in result
        assert LEADS_HEADER in result
        assert USER_QUESTION_HEADER in result
        assert "请分析" in result
        assert result.index(ANCHOR_HEADER) < result.index(EVIDENCE_HEADER)
        assert result.index(EVIDENCE_HEADER) < result.index(LEADS_HEADER)
        assert result.index(LEADS_HEADER) < result.index(USER_QUESTION_HEADER)
        assert result.index(USER_QUESTION_HEADER) < result.index("请分析")

    def test_analysis_none_uses_placeholder(self):
        result = build_news_full_context(_item(), "请分析", None)
        assert ANCHOR_HEADER in result
        assert "暂无证据或线索" in result
        assert USER_QUESTION_HEADER in result
        assert "请分析" in result

    def test_user_message_preserved_verbatim(self):
        response = NewsAnalysisResponse(
            anchor=_anchor(), question="q", evidence_cards=[], unverified_leads=[], summary=""
        )
        user_text = "  保留首尾空白与换行  "
        result = build_news_full_context(_item(), user_text, response)
        assert result.endswith(user_text)
