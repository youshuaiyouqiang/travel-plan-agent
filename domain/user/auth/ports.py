"""用户、令牌与密码哈希的持久化端口。

P2.3 引入：将 ``users`` / ``auth_token_hashes`` 表的访问以及密码哈希计算
从 domain 层下沉到 infrastructure，领域层只消费这些端口。

端口由消费方（domain）定义：
- ``UserRepositoryPort`` — 由 ``infrastructure.persistence.repositories.auth``
  提供 ``SqliteUserRepository`` 实现。
- ``TokenRepositoryPort`` — 同上，提供 ``SqliteTokenRepository`` 实现。
- ``PasswordHasherPort`` — 由 ``infrastructure.security.password_hasher``
  提供 ``BcryptPasswordHasher`` 实现（包装既有 ``infrastructure.security.password``
  模块函数，保持哈希算法与向后兼容行为不变）。

在组合根（``init_db()``）中装配默认实例。测试可用 fake 实现替代，不创建
SQLite 文件、不依赖 bcrypt。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # 避免循环导入；Protocol 仅用于静态类型检查
    from domain.user.auth.auth import User


@runtime_checkable
class UserRepositoryPort(Protocol):
    """``users`` 表的读写端口。

    实现必须保证：
    - 所有 SQL 参数化；
    - ``load_all`` 返回全量用户行，供 ``UserStore`` 构建内存缓存与 username 索引；
    - ``insert`` 与 ``update_password`` 调用后立即 commit。
    """

    def load_all(self) -> list[User]:
        """加载全部用户；用于 UserStore 的 TTL 缓存重建。"""
        ...

    def insert(self, user: User) -> None:
        """插入新用户行（user_id / username / password_hash / created_at / updated_at）。"""
        ...

    def update_password(self, user_id: str, password_hash: str, updated_at: str) -> None:
        """更新指定用户的密码哈希与 updated_at（PBKDF2 → bcrypt 自动升级路径）。"""
        ...


@runtime_checkable
class TokenRepositoryPort(Protocol):
    """``auth_token_hashes`` 表的读写端口。

    实现必须保证：
    - 所有 SQL 参数化，仅以 ``sha256(token)`` 作为 key，原始 token 永不落盘；
    - 表不存在时按 ``CREATE TABLE IF NOT EXISTS`` 幂等创建（防御性，迁移 12 已建表）；
    - ``find`` 返回 ``(user_id, expires_at)`` 元组，不存在返回 None；
    - 写操作调用后立即 commit。
    """

    def insert(self, token_hash: str, user_id: str, expires_at: float) -> None:
        """插入新 token 哈希行。"""
        ...

    def find(self, token_hash: str) -> tuple[str, float] | None:
        """按 token 哈希查询 (user_id, expires_at)；不存在返回 None。"""
        ...

    def delete_expired(self, now: float) -> None:
        """删除所有 expires_at < now 的过期行。"""
        ...

    def delete(self, token_hash: str) -> None:
        """按 token 哈希删除单行（撤销 token）。"""
        ...


@runtime_checkable
class PasswordHasherPort(Protocol):
    """密码哈希端口。

    实现必须保证：
    - ``hash`` 优先使用 bcrypt，bcrypt 不可用时回退 PBKDF2；
    - ``verify`` 同时兼容 bcrypt 与历史 PBKDF2 哈希；
    - ``needs_upgrade`` 对非 bcrypt 哈希返回 True，供自动升级路径判定。
    """

    def hash(self, password: str) -> str:
        """计算密码哈希。"""
        ...

    def verify(self, password: str, stored: str) -> bool:
        """校验密码与存储哈希是否匹配。"""
        ...

    def needs_upgrade(self, stored: str) -> bool:
        """判断存储哈希是否需要升级到 bcrypt。"""
        ...


# ── 默认仓储装配（过渡方案，同 P2.1/P2.2）─────────────────────
#
# 组合根（``app.py`` 的 ``build_orchestrator``）或 ``init_db()`` 在初始化
# 数据库后调用 ``configure_default_*`` 注册 SQLite 实现。domain 消费者在
# 未显式注入时回退到此默认值，从而保持既有测试的 ``UserStore()`` 无参
# 构造与 ``generate_token()`` / ``verify_token()`` 模块级调用兼容。
# P3 收敛组合根后，路由改为从容器取服务，这些全局变量可移除。

_default_user_repository: UserRepositoryPort | None = None
_default_token_repository: TokenRepositoryPort | None = None
_default_password_hasher: PasswordHasherPort | None = None


def configure_default_user_repository(repository: UserRepositoryPort) -> None:
    """注册全局默认用户仓储（由组合根调用）。"""
    global _default_user_repository
    _default_user_repository = repository


def get_default_user_repository() -> UserRepositoryPort:
    """获取全局默认用户仓储；未配置时抛 RuntimeError。"""
    if _default_user_repository is None:
        raise RuntimeError(
            "UserRepositoryPort 未配置：请在组合根调用 "
            "configure_default_user_repository() 或显式注入 repository 参数。"
        )
    return _default_user_repository


def configure_default_token_repository(repository: TokenRepositoryPort) -> None:
    """注册全局默认令牌仓储（由组合根调用）。"""
    global _default_token_repository
    _default_token_repository = repository


def get_default_token_repository() -> TokenRepositoryPort:
    """获取全局默认令牌仓储；未配置时抛 RuntimeError。"""
    if _default_token_repository is None:
        raise RuntimeError(
            "TokenRepositoryPort 未配置：请在组合根调用 "
            "configure_default_token_repository() 或显式注入 repository 参数。"
        )
    return _default_token_repository


def configure_default_password_hasher(hasher: PasswordHasherPort) -> None:
    """注册全局默认密码哈希器（由组合根调用）。"""
    global _default_password_hasher
    _default_password_hasher = hasher


def get_default_password_hasher() -> PasswordHasherPort:
    """获取全局默认密码哈希器；未配置时抛 RuntimeError。"""
    if _default_password_hasher is None:
        raise RuntimeError(
            "PasswordHasherPort 未配置：请在组合根调用 "
            "configure_default_password_hasher() 或显式注入 hasher 参数。"
        )
    return _default_password_hasher
