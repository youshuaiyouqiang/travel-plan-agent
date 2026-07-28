"""不可变迁移注册表。

按固定顺序导入版本组并拼接为 ``tuple``，保证注册表不可变。
版本号必须连续 1..21 且不重复；runner 依赖此顺序执行迁移。
"""

from __future__ import annotations

from infrastructure.persistence.migrations.types import Migration
from infrastructure.persistence.migrations.v001_005 import MIGRATIONS as _v001_005
from infrastructure.persistence.migrations.v006_010 import MIGRATIONS as _v006_010
from infrastructure.persistence.migrations.v011_015 import MIGRATIONS as _v011_015
from infrastructure.persistence.migrations.v016_020 import MIGRATIONS as _v016_020
from infrastructure.persistence.migrations.v021_025 import MIGRATIONS as _v021_025

#: 不可变迁移注册表；按版本号升序排列。
MIGRATIONS: tuple[Migration, ...] = (
    _v001_005 + _v006_010 + _v011_015 + _v016_020 + _v021_025
)


def _validate_registry() -> None:
    """启动期自检：版本恰为 1..N 连续且不重复。"""
    versions = [m.version for m in MIGRATIONS]
    expected = list(range(1, len(versions) + 1))
    if versions != expected:
        raise RuntimeError(
            f"Migration registry corrupted: versions={versions}, expected={expected}"
        )


_validate_registry()
