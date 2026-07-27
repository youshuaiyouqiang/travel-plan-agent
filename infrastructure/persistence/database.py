"""数据库初始化与兼容 re-export 层（P1 拆分后）。

**历史与现状：** 本文件原为 1271 行单体模块，P1 已将其拆分为：
- ``connection.py`` — 连接生命周期
- ``schema.py`` — 初始 schema 常量
- ``serialization.py`` — JSON 辅助函数
- ``migrations/`` 子包 — 版本组、注册表与执行器

**兼容承诺：** 既有调用方仍可从 ``infrastructure.persistence.database`` 导入
``get_connection``、``reset_connection``、``init_db``、``run_upgrade``、
``downgrade``、``get_migration_status``、``_json_dumps``、``_json_loads``
以及全部 ``_upgrade_N`` / ``_downgrade_N`` 函数。新代码应从拆分后的
模块直接导入。

P1 不修改迁移版本号、SQL 文本或 ``schema_migrations`` 数据。
"""

from __future__ import annotations

import logging
from pathlib import Path

from config import settings

from infrastructure.persistence.connection import get_connection, reset_connection
from infrastructure.persistence.schema import _SCHEMA
# 重新导出：外部代码（含测试）经 database 模块访问 serialization 工具函数。
from infrastructure.persistence.serialization import _json_dumps, _json_loads  # noqa: F401
from infrastructure.persistence.migrations.runner import (
    downgrade,
    get_migration_status,
    run_upgrade,
)

# 迁移函数 re-export — 既有测试直接导入 _upgrade_N / _downgrade_N。
from infrastructure.persistence.migrations.v001_005 import (  # noqa: F401
    _downgrade_1,
    _downgrade_2,
    _downgrade_3,
    _downgrade_4,
    _downgrade_5,
    _upgrade_1,
    _upgrade_2,
    _upgrade_3,
    _upgrade_4,
    _upgrade_5,
)
from infrastructure.persistence.migrations.v006_010 import (  # noqa: F401
    _downgrade_10,
    _downgrade_6,
    _downgrade_7,
    _downgrade_8,
    _downgrade_9,
    _upgrade_10,
    _upgrade_6,
    _upgrade_7,
    _upgrade_8,
    _upgrade_9,
)
from infrastructure.persistence.migrations.v011_015 import (  # noqa: F401
    _downgrade_11,
    _downgrade_12,
    _downgrade_13,
    _downgrade_14,
    _downgrade_15,
    _upgrade_11,
    _upgrade_12,
    _upgrade_13,
    _upgrade_14,
    _upgrade_15,
)
from infrastructure.persistence.migrations.v016_020 import (  # noqa: F401
    _downgrade_16,
    _downgrade_17,
    _downgrade_18,
    _downgrade_19,
    _downgrade_20,
    _upgrade_16,
    _upgrade_17,
    _upgrade_18,
    _upgrade_19,
    _upgrade_20,
)

logger = logging.getLogger(__name__)

__all__ = [
    "downgrade",
    "get_connection",
    "get_migration_status",
    "init_db",
    "reset_connection",
    "run_upgrade",
]


def init_db(db_path: str | Path | None = None) -> None:
    """初始化数据库：执行基础 schema 并运行全部待应用迁移。

    Args:
        db_path: 数据库文件路径；为 None 时取 ``settings.database_path``。

    Note:
        P2.1：初始化后自动注册默认 ``SessionRepositoryPort`` 实现，供
        ``SessionManager`` / ``TaskStateStore`` / ``SessionService`` 在
        未显式注入 repository 时回退使用。组合根亦可显式注入替代。
    """
    conn = get_connection(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    run_upgrade(conn)

    # P2.1：注册默认会话仓储（过渡方案，P3 收敛组合根后可移除全局默认）
    from domain.user.session.ports import configure_default_session_repository
    from infrastructure.persistence.repositories.session import SqliteSessionRepository

    configure_default_session_repository(SqliteSessionRepository())

    # P2.2：注册默认画像仓储
    from domain.user.profile.ports import configure_default_profile_repository
    from infrastructure.persistence.repositories.profile import SqliteProfileRepository

    configure_default_profile_repository(SqliteProfileRepository())

    # P2.3：注册默认用户/令牌仓储与密码哈希器
    from domain.user.auth.ports import (
        configure_default_password_hasher,
        configure_default_token_repository,
        configure_default_user_repository,
    )
    from infrastructure.persistence.repositories.auth import (
        SqliteTokenRepository,
        SqliteUserRepository,
    )
    from infrastructure.security.password_hasher import BcryptPasswordHasher

    configure_default_user_repository(SqliteUserRepository())
    configure_default_token_repository(SqliteTokenRepository())
    configure_default_password_hasher(BcryptPasswordHasher())

    # P2.4：注册默认记忆仓储
    from domain.memory.ports import configure_default_memory_repository
    from infrastructure.persistence.repositories.memory import SqliteMemoryRepository

    configure_default_memory_repository(SqliteMemoryRepository())

    # P2.5：注册默认 agent/feedback/itinerary 仓储
    from domain.agent.ports import configure_default_custom_agent_repository
    from domain.feedback.ports import configure_default_feedback_repository
    from domain.travel.itinerary.ports import configure_default_itinerary_repository
    from infrastructure.persistence.repositories.agent import SqliteCustomAgentRepository
    from infrastructure.persistence.repositories.feedback import SqliteFeedbackRepository
    from infrastructure.persistence.repositories.itinerary import SqliteItineraryRepository

    configure_default_custom_agent_repository(SqliteCustomAgentRepository())
    configure_default_feedback_repository(SqliteFeedbackRepository())
    configure_default_itinerary_repository(SqliteItineraryRepository())

    # P2.6：注册默认新闻来源与旅行草稿仓储
    from application.news.ports import (
        configure_default_news_favorite_repository,
        configure_default_news_source_repository,
    )
    from application.travel.ports import configure_default_travel_repository
    from infrastructure.persistence.news_repository import NewsSourceRepository
    from infrastructure.persistence.repositories.news_favorite import SqliteNewsFavoriteRepository
    from infrastructure.persistence.travel_repository import TravelRepository

    configure_default_news_source_repository(NewsSourceRepository())
    configure_default_news_favorite_repository(SqliteNewsFavoriteRepository())
    configure_default_travel_repository(TravelRepository())

    logger.info("Database initialized: %s", db_path or settings.database_path)
