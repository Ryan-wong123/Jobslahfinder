from collections.abc import Generator
from datetime import timedelta

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.rate_limit import AUTH_RATE_LIMITER
from app.main import app
from app.models.account import PasswordResetToken, Session as UserSession, User
from app.models.audit import AuditLog
from app.security.passwords import verify_password
from app.security.tokens import DEFAULT_TOKEN_URLSAFE_LENGTH, hash_token
from app.services.auth import utc_now


STRONG_PASSWORD = "StrongPass123"
NEW_PASSWORD = "BetterPass456"
VALID_RESET_TOKEN = "A" * DEFAULT_TOKEN_URLSAFE_LENGTH
WRONG_VALID_FORMAT_RESET_TOKEN = "B" * DEFAULT_TOKEN_URLSAFE_LENGTH


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    AUTH_RATE_LIMITER.clear()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    AUTH_RATE_LIMITER.clear()


def register(client: TestClient, email: str = "user@example.com", password: str = STRONG_PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def login(client: TestClient, email: str = "user@example.com", password: str = STRONG_PASSWORD):
    response = client.post("/auth/login", json={"email": email, "password": password})
    if response.status_code == 200 and response.json().get("requires_2fa_setup"):
        setup = client.get("/auth/2fa/setup")
        assert setup.status_code == 200
        code = pyotp.TOTP(setup.json()["secret"]).now()
        confirm = client.post("/auth/2fa/confirm", json={"code": code})
        assert confirm.status_code == 200
    return response


def test_successful_registration_hashes_password_and_creates_profile(
    client: TestClient, db_session: Session
) -> None:
    response = register(client, email="User@Example.com")

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "user@example.com"
    assert "password_hash" not in body

    user = db_session.scalar(select(User).where(User.email == "user@example.com"))
    assert user is not None
    assert user.profile is not None
    assert user.password_hash != STRONG_PASSWORD
    assert verify_password(STRONG_PASSWORD, user.password_hash)

    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "auth.registration"))
    assert audit is not None
    assert audit.outcome == "SUCCESS"


def test_duplicate_registration_returns_safe_error(client: TestClient) -> None:
    assert register(client).status_code == 201

    response = register(client)

    assert response.status_code == 400
    assert response.json() == {"detail": "Unable to register account."}


def test_successful_login_sets_httponly_cookie_and_stores_hashed_session(
    client: TestClient, db_session: Session
) -> None:
    assert register(client).status_code == 201

    response = login(client)

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie

    session = db_session.scalar(select(UserSession))
    assert session is not None
    raw_cookie = client.cookies.get(get_settings().session_cookie_name)
    assert raw_cookie is not None
    assert session.session_token_hash != raw_cookie
    assert session.session_token_hash == hash_token(raw_cookie, get_settings().session_secret)
    assert response.json()["requires_2fa_setup"] is True


def test_failed_login_uses_generic_error_and_logs_failure(
    client: TestClient, db_session: Session
) -> None:
    assert register(client).status_code == 201

    response = login(client, password="wrong-password")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password."}
    audit = db_session.scalars(select(AuditLog).where(AuditLog.event_type == "auth.login")).all()
    assert audit[-1].outcome == "FAILURE"
    assert "password" not in str(audit[-1].details_json).lower()


def test_login_unknown_email_uses_same_generic_error(client: TestClient) -> None:
    response = login(client, email="missing@example.com", password="anything")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password."}


def test_get_me_requires_valid_session(client: TestClient) -> None:
    assert register(client).status_code == 201
    assert login(client).status_code == 200

    response = client.get("/me")

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


def test_profile_update_validates_fields_and_audits_change(
    client: TestClient, db_session: Session
) -> None:
    assert register(client).status_code == 201
    assert login(client).status_code == 200

    response = client.patch(
        "/me/profile",
        json={
            "full_name": "  Alice Tan  ",
            "phone": "+65 9123 4567",
            "location": "Singapore",
            "summary": "Security analyst",
            "skills": ["Python", "python", " FastAPI "],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Alice Tan"
    assert body["skills"] == ["Python", "FastAPI"]

    user = db_session.scalar(select(User).where(User.email == "user@example.com"))
    assert user is not None
    assert user.profile is not None
    assert user.profile.full_name == "Alice Tan"
    assert user.profile.skills_json == {"items": ["Python", "FastAPI"]}

    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.event_type == "account.profile_update")
    )
    assert audit is not None
    assert audit.outcome == "SUCCESS"
    assert audit.details_json == {
        "changed_fields": ["full_name", "phone", "location", "summary", "skills"]
    }


def test_profile_update_rejects_invalid_fields(client: TestClient) -> None:
    assert register(client).status_code == 201
    assert login(client).status_code == 200

    response = client.patch("/me/profile", json={"phone": "<script>alert(1)</script>"})

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request."}


