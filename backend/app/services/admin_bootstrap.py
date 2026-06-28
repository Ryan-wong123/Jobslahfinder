from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.account import User, UserProfile
from app.models.enums import AuditOutcome, UserRole
from app.schemas.auth import validate_email, validate_password_strength
from app.security.passwords import hash_password
from app.services.audit import create_audit_log


class InitialAdminCreationError(ValueError):
    pass


def create_initial_admin(db: Session, *, email: str, password: str) -> User:
    normalized_email = validate_email(email)
    validate_password_strength(password)

    existing_admin = db.scalar(select(User).where(User.role == UserRole.ADMIN.value))
    if existing_admin is not None:
        raise InitialAdminCreationError("Initial admin already exists.")

    existing_user = db.scalar(select(User).where(User.email == normalized_email))
    if existing_user is not None:
        raise InitialAdminCreationError("Unable to create initial admin.")

    user = User(
        email=normalized_email,
        password_hash=hash_password(password),
        role=UserRole.ADMIN.value,
        is_active=True,
        failed_login_count=0,
    )
    user.profile = UserProfile()
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise InitialAdminCreationError("Unable to create initial admin.") from exc

    create_audit_log(
        db,
        event_type="admin.initial_admin_create",
        outcome=AuditOutcome.SUCCESS,
        user_id=user.id,
        target_type="user",
        target_id=user.id,
        details={"role": UserRole.ADMIN.value},
    )
    db.commit()
    db.refresh(user)
    return user
