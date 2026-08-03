import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.rate_limit import rate_limit_auth
from app.schemas.auth import (
    AccountDeletionRequest,
    AccountUpdateRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    ProfileResponse,
    ProfileUpdateRequest,
    RegisterRequest,
    TwoFactorConfirmRequest,
    TwoFactorSetupResponse,
    TwoFactorVerifyRequest,
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
    AccountLockedError,
    GENERIC_LOGIN_ERROR,
    GENERIC_REGISTER_ERROR,
    GENERIC_RESET_ERROR,
    GENERIC_RESET_MESSAGE,
    TOO_MANY_LOGIN_ATTEMPTS_ERROR,
    authenticate_user,
    change_password,
    confirm_password_reset,
    create_session,
    register_user,
    request_password_reset,
    revoke_session,
)
from app.models.account import User
from app.models.enums import AuditOutcome
from app.services.risk_engine import (
    APP_DEVICE_COOKIE_NAME,
    evaluate_login_risk,
    get_or_create_app_device_id,
    ip_prefix_for_risk,
    issue_device_cookie,
    learn_successful_login,
)
from app.services.audit import create_audit_log
from app.services.two_factor import (
    create_pending_2fa_challenge,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_totp_secret,
    get_pending_2fa_challenge,
    invalidate_pending_2fa_challenge,
    provisioning_uri,
    verify_totp_code,
)
from app.services.auth import utc_now
from risk_engine.config import COOKIE_NAME, TOKEN_TTL_DAYS


router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)


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


def risk_engine_device_cookie_name(settings: Settings) -> str:
    return COOKIE_NAME if settings.secure_cookies else "rba_dt"


def set_risk_engine_cookies(
    request: Request,
    response: Response,
    settings: Settings,
    *,
    user: User,
    force_rotate: bool,
) -> str | None:
    device_id, is_new_device_id = get_or_create_app_device_id(request)
    if is_new_device_id:
        response.set_cookie(
            key=APP_DEVICE_COOKIE_NAME,
            value=device_id,
            max_age=TOKEN_TTL_DAYS * 24 * 60 * 60,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            path="/",
        )

    issued = issue_device_cookie(
        user_id=user.id,
        device_id=device_id,
        force_rotate=force_rotate,
    )
    if issued.rotate and issued.raw_token:
        response.set_cookie(
            key=risk_engine_device_cookie_name(settings),
            value=issued.raw_token,
            max_age=TOKEN_TTL_DAYS * 24 * 60 * 60,
            httponly=True,
            secure=settings.secure_cookies,
            samesite="lax",
            path="/",
        )
        return issued.raw_token
    return request.cookies.get(COOKIE_NAME) or request.cookies.get(risk_engine_device_cookie_name(settings))


def risk_block_status(risk_reasons: list[str]) -> int:
    rate_limit_reasons = {"rapid_login_attempts", "excessive_login_attempts"}
    if rate_limit_reasons.intersection(risk_reasons):
        return status.HTTP_429_TOO_MANY_REQUESTS
    return status.HTTP_401_UNAUTHORIZED


def risk_block_message(risk_reasons: list[str]) -> str:
    rate_limit_reasons = {"rapid_login_attempts", "excessive_login_attempts"}
    if rate_limit_reasons.intersection(risk_reasons):
        return TOO_MANY_LOGIN_ATTEMPTS_ERROR
    return GENERIC_LOGIN_ERROR


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


@router.post("/auth/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    rate_limit_auth(request, "login", limit=10, window_seconds=60)
    risk = evaluate_login_risk(
        request,
        username=payload.email,
        device_token=request.cookies.get(COOKIE_NAME)
        or request.cookies.get(risk_engine_device_cookie_name(settings)),
        learn_on_non_block=False,
    )
    _auth_exc: HTTPException | None = None
    user = None
    try:
        user = authenticate_user(db, request, email=payload.email, password=payload.password)
    except AccountLockedError as exc:
        _auth_exc = HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=TOO_MANY_LOGIN_ATTEMPTS_ERROR,
        )
    except ValueError as exc:
        _auth_exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

    # Preserve risk-engine rate-limit/block messages even when credentials are
    # wrong, so abuse responses stay consistent.
    if risk.decision == "block":
        raise HTTPException(
            status_code=risk_block_status(risk.reasons),
            detail=risk_block_message(risk.reasons),
        )

    if _auth_exc is not None:
        raise _auth_exc

    # At this point risk.decision is never "block" (already raised above).
    create_audit_log(
        db,
        event_type="auth.risk_engine_assessment",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user.id,
        target_type="user",
        target_id=user.id,
        details={
            "decision": risk.decision,
            "score": risk.score,
            "reasons": risk.reasons,
            "ip_prefix": risk.ip_prefix,
        },
    )
    db.commit()

    logger.info("Login successful.")
    print("Login successful.")

    if not user.totp_enabled:
        token, _session = create_session(db, request, settings, user=user)
        set_session_cookie(response, settings, token)
        return LoginResponse(message="Two-factor setup required.", requires_2fa_setup=True)

    if risk.decision == "challenge":
        challenge_token = create_pending_2fa_challenge(
            user_id=user.id,
            force_rotate_device_cookie=True,
            settings=settings,
            ip_prefix=risk.ip_prefix,
        )
        return LoginResponse(
            message="Two-factor verification required.",
            requires_2fa=True,
            challenge_token=challenge_token,
        )

    token, _session = create_session(db, request, settings, user=user)
    set_session_cookie(response, settings, token)
    learned_device_token = set_risk_engine_cookies(
        request,
        response,
        settings,
        user=user,
        force_rotate=risk.decision == "challenge",
    )
    learn_successful_login(
        username=user.email,
        device_token=learned_device_token,
        ip_prefix=risk.ip_prefix,
    )
    return LoginResponse(message="Logged in.")


