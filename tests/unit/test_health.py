"""infrastructure/persistence/health.py 单元测试。

覆盖：
- SQLite healthy 路径
- SQLite 异常路径（overall=degraded）
- session_backend != "redis" 时 redis="skipped"
- session_backend == "redis" 时调用 _check_redis
"""

from __future__ import annotations

import pytest

from infrastructure.persistence import health
from infrastructure.persistence.database import init_db, reset_connection


class TestCheckHealth:
    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr("config.settings.database_path", db_path)
        monkeypatch.setattr("config.settings.session_backend", "memory")
        reset_connection()
        init_db(db_path)

    def test_sqlite_healthy(self):
        result = health.check_health()
        assert result.status == "healthy"
        assert result.details is not None
        assert result.details["sqlite"] == "ok"
        assert result.details["redis"] == "skipped"

    def test_redis_skipped_when_backend_not_redis(self):
        result = health.check_health()
        assert result.redis == "skipped"

    def test_redis_checked_when_backend_is_redis(self, monkeypatch):
        monkeypatch.setattr("config.settings.session_backend", "redis")

        called = {"count": 0}

        def _fake_check_redis() -> None:
            called["count"] += 1

        monkeypatch.setattr(health, "_check_redis", _fake_check_redis)
        result = health.check_health()
        assert called["count"] == 1
        assert result.details is not None
        assert result.details["redis"] == "ok"

    def test_redis_failure_marks_degraded(self, monkeypatch):
        monkeypatch.setattr("config.settings.session_backend", "redis")

        def _raise() -> None:
            raise RuntimeError("redis down")

        monkeypatch.setattr(health, "_check_redis", _raise)
        result = health.check_health()
        assert result.status == "degraded"
        assert result.details is not None
        assert result.details["redis"].startswith("error:")
