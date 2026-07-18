"""学术领域端口定义 — 隔离外部论文检索依赖。

学术事实检索只允许 arXiv 与论文数据库；通用网页搜索由 ``ToolPolicy``
在工具层拦截，本端口仅暴露受允许的论文检索能力。
"""

from __future__ import annotations

from typing import Protocol

from domain.academic.context import Paper


class PaperSearchPort(Protocol):
    """论文检索端口 — 基础设施层实现并注入到 ``AcademicService``。"""

    def search(self, query: str) -> list[Paper]:
        """按查询词返回论文列表；不应触碰通用网页搜索。"""
        ...
