"""``PasswordHasherPort`` 的 bcrypt 实现。

P2.3 将原本被 ``domain/user/auth/auth.py`` 直接调用的
``infrastructure.security.password`` 模块函数包装为端口实现，保持哈希算法、
bcrypt/PBKDF2 回退与向后兼容行为完全不变。

domain 层通过 ``PasswordHasherPort`` 消费；组合根（``init_db()``）装配此实现。
"""

from __future__ import annotations

from infrastructure.security import password as _password


class BcryptPasswordHasher:
    """``PasswordHasherPort`` 的 bcrypt 实现。

    委托给既有 ``infrastructure.security.password`` 模块函数：
    - ``hash`` → ``password.hash_password``（bcrypt 优先，回退 PBKDF2）
    - ``verify`` → ``password.verify_password``（兼容 bcrypt 与历史 PBKDF2）
    - ``needs_upgrade`` → ``password.needs_upgrade``（非 bcrypt 哈希需升级）

    无状态，可单例复用。模块以 ``_password`` 别名导入，避免与方法参数
    ``password`` 同名遮蔽。
    """

    def hash(self, password: str) -> str:
        """计算密码哈希（bcrypt 优先，回退 PBKDF2）。"""
        return _password.hash_password(password)

    def verify(self, password: str, stored: str) -> bool:
        """校验密码与存储哈希是否匹配（兼容 bcrypt 与 PBKDF2）。"""
        return _password.verify_password(password, stored)

    def needs_upgrade(self, stored: str) -> bool:
        """判断存储哈希是否需要升级到 bcrypt。"""
        return _password.needs_upgrade(stored)


__all__ = ["BcryptPasswordHasher"]
