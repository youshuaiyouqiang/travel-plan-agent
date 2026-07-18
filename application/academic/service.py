"""学术研究上下文服务 — 会话级临时容器，禁止长期化草稿。

业务红线（来源：plans/2026-07-17-academic-frontend-quality.md Task 1）：
- ``draft_text`` 只存在于内存中的 ``ResearchContext``；
- 切换主题（``switch_topic``）丢弃前一个 segment 的论文与草稿；
- 服务不暴露任何持久化草稿、写入长期记忆或审计正文的接口；
- 审计日志若需记录上下文，应使用 ``ResearchContext.to_audit_summary()``
  而非 ``draft_text`` 正文。
"""

from __future__ import annotations

from domain.academic.context import Paper, ResearchContext, new_segment_id
from domain.academic.ports import PaperSearchPort


class AcademicService:
    """管理学术会话的临时研究上下文。

    每个会话仅保留当前最新的 ``ResearchContext``；切换主题时旧 segment
    被丢弃，从而保证草稿不长期化、不跨主题泄漏。
    """

    def __init__(self, paper_search: PaperSearchPort) -> None:
        self._paper_search = paper_search
        self._contexts: dict[str, ResearchContext] = {}

    def start_context(
        self,
        session_id: str,
        *,
        topic: str,
        draft_text: str | None = None,
    ) -> ResearchContext:
        """为会话创建新的研究段；若已存在则覆盖（仅保留最新段）。"""
        context = ResearchContext(
            segment_id=new_segment_id(),
            session_id=session_id,
            topic=topic,
            papers=[],
            draft_text=draft_text,
        )
        self._contexts[session_id] = context
        return context

    def switch_topic(self, session_id: str, topic: str) -> ResearchContext:
        """切换研究主题 — 丢弃前一个段的论文与草稿，创建新段。

        若会话此前没有上下文，等同于以空草稿启动新段。
        """
        return self.start_context(session_id, topic=topic, draft_text=None)

    def get_current_context(self, session_id: str) -> ResearchContext | None:
        """返回会话当前研究段；会话不存在时返回 ``None``。"""
        return self._contexts.get(session_id)

    def add_papers(self, session_id: str, papers: list[Paper]) -> ResearchContext | None:
        """向当前段追加论文；会话不存在时返回 ``None``。"""
        context = self._contexts.get(session_id)
        if context is None:
            return None
        context.papers.extend(papers)
        return context

    def search_papers(self, session_id: str, query: str) -> list[Paper]:
        """经 ``PaperSearchPort`` 检索论文并追加到当前段。"""
        papers = self._paper_search.search(query)
        self.add_papers(session_id, papers)
        return papers
