from collections.abc import Generator
from datetime import datetime, timedelta, timezone

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
from app.models.account import Session as UserSession, User
from app.models.audit import AuditLog
from app.services.two_factor import PendingTwoFactorChallenge, encrypt_totp_secret

STRONG_PASSWORD = "StrongPass123"


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


def register_and_login(client: TestClient) -> None:
    assert client.post("/auth/register", json={"email": "user@example.com", "password": STRONG_PASSWORD}).status_code == 201
    assert client.post("/auth/login", json={"email": "user@example.com", "password": STRONG_PASSWORD}).status_code == 200


def test_user_can_enable_totp(client: TestClient, db_session: Session) -> None:
    register_and_login(client)

    setup_response = client.get("/auth/2fa/setup")
    assert setup_response.status_code == 200
    secret = setup_response.json()["secret"]
    assert "otpauth://totp/" in setup_response.json()["provisioning_uri"]

    confirm_response = client.post("/auth/2fa/confirm", json={"code": pyotp.TOTP(secret).now()})

    assert confirm_response.status_code == 200
    user = db_session.scalar(select(User).where(User.email == "user@example.com"))
    assert user is not None
    assert user.totp_enabled is True
    assert user.totp_secret_encrypted != secret
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "auth.2fa_setup"))
    assert audit is not None
    assert audit.outcome == "SUCCESS"


def test_enabled_totp_requires_challenge_verification(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client.post("/auth/register", json={"email": "user@example.com", "password": STRONG_PASSWORD}).status_code == 201
    settings = get_settings()
    secret = pyotp.random_base32()
    user = db_session.scalar(select(User).where(User.email == "user@example.com"))
    assert user is not None
    user.totp_secret_encrypted = encrypt_totp_secret(settings, secret)
    user.totp_enabled = True
    user.totp_confirmed_at = datetime.now(timezone.utc)
    db_session.commit()

    challenge = PendingTwoFactorChallenge(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    consumed = [False]

    def fake_invalidate(token: str, settings) -> bool:
        if consumed[0]:
            return False
        consumed[0] = True
        return True

    monkeypatch.setattr("app.api.auth.create_pending_2fa_challenge", lambda *, user_id, settings: "challenge-token-value-at-least-32")
    monkeypatch.setattr("app.api.auth.get_pending_2fa_challenge", lambda token, settings: challenge)
    monkeypatch.setattr("app.api.auth.invalidate_pending_2fa_challenge", fake_invalidate)

    login_response = client.post("/auth/login", json={"email": "user@example.com", "password": STRONG_PASSWORD})
    assert login_response.status_code == 200
    assert login_response.json()["requires_2fa"] is True
    assert db_session.scalar(select(UserSession).where(UserSession.user_id == user.id)) is None

    verify_response = client.post(
        "/auth/2fa/verify",
        json={
            "challenge_token": login_response.json()["challenge_token"],
            "code": pyotp.TOTP(secret).now(),
        },
    )

    assert verify_response.status_code == 200
    assert db_session.scalar(select(UserSession).where(UserSession.user_id == user.id)) is not None


def test_2fa_challenge_replay_does_not_create_second_session(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client.post("/auth/register", json={"email": "user@example.com", "password": STRONG_PASSWORD}).status_code == 201
    settings = get_settings()
    secret = pyotp.random_base32()
    user = db_session.scalar(select(User).where(User.email == "user@example.com"))
    assert user is not None
    user.totp_secret_encrypted = encrypt_totp_secret(settings, secret)
    user.totp_enabled = True
    user.totp_confirmed_at = datetime.now(timezone.utc)
    db_session.commit()

    challenge = PendingTwoFactorChallenge(
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    consumed = [False]

    def fake_invalidate(token: str, settings) -> bool:
        if consumed[0]:
            return False
        consumed[0] = True
        return True

    monkeypatch.setattr("app.api.auth.get_pending_2fa_challenge", lambda token, settings: challenge)
    monkeypatch.setattr("app.api.auth.invalidate_pending_2fa_challenge", fake_invalidate)

    payload = {"challenge_token": "challenge-token-value-at-least-32", "code": pyotp.TOTP(secret).now()}
    first = client.post("/auth/2fa/verify", json=payload)
    second = client.post("/auth/2fa/verify", json=payload)

    assert first.status_code == 200
    assert second.status_code == 401
    assert len(db_session.scalars(select(UserSession).where(UserSession.user_id == user.id)).all()) == 1
