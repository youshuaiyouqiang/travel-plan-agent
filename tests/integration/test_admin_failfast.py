"""P1-2 — 生产环境 YUNHE_ADMIN_USERNAME 缺失或找不到用户时，服务必须启动失败。

业务红线：
- 管理员身份只能从服务端配置 ``YUNHE_ADMIN_USERNAME`` 取得，不接受客户端传入。
- 生产环境（``environment == "production"``）下，``YUNHE_ADMIN_USERNAME`` 缺失
  或找不到对应用户时，启动期必须 fail-fast 抛 ``RuntimeError``，禁止静默降级。
- 开发环境允许缺失/找不到，仅记录 warning，``admin_user_id`` 解析为 None。

参考：``docs/FINAL_ACCEPTANCE_REVIEW_2026-07-19.md`` P1-2。
"""

from __future__ import annotations

import pytest

from config import settings
from domain.user.auth.auth import UserStore
from infrastructure.persistence.database import init_db, reset_connection
from api.server import resolve_admin_user_id


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_admin_failfast.db"
    monkeypatch.setattr("config.settings.database_path", db_path)
    reset_connection()
    init_db(db_path)
    yield db_path
    reset_connection()


# ---------------------------------------------------------------------------
# 生产环境 fail-fast
# ---------------------------------------------------------------------------


def test_production_missing_admin_username_raises(db, monkeypatch):
    """生产环境：YUNHE_ADMIN_USERNAME 为空 → RuntimeError。"""
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "admin_username", "")
    with pytest.raises(RuntimeError, match="YUNHE_ADMIN_USERNAME"):
        resolve_admin_user_id()


def test_production_admin_user_not_found_raises(db, monkeypatch):
    """生产环境：YUNHE_ADMIN_USERNAME 配置但用户不存在 → RuntimeError。"""
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "admin_username", "ghost-admin")
    with pytest.raises(RuntimeError, match="ghost-admin"):
        resolve_admin_user_id()


def test_production_admin_resolves_when_user_exists(db, monkeypatch):
    """生产环境：YUNHE_ADMIN_USERNAME 配置且用户存在 → 返回 user_id。"""
    monkeypatch.setattr(settings, "environment", "production")
    user = UserStore().create("root-admin", "secret123")
    monkeypatch.setattr(settings, "admin_username", "root-admin")
    admin_id = resolve_admin_user_id()
    assert admin_id == user.user_id


# ---------------------------------------------------------------------------
# 开发环境宽松降级
# ---------------------------------------------------------------------------


def test_development_missing_admin_username_returns_none(db, monkeypatch):
    """开发环境：YUNHE_ADMIN_USERNAME 为空 → 返回 None，不抛错。"""
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "admin_username", "")
    assert resolve_admin_user_id() is None


def test_development_admin_user_not_found_returns_none(db, monkeypatch):
    """开发环境：YUNHE_ADMIN_USERNAME 配置但用户不存在 → 返回 None，不抛错。"""
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "admin_username", "ghost-admin")
    assert resolve_admin_user_id() is None


def test_development_admin_resolves_when_user_exists(db, monkeypatch):
    """开发环境：YUNHE_ADMIN_USERNAME 配置且用户存在 → 返回 user_id。"""
    monkeypatch.setattr(settings, "environment", "development")
    user = UserStore().create("dev-admin", "secret123")
    monkeypatch.setattr(settings, "admin_username", "dev-admin")
    admin_id = resolve_admin_user_id()
    assert admin_id == user.user_id
