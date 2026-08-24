from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import rate_limit_auth
from app.schemas.job_roles import ExperienceSalaryComparisonResponse, JobRoleDetailResponse, JobRoleListResponse
from app.services.job_roles import get_job_role_detail, list_job_roles, salary_comparison_by_experience

router = APIRouter(tags=["job_roles"])

RoleSlug = Annotated[str, Path(min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")]
LocationFilter = Annotated[
    str | None,
    Query(min_length=2, max_length=100, pattern=r"^[\w\s.,()/'\-]+$"),
]


@router.get("/job-roles", response_model=JobRoleListResponse)
def job_roles(db: Session = Depends(get_db)) -> JobRoleListResponse:
    return list_job_roles(db)


@router.get("/job-roles/{slug}", response_model=JobRoleDetailResponse)
def job_role_detail(slug: RoleSlug, db: Session = Depends(get_db)) -> JobRoleDetailResponse:
    detail = get_job_role_detail(db, slug)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    return detail


@router.get("/job-roles/{slug}/salary-by-experience", response_model=ExperienceSalaryComparisonResponse)
def job_role_salary_by_experience(
    request: Request,
    slug: RoleSlug,
    location: LocationFilter = None,
    db: Session = Depends(get_db),
) -> ExperienceSalaryComparisonResponse:
    rate_limit_auth(request, "salary-by-experience", limit=60, window_seconds=300)
    comparison = salary_comparison_by_experience(db, slug=slug, location=location)
    if comparison is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    return comparison
