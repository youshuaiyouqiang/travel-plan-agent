"""SQLite 连接生命周期管理。

从 ``database.py`` 拆分（P1），仅负责线程局部连接的获取、复用与重置。
所有 SQL 和迁移逻辑在 ``migrations/`` 子包中。
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from threading import local

from config import settings

logger = logging.getLogger(__name__)

_local = local()


def reset_connection() -> None:
    """关闭并清除当前线程的连接缓存。

    测试在切换临时数据库路径时调用，避免复用旧路径的连接。
    """
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    _local.conn = None
    _local.db_path_str = None


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """获取或创建当前线程的 SQLite 连接。

    连接按 ``db_path`` 缓存在线程局部存储中；路径变化时自动重建。
    启用 WAL 日志模式和外键约束，行工厂为 ``sqlite3.Row``。

    Args:
        db_path: 数据库文件路径；为 None 时取 ``settings.database_path``。

    Returns:
        已配置的 ``sqlite3.Connection``。
    """
    db_path = Path(db_path) if db_path else settings.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path_str = str(db_path.resolve())
    conn = getattr(_local, "conn", None)
    current_path = getattr(_local, "db_path_str", None)
    if conn is not None and current_path == db_path_str:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.Error:
            pass
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    conn = sqlite3.connect(db_path_str, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    _local.conn = conn
    _local.db_path_str = db_path_str
    return conn
