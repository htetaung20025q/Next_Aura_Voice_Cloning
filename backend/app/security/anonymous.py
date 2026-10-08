import hashlib
import hmac
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from app.config import get_settings


def generate_signed_anonymous_token() -> str:
    """
    Generates a cryptographically signed anonymous session token.
    Format: <uuid>.<timestamp>.<hmac_signature>
    """
    settings = get_settings()
    anon_id = uuid.uuid4().hex
    ts = str(int(time.time()))
    data_to_sign = f"{anon_id}.{ts}".encode("utf-8")
    sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), data_to_sign, hashlib.sha256).hexdigest()
    return f"{anon_id}.{ts}.{sig}"


def verify_and_extract_anonymous_id(token: Optional[str]) -> Optional[str]:
    """
    Verifies the HMAC signature and extracts the anonymous ID.
    Returns the anonymous ID if valid, or None if invalid/tampered.
    """
    if not token or not isinstance(token, str):
        return None

    parts = token.strip().split(".")
    if len(parts) != 3:
        return None

    anon_id, ts, sig = parts
    if len(anon_id) != 32 or not anon_id.isalnum():
        return None

    settings = get_settings()
    data_to_sign = f"{anon_id}.{ts}".encode("utf-8")
    expected_sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), data_to_sign, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        return None

    return anon_id


def get_ip_abuse_hash(client_ip: str) -> str:
    """
    Generates a salted weekly rotating hash of the client IP.
    This provides abuse prevention without storing raw IP addresses permanently.
    """
    settings = get_settings()
    # Rotating weekly salt based on ISO calendar week
    now = datetime.now(timezone.utc)
    week_str = f"{now.year}-W{now.isocalendar().week}"
    key = f"{settings.SECRET_KEY}:ip-salt:{week_str}".encode("utf-8")
    return hmac.new(key, client_ip.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
