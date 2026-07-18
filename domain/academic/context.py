"""学术研究上下文 — 会话级临时容器，不进入长期记忆或审计正文。

业务红线（来源：plans/2026-07-17-academic-frontend-quality.md Task 1）：
- 草稿文本只存在于 ``ResearchContext.draft_text``，禁止写入长期存储；
- 切换主题时丢弃前一个 segment 的论文与草稿；
- ``segment_id`` 用于审计日志中标识当前研究段，但草稿正文不写入日志。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Paper:
    """论文实体 — 仅含元数据，不含全文。"""

    id: str
    title: str
    abstract: str = ""
    authors: tuple[str, ...] = ()
    url: str = ""
    published_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "abstract": self.abstract,
            "authors": list(self.authors),
            "url": self.url,
            "published_at": self.published_at,
        }


@dataclass
class ResearchContext:
    """单个会话在某个研究主题下的临时上下文。

    每次切换主题都会创建新的 ``segment_id``；前一个 segment 的论文与草稿
    不再被服务持有，从而避免跨主题污染或长期化。
    """

    segment_id: str
    session_id: str
    topic: str
    papers: list[Paper] = field(default_factory=list)
    draft_text: str | None = None

    def to_audit_summary(self) -> dict[str, Any]:
        """返回可写入审计日志的摘要 — 不包含 ``draft_text`` 正文。"""
        return {
            "segment_id": self.segment_id,
            "session_id": self.session_id,
            "topic": self.topic,
            "paper_count": len(self.papers),
            "has_draft": self.draft_text is not None,
        }


def new_segment_id() -> str:
    """生成新的研究段 ID（非确定性，避免跨主题段 ID 碰撞）。"""
    return os.urandom(8).hex()
