import hashlib
import hmac
import re
from typing import Tuple
import bcrypt


def _prepare_password_bytes(password: str) -> bytes:
    """
    Pre-hash the password with SHA-256 before feeding into bcrypt.
    This safely prevents:
    1. The bcrypt 72-byte truncation vulnerability (any password length becomes 32 bytes).
    2. CPU-exhaustion DoS attacks from maliciously long passwords.
    """
    return hashlib.sha256(password.encode("utf-8")).digest()


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """
    Validates password constraints.
    - Min length: 8 characters
    - Max length: 128 characters (prevent excessive payload size)
    """
    if not password:
        return False, "Password is required."
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if len(password) > 128:
        return False, "Password cannot exceed 128 characters."
    return True, ""


def hash_password(password: str) -> str:
    """
    Hash a password securely using SHA-256 pre-hashing + bcrypt (work factor 12).
    """
    prepared = _prepare_password_bytes(password)
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(prepared, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plaintext password against a stored bcrypt hash in constant time.
    Supports both new SHA-256 pre-hashed format and legacy unhashed format for backward compatibility.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        # Check standard pre-hashed password
        prepared = _prepare_password_bytes(plain_password)
        if bcrypt.checkpw(prepared, hashed_password.encode("utf-8")):
            return True

        # Fallback check for legacy un-prehashed bcrypt hashes
        legacy_bytes = plain_password.encode("utf-8")[:72]
        if bcrypt.checkpw(legacy_bytes, hashed_password.encode("utf-8")):
            return True

        return False
    except Exception:
        return False
