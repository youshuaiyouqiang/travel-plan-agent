"""domain/feedback/repository.py + domain/user/profile/manager.py + domain/agent/repository.py 单元测试。

这三个 repository 都使用 SQLite，覆盖核心 CRUD 路径。
"""

from __future__ import annotations

import pytest

from domain.agent.repository import CustomAgentRepository
from domain.agent.schema import AgentConfig
from domain.user.profile.manager import ProfileManager
from domain.user.profile.schema import UserProfile
from infrastructure.persistence.database import init_db, reset_connection


class TestProfileManager:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("config.settings.database_path", db_path)
        reset_connection()
        init_db(db_path)

    def test_get_returns_empty_profile_for_unknown_user(self):
        pm = ProfileManager()
        profile = pm.get("u-new")
        assert profile.user_id == "u-new"
        assert profile.interaction_count == 0
        assert profile.tags == []

    def test_update_increments_interaction_count(self):
        pm = ProfileManager()
        pm.update("u1", tags=["travel"])
        pm.update("u1", tags=["travel", "food"])
        profile = pm.get("u1")
        assert profile.interaction_count == 2
        assert profile.tags == ["travel", "food"]

    def test_update_sets_last_intent(self):
        pm = ProfileManager()
        pm.update("u1", intent="search_poi")
        profile = pm.get("u1")
        assert profile.last_intent == "search_poi"

    def test_update_appends_preferred_categories_and_trims(self):
        pm = ProfileManager()
        cats = [f"cat{i}" for i in range(15)]
        for c in cats:
            pm.update("u1", category=c)
        profile = pm.get("u1")
        # 最多保留 10 个
        assert len(profile.preferred_categories) == 10
        # 保留最后 10 个
        assert profile.preferred_categories == cats[-10:]

    def test_update_merges_custom_attributes(self):
        pm = ProfileManager()
        pm.update("u1", custom={"key1": "v1"})
        pm.update("u1", custom={"key2": "v2"})
        profile = pm.get("u1")
        assert profile.custom_attributes == {"key1": "v1", "key2": "v2"}

    def test_build_context_returns_empty_for_new_user(self):
        pm = ProfileManager()
        assert pm.build_context("u-new") == ""

    def test_build_context_renders_profile_summary(self):
        pm = ProfileManager()
        pm.update("u1", tags=["travel"], intent="search", category="food")
        ctx = pm.build_context("u1")
        assert "用户画像" in ctx
        assert "travel" in ctx
        assert "food" in ctx
        assert "search" in ctx

    def test_cache_avoids_repeated_db_loads(self):
        pm = ProfileManager()
        profile1 = pm.get("u1")
        # 第二次 get 应从缓存返回同一对象
        profile2 = pm.get("u1")
        assert profile1 is profile2


class TestCustomAgentRepository:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("config.settings.database_path", db_path)
        reset_connection()
        init_db(db_path)
        # custom_agents.user_id 外键引用 users(id)，需要预先创建 user
        from infrastructure.persistence.database import get_connection
        from infrastructure.security.password import hash_password

        conn = get_connection()
        for uid in ("u1", "u2"):
            conn.execute(
                "INSERT INTO users (user_id, username, password_hash, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (uid, uid, hash_password("dummy-pwd"), "", ""),
            )
        conn.commit()

    def test_create_returns_agent_config(self):
        repo = CustomAgentRepository()
        agent = repo.create(
            "u1",
            name="my-agent",
            description="测试 agent",
            system_prompt="你是测试",
            skills=["s1"],
            mcp_servers=["m1"],
        )
        assert isinstance(agent, AgentConfig)
        assert agent.name == "my-agent"
        assert agent.user_id == "u1"
        assert agent.skills == ["s1"]
        assert agent.mcp_servers == ["m1"]

    def test_get_returns_none_for_unknown(self):
        repo = CustomAgentRepository()
        assert repo.get("does-not-exist") is None

    def test_list_by_user_filters_by_user(self):
        repo = CustomAgentRepository()
        repo.create("u1", name="a1")
        repo.create("u1", name="a2")
        repo.create("u2", name="a3")
        agents = repo.list_by_user("u1")
        assert len(agents) == 2

    def test_list_public_returns_only_published_public(self):
        repo = CustomAgentRepository()
        repo.create("u1", name="public-published", is_public=True, status="published")
        repo.create("u1", name="private-published", is_public=False, status="published")
        repo.create("u1", name="public-draft", is_public=True, status="draft")
        agents = repo.list_public()
        assert len(agents) == 1
        assert agents[0].name == "public-published"

    def test_list_published_by_user(self):
        repo = CustomAgentRepository()
        repo.create("u1", name="published", status="published")
        repo.create("u1", name="draft", status="draft")
        agents = repo.list_published_by_user("u1")
        assert len(agents) == 1
        assert agents[0].name == "published"

    def test_update_changes_fields(self):
        repo = CustomAgentRepository()
        agent = repo.create("u1", name="original", system_prompt="original")
        updated = repo.update(agent.id, name="updated", system_prompt="new prompt")
        assert updated is not None
        assert updated.name == "updated"
        assert updated.system_prompt == "new prompt"

    def test_update_ignores_unknown_fields(self):
        repo = CustomAgentRepository()
        agent = repo.create("u1", name="original")
        # 未知字段不应进入 SQL（白名单过滤）
        updated = repo.update(agent.id, name="new", invalid_field="hack")
        assert updated is not None
        assert updated.name == "new"

    def test_update_with_no_safe_fields_returns_current(self):
        repo = CustomAgentRepository()
        agent = repo.create("u1", name="original")
        updated = repo.update(agent.id, invalid_field="hack")
        assert updated is not None
        assert updated.name == "original"

    def test_update_serializes_skills_and_mcp_servers(self):
        repo = CustomAgentRepository()
        agent = repo.create("u1", name="original")
        updated = repo.update(agent.id, skills=["a", "b"], mcp_servers=["m1"])
        assert updated is not None
        assert updated.skills == ["a", "b"]
        assert updated.mcp_servers == ["m1"]

    def test_delete_removes_agent(self):
        repo = CustomAgentRepository()
        agent = repo.create("u1", name="to-delete")
        assert repo.delete(agent.id) is True
        assert repo.get(agent.id) is None

    def test_delete_unknown_returns_false(self):
        repo = CustomAgentRepository()
        assert repo.delete("does-not-exist") is False
