from collections.abc import Generator
import re

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.rate_limit import AUTH_RATE_LIMITER
from app.main import app
from app.models.account import User, UserProfile
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.security.passwords import hash_password
from risk_engine import config as risk_config
from risk_engine.api import app as risk_engine_app
from risk_engine.dependancy import get_app_db

USER_PASSWORD = "StrongPass123"  # gitleaks:allow
ADMIN_PASSWORD = "AdminPass123"  # gitleaks:allow


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
    risk_engine_app.dependency_overrides[get_app_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    risk_engine_app.dependency_overrides.clear()
    AUTH_RATE_LIMITER.clear()


def create_user(db_session: Session, *, email: str, role: UserRole = UserRole.USER) -> User:
    user = User(
        email=email,
        password_hash=hash_password(ADMIN_PASSWORD if role == UserRole.ADMIN else USER_PASSWORD),
        role=role.value,
        is_active=True,
        failed_login_count=0,
    )
    user.profile = UserProfile()
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def login(client: TestClient, *, email: str, password: str) -> None:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    if response.json().get("requires_2fa_setup"):
        setup_response = client.get("/auth/2fa/setup")
        assert setup_response.status_code == 200
        code = pyotp.TOTP(setup_response.json()["secret"]).now()
        confirm_response = client.post("/auth/2fa/confirm", json={"code": code})
        assert confirm_response.status_code == 200


def test_risk_admin_dashboard_rejects_anonymous_users(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.get("/risk-engine/admin/dashboard")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("text/html")
    assert "Please sign in with an administrator account" in response.text
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "authorization.denied"))
    assert audit is not None
    assert audit.target_type == "risk_engine_admin"
    assert audit.details_json == {"reason": "authentication_required"}


def test_risk_admin_dashboard_rejects_normal_users_and_audits(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="user@example.com")
    login(client, email=user.email, password=USER_PASSWORD)

    response = client.get("/risk-engine/admin/dashboard")

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("text/html")
    assert "does not have permission" in response.text
    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.event_type == "authorization.denied").order_by(AuditLog.id.desc())
    )
    assert audit is not None
    assert audit.user_id == user.id
    assert audit.target_type == "risk_engine_admin"
    assert audit.details_json == {"reason": "admin_role_required"}


def test_risk_admin_dashboard_allows_main_app_admin_session(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.get("/risk-engine/admin/dashboard")

    assert response.status_code == 200
    assert "Risk Engine" in response.text


def test_risk_admin_config_rejects_api_key_without_admin_session(
    client: TestClient,
) -> None:
    response = client.get("/risk-engine/admin/config", headers={"x-api-key": "any-key"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


def test_risk_api_rejects_missing_api_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(risk_config, "ENGINE_STATE_PATH", tmp_path / "engine_state.json")
    risk_config.write_engine_state_atomically("test-engine-key")

    response = client.post(
        "/risk-engine/risk/evaluate",
        json={
            "username": "user@example.com",
            "ip": "203.0.113.10",
            "user_agent": "pytest",
            "device_token": "device-token",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized / Missing API Key"}


def test_risk_api_key_allows_machine_api_but_not_dashboard(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(risk_config, "ENGINE_STATE_PATH", tmp_path / "engine_state.json")
    risk_config.write_engine_state_atomically("test-engine-key")

    api_response = client.post(
        "/risk-engine/risk/evaluate",
        headers={"x-api-key": "test-engine-key"},
        json={
            "username": "user@example.com",
            "ip": "203.0.113.10",
            "user_agent": "pytest",
            "device_token": "device-token",
        },
    )
    dashboard_response = client.get(
        "/risk-engine/admin/dashboard",
        headers={"x-api-key": "test-engine-key"},
    )

    assert api_response.status_code == 200
    assert api_response.json()["decision"] in {"allow", "challenge", "block"}
    assert dashboard_response.status_code == 401
    assert "Please sign in with an administrator account" in dashboard_response.text


def csrf_token_from(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_risk_admin_logout_revokes_app_session_and_clears_cookies(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = create_user(db_session, email="admin-logout@example.com", role=UserRole.ADMIN)
    login(client, email=admin.email, password=ADMIN_PASSWORD)
    dashboard_response = client.get("/risk-engine/admin/dashboard")
    assert dashboard_response.status_code == 200
    assert client.cookies.get("risk_engine_admin_session") is not None

    response = client.post(
        "/risk-engine/admin/logout",
        data={"csrf_token": csrf_token_from(dashboard_response.text)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    set_cookie = response.headers.get("set-cookie", "")
    assert "job_platform_session=" in set_cookie
    assert "risk_engine_admin_session=" in set_cookie
    assert "Max-Age=0" in set_cookie
    assert client.get("/risk-engine/admin/dashboard").status_code == 401
