"""数据库迁移子包（P1 拆分）.

按版本组组织迁移函数，通过 registry 构造不可变注册表，runner 负责执行。
迁移版本号、SQL 文本与 ``schema_migrations`` 数据与拆分前完全一致。
"""

from __future__ import annotations

from infrastructure.persistence.migrations.types import Migration

__all__ = ["Migration"]
