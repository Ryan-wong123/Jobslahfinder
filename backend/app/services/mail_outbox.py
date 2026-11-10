"""Deliver recovery mail outside request handling; never put bearer tokens in the broker."""
from datetime import timedelta
import json

from sqlalchemy import select

from app.models.security import EmailDelivery
from app.models.enums import AuditOutcome
from app.services.audit import create_audit_log
from app.services.auth import utc_now, is_expired
from app.services.email import send_password_reset_email, send_account_email
from app.security.encryption import encrypt_mail_payload, decrypt_mail_payload


def queue_mail(db, settings, *, user_id: int, kind: str, to_email: str, **values) -> None:
    payload = json.dumps({"kind": kind, "to_email": to_email, **values})
    db.add(EmailDelivery(user_id=user_id, encrypted_payload=encrypt_mail_payload(settings, payload),
                         expires_at=utc_now() + timedelta(minutes=settings.password_reset_expire_minutes)))


def deliver_pending_mail(db, settings, *, limit: int = 20) -> int:
    delivered = 0
    # Claim one row at a time. PostgreSQL locks prevent duplicate workers from
    # processing a row simultaneously; SMTP is bounded to ten seconds.
    for _ in range(limit):
        item = db.scalar(select(EmailDelivery).where(EmailDelivery.status == "PENDING",
            EmailDelivery.available_at <= utc_now()).order_by(EmailDelivery.id)
            .with_for_update(skip_locked=True).limit(1))
        if item is None:
            db.rollback()
            break
        outcome = AuditOutcome.FAILURE
        if is_expired(item.expires_at):
            item.status = "EXPIRED"
            item.encrypted_payload = None
        else:
            item.attempts += 1
            try:
                data = json.loads(decrypt_mail_payload(settings, item.encrypted_payload))
                if data.pop("kind") == "password_reset":
                    send_password_reset_email(settings, **data)
                else:
                    send_account_email(settings, **data)
                item.status = "SENT"
                item.encrypted_payload = None
                outcome = AuditOutcome.SUCCESS
                delivered += 1
            except Exception:
                if item.attempts >= 3:
                    item.status = "FAILED"
                    item.encrypted_payload = None
                else:
                    item.available_at = utc_now() + timedelta(seconds=60 * item.attempts)
        create_audit_log(db, event_type="auth.mail_delivery", outcome=outcome,
            user_id=item.user_id, target_type="email_delivery", target_id=item.id,
            details={"status": item.status, "attempts": item.attempts})
        db.commit()
    return delivered
