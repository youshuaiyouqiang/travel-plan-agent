"""Task 1 — 新闻来源候选评分器。

评分维度（与计划一致）：
- 发布者类型（official/mainstream/aggregator/unknown）
- HTTPS 可用性
- 域名-品牌一致性
- 主题相关性
- 转载率（高转载 = 内容农场，扣分）
- 风险信号数（冒充、欺诈等，每个扣分）

评分结果在 ``[0.0, 1.0]`` 区间；``reason`` 拼接各维度标签供管理员参考。
"""

from __future__ import annotations

from application.news.models import SourceCandidateInput, SourceScore

# 发布者类型权重：官方 > 主流 > 聚合 > 未知
_PUBLISHER_WEIGHTS: dict[str, float] = {
    "official": 0.35,
    "mainstream": 0.25,
    "aggregator": 0.10,
    "unknown": 0.05,
}

_HTTPS_BONUS = 0.15
_BRAND_CONSISTENCY_BONUS = 0.15
_TOPIC_RELEVANCE_BONUS = 0.15
_SYNDICATION_PENALTY = 0.2  # 乘以 syndication_ratio
_RISK_SIGNAL_PENALTY = 0.15  # 每个 risk_signal 扣分


class SourceCandidateScorer:
    """候选来源评分器；无状态，可单例复用。"""

    def score(self, candidate: SourceCandidateInput) -> SourceScore:
        reasons: list[str] = []
        score = 0.0

        pub_weight = _PUBLISHER_WEIGHTS.get(candidate.publisher_type, 0.05)
        score += pub_weight
        reasons.append(f"publisher={candidate.publisher_type}")

        if candidate.https_available:
            score += _HTTPS_BONUS
            reasons.append("https")

        if candidate.domain_brand_consistent:
            score += _BRAND_CONSISTENCY_BONUS
            reasons.append("brand-consistent")

        if candidate.topic_relevant:
            score += _TOPIC_RELEVANCE_BONUS
            reasons.append("topic-relevant")

        # 转载率惩罚
        syndication_penalty = candidate.syndication_ratio * _SYNDICATION_PENALTY
        score -= syndication_penalty
        if candidate.syndication_ratio > 0.5:
            reasons.append(f"high-syndication={candidate.syndication_ratio:.2f}")

        # 风险信号惩罚
        risk_penalty = candidate.risk_signals * _RISK_SIGNAL_PENALTY
        score -= risk_penalty
        if candidate.risk_signals > 0:
            reasons.append(f"risk-signals={candidate.risk_signals}")

        # 钳制到 [0, 1]
        score = max(0.0, min(1.0, score))
        return SourceScore(score=score, reason=", ".join(reasons))
