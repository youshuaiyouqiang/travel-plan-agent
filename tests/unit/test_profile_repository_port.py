"""P2.2 ProfileRepositoryPort 的 fake 实现与消费者单元测试。

验证 ProfileManager 可通过 fake 端口运行，不创建 SQLite 文件。
"""

from __future__ import annotations



from domain.user.profile.manager import ProfileManager
from domain.user.profile.schema import UserProfile


# ── Fake 实现 ──────────────────────────────────────────────


class FakeProfileRepository:
    """``ProfileRepositoryPort`` 的内存 fake。"""

    def __init__(self) -> None:
        self._profiles: dict[str, UserProfile] = {}

    def load_profile(self, user_id: str) -> UserProfile | None:
        return self._profiles.get(user_id)

    def save_profile(self, profile: UserProfile) -> None:
        self._profiles[profile.user_id] = profile


# ── ProfileManager 单元测试 ────────────────────────────────


class TestProfileManagerWithFake:
    """ProfileManager 通过 fake 端口运行，不创建 SQLite 文件。"""

    def test_get_returns_empty_profile_for_unknown_user(self):
        repo = FakeProfileRepository()
        pm = ProfileManager(repository=repo)
        profile = pm.get("u-new")
        assert profile.user_id == "u-new"
        assert profile.interaction_count == 0
        assert profile.tags == []

    def test_update_increments_interaction_count(self):
        repo = FakeProfileRepository()
        pm = ProfileManager(repository=repo)
        pm.update("u1", tags=["travel"])
        pm.update("u1", tags=["travel", "food"])
        profile = pm.get("u1")
        assert profile.interaction_count == 2
        assert profile.tags == ["travel", "food"]

    def test_update_sets_last_intent(self):
        repo = FakeProfileRepository()
        pm = ProfileManager(repository=repo)
        pm.update("u1", intent="search_poi")
        profile = pm.get("u1")
        assert profile.last_intent == "search_poi"

    def test_update_appends_preferred_categories_and_trims(self):
        repo = FakeProfileRepository()
        pm = ProfileManager(repository=repo)
        cats = [f"cat{i}" for i in range(15)]
        for c in cats:
            pm.update("u1", category=c)
        profile = pm.get("u1")
        assert len(profile.preferred_categories) == 10
        assert profile.preferred_categories == cats[-10:]

    def test_update_merges_custom_attributes(self):
        repo = FakeProfileRepository()
        pm = ProfileManager(repository=repo)
        pm.update("u1", custom={"key1": "v1"})
        pm.update("u1", custom={"key2": "v2"})
        profile = pm.get("u1")
        assert profile.custom_attributes == {"key1": "v1", "key2": "v2"}

    def test_build_context_returns_empty_for_new_user(self):
        repo = FakeProfileRepository()
        pm = ProfileManager(repository=repo)
        assert pm.build_context("u-new") == ""

    def test_build_context_renders_profile_summary(self):
        repo = FakeProfileRepository()
        pm = ProfileManager(repository=repo)
        pm.update("u1", tags=["travel"], intent="search", category="food")
        ctx = pm.build_context("u1")
        assert "用户画像" in ctx
        assert "travel" in ctx
        assert "food" in ctx
        assert "search" in ctx

    def test_cache_avoids_repeated_loads(self):
        repo = FakeProfileRepository()
        pm = ProfileManager(repository=repo)
        profile1 = pm.get("u1")
        profile2 = pm.get("u1")
        assert profile1 is profile2

    def test_persistence_across_manager_instances(self):
        """保存后，新的 ProfileManager 实例能从 fake 重新加载。"""
        repo = FakeProfileRepository()
        pm1 = ProfileManager(repository=repo)
        pm1.update("u1", tags=["travel"], intent="search")

        pm2 = ProfileManager(repository=repo)
        profile = pm2.get("u1")
        assert profile.tags == ["travel"]
        assert profile.last_intent == "search"
        assert profile.interaction_count == 1


# ── 端口协议验证 ────────────────────────────────────────────


class TestProfileRepositoryPort:
    """验证 SqliteProfileRepository 和 FakeProfileRepository 均满足端口协议。"""

    def test_fake_satisfies_port(self):
        from domain.user.profile.ports import ProfileRepositoryPort

        repo = FakeProfileRepository()
        assert isinstance(repo, ProfileRepositoryPort)

    def test_sqlite_satisfies_port(self):
        from domain.user.profile.ports import ProfileRepositoryPort
        from infrastructure.persistence.repositories.profile import SqliteProfileRepository

        repo = SqliteProfileRepository()
        assert isinstance(repo, ProfileRepositoryPort)
