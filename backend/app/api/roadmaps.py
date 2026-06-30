from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import rate_limit_auth
from app.models.account import User
from app.schemas.roadmaps import (
    JobRoleRoadmapListResponse,
    JobRoleRoadmapResponse,
    RoadmapCreateRequest,
    RoadmapUpdateRequest,
)
from app.security.auth import require_authenticated_user
from app.services.jobs import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.services.roadmaps import (
    RoadmapNotFoundError,
    create_roadmap_for_user,
    get_roadmap_for_user,
    list_roadmaps_for_user,
    update_roadmap_for_user,
)

router = APIRouter(tags=["roadmaps"])

Page = Annotated[int, Query(ge=1, le=1000)]
PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
RoadmapId = Annotated[int, Path(gt=0)]


@router.get("/roadmaps", response_model=JobRoleRoadmapListResponse)
def roadmaps(
    page: Page = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> JobRoleRoadmapListResponse:
    return list_roadmaps_for_user(
        db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )


@router.post("/roadmaps", response_model=JobRoleRoadmapResponse)
def create_roadmap(
    payload: RoadmapCreateRequest,
    request: Request,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> JobRoleRoadmapResponse:
    rate_limit_auth(request, "roadmap-create", limit=10, window_seconds=300)
    return create_roadmap_for_user(
        db,
        request,
        current_user=current_user,
        payload=payload,
    )


@router.get("/roadmaps/{roadmap_id}", response_model=JobRoleRoadmapResponse)
def roadmap_detail(
    roadmap_id: RoadmapId,
    request: Request,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> JobRoleRoadmapResponse:
    try:
        return get_roadmap_for_user(
            db,
            request,
            current_user=current_user,
            roadmap_id=roadmap_id,
        )
    except RoadmapNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Resource not found.") from exc


@router.patch("/roadmaps/{roadmap_id}", response_model=JobRoleRoadmapResponse)
def update_roadmap(
    roadmap_id: RoadmapId,
    payload: RoadmapUpdateRequest,
    request: Request,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> JobRoleRoadmapResponse:
    try:
        return update_roadmap_for_user(
            db,
            request,
            current_user=current_user,
            roadmap_id=roadmap_id,
            payload=payload,
        )
    except RoadmapNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Resource not found.") from exc
