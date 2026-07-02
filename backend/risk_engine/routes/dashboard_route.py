from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any
import json
from datetime import datetime

from app.core.config import Settings, get_settings
from app.models.account import Session as AppUserSession
from app.models.account import User
from app.security.auth import get_session_cookie_name
from app.security.tokens import hash_token
from app.services.auth import revoke_session
from risk_engine.db.risk_model import LoginEvent
from risk_engine.dependancy import get_db, get_audit_db, get_app_db, require_admin, require_app_admin
from risk_engine.component.risk_utils import load_risk_config, reload_risk_config
from risk_engine.component.csrf_utils import get_csrf_token, verify_csrf_token
from risk_engine.component.audit_utils import log_config_change
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


def _device_token_display(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("sha256:"):
        return value.removeprefix("sha256:")[:12]
    return value[:8]


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


@dashboard_router.get("")
def admin_root():
    return RedirectResponse(url=config.admin_path("/login"), status_code=302)

@dashboard_router.get("/login")
def admin_login_form(request: Request):
    return RedirectResponse(url="/login", status_code=302)


@dashboard_router.post("/login")
def admin_login(request: Request):
    return RedirectResponse(url="/login", status_code=303)


@dashboard_router.post("/logout")
def admin_logout(
    request: Request,
    csrf_token: str = Form(...),
    app_db: Session = Depends(get_app_db),
    settings: Settings = Depends(get_settings),
):
    try:
        verify_csrf_token(request, csrf_token)
    except HTTPException:
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    session_cookie_name = get_session_cookie_name(settings)
    app_session_token = request.cookies.get(session_cookie_name)
    if app_session_token:
        app_session = app_db.scalar(
            select(AppUserSession).where(
                AppUserSession.session_token_hash == hash_token(
                    app_session_token,
                    settings.session_secret,
                )
            )
        )
        if app_session is not None:
            revoke_session(app_db, request, session=app_session, user=app_session.user)

    request.session.clear()
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(
        key=session_cookie_name,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(
        key="risk_engine_admin_session",
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/",
    )
    return response


@dashboard_router.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    app_db: Session = Depends(get_app_db),
    settings: Settings = Depends(get_settings),
):
    try:
        require_app_admin(request, app_db, settings)
    except HTTPException as exc:
        return _auth_error_page(request, exc)

    raw_events = (
    db.query(LoginEvent)
    .order_by(LoginEvent.event_time_utc.desc())
    .limit(500)
    .all()
    )

    events = [
        {
            "username": e.username,
            "event_time_utc": e.event_time_utc.isoformat(),
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
                        config_change_date = config_change_dt.strftime('%Y-%m-%d %H:%M UTC')
    except Exception:
        pass

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        context={
            **_template_context(request),
            "events": events,
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
def update_risk_config(request: Request, config_update: RiskConfigUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
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
        log_config_change(request, old_config, new_config, success=True)
        
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
            log_config_change(request, old_config, new_config, success=False, error_message=str(e))
        except Exception:
            pass  # Don't let audit logging break error handling
        raise HTTPException(status_code=500, detail="Failed to update configuration.")


@dashboard_router.get("/audit-logs")
def audit_logs_page(
    request: Request,
    audit_db: Session = Depends(get_audit_db),
    admin_user: User = Depends(require_app_admin),
):
    """View audit logs."""
    from risk_engine.db.audit_model import AuditLog
    
    # Get recent audit logs
    logs = (
        audit_db.query(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .limit(500)
        .all()
    )
    
    log_entries = [
        {
            "id": log.id,
            "timestamp": log.timestamp.isoformat(),
            "action": log.action,
            "resource": log.resource,
            "status": log.status,
            "details": log.details,
            "error_message": log.error_message
        }
        for log in logs
    ]
    
    return templates.TemplateResponse(
        request,
        "audit_logs.html",
        context={
            **_template_context(request),
            "logs": log_entries,
            "csrf_token": get_csrf_token(request)
        }
    )
