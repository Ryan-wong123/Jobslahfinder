from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.account import User
from app.schemas.activity import (
    ApplicationHistoryListResponse,
    CoverLetterListResponse,
    CoverLetterResponse,
    CoverLetterUpdateRequest,
    RecommendationListResponse,
)
from app.security.auth import require_authenticated_user
from app.services.activity import (
    ActivityNotFoundError,
    get_cover_letter_for_user,
    list_application_history_for_user,
    list_cover_letters_for_user,
    list_recommendations_for_user,
    update_cover_letter_for_user,
)
from app.services.jobs import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE


router = APIRouter(tags=["activity"])

Page = Annotated[int, Query(ge=1, le=1000)]
PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
CoverLetterId = Annotated[int, Path(gt=0)]


@router.get("/recommendations", response_model=RecommendationListResponse)
def recommendations(
    page: Page = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> RecommendationListResponse:
    return list_recommendations_for_user(
        db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )


@router.get("/cover-letters", response_model=CoverLetterListResponse)
def cover_letters(
    page: Page = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> CoverLetterListResponse:
    return list_cover_letters_for_user(
        db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )


@router.get("/cover-letters/{cover_letter_id}", response_model=CoverLetterResponse)
def cover_letter_detail(
    cover_letter_id: CoverLetterId,
    request: Request,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> CoverLetterResponse:
    try:
        return get_cover_letter_for_user(
            db,
            request,
            current_user=current_user,
            cover_letter_id=cover_letter_id,
        )
    except ActivityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Resource not found.") from exc


@router.patch("/cover-letters/{cover_letter_id}", response_model=CoverLetterResponse)
def update_cover_letter(
    cover_letter_id: CoverLetterId,
    payload: CoverLetterUpdateRequest,
    request: Request,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> CoverLetterResponse:
    try:
        return update_cover_letter_for_user(
            db,
            request,
            current_user=current_user,
            cover_letter_id=cover_letter_id,
            payload=payload,
        )
    except ActivityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Resource not found.") from exc


@router.get("/application-history", response_model=ApplicationHistoryListResponse)
def application_history(
    page: Page = 1,
    page_size: PageSize = DEFAULT_PAGE_SIZE,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> ApplicationHistoryListResponse:
    return list_application_history_for_user(
        db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )
