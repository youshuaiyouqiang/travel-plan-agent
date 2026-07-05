from __future__ import annotations
import json
import time
import secrets
from typing import Optional

from infrastructure.persistence.database import get_connection  # 注意:实际函数名是 get_connection,不是 get_conn
from domain.agent.schema import AgentConfig


class CustomAgentRepository:
    """自定义智能体的数据库操作。

    职责单一：只负责 AgentConfig 的持久化 CRUD。
    不包含任何业务逻辑（如 Prompt 构建、LLM 调用）。
    返回值统一为 AgentConfig，与内置智能体模型一致。

    注意：get_connection() 返回 sqlite3.Connection，不是上下文管理器，
    需要手动 commit() 和 close()。
    """

    _ALLOWED_FIELDS = {
        "name",
        "description",
        "icon",
        "system_prompt",
        "skills",
        "mcp_servers",
        "welcome_message",
        "temperature",
        "is_public",
        "status",
    }

    def create(self, user_id: str, **fields) -> AgentConfig:
        agent_id = secrets.token_hex(8)
        now = time.strftime("%Y-%m-%dT%H:%M:%S")

        conn = get_connection()
        try:
            conn.execute(
                """INSERT INTO custom_agents
                   (id, user_id, name, description, icon, system_prompt, skills,
                    mcp_servers, status, welcome_message, temperature, is_public, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    agent_id,
                    user_id,
                    fields.get("name", ""),
                    fields.get("description", ""),
                    fields.get("icon", "🤖"),
                    fields.get("system_prompt", ""),
                    json.dumps(fields.get("skills", [])),
                    json.dumps(fields.get("mcp_servers", [])),
                    fields.get("status", "published"),
                    fields.get("welcome_message", ""),
                    fields.get("temperature", 0.7),
                    fields.get("is_public", False),
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return self.get(agent_id)  # type: ignore

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        conn = get_connection()
        try:
            row = conn.execute("SELECT * FROM custom_agents WHERE id = ?", (agent_id,)).fetchone()
        finally:
            conn.close()
        return self._row_to_config(row) if row else None

    def list_by_user(self, user_id: str) -> list[AgentConfig]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM custom_agents WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_config(row) for row in rows]

    def list_public(self) -> list[AgentConfig]:
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM custom_agents WHERE is_public = 1 AND status = 'published' ORDER BY created_at DESC"
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_config(row) for row in rows]

    def list_published_by_user(self, user_id: str) -> list[AgentConfig]:
        """列出用户已发布的智能体（AgentCenter 只展示 published）。"""
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM custom_agents WHERE user_id = ? AND status = 'published' ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        finally:
            conn.close()
        return [self._row_to_config(row) for row in rows]

    def update(self, agent_id: str, **fields) -> Optional[AgentConfig]:
        # 白名单过滤，防止 SQL 注入
        safe_fields = {k: v for k, v in fields.items() if k in self._ALLOWED_FIELDS}
        if not safe_fields:
            return self.get(agent_id)

        if "skills" in safe_fields:
            safe_fields["skills"] = json.dumps(safe_fields["skills"])
        if "mcp_servers" in safe_fields:
            safe_fields["mcp_servers"] = json.dumps(safe_fields["mcp_servers"])
        safe_fields["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

        set_clause = ", ".join(f"{k} = ?" for k in safe_fields)
        values = list(safe_fields.values()) + [agent_id]

        conn = get_connection()
        try:
            conn.execute(f"UPDATE custom_agents SET {set_clause} WHERE id = ?", values)
            conn.commit()
        finally:
            conn.close()
        return self.get(agent_id)

    def delete(self, agent_id: str) -> bool:
        conn = get_connection()
        try:
            cursor = conn.execute("DELETE FROM custom_agents WHERE id = ?", (agent_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def _row_to_config(self, row) -> AgentConfig:
        """数据库行 → AgentConfig（统一模型）。"""
        return AgentConfig(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            icon=row["icon"],
            system_prompt=row["system_prompt"],
            skills=json.loads(row["skills"]),
            mcp_servers=json.loads(row["mcp_servers"] or "[]"),
            welcome_message=row["welcome_message"],
            temperature=row["temperature"],
            source="custom",
            is_public=bool(row["is_public"]),
            status=row["status"] if "status" in row.keys() else "published",
            user_id=row["user_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
