"""Task 1 — 新闻来源治理服务与候选评分的集成测试。

覆盖范围：
- ``SourceService.create_candidate`` 创建 ``pending`` 候选来源
- ``SourceService.review_source`` 管理员审核来源：状态流转 + 审计记录
- ``SourceService.discover_candidate`` 已 ``blocked`` 的域名不再被创建为候选
- ``SourceService.list_enabled_sources`` 仅返回 ``enabled`` 来源
- ``SourceCandidateScorer.score`` 基于输入信号返回分数与理由

业务红线：
- 正式事实结论只能由 ``enabled`` 来源支撑；未审核来源只能是 lead。
- ``blocked`` 域名永不再进入候选池。
"""

from __future__ import annotations

import pytest

from application.exceptions import NotFoundException, ValidationException
from application.news.models import SourceCandidateInput
from application.news.source_candidate_scorer import SourceCandidateScorer
from application.news.source_service import SourceService
from infrastructure.persistence.database import get_connection, init_db, reset_connection


# ---------------------------------------------------------------------------
# 共享 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_news_sources.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


@pytest.fixture
def service(db) -> SourceService:
    return SourceService()


# ---------------------------------------------------------------------------
# SourceCandidateScorer
# ---------------------------------------------------------------------------


class TestSourceCandidateScorer:
    def test_high_quality_publisher_gets_high_score(self):
        scorer = SourceCandidateScorer()
        candidate = SourceCandidateInput(
            domain="xinhuanet.com",
            name="新华网",
            publisher_type="official",
            https_available=True,
            domain_brand_consistent=True,
            topic_relevant=True,
            syndication_ratio=0.1,
            risk_signals=0,
        )
        score = scorer.score(candidate)
        assert score.score >= 0.7
        assert score.reason

    def test_risky_domain_gets_low_score(self):
        scorer = SourceCandidateScorer()
        candidate = SourceCandidateInput(
            domain="fake-news.example",
            name="Fake News",
            publisher_type="unknown",
            https_available=False,
            domain_brand_consistent=False,
            topic_relevant=False,
            syndication_ratio=0.9,
            risk_signals=3,
        )
        score = scorer.score(candidate)
        assert score.score < 0.4
        assert score.reason


# ---------------------------------------------------------------------------
# SourceService — 候选创建与发现
# ---------------------------------------------------------------------------


class TestSourceServiceCandidates:
    def test_create_candidate_returns_pending_source(self, service):
        source = service.create_candidate("example.com", 0.6, "publisher-looks-legit")
        assert source.domain == "example.com"
        assert source.status == "pending"
        assert source.ai_score == 0.6
        assert source.ai_reason == "publisher-looks-legit"
        assert source.id

    async def test_discover_candidate_returns_existing_pending(self, service):
        first = service.create_candidate("example.com", 0.5, "initial")
        second = await service.discover_candidate("example.com")
        assert second is not None
        assert second.id == first.id

    async def test_blocked_domain_is_not_recreated_as_candidate(self, service):
        source = service.create_candidate("blocked.example", 0.4, "risk")
        service.review_source("admin-1", source.id, "blocked", "impersonation")
        assert await service.discover_candidate("blocked.example") is None

    def test_create_candidate_is_idempotent_for_pending_domain(self, service):
        first = service.create_candidate("example.com", 0.5, "first")
        second = service.create_candidate("example.com", 0.6, "second")
        assert second.id == first.id

    def test_create_candidate_uses_ai_candidate_mode(self, service):
        """``create_candidate`` 必须显式写入 ``scoring_mode='ai_candidate'``。

        builtin_whitelist 与 ai_candidate 共用 ai_score/ai_reason，但语义互斥；
        候选来源必须用 ai_candidate 模式以便后续 LLM rubric 评分。
        """
        source = service.create_candidate("new.example", 0.4, "test")
        assert source.scoring_mode == "ai_candidate"
        assert source.ai_subscores == "{}"
        # 数据库里的列也对得上
        fetched = service.get_source_by_id(source.id)
        assert fetched is not None
        assert fetched.scoring_mode == "ai_candidate"


# ---------------------------------------------------------------------------
# SourceService — 管理员审核
# ---------------------------------------------------------------------------


class TestSourceServiceReview:
    def test_review_source_transitions_status(self, service):
        source = service.create_candidate("example.com", 0.7, "ok")
        reviewed = service.review_source("admin-1", source.id, "enabled", "verified")
        assert reviewed.status == "enabled"
        assert reviewed.id == source.id

    def test_review_source_records_audit_trail(self, service):
        source = service.create_candidate("example.com", 0.7, "ok")
        service.review_source("admin-1", source.id, "enabled", "verified")
        conn = get_connection()
        rows = conn.execute(
            "SELECT source_id, admin_id, previous_status, decision, reason "
            "FROM news_source_audits WHERE source_id = ?",
            (source.id,),
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        audit = rows[0]
        assert audit["source_id"] == source.id
        assert audit["admin_id"] == "admin-1"
        assert audit["previous_status"] == "pending"
        assert audit["decision"] == "enabled"
        assert audit["reason"] == "verified"

    def test_review_unknown_source_raises_not_found(self, service):
        with pytest.raises(NotFoundException):
            service.review_source("admin-1", "nonexistent-id", "enabled", "x")

    def test_review_invalid_decision_raises_validation(self, service):
        source = service.create_candidate("example.com", 0.7, "ok")
        with pytest.raises(ValidationException):
            service.review_source("admin-1", source.id, "garbage", "x")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SourceService — 列表
# ---------------------------------------------------------------------------


class TestSourceServiceListing:
    def test_list_enabled_sources_filters_status(self, service):
        s1 = service.create_candidate("a.example", 0.7, "ok")
        s2 = service.create_candidate("b.example", 0.5, "ok")
        service.create_candidate("c.example", 0.3, "ok")
        service.review_source("admin-1", s1.id, "enabled", "verified")
        service.review_source("admin-1", s2.id, "lead_only", "lead")
        enabled = service.list_enabled_sources()
        assert {s.id for s in enabled} == {s1.id}
        assert all(s.status == "enabled" for s in enabled)

    def test_list_enabled_sources_empty_when_no_enabled(self, service):
        service.create_candidate("a.example", 0.7, "ok")
        assert service.list_enabled_sources() == []
