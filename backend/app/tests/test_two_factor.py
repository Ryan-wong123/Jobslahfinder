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
from app.services.two_factor import PendingTwoFactorChallenge, encrypt_totp_secret


STRONG_PASSWORD = "StrongPass123"  # gitleaks:allow


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


def register(client: TestClient, email: str = "user@example.com") -> None:
    response = client.post("/auth/register", json={"email": email, "password": STRONG_PASSWORD})
    assert response.status_code == 201


def test_risk_device_is_learned_only_after_2fa_setup_confirmation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    cookie_calls: list[str] = []
    learn_calls: list[tuple[str, str | None]] = []

    def fake_set_risk_engine_cookies(*args, **kwargs) -> str:
        cookie_calls.append(kwargs["user"].email)
        return "learned-device-token"

    def fake_learn_successful_login(*, username: str, device_token: str | None, ip_prefix: str | None) -> None:
        learn_calls.append((username, device_token))

    monkeypatch.setattr("app.api.auth.set_risk_engine_cookies", fake_set_risk_engine_cookies)
    monkeypatch.setattr("app.api.auth.learn_successful_login", fake_learn_successful_login)

    register(client)
    login_response = client.post("/auth/login", json={"email": "user@example.com", "password": STRONG_PASSWORD})

    assert login_response.status_code == 200
    assert login_response.json()["requires_2fa_setup"] is True
    assert cookie_calls == []
    assert learn_calls == []

    setup_response = client.get("/auth/2fa/setup")
    assert setup_response.status_code == 200
    code = pyotp.TOTP(setup_response.json()["secret"]).now()

    confirm_response = client.post("/auth/2fa/confirm", json={"code": code})

    assert confirm_response.status_code == 200
    assert cookie_calls == ["user@example.com"]
    assert learn_calls == [("user@example.com", "learned-device-token")]


def test_2fa_setup_does_not_disclose_secret_after_confirmation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.auth.set_risk_engine_cookies", lambda *args, **kwargs: "device-token")
    monkeypatch.setattr("app.api.auth.learn_successful_login", lambda **kwargs: None)

    register(client)
    assert client.post("/auth/login", json={"email": "user@example.com", "password": STRONG_PASSWORD}).status_code == 200
    setup_response = client.get("/auth/2fa/setup")
    assert setup_response.status_code == 200
    code = pyotp.TOTP(setup_response.json()["secret"]).now()
    assert client.post("/auth/2fa/confirm", json={"code": code}).status_code == 200

    second_setup = client.get("/auth/2fa/setup")

    assert second_setup.status_code == 400
    assert second_setup.json() == {"detail": "Two-factor authentication is already enabled."}


def test_2fa_challenge_replay_does_not_create_second_session(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register(client)
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
        force_rotate_device_cookie=True,
        ip_prefix="127.0.0",
    )
    consumed = [False]

    def fake_invalidate(token: str, settings) -> bool:
        if consumed[0]:
            return False
        consumed[0] = True
        return True

    monkeypatch.setattr("app.api.auth.get_pending_2fa_challenge", lambda token, settings: challenge)
    monkeypatch.setattr("app.api.auth.invalidate_pending_2fa_challenge", fake_invalidate)
    monkeypatch.setattr("app.api.auth.set_risk_engine_cookies", lambda *args, **kwargs: "device-token")
    monkeypatch.setattr("app.api.auth.learn_successful_login", lambda **kwargs: None)

    payload = {"challenge_token": "challenge-token-value-at-least-32", "code": pyotp.TOTP(secret).now()}
    first = client.post("/auth/2fa/verify", json=payload)
    second = client.post("/auth/2fa/verify", json=payload)

    assert first.status_code == 200
    assert second.status_code == 401
    assert db_session.scalars(select(UserSession).where(UserSession.user_id == user.id)).all()
    assert len(db_session.scalars(select(UserSession).where(UserSession.user_id == user.id)).all()) == 1
