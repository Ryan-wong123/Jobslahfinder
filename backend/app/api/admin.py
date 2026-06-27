from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models.account import User
from app.models.enums import AuditOutcome
from app.models.job import JobSource, ScrapingRun
from app.schemas.admin import AdminHealthResponse
from app.schemas.jobs import (
    JobSourceResponse,
    JobSourceUpdateRequest,
    ScrapingRunResponse,
    ScrapingRunTriggerRequest,
)
from app.security.auth import require_admin
from app.services.audit import create_audit_log
from app.services.jobs import seed_approved_job_sources, update_job_source_enabled
from app.services.scraping import ScrapingError, run_scraper_for_source


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health", response_model=AdminHealthResponse)
def admin_health(_current_admin: User = Depends(require_admin)) -> AdminHealthResponse:
    return AdminHealthResponse(status="ok", service="backend", access="admin")


@router.get("/job-sources", response_model=list[JobSourceResponse])
def list_job_sources(
    _current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[JobSource]:
    return list(db.scalars(select(JobSource).order_by(JobSource.source_name)).all())


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
    source_id: int,
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
    _current_admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[ScrapingRun]:
    return list(
        db.scalars(
            select(ScrapingRun).order_by(desc(ScrapingRun.started_at), desc(ScrapingRun.id)).limit(100)
        ).all()
    )


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
