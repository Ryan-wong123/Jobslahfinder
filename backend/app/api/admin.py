from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from redis import Redis
from sqlalchemy import delete, desc, func, not_, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models.account import User
from app.models.activity import ApplicationHistory, CoverLetter, Recommendation, SavedJob
from app.models.audit import AuditLog
from app.models.enums import AuditOutcome, UserRole
from app.models.job import JobPosting, JobSource, ScrapingRun
from app.models.resume import Resume
from app.schemas.admin import (
    AdminDependencyHealth,
    AdminAuditLogListResponse,
    AdminAuditLogResponse,
    AdminHealthResponse,
    AdminJobUpdateRequest,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserUpdateRequest,
)
from app.schemas.auth import MessageResponse
from app.schemas.jobs import (
    JobListResponse,
    JobSourceResponse,
    JobSourceUpdateRequest,
    JobSummaryResponse,
    ScrapingRunResponse,
    ScrapingRunTriggerRequest,
)
from app.security.auth import require_admin
from app.services.audit import SENSITIVE_DETAIL_KEYS, create_audit_log
from app.services.jobs import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    job_to_summary_response,
    escape_like_term,
    seed_approved_job_sources,
    update_job_source_enabled,
)
from app.services.scraping import ScrapingError, run_scraper_for_source
from app.workers.celery_app import celery_app


router = APIRouter(prefix="/admin", tags=["admin"])

Page = Annotated[int, Query(ge=1, le=1000)]
PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
PositiveId = Annotated[int, Path(gt=0)]
SearchText = Annotated[str | None, Query(min_length=1, max_length=100, pattern=r"^[\w\s.@,+#/'\-]+$")]
AuditEventType = Annotated[str | None, Query(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.:-]+$")]
AuditOutcomeFilter = Literal["SUCCESS", "FAILURE", "DENIED"]
RunStatusFilter = Literal["PENDING", "RUNNING", "SUCCESS", "FAILED"]
ApprovedSource = Literal["JobStreet", "MyCareersFuture", "JobsLah", "FastJobs"]
AuditDateTime = Annotated[datetime | None, Query()]
ADMIN_AUDIT_DETAIL_BLOCKLIST = SENSITIVE_DETAIL_KEYS | {
    "prompt",
    "full_prompt",
    "resume_content",
    "resume_text",
    "extracted_text",
    "cover_letter_text",
    "generated_text",
    "edited_text",
    "api_key",
    "secret",
}


def safe_admin_audit_details(details: dict | None) -> dict | None:
    if details is None:
        return None
    return {
        key: value
        for key, value in details.items()
        if key.lower() not in ADMIN_AUDIT_DETAIL_BLOCKLIST
    }


def audit_log_to_admin_response(audit_log: AuditLog) -> AdminAuditLogResponse:
    return AdminAuditLogResponse(
        id=audit_log.id,
        user_id=audit_log.user_id,
        event_type=audit_log.event_type,
        target_type=audit_log.target_type,
        target_id=audit_log.target_id,
        outcome=audit_log.outcome,
        details_json=safe_admin_audit_details(audit_log.details_json),
        created_at=audit_log.created_at,
    )


def dependency_status(status_value: str) -> AdminDependencyHealth:
    return AdminDependencyHealth(status=status_value)


def check_redis_status(settings: Settings) -> str:
    try:
        client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        try:
            return "ok" if client.ping() else "unavailable"
        finally:
            client.close()
    except Exception:
        return "unavailable"


def check_worker_status() -> str:
    try:
        responses = celery_app.control.inspect(timeout=0.5).ping()
    except Exception:
        return "unavailable"
    return "ok" if responses else "unavailable"


def admin_user_detail_response(db: Session, user: User) -> AdminUserDetailResponse:
    return AdminUserDetailResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
        resume_count=db.scalar(select(func.count()).select_from(Resume).where(Resume.user_id == user.id)) or 0,
        saved_job_count=db.scalar(select(func.count()).select_from(SavedJob).where(SavedJob.user_id == user.id)) or 0,
        recommendation_count=db.scalar(
            select(func.count()).select_from(Recommendation).where(Recommendation.user_id == user.id)
        )
        or 0,
        cover_letter_count=db.scalar(
            select(func.count()).select_from(CoverLetter).where(CoverLetter.user_id == user.id)
        )
        or 0,
        application_history_count=db.scalar(
            select(func.count()).select_from(ApplicationHistory).where(ApplicationHistory.user_id == user.id)
        )
        or 0,
    )


