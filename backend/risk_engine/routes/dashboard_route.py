from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import Dict, Any
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

from app.core.config import Settings, get_settings
from app.models.account import User
from risk_engine.db.audit_model import AuditLog
from risk_engine.db.risk_model import LoginEvent
from risk_engine.dependancy import get_db, get_audit_db, get_app_db, require_admin, require_app_admin
from risk_engine.component.risk_utils import load_risk_config, reload_risk_config
from risk_engine.component.csrf_utils import get_csrf_token, verify_csrf_token
from risk_engine.component.audit_utils import (
    log_admin_access,
    log_config_change,
)
from risk_engine.component.validation_utils import (
    validate_risk_score,
    validate_threshold,
    validate_positive_integer,
)
from risk_engine import config

dashboard_router = APIRouter(
    prefix="/admin",
    tags=["dashboard"],
)

templates = Jinja2Templates(directory=str(config.BASE_DIR / "templates"))
SGT = ZoneInfo("Asia/Singapore")


def _device_token_display(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("sha256:"):
        return value.removeprefix("sha256:")[:12]
    return value[:8]


def _format_sgt(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(SGT).strftime("%Y-%m-%d %H:%M:%S")


def _template_context(request: Request, **values: Any) -> dict[str, Any]:
    return {
        "request": request,
        "base_path": config.BASE_PATH,
        "admin_base_path": config.admin_path(),
        "static_base_path": f"{config.BASE_PATH}/static",
        **values,
    }


def _auth_error_page(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else "Authentication required."
    return templates.TemplateResponse(
        request,
        "auth_error.html",
        context=_template_context(request, detail=detail),
        status_code=exc.status_code,
    )


def _display_name(value: str) -> str:
    return value.replace("_", " ").replace(".", " ").title()


def _audit_value_to_text(value: Any) -> str:
    if value is None or value == "":
        return "None"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return ", ".join(_audit_value_to_text(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(f"{_display_name(str(key))}: {_audit_value_to_text(item)}" for key, item in value.items())
    return str(value)


def _audit_action_label(action: str) -> str:
    labels = {
        "risk_engine.admin_access": "Risk dashboard opened",
        "risk_engine.config_update": "Risk configuration changed",
        "authorization.denied": "Access denied",
    }
    return labels.get(action, _display_name(action))


def _audit_status_label(status: str) -> str:
    labels = {
        "success": "Success",
        "failure": "Failure",
        "error": "Error",
    }
    return labels.get(status, _display_name(status))


def _audit_details_from_json(raw_details: str | None) -> dict[str, Any]:
    if not raw_details:
        return {}
    try:
        parsed = json.loads(raw_details)
    except json.JSONDecodeError:
        return {"note": raw_details}
    return parsed if isinstance(parsed, dict) else {"details": parsed}


def _audit_detail_lines(details: dict[str, Any]) -> list[str]:
    changes = details.get("changes")
    if isinstance(changes, list):
        lines = []
        for change in changes:
            if isinstance(change, dict) and isinstance(change.get("summary"), str):
                lines.append(change["summary"])
            else:
                lines.append(_audit_value_to_text(change))
        return lines

    hidden_keys = {"admin_email", "admin_role", "auth_source", "change_count", "changes"}
    lines = []
    for key, value in details.items():
        if key in hidden_keys or value in (None, ""):
            continue
        lines.append(f"{_display_name(str(key))}: {_audit_value_to_text(value)}")
    return lines


def _audit_actor(details: dict[str, Any]) -> str:
    admin_email = details.get("admin_email")
    if isinstance(admin_email, str) and admin_email:
        return admin_email
    admin_user_id = details.get("admin_user_id")
    if admin_user_id:
        return f"Admin user {admin_user_id}"
    return "System"


def _audit_action_options(audit_db: Session) -> list[dict[str, str]]:
    actions = audit_db.query(AuditLog.action).distinct().order_by(AuditLog.action.asc()).all()
    return [{"value": action, "label": _audit_action_label(action)} for (action,) in actions]


def _audit_page_url(*, page: int, page_size: int, action: str | None, status_filter: str | None, actor: str | None) -> str:
    query = {
        "page": page,
        "page_size": page_size,
    }
    if action:
        query["action"] = action
    if status_filter:
        query["status"] = status_filter
    if actor:
        query["actor"] = actor
    return f"{config.admin_path('/audit-logs')}?{urlencode(query)}"


def _pagination_window(
    page: int,
    page_size: int,
    total: int,
    *,
    action: str | None,
    status_filter: str | None,
    actor: str | None,
) -> dict[str, int | bool | str]:
    total_pages = max(1, (total + page_size - 1) // page_size)
    previous_page = max(1, page - 1)
    next_page = min(total_pages, page + 1)
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_previous": page > 1,
        "has_next": page < total_pages,
        "previous_url": _audit_page_url(
            page=previous_page,
            page_size=page_size,
            action=action,
            status_filter=status_filter,
            actor=actor,
        ),
        "next_url": _audit_page_url(
            page=next_page,
            page_size=page_size,
            action=action,
            status_filter=status_filter,
            actor=actor,
        ),
    }


@dashboard_router.get("")
def admin_root():
    return RedirectResponse(url=config.admin_path("/login"), status_code=302)

@dashboard_router.get("/login")
def admin_login_form(request: Request):
    return RedirectResponse(url="/login", status_code=302)


@dashboard_router.post("/login")
def admin_login(request: Request):
    return RedirectResponse(url="/login", status_code=303)


@dashboard_router.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    app_db: Session = Depends(get_app_db),
    settings: Settings = Depends(get_settings),
    username: str = Query("", max_length=254),
    decision: str = Query("", max_length=20),
    min_score: int | None = Query(None, ge=0, le=1000),
    max_score: int | None = Query(None, ge=0, le=1000),
):
    try:
        admin_user = require_app_admin(request, app_db, settings)
    except HTTPException as exc:
        return _auth_error_page(request, exc)
    if request.session.get("risk_dashboard_access_logged_for_user") != admin_user.id:
        log_admin_access(request, admin_user=admin_user, page="dashboard")
        request.session["risk_dashboard_access_logged_for_user"] = admin_user.id

    username_filter = username.strip().lower()
    decision_filter = decision.strip().lower()
    if decision_filter not in {"", "allow", "challenge", "block"}:
        decision_filter = ""

    query = db.query(LoginEvent)
    if username_filter:
        query = query.filter(func.lower(LoginEvent.username).contains(username_filter))
    if decision_filter:
        query = query.filter(LoginEvent.decision == decision_filter)
    if min_score is not None:
        query = query.filter(LoginEvent.score >= min_score)
    if max_score is not None:
        query = query.filter(LoginEvent.score <= max_score)

    raw_events = query.order_by(LoginEvent.event_time_utc.desc()).limit(500).all()

    events = [
        {
            "username": e.username,
            "event_time_sgt": _format_sgt(e.event_time_utc),
            "ip": e.ip,
            "ip_prefix": e.ip_prefix,
            "user_agent": e.user_agent,
            "device_token": _device_token_display(e.device_token),
            "decision": e.decision,
            "score": e.score,
            "reasons": e.reasons,
        }
        for e in raw_events
    ]
    
    # Check if viewing old data (before last config change)
    show_config_warning = False
    config_change_date = None
    try:
        state_path = config.ENGINE_STATE_PATH
        if state_path.exists():
            with open(state_path, 'r') as f:
                state = json.load(f)
                last_config_change = state.get('last_config_change')
                if last_config_change and raw_events:
                    config_change_dt = datetime.fromisoformat(last_config_change)
                    oldest_event = raw_events[-1]
                    if oldest_event.event_time_utc < config_change_dt:
                        show_config_warning = True
                        config_change_date = _format_sgt(config_change_dt)
    except Exception:
        pass

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        context={
            **_template_context(request),
            "events": events,
            "filters": {
                "username": username.strip(),
                "decision": decision_filter,
                "min_score": "" if min_score is None else min_score,
                "max_score": "" if max_score is None else max_score,
            },
            "show_config_warning": show_config_warning,
            "config_change_date": config_change_date,
            "csrf_token": get_csrf_token(request)
        }
    )


@dashboard_router.get("/config-page")
def config_page(
    request: Request,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_app_admin),
):
    """Render the risk configuration editor page."""
    return templates.TemplateResponse(
        request,
        "config.html",
        context={
            **_template_context(request),
            "csrf_token": get_csrf_token(request)
        }
    )


class RiskConfigUpdate(BaseModel):
    risk_scores: Dict[str, int]
    decision_thresholds: Dict[str, int]
    rate_limit: Dict[str, Any]
    baseline: Dict[str, Any]


@dashboard_router.get("/config")
def get_risk_config_redirect(
    request: Request,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_app_admin),
):
    risk_config = load_risk_config()
    return JSONResponse(content=risk_config)


@dashboard_router.post("/config/read")
def get_risk_config(request: Request, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Get current risk scoring configuration (session-required)."""
    # Verify CSRF token from header
    csrf_token = request.headers.get("X-CSRF-Token")
    try:
        verify_csrf_token(request, csrf_token)
    except HTTPException:
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    
    risk_config = load_risk_config()
    return JSONResponse(content=risk_config)


@dashboard_router.post("/config")
def update_risk_config(
    request: Request,
    config_update: RiskConfigUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    """Update risk scoring configuration."""
    # Verify CSRF token from header
    csrf_token = request.headers.get("X-CSRF-Token")
    try:
        verify_csrf_token(request, csrf_token)
    except HTTPException as e:
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    
    try:
        # Validate all config values
        for key, value in config_update.risk_scores.items():
            validate_risk_score(value, f"risk_scores.{key}")
        
        for key, value in config_update.decision_thresholds.items():
            validate_threshold(value, f"decision_thresholds.{key}")
        
        # Validate rate_limit config
        if "window_seconds" in config_update.rate_limit:
            validate_positive_integer(
                config_update.rate_limit["window_seconds"],
                "rate_limit.window_seconds",
                min_val=1,
                max_val=3600
            )
        if "thresholds" in config_update.rate_limit:
            thresholds = config_update.rate_limit["thresholds"]
            if not isinstance(thresholds, list):
                raise HTTPException(
                    status_code=400,
                    detail="rate_limit.thresholds must be a list"
                )
            for idx, threshold in enumerate(thresholds):
                if not isinstance(threshold, dict):
                    raise HTTPException(
                        status_code=400,
                        detail=f"rate_limit.thresholds[{idx}] must be an object"
                    )
                if "attempts" in threshold:
                    validate_positive_integer(
                        threshold["attempts"],
                        f"rate_limit.thresholds[{idx}].attempts",
                        min_val=1,
                        max_val=1000
                    )
                if "score" in threshold:
                    validate_risk_score(
                        threshold["score"],
                        f"rate_limit.thresholds[{idx}].score"
                    )
        
        if "event_limit" in config_update.baseline:
            validate_positive_integer(
                config_update.baseline["event_limit"],
                "baseline.event_limit",
                min_val=10,
                max_val=10000
            )
        if "max_known_devices" in config_update.baseline:
            validate_positive_integer(
                config_update.baseline["max_known_devices"],
                "baseline.max_known_devices",
                min_val=1,
                max_val=100
            )
        if "max_known_ip_prefixes" in config_update.baseline:
            validate_positive_integer(
                config_update.baseline["max_known_ip_prefixes"],
                "baseline.max_known_ip_prefixes",
                min_val=1,
                max_val=100
            )

        config_path = config.RISK_CONFIG_PATH
        
        # Load old config for audit trail
        old_config = load_risk_config()
        
        # Convert Pydantic model to dict
        new_config = config_update.model_dump()
        
        # Preserve impossible_travel settings from old config (not exposed in UI)
        if "impossible_travel" in old_config:
            new_config["impossible_travel"] = old_config["impossible_travel"]
        
        # Preserve impossible_travel risk score from old config
        if "impossible_travel" in old_config.get("risk_scores", {}):
            new_config["risk_scores"]["impossible_travel"] = old_config["risk_scores"]["impossible_travel"]
        
        # Write to file
        with open(config_path, 'w') as f:
            json.dump(new_config, f, indent=2)
        
        # Record config change timestamp
        state_path = config.ENGINE_STATE_PATH
        if state_path.exists():
            with open(state_path, 'r') as f:
                state = json.load(f)
            state['last_config_change'] = datetime.utcnow().isoformat()
            with open(state_path, 'w') as f:
                json.dump(state, f, indent=2)
        
        # Reload config cache
        reload_risk_config()
        
        # Log the config change
        log_config_change(request, admin_user, old_config, new_config, success=True)
        
        return JSONResponse(content={
            "status": "success",
            "message": "Risk configuration updated successfully",
            "config": new_config
        })
    except HTTPException:
        raise
    except Exception as e:
        # Log the failure
        try:
            old_config = load_risk_config()
            new_config = config_update.model_dump()
            log_config_change(
                request,
                admin_user,
                old_config,
                new_config,
                success=False,
                error_message="configuration_update_failed",
            )
        except Exception:
            pass  # Don't let audit logging break error handling
        raise HTTPException(status_code=500, detail="Failed to update configuration.")


@dashboard_router.get("/audit-logs")
def audit_logs_page(
    request: Request,
    audit_db: Session = Depends(get_audit_db),
    admin_user: User = Depends(require_app_admin),
    action: str | None = Query(default=None, min_length=1, max_length=100),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(success|failure|error)$"),
    actor: str | None = Query(default=None, min_length=1, max_length=255),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=5, le=100),
):
    """View audit logs."""
    filters = []
    if action:
        filters.append(AuditLog.action == action)
    if status_filter:
        filters.append(AuditLog.status == status_filter)
    if actor:
        filters.append(AuditLog.details.ilike(f"%{actor}%"))

    base_query = audit_db.query(AuditLog)
    if filters:
        base_query = base_query.filter(*filters)

    total = base_query.with_entities(func.count(AuditLog.id)).scalar() or 0
    logs = (
        base_query
        .order_by(AuditLog.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    
    log_entries = [
        {
            "id": log.id,
            "timestamp_sgt": _format_sgt(log.timestamp),
            "action": log.action,
            "action_label": _audit_action_label(log.action),
            "resource": log.resource,
            "status": log.status,
            "status_label": _audit_status_label(log.status),
            "actor": _audit_actor(_audit_details_from_json(log.details)),
            "detail_lines": _audit_detail_lines(_audit_details_from_json(log.details)),
            "error_message": log.error_message,
        }
        for log in logs
    ]
    return templates.TemplateResponse(
        request,
        "audit_logs.html",
        context={
            **_template_context(request),
            "logs": log_entries,
            "action_options": _audit_action_options(audit_db),
            "selected_action": action or "",
            "selected_status": status_filter or "",
            "actor_filter": actor or "",
            "pagination": _pagination_window(
                page,
                page_size,
                total,
                action=action,
                status_filter=status_filter,
                actor=actor,
            ),
            "csrf_token": get_csrf_token(request)
        }
    )
