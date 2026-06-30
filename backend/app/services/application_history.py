from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.activity import ApplicationHistory


APPLICATION_HISTORY_ACTION_TYPES = frozenset(
    {
        "cover_letter_generated",
        "cover_letter_edited",
        "job_saved",
        "job_unsaved",
        "recommendations_refreshed",
    }
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def add_application_history(
    db: Session,
    *,
    user_id: int,
    action_type: str,
    job_id: int | None = None,
    cover_letter_id: int | None = None,
    action_time: datetime | None = None,
) -> ApplicationHistory:
    if action_type not in APPLICATION_HISTORY_ACTION_TYPES:
        raise ValueError("unsupported_application_history_action")

    history = ApplicationHistory(
        user_id=user_id,
        job_id=job_id,
        cover_letter_id=cover_letter_id,
        action_type=action_type,
        action_time=action_time or utc_now(),
    )
    db.add(history)
    return history
