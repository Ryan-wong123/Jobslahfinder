from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import User
from app.models.activity import ApplicationHistory, CoverLetter, Recommendation
from app.models.enums import AuditOutcome
from app.models.job import JobPosting
from app.schemas.activity import (
    ApplicationHistoryListResponse,
    ApplicationHistoryResponse,
    CoverLetterListResponse,
    CoverLetterResponse,
    CoverLetterUpdateRequest,
    RecommendationListResponse,
    RecommendationResponse,
)
from app.security.auth import assert_owner_or_admin
from app.services.audit import create_audit_log
from app.services.jobs import DEFAULT_PAGE_SIZE, job_to_summary_response


class ActivityNotFoundError(ValueError):
    pass


def recommendation_to_response(recommendation: Recommendation) -> RecommendationResponse:
    return RecommendationResponse(
        id=recommendation.id,
        job=job_to_summary_response(recommendation.job),
        resume_id=recommendation.resume_id,
        match_score=float(recommendation.match_score),
        rank=recommendation.rank,
        rationale=recommendation.rationale,
        metadata=recommendation.metadata_json,
        generated_at=recommendation.generated_at,
    )


def cover_letter_to_response(cover_letter: CoverLetter) -> CoverLetterResponse:
    return CoverLetterResponse(
        id=cover_letter.id,
        job=job_to_summary_response(cover_letter.job),
        resume_id=cover_letter.resume_id,
        generated_text=cover_letter.generated_text,
        edited_text=cover_letter.edited_text,
        version_no=cover_letter.version_no,
        created_at=cover_letter.created_at,
        updated_at=cover_letter.updated_at,
    )


def application_history_to_response(history: ApplicationHistory) -> ApplicationHistoryResponse:
    return ApplicationHistoryResponse(
        id=history.id,
        job=job_to_summary_response(history.job) if history.job is not None else None,
        cover_letter_id=history.cover_letter_id,
        action_type=history.action_type,
        action_time=history.action_time,
    )


def list_recommendations_for_user(
    db: Session,
    *,
    user_id: int,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> RecommendationListResponse:
    base_stmt = select(Recommendation).where(Recommendation.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
    recommendations = list(
        db.scalars(
            base_stmt.options(selectinload(Recommendation.job).selectinload(JobPosting.source))
            .order_by(Recommendation.rank.asc().nullslast(), Recommendation.generated_at.desc(), Recommendation.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return RecommendationListResponse(
        items=[recommendation_to_response(recommendation) for recommendation in recommendations],
        page=page,
        page_size=page_size,
        total=total,
    )


def list_cover_letters_for_user(
    db: Session,
    *,
    user_id: int,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> CoverLetterListResponse:
    base_stmt = select(CoverLetter).where(CoverLetter.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
    cover_letters = list(
        db.scalars(
            base_stmt.options(selectinload(CoverLetter.job).selectinload(JobPosting.source))
            .order_by(CoverLetter.updated_at.desc(), CoverLetter.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return CoverLetterListResponse(
        items=[cover_letter_to_response(cover_letter) for cover_letter in cover_letters],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_cover_letter_for_user(
    db: Session,
    request,
    *,
    current_user: User,
    cover_letter_id: int,
) -> CoverLetterResponse:
    cover_letter = db.scalar(
        select(CoverLetter)
        .options(selectinload(CoverLetter.job).selectinload(JobPosting.source))
        .where(CoverLetter.id == cover_letter_id)
    )
    if cover_letter is None:
        raise ActivityNotFoundError("Resource not found.")

    assert_owner_or_admin(
        db,
        request,
        current_user=current_user,
        owner_user_id=cover_letter.user_id,
        target_type="cover_letter",
        target_id=cover_letter.id,
    )
    return cover_letter_to_response(cover_letter)


def update_cover_letter_for_user(
    db: Session,
    request,
    *,
    current_user: User,
    cover_letter_id: int,
    payload: CoverLetterUpdateRequest,
) -> CoverLetterResponse:
    cover_letter = db.scalar(
        select(CoverLetter)
        .options(selectinload(CoverLetter.job).selectinload(JobPosting.source))
        .where(CoverLetter.id == cover_letter_id)
    )
    if cover_letter is None:
        raise ActivityNotFoundError("Resource not found.")

    assert_owner_or_admin(
        db,
        request,
        current_user=current_user,
        owner_user_id=cover_letter.user_id,
        target_type="cover_letter",
        target_id=cover_letter.id,
    )
    cover_letter.edited_text = payload.edited_text
    cover_letter.version_no += 1
    create_audit_log(
        db,
        event_type="cover_letter.edit",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=current_user.id,
        target_type="cover_letter",
        target_id=cover_letter.id,
        details={"version_no": cover_letter.version_no},
    )
    db.commit()
    db.refresh(cover_letter)
    return cover_letter_to_response(cover_letter)


def list_application_history_for_user(
    db: Session,
    *,
    user_id: int,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> ApplicationHistoryListResponse:
    base_stmt = select(ApplicationHistory).where(ApplicationHistory.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
    history_items = list(
        db.scalars(
            base_stmt.options(selectinload(ApplicationHistory.job).selectinload(JobPosting.source))
            .order_by(ApplicationHistory.action_time.desc(), ApplicationHistory.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return ApplicationHistoryListResponse(
        items=[application_history_to_response(history) for history in history_items],
        page=page,
        page_size=page_size,
        total=total,
    )
