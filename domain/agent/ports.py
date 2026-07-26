"""自定义智能体仓储端口。

P2.5 引入：将 ``custom_agents`` 表的访问从 domain 层下沉到 infrastructure，
领域层只消费此端口。

端口由消费方（domain）定义，由 ``infrastructure.persistence.repositories.agent``
提供 ``SqliteCustomAgentRepository`` 实现，在 ``init_db()`` 中装配默认实例。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # 避免循环导入；Protocol 仅用于静态类型检查
    from domain.agent.schema import AgentConfig


@runtime_checkable
class CustomAgentRepositoryPort(Protocol):
    """``custom_agents`` 表的读写端口。

    实现必须保证：
    - 所有 SQL 参数化；``update`` 的字段白名单在实现层硬编码，拒绝非白名单字段；
    - ``skills`` / ``mcp_servers`` 以 JSON 序列化存储；
    - ``create`` 返回完整 ``AgentConfig``（内部先 INSERT 再 SELECT）。
    """

    def create(self, user_id: str, **fields: object) -> AgentConfig:
        """创建自定义智能体，返回完整配置。"""
        ...

    def get(self, agent_id: str) -> AgentConfig | None:
        """按 ID 查询智能体；不存在返回 None。"""
        ...

    def list_by_user(self, user_id: str) -> list[AgentConfig]:
        """列出用户全部智能体，按 updated_at 倒序。"""
        ...

    def list_public(self) -> list[AgentConfig]:
        """列出全部公开已发布智能体，按 created_at 倒序。"""
        ...

    def list_published_by_user(self, user_id: str) -> list[AgentConfig]:
        """列出用户已发布智能体（AgentCenter 只展示 published）。"""
        ...

    def update(self, agent_id: str, **fields: object) -> AgentConfig | None:
        """按白名单字段更新智能体；无白名单字段时返回当前值。"""
        ...

    def delete(self, agent_id: str) -> bool:
        """删除智能体；返回是否删除成功。"""
        ...


# ── 默认仓储装配（过渡方案，同 P2.1–P2.4）───────────────────

_default_repository: CustomAgentRepositoryPort | None = None


def configure_default_custom_agent_repository(repository: CustomAgentRepositoryPort) -> None:
    """注册全局默认自定义智能体仓储（由组合根调用）。"""
    global _default_repository
    _default_repository = repository


def get_default_custom_agent_repository() -> CustomAgentRepositoryPort:
    """获取全局默认自定义智能体仓储；未配置时抛 RuntimeError。"""
    if _default_repository is None:
        raise RuntimeError(
            "CustomAgentRepositoryPort 未配置：请在组合根调用 "
            "configure_default_custom_agent_repository() 或显式注入 repository 参数。"
        )
    return _default_repository
