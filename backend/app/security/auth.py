from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models.account import Session as UserSession, User
from app.models.enums import AuditOutcome, UserRole
from app.security.tokens import hash_token
from app.services.audit import create_audit_log
from app.services.auth import is_expired, utc_now


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    session: UserSession


def get_session_cookie_name(settings: Settings) -> str:
    return settings.session_cookie_name


def require_authenticated_session(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedSession:
    token = request.cookies.get(get_session_cookie_name(settings))
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    session_token_hash = hash_token(token, settings.session_secret)
    session = db.scalar(select(UserSession).where(UserSession.session_token_hash == session_token_hash))
    if (
        session is None
        or session.revoked_at is not None
        or is_expired(session.expires_at)
        or not session.user.is_active
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")

    return AuthenticatedSession(user=session.user, session=session)


def require_authenticated_user(
    authenticated_session: AuthenticatedSession = Depends(require_authenticated_session),
) -> User:
    return authenticated_session.user


def log_authorization_denied(
    db: Session,
    request: Request | None,
    *,
    user: User | None,
    target_type: str | None,
    target_id: int | None,
    reason: str,
) -> None:
    create_audit_log(
        db,
        event_type="authorization.denied",
        outcome=AuditOutcome.DENIED,
        request=request,
        user_id=user.id if user else None,
        target_type=target_type,
        target_id=target_id,
        details={"reason": reason},
    )
    db.commit()


def require_admin(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    authenticated_session: AuthenticatedSession = Depends(require_authenticated_session),
) -> User:
    user = authenticated_session.user
    if user.role != UserRole.ADMIN.value:
        log_authorization_denied(
            db,
            request,
            user=user,
            target_type="admin",
            target_id=None,
            reason="admin_role_required",
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    created_at = authenticated_session.session.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=utc_now().tzinfo)
    if created_at + timedelta(minutes=settings.admin_session_max_age_minutes) <= utc_now():
        log_authorization_denied(
            db,
            request,
            user=user,
            target_type="admin",
            target_id=None,
            reason="admin_recent_session_required",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authentication required.")

    return user


def assert_owner_or_admin(
    db: Session,
    request: Request | None,
    *,
    current_user: User,
    owner_user_id: int,
    target_type: str,
    target_id: int | None = None,
) -> None:
    if current_user.role == UserRole.ADMIN.value or current_user.id == owner_user_id:
        return

    log_authorization_denied(
        db,
        request,
        user=current_user,
        target_type=target_type,
        target_id=target_id,
        reason="owner_or_admin_required",
    )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
