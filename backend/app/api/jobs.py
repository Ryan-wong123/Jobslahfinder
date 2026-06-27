from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.account import User
from app.schemas.auth import MessageResponse
from app.schemas.jobs import JobDetailResponse, JobListResponse, SavedJobListResponse, SavedJobResponse
from app.security.auth import require_authenticated_user
from app.services.jobs import (
    APPROVED_JOB_SOURCES,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    JobNotFoundError,
    get_visible_job_detail,
    list_jobs,
    list_saved_jobs_for_user,
    save_job_for_user,
    unsave_job_for_user,
)


router = APIRouter(tags=["jobs"])

SearchText = Annotated[
    str | None,
    Query(
        min_length=1,
        max_length=100,
        pattern=r"^[\w\s.,&()+#/'\-]+$",
    ),
]
Page = Annotated[int, Query(ge=1, le=1000)]
PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
JobId = Annotated[int, Path(gt=0)]
ApprovedSource = Literal["JobStreet", "MyCareersFuture"]


@router.get("/jobs", response_model=JobListResponse)
def browse_jobs(
    keyword: SearchText = None,
    company: SearchText = None,
    location: SearchText = None,
    category: SearchText = None,
    source: Annotated[ApprovedSource | None, Query()] = None,
    active_only: bool = True,
    include_suspicious: bool = False,
    page: Page = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    db: Session = Depends(get_db),
) -> JobListResponse:
    if source is not None and source not in APPROVED_JOB_SOURCES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid request.")
    return list_jobs(
        db,
        keyword=keyword,
        company=company,
        location=location,
        category=category,
        source=source,
        active_only=active_only,
        include_suspicious=include_suspicious,
        page=page,
        page_size=page_size,
    )


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
def job_detail(job_id: JobId, db: Session = Depends(get_db)) -> JobDetailResponse:
    try:
        return get_visible_job_detail(db, job_id=job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.") from exc


@router.post("/jobs/{job_id}/save", response_model=SavedJobResponse, status_code=status.HTTP_201_CREATED)
def save_job(
    job_id: JobId,
    request: Request,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> SavedJobResponse:
    try:
        return save_job_for_user(db, request, user_id=current_user.id, job_id=job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.") from exc


@router.delete("/jobs/{job_id}/save", response_model=MessageResponse)
def unsave_job(
    job_id: JobId,
    request: Request,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    try:
        unsave_job_for_user(db, request, user_id=current_user.id, job_id=job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.") from exc
    return MessageResponse(message="Job removed from saved jobs.")


@router.get("/saved-jobs", response_model=SavedJobListResponse)
def saved_jobs(
    page: Page = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> SavedJobListResponse:
    return list_saved_jobs_for_user(
        db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )
