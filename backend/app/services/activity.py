from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import User
from app.models.activity import ApplicationHistory, CoverLetter, Recommendation
from app.models.enums import AuditOutcome, ProcessingStatus, UploadStatus
from app.models.job import JobPosting
from app.models.resume import Resume, ResumeExtraction
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
from app.services.jobs import DEFAULT_PAGE_SIZE, JobNotFoundError, clean_text, get_saveable_job, job_to_summary_response


class ActivityNotFoundError(ValueError):
    pass


class CoverLetterGenerationInputMissingError(ValueError):
    pass


class CoverLetterGenerationJobUnavailableError(ValueError):
    pass


MAX_DRAFT_TEXT_LENGTH = 8_000
MAX_PROFILE_ITEM_LENGTH = 120
MAX_JOB_CONTEXT_LENGTH = 700
COVER_LETTER_GENERATOR_VERSION = "deterministic-cover-letter-v1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def json_items(value: dict | None) -> list:
    if not isinstance(value, dict):
        return []
    items = value.get("items")
    return items if isinstance(items, list) else []


def safe_profile_text(value: object, *, max_length: int = MAX_PROFILE_ITEM_LENGTH) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = clean_text(value, max_length=max_length)
    return cleaned or None


def safe_profile_items(value: dict | None, *, limit: int = 6) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for item in json_items(value):
        text = safe_profile_text(item)
        if text is None or text.casefold() in seen:
            continue
        items.append(text)
        seen.add(text.casefold())
        if len(items) >= limit:
            break
    return items


def safe_profile_dict_items(value: dict | None, *, keys: tuple[str, ...], limit: int = 3) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for item in json_items(value):
        if not isinstance(item, dict):
            continue
        parts = [safe_profile_text(item.get(key)) for key in keys]
        text = ", ".join(part for part in parts if part)
        if not text or text.casefold() in seen:
            continue
        items.append(text[:MAX_PROFILE_ITEM_LENGTH])
        seen.add(text.casefold())
        if len(items) >= limit:
            break
    return items


def latest_completed_extraction(db: Session, *, user_id: int) -> ResumeExtraction | None:
    return db.scalar(
        select(ResumeExtraction)
        .join(Resume)
        .where(
            Resume.user_id == user_id,
            Resume.upload_status == UploadStatus.STORED.value,
            ResumeExtraction.processing_status == ProcessingStatus.COMPLETED.value,
        )
        .order_by(desc(ResumeExtraction.processed_at), desc(ResumeExtraction.id))
    )


def build_deterministic_cover_letter(*, extraction: ResumeExtraction, job: JobPosting) -> str:
    skills = safe_profile_items(extraction.skills_json)
    experience = safe_profile_dict_items(
        extraction.experience_json,
        keys=("title", "company"),
    )
    education = safe_profile_dict_items(
        extraction.education_json,
        keys=("credential", "field"),
        limit=2,
    )
    title = clean_text(job.title, max_length=120) or "this role"
    company = clean_text(job.company, max_length=120) or "your team"
    location = clean_text(job.location, max_length=120)
    category = clean_text(job.category, max_length=120)
    job_context = clean_text(job.description, max_length=MAX_JOB_CONTEXT_LENGTH)
    years = float(extraction.years_experience) if extraction.years_experience is not None else None

    opening_context = f" for the {title} role"
    if location:
        opening_context += f" in {location}"

    skill_sentence = (
        f"My background includes {', '.join(skills[:5])}."
        if skills
        else "My background includes adaptable technical and collaboration skills."
    )
    experience_sentence = (
        f"Recent experience includes {', '.join(experience)}."
        if experience
        else "I have practical experience turning requirements into reliable, maintainable work."
    )
    if years is not None:
        experience_sentence += f" I bring about {years:g} years of relevant experience."
    education_sentence = f"My education includes {', '.join(education)}." if education else ""
    category_sentence = f"The role's {category} focus is especially relevant to my profile." if category else ""
    job_sentence = (
        f"I noted that the posting emphasizes {job_context[:360]}."
        if job_context
        else "I am interested in contributing to the responsibilities described for this position."
    )

    paragraphs = [
        f"Dear Hiring Team,\n\nI am writing to express my interest{opening_context} at {company}. "
        "This draft is intended as a starting point for review and tailoring before any application is submitted.",
        " ".join(part for part in [skill_sentence, experience_sentence, education_sentence] if part),
        " ".join(part for part in [job_sentence, category_sentence] if part),
        "I would welcome the opportunity to discuss how my profile can support your team's needs. "
        "Thank you for considering my application.\n\nSincerely,\n[Your Name]",
    ]
    return "\n\n".join(paragraphs)[:MAX_DRAFT_TEXT_LENGTH]


def create_cover_letter_for_job(
    db: Session,
    request,
    *,
    current_user: User,
    job_id: int,
) -> CoverLetterResponse:
    try:
        job = get_saveable_job(db, job_id=job_id)
    except JobNotFoundError as exc:
        create_audit_log(
            db,
            event_type="cover_letter.generate",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=current_user.id,
            target_type="job_posting",
            target_id=job_id,
            details={"reason": "job_unavailable"},
        )
        db.commit()
        raise CoverLetterGenerationJobUnavailableError("Resource not found.") from exc

    extraction = latest_completed_extraction(db, user_id=current_user.id)
    if extraction is None:
        create_audit_log(
            db,
            event_type="cover_letter.generate",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=current_user.id,
            target_type="job_posting",
            target_id=job.id,
            details={"reason": "no_completed_extraction", "job_id": job.id},
        )
        db.commit()
        raise CoverLetterGenerationInputMissingError("No completed resume extraction is available.")

    generated_text = build_deterministic_cover_letter(extraction=extraction, job=job)
    cover_letter = CoverLetter(
        user_id=current_user.id,
        job_id=job.id,
        resume_id=extraction.resume_id,
        generated_text=generated_text,
        version_no=1,
    )
    db.add(cover_letter)
    db.flush()
    db.add(
        ApplicationHistory(
            user_id=current_user.id,
            job_id=job.id,
            cover_letter_id=cover_letter.id,
            action_type="cover_letter_generated",
            action_time=utc_now(),
        )
    )
    create_audit_log(
        db,
        event_type="cover_letter.generate",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=current_user.id,
        target_type="cover_letter",
        target_id=cover_letter.id,
        details={
            "job_id": job.id,
            "resume_id": extraction.resume_id,
            "extraction_id": extraction.id,
            "generator_version": COVER_LETTER_GENERATOR_VERSION,
        },
    )
    db.commit()
    db.refresh(cover_letter)
    cover_letter.job = job
    return cover_letter_to_response(cover_letter)


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
        create_audit_log(
            db,
            event_type="cover_letter.edit",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=current_user.id,
            target_type="cover_letter",
            target_id=cover_letter_id,
            details={"reason": "not_found"},
        )
        db.commit()
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
    db.add(
        ApplicationHistory(
            user_id=current_user.id,
            job_id=cover_letter.job_id,
            cover_letter_id=cover_letter.id,
            action_type="cover_letter_edited",
            action_time=utc_now(),
        )
    )
    create_audit_log(
        db,
        event_type="cover_letter.edit",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=current_user.id,
        target_type="cover_letter",
        target_id=cover_letter.id,
        details={
            "job_id": cover_letter.job_id,
            "resume_id": cover_letter.resume_id,
            "cover_letter_id": cover_letter.id,
            "version_no": cover_letter.version_no,
            "action": "edited",
        },
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
