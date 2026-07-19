"""infrastructure/security/password.py 单元测试。"""

from __future__ import annotations

import pytest

from infrastructure.security import password


class TestPasswordHashing:
    def test_hash_password_returns_non_empty_string(self):
        h = password.hash_password("my-secret-123")
        assert isinstance(h, str)
        assert len(h) > 0
        assert h != "my-secret-123"

    def test_verify_password_with_correct_password(self):
        h = password.hash_password("my-secret-123")
        assert password.verify_password("my-secret-123", h) is True

    def test_verify_password_with_wrong_password(self):
        h = password.hash_password("my-secret-123")
        assert password.verify_password("wrong", h) is False

    def test_verify_password_with_empty_stored_returns_false(self):
        assert password.verify_password("any", "") is False

    def test_needs_upgrade_for_pbkdf2(self):
        h = password._hash_pbkdf2("test")
        assert password.needs_upgrade(h) is True

    def test_needs_upgrade_false_for_bcrypt(self):
        h = password.hash_password("test")
        # 如果 bcrypt 可用，则不需要升级；否则 PBKDF2 仍需升级
        if h.startswith(("$2b$", "$2a$", "$2y$")):
            assert password.needs_upgrade(h) is False
        else:
            assert password.needs_upgrade(h) is True

    def test_needs_upgrade_false_for_empty(self):
        assert password.needs_upgrade("") is False

    def test_pbkdf2_hash_and_verify(self):
        h = password._hash_pbkdf2("my-password")
        assert password._verify_pbkdf2("my-password", h) is True
        assert password._verify_pbkdf2("wrong", h) is False

    def test_pbkdf2_verify_old_format(self):
        # 旧格式：salt$hex (100000 iterations)
        import hashlib

        salt = "abcd1234"
        dk = hashlib.pbkdf2_hmac("sha256", b"my-password", salt.encode("utf-8"), 100000)
        h = f"{salt}${dk.hex()}"
        assert password._verify_pbkdf2("my-password", h) is True
        assert password._verify_pbkdf2("wrong", h) is False

    def test_pbkdf2_verify_invalid_format_returns_false(self):
        assert password._verify_pbkdf2("any", "not-a-valid-hash") is False
        assert password._verify_pbkdf2("any", "a$b$c$d") is False

    def test_verify_password_with_pbkdf2_stored(self):
        h = password._hash_pbkdf2("legacy-password")
        # 即使 bcrypt 可用，也应能验证 PBKDF2 哈希
        assert password.verify_password("legacy-password", h) is True
        assert password.verify_password("wrong", h) is False

    def test_verify_password_bcrypt_stored_but_bcrypt_unavailable(self, monkeypatch):
        # 模拟 bcrypt 不可用：hash_password 会回退到 PBKDF2
        h = password.hash_password("my-pwd")
        if not h.startswith(("$2b$", "$2a$", "$2y$")):
            pytest.skip("bcrypt not installed, no bcrypt hash to test")

        # 强制 bcrypt 验证路径抛 ImportError
        import builtins

        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "bcrypt":
                raise ImportError("simulated")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        assert password.verify_password("my-pwd", h) is False
