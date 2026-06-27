from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit_auth
from app.schemas.auth import (
    AccountDeletionRequest,
    AccountUpdateRequest,
    LoginRequest,
    MessageResponse,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    ProfileResponse,
    ProfileUpdateRequest,
    RegisterRequest,
    UserResponse,
)
from app.security.auth import AuthenticatedSession, require_authenticated_session, require_authenticated_user
from app.services.accounts import (
    GENERIC_ACCOUNT_UPDATE_ERROR,
    GENERIC_DELETE_ERROR,
    delete_account_for_user,
    profile_to_response,
    update_account_for_user,
    update_profile_for_user,
)
from app.services.auth import (
    GENERIC_LOGIN_ERROR,
    GENERIC_REGISTER_ERROR,
    GENERIC_RESET_ERROR,
    GENERIC_RESET_MESSAGE,
    authenticate_user,
    change_password,
    confirm_password_reset,
    create_session,
    register_user,
    request_password_reset,
    revoke_session,
)
from app.models.account import User


router = APIRouter(tags=["auth"])


def set_session_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_expire_minutes * 60,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    rate_limit_auth(request, "register", limit=10, window_seconds=300)
    try:
        return register_user(db, request, email=payload.email, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=GENERIC_REGISTER_ERROR) from exc


@router.post("/auth/login", response_model=MessageResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    rate_limit_auth(request, "login", limit=20, window_seconds=300)
    try:
        user = authenticate_user(db, request, email=payload.email, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR) from exc
    token, _session = create_session(db, request, settings, user=user)
    set_session_cookie(response, settings, token)
    return MessageResponse(message="Logged in.")


@router.post("/auth/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    authenticated_session: AuthenticatedSession = Depends(require_authenticated_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    revoke_session(db, request, session=authenticated_session.session, user=authenticated_session.user)
    clear_session_cookie(response, settings)
    return MessageResponse(message="Logged out.")


@router.post("/auth/password-change", response_model=MessageResponse)
def password_change(
    payload: PasswordChangeRequest,
    request: Request,
    authenticated_session: AuthenticatedSession = Depends(require_authenticated_session),
    db: Session = Depends(get_db),
) -> MessageResponse:
    rate_limit_auth(request, "password-change", limit=10, window_seconds=300)
    try:
        change_password(
            db,
            request,
            user=authenticated_session.user,
            current_session=authenticated_session.session,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to change password.") from exc
    return MessageResponse(message="Password changed.")


@router.post("/auth/password-reset/request", response_model=MessageResponse)
def password_reset_request(
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    rate_limit_auth(request, "password-reset-request", limit=10, window_seconds=300)
    request_password_reset(db, request, settings, email=payload.email)
    return MessageResponse(message=GENERIC_RESET_MESSAGE)


@router.post("/auth/password-reset/confirm", response_model=MessageResponse)
def password_reset_confirm(
    payload: PasswordResetConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    rate_limit_auth(request, "password-reset-confirm", limit=20, window_seconds=300)
    try:
        confirm_password_reset(
            db,
            request,
            settings,
            token=payload.token,
            new_password=payload.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=GENERIC_RESET_ERROR) from exc
    return MessageResponse(message="Password reset complete.")


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(require_authenticated_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_me(
    payload: AccountUpdateRequest,
    request: Request,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> User:
    try:
        return update_account_for_user(db, request, user=current_user, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=GENERIC_ACCOUNT_UPDATE_ERROR) from exc


@router.get("/me/profile", response_model=ProfileResponse)
def get_my_profile(
    current_user: User = Depends(require_authenticated_user),
) -> ProfileResponse:
    if current_user.profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found.")
    return profile_to_response(current_user.profile)


@router.patch("/me/profile", response_model=ProfileResponse)
def update_my_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> ProfileResponse:
    return update_profile_for_user(db, request, user=current_user, payload=payload)


@router.delete("/me", response_model=MessageResponse)
def delete_me(
    payload: AccountDeletionRequest,
    request: Request,
    response: Response,
    authenticated_session: AuthenticatedSession = Depends(require_authenticated_session),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessageResponse:
    rate_limit_auth(request, "account-delete", limit=5, window_seconds=300)
    try:
        delete_account_for_user(
            db,
            request,
            user=authenticated_session.user,
            password=payload.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=GENERIC_DELETE_ERROR) from exc
    clear_session_cookie(response, settings)
    return MessageResponse(message="Account deleted.")
