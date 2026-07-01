from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.job_roles import JobRoleDetailResponse, JobRoleListResponse
from app.services.job_roles import get_job_role_detail, list_job_roles

router = APIRouter(tags=["job_roles"])

RoleSlug = Annotated[str, Path(min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")]


@router.get("/job-roles", response_model=JobRoleListResponse)
def job_roles(db: Session = Depends(get_db)) -> JobRoleListResponse:
    return list_job_roles(db)


@router.get("/job-roles/{slug}", response_model=JobRoleDetailResponse)
def job_role_detail(slug: RoleSlug, db: Session = Depends(get_db)) -> JobRoleDetailResponse:
    detail = get_job_role_detail(db, slug)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    return detail
