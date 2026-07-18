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


@dataclass
class Source:
    """新闻来源记录。"""

    id: str
    name: str
    domain: str
    tier: str
    status: SourceStatus
    ai_score: float | None
    ai_reason: str
    created_at: str
    updated_at: str


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
    """候选来源评分结果。"""

    score: float
    reason: str
