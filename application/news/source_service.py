"""Task 1 — 新闻来源治理应用服务。

设计要点：
- ``create_candidate`` 幂等：同域名已存在则返回已有记录，不重复创建；
  新建时 ``scoring_mode='ai_candidate'``。
- ``discover_candidate`` 对 ``blocked`` 域名返回 None，永不重新创建候选。
  评分优先走 :class:`SourceRubricScorer`（LLM 6 维度 rubric），不可用时
  回退到 :class:`SourceCandidateScorer`（启发式）。
- ``register_builtin_whitelist`` 幂等注册产品内置白名单：
  ``scoring_mode='builtin_whitelist'``, ``ai_score=None``,
  ``ai_reason='产品内置白名单'``, ``status='enabled'``。
  写 ``news_source_inits`` 事件，**不写** ``news_source_audits``
  （内置不是审核动作）。
- ``review_source`` 校验决策合法性，更新状态并写审计记录。
- ``list_enabled_sources`` 仅返回 ``enabled`` 来源，供热点池抓取使用。
- 管理员 ID 由调用方（API 层）从服务端认证上下文传入，服务层不信任客户端。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from application.exceptions import NotFoundException, ValidationException
from application.news.models import (
    NewsSourceInit,
    Source,
    SourceAudit,
    SourceCandidateInput,
    SourceScore,
    SourceStatus,
)
from application.news.source_candidate_scorer import SourceCandidateScorer
from application.news.source_rubric_scorer import (
    LlmJsonClient,
    SourceRubricScorer,
)
from infrastructure.persistence.news_repository import NewsSourceRepository

logger = logging.getLogger(__name__)

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


# 内置白名单常量：domain / name / tier。
# tier 由产品决策（mainstream / aggregator），不属于 AI 评分结果。
BUILTIN_WHITELIST: tuple[tuple[str, str, str], ...] = (
    ("zhihu.com", "知乎热榜", "mainstream"),
    ("weibo.com", "微博热搜", "mainstream"),
    ("www.toutiao.com", "今日头条", "mainstream"),
    ("top.baidu.com", "百度热搜", "aggregator"),
)


class SourceService:
    """新闻来源治理应用服务。"""

    def __init__(
        self,
        repository: NewsSourceRepository | None = None,
        scorer: SourceCandidateScorer | None = None,
        rubric_scorer: SourceRubricScorer | None = None,
        llm: LlmJsonClient | None = None,
    ) -> None:
        self._repo = repository or NewsSourceRepository()
        # 启发式评分器保留为回退路径；rubric 评分器在 llm=None 时直接走启发式。
        self._scorer = scorer or SourceCandidateScorer()
        if rubric_scorer is None:
            self._rubric_scorer = SourceRubricScorer(llm=llm)
        else:
            self._rubric_scorer = rubric_scorer

    # ------------------------------------------------------------------
    # 内置白名单注册
    # ------------------------------------------------------------------

    def register_builtin_whitelist(
        self,
        domain: str,
        name: str,
        tier: str,
        init_reason: str = "产品内置白名单",
    ) -> Source:
        """注册内置白名单来源；幂等。

        行为：
        - 域名不存在：创建新 Source，``scoring_mode='builtin_whitelist'``、
          ``ai_score=None``、``ai_reason='产品内置白名单'``、``status='enabled'``。
        - 域名已存在：保证 ``scoring_mode`` 与 ``tier`` 正确（覆盖脏数据），
          ``ai_score`` 置 NULL、``ai_reason`` 标准化、``status`` 不动。
        - 无论新旧都向 ``news_source_inits`` 写一条初始化事件。
        """
        now = _now_iso()
        existing = self._repo.get_source_by_domain(domain)
        if existing is not None:
            source = existing
            needs_scoring_mode_fix = source.scoring_mode != "builtin_whitelist"
            needs_metadata_fix = (
                source.tier != tier
                or source.ai_reason != "产品内置白名单"
                or source.ai_score is not None
            )
            if needs_scoring_mode_fix:
                self._repo.update_source_builtin_scoring_mode(
                    source.id, "builtin_whitelist", now
                )
            if needs_metadata_fix:
                self._repo.update_source_status_builtin_metadata(
                    source.id,
                    tier=tier,
                    ai_score=None,
                    ai_reason="产品内置白名单",
                    ai_subscores="{}",
                    updated_at=now,
                )
            source = self._repo.get_source_by_id(source.id)  # type: ignore[assignment]
            assert source is not None
        else:
            source = Source(
                id=_new_id(),
                name=name,
                domain=domain,
                tier=tier,
                status="enabled",
                scoring_mode="builtin_whitelist",
                ai_score=None,
                ai_reason="产品内置白名单",
                ai_subscores="{}",
                created_at=now,
                updated_at=now,
            )
            self._repo.insert_source(source)

        init_event = NewsSourceInit(
            id=_new_id(),
            source_id=source.id,
            tier=source.tier,
            scoring_mode="builtin_whitelist",
            init_at=now,
            init_reason=init_reason,
        )
        self._repo.insert_init(init_event)
        return source

    # ------------------------------------------------------------------
    # 候选创建与发现
    # ------------------------------------------------------------------

    def create_candidate(
        self, domain: str, ai_score: float, ai_reason: str
    ) -> Source:
        """创建 ``pending`` AI 评分候选；同域名已存在则返回已有记录。"""
        existing = self._repo.get_source_by_domain(domain)
        if existing is not None:
            return existing
        now = _now_iso()
        source = Source(
            id=_new_id(),
            name=domain,
            domain=domain,
            tier="unknown",
            status="pending",
            scoring_mode="ai_candidate",
            ai_score=float(ai_score),
            ai_reason=ai_reason,
            ai_subscores="{}",
            created_at=now,
            updated_at=now,
        )
        self._repo.insert_source(source)
        return source

    async def discover_candidate(self, domain: str) -> Source | None:
        """发现候选来源。

        - ``blocked`` 域名：返回 None，永不再进入候选池。
        - 已存在且非 blocked：返回已有记录。
        - 新域名：用 LLM rubric 评分（失败回退启发式）后创建 ``pending`` 候选。
        """
        existing = self._repo.get_source_by_domain(domain)
        if existing is not None:
            if existing.status == "blocked":
                return None
            return existing
        score: SourceScore = await self._rubric_scorer.score(
            SourceCandidateInput(domain=domain)
        )
        now = _now_iso()
        source = Source(
            id=_new_id(),
            name=domain,
            domain=domain,
            tier="unknown",
            status="pending",
            scoring_mode="ai_candidate",
            ai_score=score.score,
            ai_reason=score.reason,
            ai_subscores=score.subscores,
            created_at=now,
            updated_at=now,
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
    # 读取
    # ------------------------------------------------------------------

    def get_source_by_id(self, source_id: str) -> Source | None:
        """按 ID 读取来源；不存在返回 None。

        供 :class:`NewsAnalysisService` 在研判时查询证据对应来源的当前状态。
        """
        return self._repo.get_source_by_id(source_id)

    def get_source_by_domain(self, domain: str) -> Source | None:
        """按域名读取来源；不存在返回 None。"""
        return self._repo.get_source_by_domain(domain)

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

    def list_inits(self) -> list[NewsSourceInit]:
        """返回系统初始化事件列表。"""
        return self._repo.list_inits()
