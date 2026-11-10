from datetime import timedelta
from urllib.parse import quote

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.models.account import User, PasswordResetToken, Session as UserSession
from app.models.security import EmailChangeToken
from app.models.enums import AuditOutcome
from app.security.passwords import verify_password
from app.security.tokens import generate_token, hash_token
from app.services.audit import create_audit_log
from app.services.auth import utc_now
from app.services.mail_outbox import queue_mail
from app.services.two_factor import verify_totp_code

ERROR = "Unable to change email."


def request_email_change(db, request, settings, user, payload):
    if not verify_password(payload.current_password, user.password_hash) or not verify_totp_code(settings, user, payload.code):
        create_audit_log(db, event_type="account.email_change_request", outcome=AuditOutcome.DENIED,
            request=request, user_id=user.id, target_type="user", target_id=user.id)
        db.commit()
        raise ValueError(ERROR)
    # Serialize requests and confirmation against this account.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    db.execute(update(EmailChangeToken).where(EmailChangeToken.user_id == user.id,
        EmailChangeToken.used_at.is_(None)).values(used_at=utc_now()))
    if payload.email != user.email and db.scalar(select(User.id).where(User.email == payload.email)) is None:
        token = generate_token()
        db.add(EmailChangeToken(user_id=user.id, old_email=user.email, new_email=payload.email,
            token_hash=hash_token(token, settings.password_reset_secret),
            expires_at=utc_now() + timedelta(minutes=settings.password_reset_expire_minutes)))
        # Fragments are not sent in HTTP requests, access logs, or Referer headers.
        link = f"{settings.frontend_base_url}/account#email_change_token={quote(token, safe='')}"
        queue_mail(db, settings, user_id=user.id, kind="account", to_email=payload.email,
            subject="Verify your new email address", body=f"Confirm your email change: {link}\nThis link expires in {settings.password_reset_expire_minutes} minutes.")
        queue_mail(db, settings, user_id=user.id, kind="account", to_email=user.email,
            subject="Email change requested", body="An email change was requested for your account. If this was not you, change your password immediately.")
    create_audit_log(db, event_type="account.email_change_request", outcome=AuditOutcome.SUCCESS,
        request=request, user_id=user.id, target_type="user", target_id=user.id)
    db.commit()


def confirm_email_change(db, request, settings, user, token):
    db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
    pending = db.scalar(select(EmailChangeToken).where(
        EmailChangeToken.user_id == user.id,
        EmailChangeToken.token_hash == hash_token(token, settings.password_reset_secret),
        EmailChangeToken.old_email == user.email,
        EmailChangeToken.used_at.is_(None), EmailChangeToken.expires_at > utc_now()).with_for_update())
    if pending is None:
        create_audit_log(db, event_type="account.email_change_confirm", outcome=AuditOutcome.DENIED,
            request=request, user_id=user.id, target_type="user", target_id=user.id)
        db.commit()
        raise ValueError(ERROR)
    old_email = user.email
    db.execute(update(EmailChangeToken).where(EmailChangeToken.user_id == user.id,
        EmailChangeToken.used_at.is_(None)).values(used_at=utc_now()))
    db.execute(update(PasswordResetToken).where(PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None)).values(used_at=utc_now()))
    db.execute(update(UserSession).where(UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None)).values(revoked_at=utc_now()))
    queue_mail(db, settings, user_id=user.id, kind="account", to_email=old_email,
        subject="Your account email changed", body="Your account email was changed. Contact support immediately if you did not authorize this change.")
    create_audit_log(db, event_type="account.email_change_confirm", outcome=AuditOutcome.SUCCESS,
        request=request, user_id=user.id, target_type="user", target_id=user.id)
    user.email = pending.new_email
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        create_audit_log(db, event_type="account.email_change_confirm", outcome=AuditOutcome.FAILURE,
            request=request, user_id=user.id, target_type="user", target_id=user.id)
        db.commit()
        raise ValueError(ERROR) from exc
