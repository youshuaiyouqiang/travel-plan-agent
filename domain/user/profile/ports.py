"""用户画像持久化端口。

P2.2 引入：将 ``profiles`` 表的访问从 domain 层下沉到 infrastructure，
领域层只消费此端口。

端口由消费方（domain）定义，由 ``infrastructure.persistence.repositories.profile``
提供 SQLite 实现，在 ``init_db()`` 中装配默认实例。测试可用 fake 实现替代。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # 避免循环导入；Protocol 仅用于静态类型检查
    from domain.user.profile.schema import UserProfile


@runtime_checkable
class ProfileRepositoryPort(Protocol):
    """用户画像的读写端口。

    实现必须保证：
    - 所有 SQL 参数化；
    - ``load_profile`` 在用户不存在时返回 ``None``（由调用方决定默认值）；
    - ``save_profile`` 使用 upsert 语义（INSERT ... ON CONFLICT DO UPDATE）。
    """

    def load_profile(self, user_id: str) -> UserProfile | None:
        """加载用户画像；不存在返回 None。"""
        ...

    def save_profile(self, profile: UserProfile) -> None:
        """Upsert 用户画像行。"""
        ...


# ── 默认仓储装配（过渡方案，同 P2.1）─────────────────────────

_default_repository: ProfileRepositoryPort | None = None


def configure_default_profile_repository(repository: ProfileRepositoryPort) -> None:
    """注册全局默认画像仓储（由组合根调用）。"""
    global _default_repository
    _default_repository = repository


def get_default_profile_repository() -> ProfileRepositoryPort:
    """获取全局默认画像仓储；未配置时抛 RuntimeError。"""
    if _default_repository is None:
        raise RuntimeError(
            "ProfileRepositoryPort 未配置：请在组合根调用 "
            "configure_default_profile_repository() 或显式注入 repository 参数。"
        )
    return _default_repository
