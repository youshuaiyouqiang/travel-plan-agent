"""新闻来源治理仓储端口。

P2.6 引入：将 ``news_sources`` / ``news_source_audits`` / ``news_source_inits``
三张表的访问从 application 层下沉到 infrastructure，应用层只消费此端口。

端口由消费方（application）定义，由 ``infrastructure.persistence.news_repository``
提供 ``NewsSourceRepository`` 实现，在 ``init_db()`` 中装配默认实例。
测试可用 fake 实现替代，不创建 SQLite 文件。

注意：新闻来源模型（``Source`` / ``SourceAudit`` / ``NewsSourceInit``）当前定义
在 ``application/news/models.py``，故端口也放在 application 层。后续若将模型
迁至 domain 层，端口应同步迁移至 ``domain/news/ports.py``。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # 避免循环导入；Protocol 仅用于静态类型检查
    from application.news.models import NewsSourceInit, Source, SourceAudit, SourceStatus


@runtime_checkable
class NewsSourceRepositoryPort(Protocol):
    """新闻来源、审核审计与系统初始化的读写端口。

    实现必须保证：
    - 所有 SQL 参数化；列名来自硬编码白名单；
    - ``insert_source`` / ``insert_audit`` / ``insert_init`` 各自独立提交；
    - ``update_source_status_builtin_metadata`` 与 ``update_source_builtin_scoring_mode``
      分离，降低误改风险。
    """

    def insert_source(self, source: Source) -> None:
        """插入新闻来源行。"""
        ...

    def get_source_by_id(self, source_id: str) -> Source | None:
        """按 ID 查询来源；不存在返回 None。"""
        ...

    def get_source_by_domain(self, domain: str) -> Source | None:
        """按域名查询来源；不存在返回 None。"""
        ...

    def list_sources_by_status(self, status: SourceStatus) -> list[Source]:
        """按状态列出来源，按 created_at 升序。"""
        ...

    def list_all_sources(self) -> list[Source]:
        """列出全部来源，按 created_at 倒序。"""
        ...

    def update_source_status(
        self, source_id: str, status: SourceStatus, updated_at: str
    ) -> None:
        """更新来源状态。"""
        ...

    def update_source_builtin(
        self, source_id: str, tier: str, updated_at: str
    ) -> None:
        """仅修正内置白名单来源的 tier 与 updated_at。"""
        ...

    def update_source_status_builtin_metadata(
        self,
        source_id: str,
        tier: str,
        ai_score: float | None,
        ai_reason: str,
        ai_subscores: str,
        updated_at: str,
    ) -> None:
        """内置白名单元数据全量校正。"""
        ...

    def update_source_builtin_scoring_mode(
        self, source_id: str, scoring_mode: str, updated_at: str
    ) -> None:
        """仅修正 ``scoring_mode`` 字段。"""
        ...

    def insert_audit(self, audit: SourceAudit) -> None:
        """插入审核审计行。"""
        ...

    def list_audits(self) -> list[SourceAudit]:
        """列出全部审核审计，按 created_at 倒序。"""
        ...

    def insert_init(self, init: NewsSourceInit) -> None:
        """插入系统初始化事件行。"""
        ...

    def list_inits(self) -> list[NewsSourceInit]:
        """列出全部初始化事件，按 init_at 倒序。"""
        ...


# ── 默认仓储装配（过渡方案，同 P2.1–P2.5）───────────────────

_default_repository: NewsSourceRepositoryPort | None = None


def configure_default_news_source_repository(repository: NewsSourceRepositoryPort) -> None:
    """注册全局默认新闻来源仓储（由组合根调用）。"""
    global _default_repository
    _default_repository = repository


def get_default_news_source_repository() -> NewsSourceRepositoryPort:
    """获取全局默认新闻来源仓储；未配置时抛 RuntimeError。"""
    if _default_repository is None:
        raise RuntimeError(
            "NewsSourceRepositoryPort 未配置：请在组合根调用 "
            "configure_default_news_source_repository() 或显式注入 repository 参数。"
        )
    return _default_repository