def test_profile_update_rejects_html_payloads_before_storage(
    client: TestClient, db_session: Session
) -> None:
    assert register(client).status_code == 201
    assert login(client).status_code == 200

    response = client.patch(
        "/me/profile",
        json={
            "full_name": "<img src=x onerror=alert(1)>Alice",
            "summary": "<script>alert(1)</script>",
            "skills": ["Python", "<b>FastAPI</b>"],
        },
    )

    assert response.status_code == 422
    user = db_session.scalar(select(User).where(User.email == "user@example.com"))
    assert user is not None
    assert user.profile is not None
    assert user.profile.full_name is None
    assert user.profile.summary is None
    assert user.profile.skills_json is None


def test_account_update_rejects_protected_role_field(
    client: TestClient, db_session: Session
) -> None:
    assert register(client).status_code == 201
    assert login(client).status_code == 200

    response = client.patch("/me", json={"role": "ADMIN"})

    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request."}
    user = db_session.scalar(select(User).where(User.email == "user@example.com"))
    assert user is not None
    assert user.role == "USER"


def test_account_update_changes_allowed_fields_and_audits(
    client: TestClient, db_session: Session
) -> None:
    assert register(client).status_code == 201
    assert login(client).status_code == 200

    response = client.patch(
        "/me",
        json={
            "full_name": "New Name",
        },
    )

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"
    user = db_session.scalar(select(User).where(User.email == "user@example.com"))
    assert user is not None
    assert user.profile is not None
    assert user.profile.full_name == "New Name"
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "account.update"))
    assert audit is not None
    assert audit.details_json == {"changed_fields": ["full_name"]}


def test_account_deletion_requires_password(client: TestClient, db_session: Session) -> None:
    assert register(client).status_code == 201
    assert login(client).status_code == 200

    response = client.request("DELETE", "/me", json={"password": "wrong-password"})

    assert response.status_code == 400
    assert response.json() == {"detail": "Unable to delete account."}
    assert client.get("/me").status_code == 200
    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.event_type == "account.deletion_request")
    )
    assert audit is not None
    assert audit.outcome == "FAILURE"
    assert audit.details_json == {"reason": "invalid_password"}


def test_account_deletion_soft_deletes_user_and_invalidates_sessions(
    client: TestClient, db_session: Session
) -> None:
    assert register(client).status_code == 201
    assert login(client).status_code == 200
    assert client.patch("/me/profile", json={"full_name": "Delete Me"}).status_code == 200
    user = db_session.scalar(select(User).where(User.email == "user@example.com"))
    assert user is not None
    user_id = user.id

    response = client.request("DELETE", "/me", json={"password": STRONG_PASSWORD})

    assert response.status_code == 200
    assert response.json() == {"message": "Account deleted."}
    assert client.get("/me").status_code == 401

    deleted_user = db_session.get(User, user_id)
    assert deleted_user is not None
    assert deleted_user.is_active is False
    assert deleted_user.email == f"deleted-user-{user_id}@deleted.invalid"
    assert deleted_user.profile is not None
    assert deleted_user.profile.full_name is None

    session = db_session.scalar(select(UserSession).where(UserSession.user_id == user_id))
    assert session is not None
    assert session.revoked_at is not None

    audit_events = db_session.scalars(
        select(AuditLog)
        .where(AuditLog.event_type.in_(["account.deletion_request", "account.deletion"]))
        .order_by(AuditLog.id)
    ).all()
    assert [event.outcome for event in audit_events[-2:]] == ["SUCCESS", "SUCCESS"]
    assert audit_events[-1].details_json["strategy"] == "soft_delete"

    assert register(client, email="user@example.com").status_code == 201


def test_logout_revokes_session(client: TestClient, db_session: Session) -> None:
    assert register(client).status_code == 201
    assert login(client).status_code == 200

    response = client.post("/auth/logout")

    assert response.status_code == 200
    assert client.get("/me").status_code == 401
    session = db_session.scalar(select(UserSession))
    assert session is not None
    assert session.revoked_at is not None


