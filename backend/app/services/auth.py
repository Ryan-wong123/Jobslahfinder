from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.account import PasswordResetToken, Session as UserSession, User, UserProfile
from app.models.enums import AuditOutcome, UserRole
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.tokens import generate_token, hash_token
from app.services.audit import create_audit_log


GENERIC_LOGIN_ERROR = "Invalid email or password."
GENERIC_REGISTER_ERROR = "Unable to register account."
GENERIC_RESET_MESSAGE = "If the account exists, a reset link has been sent."
GENERIC_RESET_ERROR = "Unable to reset password."

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15


def utc_now() -> datetime:
    return datetime.now(UTC)


def is_expired(expires_at: datetime, now: datetime | None = None) -> bool:
    comparison_time = now or utc_now()
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= comparison_time


def register_user(db: Session, request: Request, *, email: str, password: str) -> User:
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        create_audit_log(
            db,
            event_type="auth.registration",
            outcome=AuditOutcome.FAILURE,
            request=request,
            target_type="user",
            details={"reason": "duplicate_email"},
        )
        db.commit()
        raise ValueError(GENERIC_REGISTER_ERROR)

    user = User(
        email=email,
        password_hash=hash_password(password),
        role=UserRole.USER.value,
        is_active=True,
        failed_login_count=0,
    )
    user.profile = UserProfile()
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        create_audit_log(
            db,
            event_type="auth.registration",
            outcome=AuditOutcome.FAILURE,
            request=request,
            target_type="user",
            details={"reason": "integrity_error"},
        )
        db.commit()
        raise ValueError(GENERIC_REGISTER_ERROR) from exc

    create_audit_log(
        db,
        event_type="auth.registration",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user.id,
        target_type="user",
        target_id=user.id,
    )
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, request: Request, *, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        create_audit_log(
            db,
            event_type="auth.login",
            outcome=AuditOutcome.FAILURE,
            request=request,
            target_type="user",
            details={"reason": "invalid_credentials"},
        )
        db.commit()
        raise ValueError(GENERIC_LOGIN_ERROR)

    if user.locked_until is not None and not is_expired(user.locked_until):
        create_audit_log(
            db,
            event_type="auth.login",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=user.id,
            target_type="user",
            target_id=user.id,
            details={"reason": "account_locked"},
        )
        db.commit()
        raise ValueError(GENERIC_LOGIN_ERROR)

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = utc_now() + timedelta(minutes=LOCKOUT_MINUTES)
        create_audit_log(
            db,
            event_type="auth.login",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=user.id,
            target_type="user",
            target_id=user.id,
            details={"reason": "invalid_credentials"},
        )
        db.commit()
        raise ValueError(GENERIC_LOGIN_ERROR)

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = utc_now()
    create_audit_log(
        db,
        event_type="auth.login",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user.id,
        target_type="user",
        target_id=user.id,
    )
    db.commit()
    db.refresh(user)
    return user


def create_session(
    db: Session,
    request: Request,
    settings: Settings,
    *,
    user: User,
) -> tuple[str, UserSession]:
    token = generate_token()
    user_agent = request.headers.get("user-agent")
    session = UserSession(
        user_id=user.id,
        session_token_hash=hash_token(token, settings.session_secret),
        expires_at=utc_now() + timedelta(minutes=settings.session_expire_minutes),
        ip_address=request.client.host[:64] if request.client and request.client.host else None,
        user_agent=user_agent[:1024] if user_agent else None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return token, session


def revoke_session(db: Session, request: Request, *, session: UserSession, user: User) -> None:
    if session.revoked_at is None:
        session.revoked_at = utc_now()
    create_audit_log(
        db,
        event_type="auth.logout",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user.id,
        target_type="session",
        target_id=session.id,
    )
    db.commit()


def change_password(
    db: Session,
    request: Request,
    *,
    user: User,
    current_session: UserSession,
    current_password: str,
    new_password: str,
) -> None:
    if not verify_password(current_password, user.password_hash):
        create_audit_log(
            db,
            event_type="auth.password_change",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=user.id,
            target_type="user",
            target_id=user.id,
            details={"reason": "invalid_current_password"},
        )
        db.commit()
        raise ValueError("Unable to change password.")

    user.password_hash = hash_password(new_password)
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id)
        .where(UserSession.id != current_session.id)
        .where(UserSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    create_audit_log(
        db,
        event_type="auth.password_change",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user.id,
        target_type="user",
        target_id=user.id,
    )
    db.commit()


def request_password_reset(db: Session, request: Request, settings: Settings, *, email: str) -> None:
    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if user is None:
        create_audit_log(
            db,
            event_type="auth.password_reset_request",
            outcome=AuditOutcome.SUCCESS,
            request=request,
            target_type="user",
            details={"account_matched": False},
        )
        db.commit()
        return

    token = generate_token()
    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(token, settings.password_reset_secret),
        expires_at=utc_now() + timedelta(minutes=settings.password_reset_expire_minutes),
    )
    db.add(reset_token)
    create_audit_log(
        db,
        event_type="auth.password_reset_request",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user.id,
        target_type="user",
        target_id=user.id,
        details={"account_matched": True, "delivery": "not_configured"},
    )
    db.commit()


def confirm_password_reset(
    db: Session,
    request: Request,
    settings: Settings,
    *,
    token: str,
    new_password: str,
) -> None:
    token_hash = hash_token(token, settings.password_reset_secret)
    reset_token = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    if (
        reset_token is None
        or reset_token.used_at is not None
        or is_expired(reset_token.expires_at)
        or not reset_token.user.is_active
    ):
        create_audit_log(
            db,
            event_type="auth.password_reset_confirm",
            outcome=AuditOutcome.FAILURE,
            request=request,
            target_type="password_reset_token",
            details={"reason": "invalid_or_expired"},
        )
        db.commit()
        raise ValueError(GENERIC_RESET_ERROR)

    user = reset_token.user
    user.password_hash = hash_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    reset_token.used_at = utc_now()
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id)
        .where(UserSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    create_audit_log(
        db,
        event_type="auth.password_reset_confirm",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user.id,
        target_type="user",
        target_id=user.id,
    )
    db.commit()
