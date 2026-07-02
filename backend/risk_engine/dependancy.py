from base64 import b64decode
from binascii import Error as BinasciiError
from datetime import timedelta
import hmac
import os
import time

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import Settings, get_settings
from app.core.database import SessionLocal as AppSessionLocal
from app.models.account import Session as AppUserSession
from app.models.account import User
from app.models.enums import AuditOutcome, UserRole
from app.security.auth import get_session_cookie_name
from app.security.tokens import hash_token
from app.services.audit import create_audit_log
from app.services.auth import is_expired, utc_now
from risk_engine.db.db_setup import SessionLocal, AuditSessionLocal
from risk_engine import config
# use to check when web app call that it is secure




def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_audit_db():
    """Get audit database session."""
    db = AuditSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_app_db():
    db = AppSessionLocal()
    try:
        yield db
    finally:
        db.close()


def _log_risk_admin_denied(
    db: Session,
    request: Request,
    *,
    user: User | None,
    reason: str,
) -> None:
    create_audit_log(
        db,
        event_type="authorization.denied",
        outcome=AuditOutcome.DENIED,
        request=request,
        user_id=user.id if user else None,
        target_type="risk_engine_admin",
        target_id=None,
        details={"reason": reason},
    )
    db.commit()


def require_app_admin(
    request: Request,
    app_db: Session = Depends(get_app_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Require a real SSD admin session for the human risk dashboard."""
    token = request.cookies.get(get_session_cookie_name(settings))
    if not token:
        _log_risk_admin_denied(app_db, request, user=None, reason="authentication_required")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    session_token_hash = hash_token(token, settings.session_secret)
    session = app_db.scalar(
        select(AppUserSession).where(AppUserSession.session_token_hash == session_token_hash)
    )
    if (
        session is None
        or session.revoked_at is not None
        or is_expired(session.expires_at)
        or not session.user.is_active
    ):
        _log_risk_admin_denied(app_db, request, user=None, reason="invalid_session")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    user = session.user
    if not user.totp_enabled:
        _log_risk_admin_denied(app_db, request, user=user, reason="two_factor_required")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Two-factor setup required.")

    if user.role != UserRole.ADMIN.value:
        _log_risk_admin_denied(app_db, request, user=user, reason="admin_role_required")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    created_at = session.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=utc_now().tzinfo)
    if created_at + timedelta(minutes=settings.admin_session_max_age_minutes) <= utc_now():
        _log_risk_admin_denied(app_db, request, user=user, reason="admin_recent_session_required")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required.",
        )

    return user




# used to secure RBA API. verify when API called is it the web app

def _basic_password(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "basic" or not value:
        return None
    try:
        decoded = b64decode(value).decode("utf-8")
    except (BinasciiError, UnicodeDecodeError):
        return None
    _, _, password = decoded.partition(":")
    return password or None


def _is_api_key_valid(x_api_key: str | None, authorization: str | None) -> bool:
    expected = config.get_engine_api_key()

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key not configured",
        )

    basic_password = _basic_password(authorization)

    if x_api_key and hmac.compare_digest(x_api_key, expected):
        return True

    if basic_password and hmac.compare_digest(basic_password, expected):
        return True

    return False


ADMIN_SESSION_TIMEOUT_SEC = int(os.getenv("RISK_ENGINE_ADMIN_SESSION_TIMEOUT_SEC", "900"))


def is_admin_session_active(request: Request) -> bool:
    if request.session.get("admin_auth") is not True:
        return False

    now = int(time.time())
    last_seen = request.session.get("admin_last_seen")

    if last_seen is None:
        request.session["admin_last_seen"] = now
        return True

    try:
        last_seen_int = int(last_seen)
    except (TypeError, ValueError):
        request.session.pop("admin_auth", None)
        request.session.pop("admin_last_seen", None)
        return False

    if now - last_seen_int > ADMIN_SESSION_TIMEOUT_SEC:
        request.session.pop("admin_auth", None)
        request.session.pop("admin_last_seen", None)
        return False

    request.session["admin_last_seen"] = now
    return True


def require_api_key(
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):

    if config.ENFORCE_API_KEY:


        expected = config.get_engine_api_key()

        if not expected:
            # Engine is misconfigured or not initialized
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API key not configured",
            )

        if _is_api_key_valid(x_api_key, authorization):
            return

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized / Missing API Key",
            headers={"WWW-Authenticate": 'Basic realm="RBA Admin"'},
        )


def require_admin(
    request: Request,
    app_db: Session = Depends(get_app_db),
    settings: Settings = Depends(get_settings),
) -> User:
    return require_app_admin(request, app_db, settings)
