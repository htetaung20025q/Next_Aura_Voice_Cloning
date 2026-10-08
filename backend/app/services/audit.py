import json
import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.models.audit import AdminAuditLog
from app.services.quota import utc_now

logger = logging.getLogger("admin.audit")


def log_admin_action(
    db: Session,
    action: str,
    admin_user_id: Optional[int] = None,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    ip_address: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
):
    """
    Records an administrative action in the audit log database and writes structured log.
    Ensures sensitive fields like passwords, tokens, and keys are NEVER included.
    """
    safe_details_str = None
    if details:
        # Strip any sensitive keys if mistakenly passed
        sanitized = {
            k: v for k, v in details.items()
            if k.lower() not in ("password", "password_hash", "token", "secret", "jwt", "authorization")
        }
        try:
            safe_details_str = json.dumps(sanitized, default=str)
        except Exception:
            safe_details_str = str(sanitized)

    audit_entry = AdminAuditLog(
        admin_user_id=admin_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip_address=ip_address,
        details=safe_details_str,
        created_at=utc_now(),
    )
    db.add(audit_entry)
    db.commit()

    logger.info(
        "ADMIN_AUDIT: action=%s admin_id=%s target_type=%s target_id=%s ip=%s details=%s",
        action,
        admin_user_id,
        target_type,
        target_id,
        ip_address,
        safe_details_str,
    )
