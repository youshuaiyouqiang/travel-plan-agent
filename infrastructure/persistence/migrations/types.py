"""迁移类型定义。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Migration:
    """单条数据库迁移定义。

    Attributes:
        version: 迁移版本号（1-based，连续递增）。
        description: 人类可读的迁移描述，写入 ``schema_migrations``。
        upgrade: 升级函数，接收 ``sqlite3.Connection`` 执行 DDL/DML。
        downgrade: 降级函数；SQLite <3.35 不支持 DROP COLUMN 时记日志跳过。
    """

    version: int
    description: str
    upgrade: Callable[[Any], None]
    downgrade: Callable[[Any], None]
