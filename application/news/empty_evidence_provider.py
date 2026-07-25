"""生产默认的 EvidenceProvider 实现。

设计要点：
- 当前生产环境没有可用的证据抽取通道（LLM 抽取、检索器等均未集成）；
  ``EmptyEvidenceProvider`` 显式声明这一事实，返回空列表。
- 调用方（``NewsAnalysisService.analyze``）拿到空列表后会得到
  ``evidence_cards=[]`` 与 ``unverified_leads=[]``，新闻 Agent 据此产出
  "现有证据不足"的研判而不是胡编。
- 一旦后续接入真实证据通道，替换为 LLM 抽取 / 检索器实现即可，不需要
  改动 ``NewsAnalysisService``。
- 业务红线：永不伪造证据；绝不从外部抓取新闻全文。
"""

from __future__ import annotations

from application.news.analysis_service import EvidenceProvider
from application.news.models import Evidence, NewsAnchor


class EmptyEvidenceProvider:
    """空证据提供者：返回空列表，供生产默认使用。

    用于生产环境尚未接入真实证据通道的场景；新闻 Agent 在缺少证据时应
    直接说明"现有证据不足"，绝不胡编或要求用户补充。
    """

    def get_evidence(self, anchor: NewsAnchor) -> list[Evidence]:  # noqa: ARG002 - 参数预留
        return []
