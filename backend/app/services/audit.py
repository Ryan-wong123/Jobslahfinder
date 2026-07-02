from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.rate_limit import get_client_ip
from app.models.audit import AuditLog
from app.models.enums import AuditOutcome
from app.security.text import sanitize_text


SENSITIVE_DETAIL_KEYS = {
    "api_key",
    "authorization",
    "cover_letter",
    "cover_letter_text",
    "edited_cover_letter",
    "edited_text",
    "extracted_text",
    "full_resume_text",
    "generated_cover_letter",
    "password",
    "password_hash",
    "private_key",
    "prompt",
    "full_prompt",
    "raw_prompt",
    "ai_prompt",
    "raw_resume_text",
    "resume_content",
    "resume_text",
    "current_password",
    "generated_text",
    "new_password",
    "secret",
    "reset_token",
    "session_token",
    "token",
}
MAX_AUDIT_DETAIL_TEXT_LENGTH = 4096
MAX_AUDIT_USER_AGENT_LENGTH = 1024
MAX_AUDIT_DETAIL_KEY_LENGTH = 128
MAX_AUDIT_DETAIL_CONTAINER_ITEMS = 50
MAX_AUDIT_DETAIL_DEPTH = 6
AUDIT_DETAIL_TRUNCATED_MARKER = "[TRUNCATED]"


def is_sensitive_detail_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in SENSITIVE_DETAIL_KEYS or any(
        marker in normalized
        for marker in ("api_key", "apikey", "password", "private_key", "prompt", "secret", "token")
    )


def safe_detail_key(key: Any) -> str:
    cleaned = sanitize_text(
        key,
        field_name="audit detail key",
        max_length=MAX_AUDIT_DETAIL_KEY_LENGTH,
        empty_to_none=False,
        html_policy="allow",
        overflow="truncate",
        control_policy="strip",
        collapse_whitespace=False,
        allow_multiline=False,
    )
    return cleaned or "detail"


def safe_detail_value(key: str, value: Any, *, depth: int = 0) -> Any:
    if is_sensitive_detail_key(key):
        return "[REDACTED]"
    if depth >= MAX_AUDIT_DETAIL_DEPTH:
        return AUDIT_DETAIL_TRUNCATED_MARKER
    if isinstance(value, dict):
        return safe_details(value, depth=depth + 1)
    if isinstance(value, list):
        safe_items = [
            safe_detail_value("", item, depth=depth + 1)
            for item in value[:MAX_AUDIT_DETAIL_CONTAINER_ITEMS]
        ]
        if len(value) > MAX_AUDIT_DETAIL_CONTAINER_ITEMS:
            safe_items.append(AUDIT_DETAIL_TRUNCATED_MARKER)
        return safe_items
    if isinstance(value, str):
        return sanitize_text(
            value,
            field_name="audit detail",
            max_length=MAX_AUDIT_DETAIL_TEXT_LENGTH,
            empty_to_none=False,
            html_policy="allow",
            overflow="truncate",
            control_policy="strip",
            collapse_whitespace=False,
            allow_multiline=True,
        )
    return value


def safe_details(details: dict[str, Any] | None, *, depth: int = 0) -> dict[str, Any] | None:
    if details is None:
        return None
    safe: dict[str, Any] = {}
    omitted_count = 0
    for index, (key, value) in enumerate(details.items()):
        if index >= MAX_AUDIT_DETAIL_CONTAINER_ITEMS:
            omitted_count += 1
            continue
        original_key = str(key)
        safe[safe_detail_key(original_key)] = safe_detail_value(original_key, value, depth=depth)
    if omitted_count:
        safe[AUDIT_DETAIL_TRUNCATED_MARKER] = f"{omitted_count} omitted"
    return safe


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
    safe_user_agent = (
        sanitize_text(
            user_agent,
            field_name="user_agent",
            max_length=MAX_AUDIT_USER_AGENT_LENGTH,
            empty_to_none=True,
            html_policy="allow",
            overflow="truncate",
            control_policy="strip",
            collapse_whitespace=True,
            allow_multiline=False,
        )
        if user_agent
        else None
    )
    audit_log = AuditLog(
        user_id=user_id,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        ip_address=get_client_ip(request) if request else None,
        user_agent=safe_user_agent,
        outcome=outcome.value,
        details_json=safe_details(details),
    )
    db.add(audit_log)
    return audit_log
