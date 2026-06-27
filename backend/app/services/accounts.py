from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.account import PasswordResetToken, Session as UserSession, User, UserProfile
from app.models.activity import ApplicationHistory, CoverLetter, Recommendation, SavedJob
from app.models.enums import AuditOutcome
from app.models.resume import Resume, ResumeExtraction
from app.schemas.auth import AccountUpdateRequest, ProfileResponse, ProfileUpdateRequest
from app.security.passwords import hash_password, verify_password
from app.security.tokens import generate_token
from app.services.audit import create_audit_log
from app.services.auth import utc_now


GENERIC_ACCOUNT_UPDATE_ERROR = "Unable to update account."
GENERIC_DELETE_ERROR = "Unable to delete account."


def _skills_from_json(skills_json: dict[str, Any] | list[Any] | None) -> list[str]:
    raw_items: Any
    if isinstance(skills_json, dict):
        raw_items = skills_json.get("items", [])
    elif isinstance(skills_json, list):
        raw_items = skills_json
    else:
        raw_items = []

    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items if isinstance(item, str)]


def profile_to_response(profile: UserProfile) -> ProfileResponse:
    return ProfileResponse(
        user_id=profile.user_id,
        full_name=profile.full_name,
        phone=profile.phone,
        location=profile.location,
        summary=profile.summary,
        skills=_skills_from_json(profile.skills_json),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def get_or_create_profile(db: Session, user: User) -> UserProfile:
    if user.profile is not None:
        return user.profile
    profile = UserProfile(user_id=user.id)
    db.add(profile)
    db.flush()
    return profile


def _apply_profile_updates(profile: UserProfile, payload: ProfileUpdateRequest) -> list[str]:
    changed_fields: list[str] = []
    for field_name in ("full_name", "phone", "location", "summary"):
        if field_name in payload.model_fields_set:
            setattr(profile, field_name, getattr(payload, field_name))
            changed_fields.append(field_name)
    if "skills" in payload.model_fields_set:
        profile.skills_json = {"items": payload.skills or []}
        changed_fields.append("skills")
    return changed_fields


def update_profile_for_user(
    db: Session,
    request: Request,
    *,
    user: User,
    payload: ProfileUpdateRequest,
) -> ProfileResponse:
    profile = get_or_create_profile(db, user)
    changed_fields = _apply_profile_updates(profile, payload)
    create_audit_log(
        db,
        event_type="account.profile_update",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user.id,
        target_type="user_profile",
        target_id=user.id,
        details={"changed_fields": changed_fields},
    )
    db.commit()
    db.refresh(profile)
    return profile_to_response(profile)


def update_account_for_user(
    db: Session,
    request: Request,
    *,
    user: User,
    payload: AccountUpdateRequest,
) -> User:
    changed_fields: list[str] = []
    if "email" in payload.model_fields_set and payload.email is not None and payload.email != user.email:
        existing_user = db.scalar(select(User).where(User.email == payload.email, User.id != user.id))
        if existing_user is not None:
            create_audit_log(
                db,
                event_type="account.update",
                outcome=AuditOutcome.FAILURE,
                request=request,
                user_id=user.id,
                target_type="user",
                target_id=user.id,
                details={"reason": "duplicate_email"},
            )
            db.commit()
            raise ValueError(GENERIC_ACCOUNT_UPDATE_ERROR)
        user.email = payload.email
        changed_fields.append("email")

    profile = get_or_create_profile(db, user)
    changed_fields.extend(_apply_profile_updates(profile, payload))
    create_audit_log(
        db,
        event_type="account.update",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user.id,
        target_type="user",
        target_id=user.id,
        details={"changed_fields": changed_fields},
    )
    db.commit()
    db.refresh(user)
    return user


def _unlink_resume_files(resumes: list[Resume]) -> int:
    deleted_count = 0
    for resume in resumes:
        try:
            Path(resume.file_path).unlink(missing_ok=True)
            deleted_count += 1
        except OSError:
            continue
    return deleted_count


def delete_account_for_user(
    db: Session,
    request: Request,
    *,
    user: User,
    password: str,
) -> None:
    if not verify_password(password, user.password_hash):
        create_audit_log(
            db,
            event_type="account.deletion_request",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=user.id,
            target_type="user",
            target_id=user.id,
            details={"reason": "invalid_password"},
        )
        db.commit()
        raise ValueError(GENERIC_DELETE_ERROR)

    create_audit_log(
        db,
        event_type="account.deletion_request",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user.id,
        target_type="user",
        target_id=user.id,
        details={"verification": "password"},
    )

    resumes = list(db.scalars(select(Resume).where(Resume.user_id == user.id)).all())
    resume_ids = [resume.id for resume in resumes]
    resume_files_deleted = _unlink_resume_files(resumes)

    if resume_ids:
        db.execute(delete(ResumeExtraction).where(ResumeExtraction.resume_id.in_(resume_ids)))
    db.execute(delete(ApplicationHistory).where(ApplicationHistory.user_id == user.id))
    db.execute(delete(CoverLetter).where(CoverLetter.user_id == user.id))
    db.execute(delete(Recommendation).where(Recommendation.user_id == user.id))
    db.execute(delete(SavedJob).where(SavedJob.user_id == user.id))
    db.execute(delete(Resume).where(Resume.user_id == user.id))

    profile = get_or_create_profile(db, user)
    profile.full_name = None
    profile.phone = None
    profile.location = None
    profile.summary = None
    profile.skills_json = {"items": []}

    now = utc_now()
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id)
        .where(UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id)
        .where(PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )

    user.email = f"deleted-user-{user.id}@deleted.invalid"
    user.password_hash = hash_password(generate_token())
    user.is_active = False
    user.failed_login_count = 0
    user.locked_until = None

    create_audit_log(
        db,
        event_type="account.deletion",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user.id,
        target_type="user",
        target_id=user.id,
        details={
            "strategy": "soft_delete",
            "sessions_invalidated": True,
            "resume_records_deleted": len(resumes),
            "resume_files_deleted": resume_files_deleted,
        },
    )
    db.commit()
