"""Audit logging utilities for tracking risk engine admin actions."""
from fastapi import Request
from datetime import datetime
import json
from typing import Optional, Dict, Any

from app.models.account import User
from risk_engine.db.audit_model import AuditLog
from risk_engine.db.db_setup import AuditSessionLocal


def _request_metadata(request: Request) -> Dict[str, Any]:
    user_agent = request.headers.get("user-agent")
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": user_agent[:255] if user_agent else None,
    }


def _actor_metadata(admin_user: User) -> Dict[str, Any]:
    return {
        "admin_user_id": admin_user.id,
        "admin_email": admin_user.email,
        "admin_role": admin_user.role,
        "auth_source": "main_app_admin_session",
    }


def _display_name(value: str) -> str:
    return value.replace("_", " ").replace(".", " ").title()


CONFIG_SETTING_LABELS = {
    "risk_scores.new_device": "New device score",
    "risk_scores.new_ip_prefix": "New IP prefix score",
    "risk_scores.missing_user_agent": "Missing user agent score",
    "risk_scores.impossible_travel": "Impossible travel score",
    "decision_thresholds.block": "Block threshold",
    "decision_thresholds.challenge": "Challenge threshold",
    "rate_limit.window_seconds": "Rate-limit window",
    "baseline.event_limit": "Baseline event limit",
    "baseline.max_known_devices": "Maximum known devices",
    "baseline.max_known_ip_prefixes": "Maximum known IP prefixes",
}


def _setting_label(key: str) -> str:
    if key in CONFIG_SETTING_LABELS:
        return CONFIG_SETTING_LABELS[key]
    if key.startswith("rate_limit.thresholds."):
        parts = key.split(".")
        if len(parts) == 4 and parts[2].isdigit():
            rule_number = int(parts[2]) + 1
            return f"Rate-limit rule {rule_number} {_display_name(parts[3]).lower()}"
    return _display_name(key)


def _flatten_config(value: Any, prefix: str = "") -> Dict[str, Any]:
    if isinstance(value, dict):
        flattened: Dict[str, Any] = {}
        for key, nested_value in value.items():
            nested_key = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_config(nested_value, nested_key))
        return flattened
    return {prefix: value}


def _friendly_change_summary(old_config: Dict[str, Any], new_config: Dict[str, Any]) -> list[Dict[str, Any]]:
    old_values = _flatten_config(old_config)
    new_values = _flatten_config(new_config)
    changes: list[Dict[str, Any]] = []

    for key in sorted(set(old_values) | set(new_values)):
        old_value = old_values.get(key)
        new_value = new_values.get(key)
        if old_value == new_value:
            continue

        section, _, setting = key.partition(".")
        changes.append(
            {
                "section": _display_name(section),
                "setting": _setting_label(key),
                "old_value": old_value,
                "new_value": new_value,
                "summary": f"{_setting_label(key)} changed from {old_value!r} to {new_value!r}",
            }
        )

    return changes


def log_audit_event(
    action: str,
    request: Request,
    status: str = "success",
    resource: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None
) -> None:
    """
    Log an audit event to the database.
    
    Args:
        action: The action performed (e.g., 'risk_engine.config_update')
        request: The FastAPI request object
        status: 'success', 'failure', or 'error'
        resource: What was affected (e.g., 'risk_config', 'risk_dashboard')
        details: Additional context as a dictionary (will be JSON serialized)
        error_message: Error description if status is failure/error
    """
    db = AuditSessionLocal()
    try:
        audit_entry = AuditLog(
            timestamp=datetime.utcnow(),
            action=action,
            resource=resource,
            status=status,
            details=json.dumps(details) if details else None,
            error_message=error_message
        )
        
        db.add(audit_entry)
        db.commit()
    except Exception:
        # Don't let audit logging failures break the application
        # But we should at least try to rollback
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def log_admin_access(request: Request, *, admin_user: User, page: str) -> None:
    """Log successful access to a privileged risk engine admin page."""
    log_audit_event(
        action="risk_engine.admin_access",
        request=request,
        status="success",
        resource="risk_dashboard",
        details={
            "page": page,
            **_actor_metadata(admin_user),
            **_request_metadata(request),
        },
    )


def log_config_change(
    request: Request,
    admin_user: User,
    old_config: Dict[str, Any],
    new_config: Dict[str, Any],
    success: bool = True,
    error_message: Optional[str] = None
) -> None:
    """Log a risk configuration change."""
    changes = _friendly_change_summary(old_config, new_config)
    
    log_audit_event(
        action="risk_engine.config_update",
        request=request,
        status="success" if success else "failure",
        resource="risk_config",
        details={
            "change_count": len(changes),
            "changes": changes,
            **_actor_metadata(admin_user),
            **_request_metadata(request),
        },
        error_message=error_message
    )
