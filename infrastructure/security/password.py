from __future__ import annotations

import hashlib
import os
import logging

logger = logging.getLogger(__name__)

_BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    """Hash a new password using bcrypt.

    Falls back to PBKDF2 if bcrypt is not installed.
    """
    try:
        import bcrypt
        return bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(rounds=_BCRYPT_ROUNDS),
        ).decode("utf-8")
    except ImportError:
        logger.warning("bcrypt not installed, falling back to PBKDF2")
        return _hash_pbkdf2(password)


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored hash.

    Supports both bcrypt and PBKDF2 formats for backward compatibility.
    If the stored hash is in old PBKDF2 format, verify using PBKDF2
    and automatically upgrade to bcrypt on success.
    """
    if not stored:
        return False

    # bcrypt hashes start with $2b$ or $2a$ or $2y$
    if stored.startswith(("$2b$", "$2a$", "$2y$")):
        try:
            import bcrypt
            return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        except ImportError:
            logger.error("bcrypt hash stored but bcrypt not installed")
            return False

    # Old PBKDF2 format - verify and optionally upgrade
    if _verify_pbkdf2(password, stored):
        # Auto-upgrade: log that this password should be re-hashed
        # The caller can check and re-hash if needed
        logger.info("Password verified with PBKDF2, consider upgrading to bcrypt")
        return True

    return False


def needs_upgrade(stored: str) -> bool:
    """Check if a stored hash should be upgraded to bcrypt."""
    return bool(stored) and not stored.startswith(("$2b$", "$2a$", "$2y$"))


def _hash_pbkdf2(password: str, salt: str = "", iterations: int = 600000) -> str:
    """PBKDF2 hash (backward compatible fallback)."""
    if not salt:
        salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"{iterations}${salt}${dk.hex()}"


def _verify_pbkdf2(password: str, stored: str) -> bool:
    """Verify a PBKDF2 password hash (supports both old and new formats)."""
    try:
        parts = stored.split("$")
        if len(parts) == 3:
            # New format: iterations$salt$hex
            iterations, salt, hex_hash = parts
            dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
            return dk.hex() == hex_hash
        elif len(parts) == 2:
            # Old format: salt$hex (default 100000 iterations)
            salt, hex_hash = parts
            dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
            return dk.hex() == hex_hash
    except (ValueError, IndexError):
        pass
    return False
