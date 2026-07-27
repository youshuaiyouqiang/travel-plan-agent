"""Task 2 — 新闻研判分析服务的单元测试。

覆盖范围：
- 未审核来源的证据只能作为 ``unverified_leads``，不进入 ``evidence_cards``
- ``enabled`` 来源的证据成为 ``verified`` 证据卡片
- 多个 ``enabled`` 来源证据相互矛盾时标记为 ``conflicted``
- ``blocked`` / ``rejected`` 来源的证据归入 ``unverified_leads``

业务红线：
- 正式事实结论和证据卡片只能由 ``enabled`` 来源支撑。
- 未审核来源只能是 ``unverified_leads``。
- 冲突的 ``enabled`` 证据标记为 ``conflicted``。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from application.news.analysis_service import NewsAnalysisService
from application.news.models import (
    Evidence,
    NewsAnchor,
    SourceStatus,
)
from application.news.source_service import SourceService
from infrastructure.persistence.database import init_db, reset_connection


# ---------------------------------------------------------------------------
# 共享 fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_news_analysis_service.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


@dataclass
class FakeEvidenceProvider:
    """返回预设证据列表的假证据提供者。"""

    evidence: list[Evidence]

    def get_evidence(self, anchor: NewsAnchor) -> list[Evidence]:
        return list(self.evidence)


@pytest.fixture
def anchor() -> NewsAnchor:
    return NewsAnchor(
        news_id="news-1",
        title="测试热点",
        source="测试来源",
        url="https://example.com/news-1",
        summary="测试摘要",
        published_at="2026-07-18T00:00:00Z",
    )


@pytest.fixture
def source_service(db) -> SourceService:
    return SourceService()


def _make_source(service: SourceService, domain: str, status: SourceStatus) -> str:
    """创建来源并审核到指定状态，返回 source_id。"""
    candidate = service.create_candidate(domain, 0.7, "test")
    if status != "pending":
        service.review_source("admin-1", candidate.id, status, "test")
    return candidate.id


# ---------------------------------------------------------------------------
# 证据分类
# ---------------------------------------------------------------------------


class TestEvidenceClassification:
    def test_unreviewed_evidence_is_only_a_lead(
        self, source_service, anchor
    ):
        """pending 来源的证据只能作为 unverified_lead。"""
        pending_id = _make_source(source_service, "pending.example", "pending")
        provider = FakeEvidenceProvider(
            evidence=[
                Evidence(
                    source_id=pending_id,
                    source_name="pending.example",
                    url="https://pending/a",
                    claim="某说法",
                )
            ]
        )
        analysis_service = NewsAnalysisService(
            sources=source_service, evidence_provider=provider
        )
        response = analysis_service.analyze(anchor, "影响是什么？")
        assert response.evidence_cards == []
        assert response.unverified_leads
        assert response.unverified_leads[0].claim == "某说法"

    def test_enabled_source_evidence_becomes_verified_card(
        self, source_service, anchor
    ):
        """enabled 来源的证据成为 verified 证据卡片。"""
        enabled_id = _make_source(source_service, "enabled.example", "enabled")
        provider = FakeEvidenceProvider(
            evidence=[
                Evidence(
                    source_id=enabled_id,
                    source_name="enabled.example",
                    url="https://enabled/a",
                    claim="已核实说法",
                )
            ]
        )
        analysis_service = NewsAnalysisService(
            sources=source_service, evidence_provider=provider
        )
        response = analysis_service.analyze(anchor, "影响是什么？")
        assert len(response.evidence_cards) == 1
        assert response.evidence_cards[0].status == "verified"
        assert response.evidence_cards[0].claim == "已核实说法"
        assert response.unverified_leads == []

    def test_conflicting_enabled_evidence_is_conflicted(
        self, source_service, anchor
    ):
        """多个 enabled 来源证据相互矛盾时标记为 conflicted。"""
        enabled_id_1 = _make_source(source_service, "src-a.example", "enabled")
        enabled_id_2 = _make_source(source_service, "src-b.example", "enabled")
        provider = FakeEvidenceProvider(
            evidence=[
                Evidence(
                    source_id=enabled_id_1,
                    source_name="src-a.example",
                    url="https://a/x",
                    claim="说法 A",
                ),
                Evidence(
                    source_id=enabled_id_2,
                    source_name="src-b.example",
                    url="https://b/x",
                    claim="说法 B（与 A 矛盾）",
                ),
            ]
        )
        analysis_service = NewsAnalysisService(
            sources=source_service, evidence_provider=provider
        )
        response = analysis_service.analyze(anchor, "影响是什么？")
        assert len(response.evidence_cards) == 2
        assert all(c.status == "conflicted" for c in response.evidence_cards)

    def test_blocked_source_evidence_becomes_lead(
        self, source_service, anchor
    ):
        """blocked 来源的证据归入 unverified_leads。"""
        blocked_id = _make_source(source_service, "blocked.example", "blocked")
        provider = FakeEvidenceProvider(
            evidence=[
                Evidence(
                    source_id=blocked_id,
                    source_name="blocked.example",
                    url="https://blocked/a",
                    claim="被封禁说法",
                )
            ]
        )
        analysis_service = NewsAnalysisService(
            sources=source_service, evidence_provider=provider
        )
        response = analysis_service.analyze(anchor, "影响是什么？")
        assert response.evidence_cards == []
        assert len(response.unverified_leads) == 1
        assert response.unverified_leads[0].claim == "被封禁说法"

    def test_mixed_evidence_splits_correctly(
        self, source_service, anchor
    ):
        """混合证据：enabled → verified card；pending → lead。"""
        enabled_id = _make_source(source_service, "ok.example", "enabled")
        pending_id = _make_source(source_service, "unverified.example", "pending")
        provider = FakeEvidenceProvider(
            evidence=[
                Evidence(
                    source_id=enabled_id,
                    source_name="ok.example",
                    url="https://ok/a",
                    claim="已核实",
                ),
                Evidence(
                    source_id=pending_id,
                    source_name="unverified.example",
                    url="https://unverified/a",
                    claim="未核实",
                ),
            ]
        )
        analysis_service = NewsAnalysisService(
            sources=source_service, evidence_provider=provider
        )
        response = analysis_service.analyze(anchor, "影响是什么？")
        assert len(response.evidence_cards) == 1
        assert response.evidence_cards[0].status == "verified"
        assert len(response.unverified_leads) == 1
        assert response.unverified_leads[0].claim == "未核实"
