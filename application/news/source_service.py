"""Task 1 — 新闻来源治理应用服务。

设计要点：
- ``create_candidate`` 幂等：同域名已存在则返回已有记录，不重复创建。
- ``discover_candidate`` 对 ``blocked`` 域名返回 None，永不重新创建候选。
- ``review_source`` 校验决策合法性，更新状态并写审计记录。
- ``list_enabled_sources`` 仅返回 ``enabled`` 来源，供热点池抓取使用。
- 管理员 ID 由调用方（API 层）从服务端认证上下文传入，服务层不信任客户端。
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from application.exceptions import NotFoundException, ValidationException
from application.news.models import Source, SourceAudit, SourceCandidateInput, SourceStatus
from application.news.source_candidate_scorer import SourceCandidateScorer
from infrastructure.persistence.news_repository import NewsSourceRepository

_VALID_DECISIONS: set[str] = {
    "pending",
    "enabled",
    "lead_only",
    "rejected",
    "blocked",
    "needs_review",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return os.urandom(8).hex()


class SourceService:
    """新闻来源治理应用服务。"""

    def __init__(
        self,
        repository: NewsSourceRepository | None = None,
        scorer: SourceCandidateScorer | None = None,
    ) -> None:
        self._repo = repository or NewsSourceRepository()
        self._scorer = scorer or SourceCandidateScorer()

    # ------------------------------------------------------------------
    # 候选创建与发现
    # ------------------------------------------------------------------

    def create_candidate(
        self, domain: str, ai_score: float, ai_reason: str
    ) -> Source:
        """创建 ``pending`` 候选来源；同域名已存在则返回已有记录。"""
        existing = self._repo.get_source_by_domain(domain)
        if existing is not None:
            return existing
        source = Source(
            id=_new_id(),
            name=domain,
            domain=domain,
            tier="unknown",
            status="pending",
            ai_score=float(ai_score),
            ai_reason=ai_reason,
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        self._repo.insert_source(source)
        return source

    def discover_candidate(self, domain: str) -> Source | None:
        """发现候选来源。

        - ``blocked`` 域名：返回 None，永不再进入候选池。
        - 已存在且非 blocked：返回已有记录。
        - 新域名：用默认信号评分后创建 ``pending`` 候选。
        """
        existing = self._repo.get_source_by_domain(domain)
        if existing is not None:
            if existing.status == "blocked":
                return None
            return existing
        score = self._scorer.score(SourceCandidateInput(domain=domain))
        source = Source(
            id=_new_id(),
            name=domain,
            domain=domain,
            tier="unknown",
            status="pending",
            ai_score=score.score,
            ai_reason=score.reason,
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        self._repo.insert_source(source)
        return source

    # ------------------------------------------------------------------
    # 管理员审核
    # ------------------------------------------------------------------

    def review_source(
        self,
        admin_id: str,
        source_id: str,
        decision: SourceStatus,
        reason: str,
    ) -> Source:
        """管理员审核来源：更新状态 + 写审计记录。"""
        if decision not in _VALID_DECISIONS:
            raise ValidationException(f"无效的审核决定: {decision}")
        source = self._repo.get_source_by_id(source_id)
        if source is None:
            raise NotFoundException("news_source", source_id)
        previous_status = source.status
        now = _now_iso()
        self._repo.update_source_status(source_id, decision, now)
        audit = SourceAudit(
            id=_new_id(),
            source_id=source_id,
            admin_id=admin_id,
            previous_status=previous_status,
            decision=decision,
            reason=reason,
            created_at=now,
        )
        self._repo.insert_audit(audit)
        source.status = decision
        source.updated_at = now
        return source

    # ------------------------------------------------------------------
    # 列表
    # ------------------------------------------------------------------

    def list_enabled_sources(self) -> list[Source]:
        """仅返回 ``enabled`` 来源；供热点池抓取使用。"""
        return self._repo.list_sources_by_status("enabled")

    def list_all_sources(self) -> list[Source]:
        """返回所有来源；供管理员审核后台使用。"""
        return self._repo.list_all_sources()

    def list_audits(self) -> list[SourceAudit]:
        """返回所有审核审计记录。"""
        return self._repo.list_audits()