def test_password_change_requires_current_password_and_allows_new_login(
    client: TestClient, db_session: Session
) -> None:
    assert register(client).status_code == 201
    assert login(client).status_code == 200

    bad_response = client.post(
        "/auth/password-change",
        json={"current_password": "wrong-password", "new_password": NEW_PASSWORD},
    )
    assert bad_response.status_code == 400
    assert bad_response.json() == {"detail": "Unable to change password."}

    response = client.post(
        "/auth/password-change",
        json={"current_password": STRONG_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 200
    client.post("/auth/logout")
    assert login(client, password=STRONG_PASSWORD).status_code == 401
    assert login(client, password=NEW_PASSWORD).status_code == 200

    audit_events = db_session.scalars(
        select(AuditLog).where(AuditLog.event_type == "auth.password_change")
    ).all()
    assert [event.outcome for event in audit_events] == ["FAILURE", "SUCCESS"]


def test_password_reset_request_is_generic_for_existing_and_missing_accounts(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent_emails: list[str] = []

    def fake_send_password_reset_email(settings, *, to_email: str, token: str) -> None:
        sent_emails.append(to_email)

    monkeypatch.setattr("app.services.auth.send_password_reset_email", fake_send_password_reset_email)

    assert register(client).status_code == 201

    existing = client.post("/auth/password-reset/request", json={"email": "user@example.com"})
    missing = client.post("/auth/password-reset/request", json={"email": "missing@example.com"})

    assert existing.status_code == 200
    assert missing.status_code == 200
    assert existing.json() == missing.json()
    assert sent_emails == []  # SMTP is never called on the request thread.
    from app.services.mail_outbox import deliver_pending_mail
    monkeypatch.setattr("app.services.mail_outbox.send_password_reset_email", fake_send_password_reset_email)
    assert deliver_pending_mail(db_session, get_settings()) == 1
    assert sent_emails == ["user@example.com"]

    reset_tokens = db_session.scalars(select(PasswordResetToken)).all()
    assert len(reset_tokens) == 1
    assert len(reset_tokens[0].token_hash) == 64


def test_password_reset_request_does_not_print_raw_token_when_email_unconfigured(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    known_token = VALID_RESET_TOKEN
    monkeypatch.setattr("app.services.auth.generate_token", lambda: known_token)
    assert register(client).status_code == 201

    response = client.post("/auth/password-reset/request", json={"email": "user@example.com"})

    assert response.status_code == 200
    stdio = capsys.readouterr()
    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.event_type == "auth.password_reset_request")
    )
    assert audit is not None
    combined = f"{stdio.out}\n{stdio.err}\n{audit.details_json}"
    assert known_token not in combined
    assert "/reset-password?token=" not in combined
    assert audit.details_json == {"account_matched": True, "delivery": "queued"}


@pytest.mark.parametrize(
    "token",
    [
        "A" * (DEFAULT_TOKEN_URLSAFE_LENGTH - 1),
        "A" * (DEFAULT_TOKEN_URLSAFE_LENGTH + 1),
        ("A" * (DEFAULT_TOKEN_URLSAFE_LENGTH - 1)) + "!",
        ("A" * (DEFAULT_TOKEN_URLSAFE_LENGTH - 1)) + " ",
    ],
)
def test_password_reset_confirm_rejects_malformed_tokens_before_service_logic(
    client: TestClient, db_session: Session, token: str
) -> None:
    assert register(client).status_code == 201

    response = client.post(
        "/auth/password-reset/confirm",
        json={"token": token, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 422
    audit_events = db_session.scalars(
        select(AuditLog).where(AuditLog.event_type == "auth.password_reset_confirm")
    ).all()
    assert audit_events == []


def test_password_reset_confirm_rejects_invalid_expired_and_reused_tokens(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    known_token = VALID_RESET_TOKEN
    wrong_token = WRONG_VALID_FORMAT_RESET_TOKEN
    monkeypatch.setattr("app.services.auth.generate_token", lambda: known_token)
    assert register(client).status_code == 201
    assert client.post("/auth/password-reset/request", json={"email": "user@example.com"}).status_code == 200

    invalid = client.post(
        "/auth/password-reset/confirm",
        json={"token": wrong_token, "new_password": NEW_PASSWORD},
    )
    assert invalid.status_code == 400
    assert invalid.json() == {"detail": "Unable to reset password."}

    reset_token = db_session.scalar(select(PasswordResetToken))
    assert reset_token is not None
    reset_token.expires_at = utc_now() - timedelta(minutes=1)
    db_session.commit()

    expired = client.post(
        "/auth/password-reset/confirm",
        json={"token": known_token, "new_password": NEW_PASSWORD},
    )
    assert expired.status_code == 400

    reset_token.expires_at = utc_now() + timedelta(minutes=30)
    db_session.commit()
    success = client.post(
        "/auth/password-reset/confirm",
        json={"token": known_token, "new_password": NEW_PASSWORD},
    )
    assert success.status_code == 200

    reused = client.post(
        "/auth/password-reset/confirm",
        json={"token": known_token, "new_password": STRONG_PASSWORD},
    )
    assert reused.status_code == 400
    assert login(client, password=NEW_PASSWORD).status_code == 200

    audit_events = db_session.scalars(
        select(AuditLog).where(AuditLog.event_type == "auth.password_reset_confirm")
    ).all()
    serialized_details = repr([event.details_json for event in audit_events])
    assert known_token not in serialized_details
    assert wrong_token not in serialized_details


def test_expired_session_is_rejected(client: TestClient, db_session: Session) -> None:
    assert register(client).status_code == 201
    assert login(client).status_code == 200
    session = db_session.scalar(select(UserSession))
    assert session is not None
    session.expires_at = utc_now() - timedelta(minutes=1)
    db_session.commit()

    response = client.get("/me")

    assert response.status_code == 401


def test_auth_rate_limit_blocks_repeated_login_abuse(client: TestClient) -> None:
    blocked = None
    for _ in range(20):
        response = login(client, email="missing@example.com", password="anything")
        if response.status_code == 429:
            blocked = response
            break
        assert response.status_code == 401

    assert blocked is not None
    assert blocked.status_code == 429
    assert blocked.json()["detail"] in {
        "Too many requests. Please try again later.",
        "Too many login attempts. Please try again later.",
    }