@router.get("/health", response_model=AdminHealthResponse)
def admin_health(
    _current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AdminHealthResponse:
    try:
        db.execute(select(1))
        database_status = "ok"
    except Exception:
        database_status = "unavailable"
    return AdminHealthResponse(
        status="ok",
        service="backend",
        access="admin",
        timestamp=datetime.now(timezone.utc),
        database=dependency_status(database_status),
        redis=dependency_status(check_redis_status(settings)),
        worker=dependency_status(check_worker_status()),
    )


@router.get("/users", response_model=AdminUserListResponse)
def list_admin_users(
    email: SearchText = None,
    role: Annotated[Literal["USER", "ADMIN"] | None, Query()] = None,
    is_active: bool | None = None,
    page: Page = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    _current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserListResponse:
    filters = []
    if email:
        filters.append(User.email.ilike(f"%{escape_like_term(email.strip())}%", escape="\\"))
    if role:
        filters.append(User.role == role)
    if is_active is not None:
        filters.append(User.is_active.is_(is_active))

    base_stmt = select(User).where(*filters)
    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
    users = list(
        db.scalars(
            base_stmt.order_by(desc(User.created_at), desc(User.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return AdminUserListResponse(
        items=[AdminUserResponse.model_validate(user) for user in users],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
def get_admin_user_detail(
    user_id: PositiveId,
    _current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserDetailResponse:
    target = db.scalar(select(User).where(User.id == user_id))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    return admin_user_detail_response(db, target)


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
def update_admin_user(
    user_id: PositiveId,
    payload: AdminUserUpdateRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    target = db.scalar(select(User).where(User.id == user_id))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    if target.id == current_admin.id and payload.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid admin update.")
    if target.role == UserRole.ADMIN.value and payload.is_active is False:
        active_admin_count = db.scalar(
            select(func.count()).select_from(User).where(
                User.role == UserRole.ADMIN.value,
                User.is_active.is_(True),
            )
        ) or 0
        if active_admin_count <= 1:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid admin update.")

    target.is_active = payload.is_active
    create_audit_log(
        db,
        event_type="admin.user.update",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=current_admin.id,
        target_type="user",
        target_id=target.id,
        details={"is_active": payload.is_active},
    )
    db.commit()
    db.refresh(target)
    return target


@router.get("/jobs", response_model=JobListResponse)
def list_admin_jobs(
    keyword: SearchText = None,
    company: SearchText = None,
    location: SearchText = None,
    category: SearchText = None,
    source: Annotated[ApprovedSource | None, Query()] = None,
    is_active: bool | None = None,
    is_suspicious: bool | None = None,
    page: Page = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    _current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JobListResponse:
    filters = []
    if is_active is not None:
        filters.append(JobPosting.is_active.is_(is_active))
    if is_suspicious is not None:
        filters.append(JobPosting.is_suspicious.is_(is_suspicious))
    if keyword:
        pattern = f"%{escape_like_term(keyword.strip())}%"
        filters.append(
            or_(
                JobPosting.title.ilike(pattern, escape="\\"),
                JobPosting.company.ilike(pattern, escape="\\"),
                JobPosting.location.ilike(pattern, escape="\\"),
                JobPosting.category.ilike(pattern, escape="\\"),
                JobPosting.description.ilike(pattern, escape="\\"),
            )
        )
    if company:
        filters.append(JobPosting.company.ilike(f"%{escape_like_term(company.strip())}%", escape="\\"))
    if location:
        filters.append(JobPosting.location.ilike(f"%{escape_like_term(location.strip())}%", escape="\\"))
    if category:
        filters.append(JobPosting.category.ilike(f"%{escape_like_term(category.strip())}%", escape="\\"))
    if source:
        filters.append(JobSource.source_name == source)

    base_stmt = select(JobPosting).join(JobPosting.source).where(*filters)
    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
    jobs = list(
        db.scalars(
            base_stmt.options(selectinload(JobPosting.source))
            .order_by(
                JobPosting.posted_at.desc().nullslast(),
                JobPosting.posting_date.desc().nullslast(),
                JobPosting.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return JobListResponse(
        items=[job_to_summary_response(job) for job in jobs],
        page=page,
        page_size=page_size,
        total_items=total,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.patch("/jobs/{job_id}", response_model=JobSummaryResponse)
def update_admin_job(
    job_id: PositiveId,
    payload: AdminJobUpdateRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JobSummaryResponse:
    if payload.is_active is None and payload.is_suspicious is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No changes provided.")
    job = db.scalar(
        select(JobPosting).options(selectinload(JobPosting.source)).where(JobPosting.id == job_id)
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")

    changed_fields: dict[str, bool] = {}
    if payload.is_active is not None and job.is_active != payload.is_active:
        job.is_active = payload.is_active
        changed_fields["is_active"] = payload.is_active
    if payload.is_suspicious is not None and job.is_suspicious != payload.is_suspicious:
        job.is_suspicious = payload.is_suspicious
        changed_fields["is_suspicious"] = payload.is_suspicious

    create_audit_log(
        db,
        event_type="admin.job.update",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=current_admin.id,
        target_type="job_posting",
        target_id=job.id,
        details={"changed_fields": changed_fields},
    )
    db.commit()
    db.refresh(job)
    return job_to_summary_response(job)


@router.delete("/jobs/{job_id}", response_model=MessageResponse)
def delete_admin_job(
    job_id: PositiveId,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MessageResponse:
    job = db.scalar(select(JobPosting).where(JobPosting.id == job_id))
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")

    saved_job_count = db.scalar(select(func.count()).select_from(SavedJob).where(SavedJob.job_id == job.id)) or 0
    recommendation_count = (
        db.scalar(select(func.count()).select_from(Recommendation).where(Recommendation.job_id == job.id)) or 0
    )
    cover_letter_ids = list(db.scalars(select(CoverLetter.id).where(CoverLetter.job_id == job.id)).all())
    cover_letter_count = len(cover_letter_ids)
    history_filters = [ApplicationHistory.job_id == job.id]
    if cover_letter_ids:
        history_filters.append(ApplicationHistory.cover_letter_id.in_(cover_letter_ids))
    history_unlinked_count = (
        db.scalar(select(func.count()).select_from(ApplicationHistory).where(or_(*history_filters))) or 0
    )

    if cover_letter_ids:
        db.execute(
            update(ApplicationHistory)
            .where(ApplicationHistory.cover_letter_id.in_(cover_letter_ids))
            .values(cover_letter_id=None)
        )
    db.execute(update(ApplicationHistory).where(ApplicationHistory.job_id == job.id).values(job_id=None))
    db.execute(delete(SavedJob).where(SavedJob.job_id == job.id))
    db.execute(delete(Recommendation).where(Recommendation.job_id == job.id))
    db.execute(delete(CoverLetter).where(CoverLetter.job_id == job.id))
    db.delete(job)
    create_audit_log(
        db,
        event_type="admin.job.delete",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=current_admin.id,
        target_type="job_posting",
        target_id=job_id,
        details={
            "saved_jobs_deleted": saved_job_count,
            "recommendations_deleted": recommendation_count,
            "cover_letters_deleted": cover_letter_count,
            "application_history_unlinked": history_unlinked_count,
        },
    )
    db.commit()
    return MessageResponse(message="Job deleted.")


@router.get("/job-sources", response_model=list[JobSourceResponse])
def list_job_sources(
    _current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[JobSourceResponse]:
    rows = db.execute(
        select(JobSource, func.count(JobPosting.id))
        .outerjoin(JobPosting, JobPosting.source_id == JobSource.id)
        .group_by(
            JobSource.id,
            JobSource.source_name,
            JobSource.base_url,
            JobSource.is_enabled,
            JobSource.created_at,
        )
        .order_by(JobSource.source_name)
    ).all()
    return [
        JobSourceResponse(
            id=source.id,
            source_name=source.source_name,
            base_url=source.base_url,
            is_enabled=source.is_enabled,
            created_at=source.created_at,
            job_count=job_count,
        )
        for source, job_count in rows
    ]


@router.post("/job-sources/seed", response_model=list[JobSourceResponse])
def seed_job_sources(
    request: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[JobSource]:
    return seed_approved_job_sources(
        db,
        settings,
        request=request,
        admin_user_id=current_admin.id,
    )


@router.patch("/job-sources/{source_id}", response_model=JobSourceResponse)
def update_job_source(
    source_id: PositiveId,
    payload: JobSourceUpdateRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JobSource:
    source = db.scalar(select(JobSource).where(JobSource.id == source_id))
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    return update_job_source_enabled(
        db,
        source=source,
        is_enabled=payload.is_enabled,
        request=request,
        admin_user_id=current_admin.id,
    )


@router.get("/scraping-runs", response_model=list[ScrapingRunResponse])
def list_scraping_runs(
    status_filter: Annotated[RunStatusFilter | None, Query(alias="status")] = None,
    source_id: Annotated[int | None, Query(gt=0)] = None,
    page: Page = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    _current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[ScrapingRun]:
    filters = []
    if status_filter:
        filters.append(ScrapingRun.status == status_filter)
    if source_id is not None:
        filters.append(ScrapingRun.source_id == source_id)
    return list(
        db.scalars(
            select(ScrapingRun)
            .where(*filters)
            .order_by(desc(ScrapingRun.started_at), desc(ScrapingRun.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )


@router.get("/scraping-runs/{run_id}", response_model=ScrapingRunResponse)
def get_scraping_run_detail(
    run_id: PositiveId,
    _current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ScrapingRun:
    run = db.scalar(select(ScrapingRun).where(ScrapingRun.id == run_id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    return run


@router.post("/scraping-runs", response_model=ScrapingRunResponse, status_code=status.HTTP_201_CREATED)
def trigger_scraping_run(
    payload: ScrapingRunTriggerRequest,
    request: Request,
    current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ScrapingRun:
    source = db.scalar(select(JobSource).where(JobSource.id == payload.source_id))
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    try:
        return run_scraper_for_source(db, source=source, request=request, user_id=current_admin.id)
    except ScrapingError as exc:
        create_audit_log(
            db,
            event_type="admin.scraping_run.trigger",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=current_admin.id,
            target_type="job_source",
            target_id=source.id,
            details={"reason": "source_unavailable"},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to start scraping run.",
        ) from exc


@router.get("/audit-logs", response_model=AdminAuditLogListResponse)
def list_admin_audit_logs(
    event_type: AuditEventType = None,
    outcome: Annotated[AuditOutcomeFilter | None, Query()] = None,
    user_id: Annotated[int | None, Query(gt=0)] = None,
    created_from: AuditDateTime = None,
    created_to: AuditDateTime = None,
    page: Page = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    _current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminAuditLogListResponse:
    filters = [
        not_(AuditLog.event_type.like("risk_engine.%")),
        AuditLog.event_type != "auth.risk_engine_assessment",
    ]
    if event_type:
        filters.append(AuditLog.event_type == event_type)
    if outcome:
        filters.append(AuditLog.outcome == outcome)
    if user_id is not None:
        filters.append(AuditLog.user_id == user_id)
    if created_from is not None:
        filters.append(AuditLog.created_at >= created_from)
    if created_to is not None:
        filters.append(AuditLog.created_at <= created_to)
    if created_from is not None and created_to is not None and created_from > created_to:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid date range.")

    base_stmt = select(AuditLog).where(*filters)
    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
    logs = list(
        db.scalars(
            base_stmt.order_by(desc(AuditLog.created_at), desc(AuditLog.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return AdminAuditLogListResponse(
        items=[audit_log_to_admin_response(log) for log in logs],
        page=page,
        page_size=page_size,
        total=total,
    )