@router.get("/auth/2fa/setup", response_model=TwoFactorSetupResponse)
def two_factor_setup(
    current_user: User = Depends(require_authenticated_user),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> TwoFactorSetupResponse:
    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is already enabled.",
        )
    if current_user.totp_secret_encrypted:
        secret = decrypt_totp_secret(settings, current_user.totp_secret_encrypted)
    else:
        secret = generate_totp_secret()
        current_user.totp_secret_encrypted = encrypt_totp_secret(settings, secret)
        db.commit()
    return TwoFactorSetupResponse(
        secret=secret,
        provisioning_uri=provisioning_uri(email=current_user.email, secret=secret),
    )


@router.post("/auth/2fa/confirm", response_model=MessageResponse)
def two_factor_confirm(
    payload: TwoFactorConfirmRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(require_authenticated_user),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> MessageResponse:
    rate_limit_auth(request, "2fa_confirm", limit=5, window_seconds=60)
    if current_user.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is already enabled.",
        )
    if not verify_totp_code(settings, current_user, payload.code):
        create_audit_log(
            db,
            event_type="auth.2fa_setup",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=current_user.id,
            target_type="user",
            target_id=current_user.id,
            details={"reason": "invalid_code"},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")

    current_user.totp_enabled = True
    current_user.totp_confirmed_at = utc_now()
    create_audit_log(
        db,
        event_type="auth.2fa_setup",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=current_user.id,
        target_type="user",
        target_id=current_user.id,
    )
    db.commit()
    try:
        learned_device_token = set_risk_engine_cookies(
            request,
            response,
            settings,
            user=current_user,
            force_rotate=True,
        )
        learn_successful_login(
            username=current_user.email,
            device_token=learned_device_token,
            ip_prefix=ip_prefix_for_risk(request),
        )
    except Exception:
        create_audit_log(
            db,
            event_type="auth.risk_engine_assessment",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=current_user.id,
            target_type="user",
            target_id=current_user.id,
            details={"reason": "post_2fa_setup_learning_failed"},
        )
        db.commit()
    return MessageResponse(message="Two-factor authentication enabled.")


@router.post("/auth/2fa/verify", response_model=LoginResponse)
def two_factor_verify(
    payload: TwoFactorVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    # Limit both the specific challenge token and the client IP. The challenge
    # remains retryable on wrong codes until these limits or its Redis TTL stop it.
    rate_limit_auth(request, f"2fa_verify:token:{payload.challenge_token}", limit=5, window_seconds=60)
    rate_limit_auth(request, "2fa_verify", limit=10, window_seconds=60)
    # Read without consuming first; consume only after TOTP verification succeeds.
    challenge = get_pending_2fa_challenge(payload.challenge_token, settings)
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Two-factor verification expired.")
    user = db.get(User, challenge.user_id)
    if user is None or not user.is_active or not user.totp_enabled:
        create_audit_log(
            db,
            event_type="auth.2fa_verify",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=user.id if user else None,
            target_type="user",
            target_id=user.id if user else None,
            details={"reason": "invalid_user"},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code.")
    if not verify_totp_code(settings, user, payload.code):
        create_audit_log(
            db,
            event_type="auth.2fa_verify",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=user.id,
            target_type="user",
            target_id=user.id,
            details={"reason": "invalid_code"},
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code.")

    # TOTP verified; consume the challenge before creating a session so a
    # replay racing with this request cannot also complete login.
    if not invalidate_pending_2fa_challenge(payload.challenge_token, settings):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Two-factor verification expired.")
    create_audit_log(
        db,
        event_type="auth.2fa_verify",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user.id,
        target_type="user",
        target_id=user.id,
    )
    db.commit()
    token, _session = create_session(db, request, settings, user=user)
    set_session_cookie(response, settings, token)
    learned_device_token = set_risk_engine_cookies(
        request,
        response,
        settings,
        user=user,
        force_rotate=challenge.force_rotate_device_cookie,
    )
    learn_successful_login(
        username=user.email,
        device_token=learned_device_token,
        ip_prefix=challenge.ip_prefix,
    )
    return LoginResponse(message="Logged in.")


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
