from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.rate_limit import get_client_ip
from app.models.audit import AuditLog
from app.models.enums import AuditOutcome


SENSITIVE_DETAIL_KEYS = {
    "password",
    "current_password",
    "new_password",
    "token",
    "session_token",
    "reset_token",
    "password_hash",
}


def safe_details(details: dict[str, Any] | None) -> dict[str, Any] | None:
    if details is None:
        return None
    return {
        key: "[REDACTED]" if key.lower() in SENSITIVE_DETAIL_KEYS else value
        for key, value in details.items()
    }


def create_audit_log(
    db: Session,
    *,
    event_type: str,
    outcome: AuditOutcome,
    request: Request | None = None,
    user_id: int | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    user_agent = request.headers.get("user-agent") if request else None
    audit_log = AuditLog(
        user_id=user_id,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        ip_address=get_client_ip(request) if request else None,
        user_agent=user_agent[:1024] if user_agent else None,
        outcome=outcome.value,
        details_json=safe_details(details),
    )
    db.add(audit_log)
    return audit_log
