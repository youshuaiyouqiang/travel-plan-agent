from __future__ import annotations

from typing import Optional

from domain.agent.ports import (
    CustomAgentRepositoryPort,
    get_default_custom_agent_repository,
)
from domain.agent.schema import AgentConfig


class CustomAgentRepository:
    """自定义智能体仓储；通过 ``CustomAgentRepositoryPort`` 访问持久化层。

    P2.5：原直连 ``get_connection()`` 的 SQL 已下沉到
    ``infrastructure.persistence.repositories.agent.SqliteCustomAgentRepository``。
    本类只负责委托持久化操作，保持既有调用方的无参构造兼容。
    """

    def __init__(self, repository: CustomAgentRepositoryPort | None = None) -> None:
        self._repository = repository or get_default_custom_agent_repository()

    def create(self, user_id: str, **fields: object) -> AgentConfig:
        return self._repository.create(user_id, **fields)

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        return self._repository.get(agent_id)

    def list_by_user(self, user_id: str) -> list[AgentConfig]:
        return self._repository.list_by_user(user_id)

    def list_public(self) -> list[AgentConfig]:
        return self._repository.list_public()

    def list_published_by_user(self, user_id: str) -> list[AgentConfig]:
        return self._repository.list_published_by_user(user_id)

    def update(self, agent_id: str, **fields: object) -> Optional[AgentConfig]:
        return self._repository.update(agent_id, **fields)

    def delete(self, agent_id: str) -> bool:
        return self._repository.delete(agent_id)
