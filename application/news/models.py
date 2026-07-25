"""Task 1 — 新闻来源治理领域模型。

设计要点：
- ``SourceStatus`` 覆盖来源在全生命周期中的所有合法状态。
- ``Source`` 仅保存来源元数据与 AI 评分；绝不保存新闻全文。
- ``SourceAudit`` 记录每次管理员审核决策，构成不可篡改的审计链。
- ``SourceCandidateInput`` / ``SourceScore`` 用于候选评分的输入输出契约。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# 来源状态：
# - pending      新发现的候选，待管理员审核
# - enabled      已审核通过，可作为正式事实结论与证据卡片的支撑来源
# - lead_only    仅可作为 unverified_leads，不可支撑正式结论
# - rejected     审核拒绝；不再抓取但保留记录
# - blocked      封禁（如冒充、欺诈）；该域名永不再进入候选池
# - needs_review 需要人工复审
SourceStatus = Literal[
    "pending", "enabled", "lead_only", "rejected", "blocked", "needs_review"
]

# 来源评分模式：
# - builtin_whitelist  产品内置白名单（tier 与 ai_score 由产品/管理员指定，非 AI 评分）
# - ai_candidate       AI 评分候选；由 LLM rubric 评分，存 ai_subscores 明细
# 两种模式共用 ``ai_score/ai_reason`` 字段，但语义互斥：
# builtin_whitelist 的 ai_score 必须为 None，ai_reason 固定为"产品内置白名单"。
ScoringMode = Literal["builtin_whitelist", "ai_candidate"]


@dataclass
class Source:
    """新闻来源记录。"""

    id: str
    name: str
    domain: str
    tier: str
    status: SourceStatus
    scoring_mode: ScoringMode
    ai_score: float | None
    ai_reason: str
    # 6 维度子分明细（JSON 字符串，ai_candidate 模式才有意义）：
    # {"publisher_authority":0.30, "domain_brand":0.20, ...}
    # builtin_whitelist 模式固定为 "{}"。
    ai_subscores: str
    created_at: str
    updated_at: str


@dataclass
class NewsSourceInit:
    """系统初始化事件（替代"初始化内置来源"占位审计行）。

    记录：何时由何种理由把某个来源初始化进白名单/候选池。
    不属于"管理员审核动作"，不进入 ``news_source_audits``。
    """

    id: str
    source_id: str
    tier: str
    scoring_mode: ScoringMode
    init_at: str
    init_reason: str


@dataclass
class SourceAudit:
    """来源审核审计记录。"""

    id: str
    source_id: str
    admin_id: str
    previous_status: SourceStatus
    decision: SourceStatus
    reason: str
    created_at: str


@dataclass
class SourceCandidateInput:
    """候选来源评分输入。

    各字段由发现阶段从外部信号采集，供 ``SourceCandidateScorer`` 综合打分。
    """

    domain: str
    name: str = ""
    publisher_type: str = "unknown"
    https_available: bool = False
    domain_brand_consistent: bool = False
    topic_relevant: bool = False
    syndication_ratio: float = 0.0
    risk_signals: int = 0


@dataclass
class SourceScore:
    """候选来源评分结果。

    - ``score``: 总分 ``[0.0, 1.0]``。
    - ``reason``: 评分理由标签；启发式模式拼接维度标签，LLM rubric 模式固定为
      ``"LLM rubric"`` 或降级信息。
    - ``subscores``: 6 维度 JSON 明细（``publisher_authority`` /
      ``domain_brand`` / ``topic_relevance`` / ``editorial_standard`` /
      ``accessibility`` / ``risk_signals``）。启发式模式固定为 ``"{}"``；
      LLM rubric 模式由 :class:`SourceRubricScorer` 序列化。
    """

    score: float
    reason: str
    subscores: str = "{}"


# ---------------------------------------------------------------------------
# Task 2 — 热点池与证据化研判模型
# ---------------------------------------------------------------------------


@dataclass
class NewsItem:
    """缓存中的新闻热点条目。

    仅保存标题、来源、URL、摘要和发布时间；绝不保存新闻全文。
    """

    id: str
    title: str
    source: str
    url: str
    summary: str
    published_at: str = ""


@dataclass
class NewsAnchor:
    """新闻研判锚点。

    锁定会话 ``news_analysis_locked`` 必须锚定一个 ``NewsAnchor``；
    新闻 Agent 只接收锚点字段，不接收新闻全文。
    """

    news_id: str
    title: str
    source: str
    url: str
    summary: str
    published_at: str = ""


@dataclass
class Evidence:
    """从外部来源采集的证据条目。

    ``status`` 不在此字段，而是由 :class:`NewsAnalysisService` 根据对应
    :class:`Source` 的当前状态动态判定，避免来源审核状态变更后证据状态过期。
    """

    source_id: str
    source_name: str
    url: str
    claim: str


# 证据卡片状态：仅 ``enabled`` 来源可支撑正式结论。
EvidenceCardStatus = Literal["verified", "conflicted"]


@dataclass
class EvidenceCard:
    """正式证据卡片：仅由 ``enabled`` 来源支撑。

    - ``verified``：单一或多个 ``enabled`` 来源一致
    - ``conflicted``：多个 ``enabled`` 来源 claim 相互矛盾

    ``source_id`` 携带原始来源记录 ID，便于前端跳转到该来源的人工审核页
    （``/admin/news?source=xxx``）。绝不在 prompt / 报告中输出，仅用于前端
    跳转与审计追溯。
    """

    source_id: str
    source_name: str
    url: str
    claim: str
    status: EvidenceCardStatus


@dataclass
class UnverifiedLead:
    """未审核来源的线索。

    ``pending`` / ``lead_only`` / ``rejected`` / ``blocked`` 来源的证据
    只能进入 ``unverified_leads``，不构成正式事实结论。
    """

    source_name: str
    url: str
    claim: str


@dataclass
class NewsAnalysisResponse:
    """新闻研判响应。"""

    anchor: NewsAnchor
    question: str
    evidence_cards: list[EvidenceCard]
    unverified_leads: list[UnverifiedLead]
    summary: str


@dataclass
class RefreshResult:
    """热点池刷新结果。"""

    count: int
    fetched_at: str
    sources_used: list[str]
