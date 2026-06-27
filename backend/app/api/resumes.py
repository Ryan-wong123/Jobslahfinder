from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Path, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit_auth
from app.models.account import User
from app.schemas.auth import MessageResponse
from app.schemas.resumes import ResumeExtractionResponse, ResumeListResponse, ResumeResponse
from app.security.auth import require_authenticated_user
from app.services.resumes import (
    GENERIC_UPLOAD_ERROR,
    ResumeNotFoundError,
    ResumeValidationError,
    create_resume_upload,
    delete_resume_for_user,
    get_resume_detail,
    get_resume_extraction,
    list_resumes_for_user,
)


router = APIRouter(tags=["resumes"])

ResumeId = Annotated[int, Path(gt=0)]


@router.post("/resumes", response_model=ResumeResponse, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ResumeResponse:
    rate_limit_auth(request, "resume-upload", limit=10, window_seconds=300)
    try:
        return await create_resume_upload(db, request, user=current_user, file=file, settings=settings)
    except ResumeValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=GENERIC_UPLOAD_ERROR) from exc


@router.get("/resumes", response_model=ResumeListResponse)
def list_resumes(
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> ResumeListResponse:
    return list_resumes_for_user(db, user_id=current_user.id)


@router.get("/resumes/{resume_id}", response_model=ResumeResponse)
def resume_detail(
    resume_id: ResumeId,
    request: Request,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> ResumeResponse:
    try:
        return get_resume_detail(db, request, user=current_user, resume_id=resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.") from exc


@router.delete("/resumes/{resume_id}", response_model=MessageResponse)
def delete_resume(
    resume_id: ResumeId,
    request: Request,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    try:
        delete_resume_for_user(db, request, user=current_user, resume_id=resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.") from exc
    return MessageResponse(message="Resume deleted.")


@router.get("/resumes/{resume_id}/extraction", response_model=ResumeExtractionResponse)
def resume_extraction(
    resume_id: ResumeId,
    request: Request,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> ResumeExtractionResponse:
    try:
        return get_resume_extraction(db, request, user=current_user, resume_id=resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.") from exc
