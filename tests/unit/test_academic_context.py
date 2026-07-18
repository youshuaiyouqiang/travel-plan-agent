"""Academic Agent 临时研究上下文与草稿隔离测试。

业务红线（来源：plans/2026-07-17-academic-frontend-quality.md Task 1）：
- 切换研究主题时，前一个主题的论文列表与草稿必须被丢弃；
- 草稿不得进入长期记忆、用户画像或审计日志正文；
- 学术事实检索只允许 arXiv 与论文数据库工具，禁止 web_search。
"""

from __future__ import annotations

import pytest

from application.academic.service import AcademicService
from domain.academic.context import Paper, ResearchContext
from domain.academic.ports import PaperSearchPort


class _StubPaperSearch(PaperSearchPort):
    """内存版 PaperSearchPort — 测试专用，避免触碰真实网络。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def search(self, query: str) -> list[Paper]:
        self.calls.append(query)
        # 测试不需要返回真实结果；switch_topic 应丢弃结果。
        return []


@pytest.fixture
def service() -> AcademicService:
    return AcademicService(paper_search=_StubPaperSearch())


class TestAcademicContext:
    def test_start_context_returns_segment_with_topic_and_draft(self, service: AcademicService) -> None:
        ctx = service.start_context("s1", topic="RAG", draft_text="private draft")
        assert isinstance(ctx, ResearchContext)
        assert ctx.session_id == "s1"
        assert ctx.topic == "RAG"
        assert ctx.draft_text == "private draft"
        assert ctx.segment_id  # 非空
        assert ctx.papers == []

    def test_switch_topic_drops_previous_papers_and_draft(self, service: AcademicService) -> None:
        first = service.start_context("s1", topic="RAG", draft_text="private draft")
        first.papers = [Paper(id="p1", title="RAG")]
        second = service.switch_topic("s1", "diffusion models")

        assert second.segment_id != first.segment_id
        assert second.papers == []
        assert second.draft_text is None
        assert second.topic == "diffusion models"

    def test_switch_topic_creates_new_segment_for_same_session(self, service: AcademicService) -> None:
        first = service.start_context("s1", topic="RAG")
        second = service.switch_topic("s1", "transformers")

        assert first.session_id == second.session_id == "s1"
        assert first.segment_id != second.segment_id

    def test_get_current_context_returns_latest_segment(self, service: AcademicService) -> None:
        first = service.start_context("s1", topic="RAG")
        second = service.switch_topic("s1", "transformers")

        current = service.get_current_context("s1")
        assert current is not None
        assert current.segment_id == second.segment_id

    def test_get_current_context_returns_none_for_unknown_session(self, service: AcademicService) -> None:
        assert service.get_current_context("unknown") is None

    def test_draft_text_is_not_persisted_to_long_term_store(self, service: AcademicService) -> None:
        """草稿只存在于会话级临时上下文；服务不暴露任何长期持久化接口。"""
        service.start_context("s1", topic="RAG", draft_text="secret draft content")
        # 服务公开 API 中不存在 save_draft / persist_draft / write_draft_to_memory 等方法。
        public_methods = [m for m in dir(service) if not m.startswith("_")]
        assert not any("persist" in m or "save_draft" in m or "write_to_memory" in m for m in public_methods)


class TestPaperModel:
    def test_paper_construction(self) -> None:
        paper = Paper(id="arxiv:2401.00001", title="RAG Survey", abstract="ab", authors=["A"], url="u")
        assert paper.id == "arxiv:2401.00001"
        assert paper.title == "RAG Survey"
