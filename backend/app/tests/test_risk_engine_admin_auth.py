from collections.abc import Generator
from datetime import datetime
import json

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
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
from risk_engine.db.audit_model import AuditLog as RiskAuditLog
from risk_engine.db.db_setup import AuditBase
from risk_engine.dependancy import get_app_db, get_audit_db

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
def risk_audit_session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    AuditBase.metadata.create_all(bind=engine)
    TestingAuditSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr("risk_engine.component.audit_utils.AuditSessionLocal", TestingAuditSessionLocal)
    try:
        yield TestingAuditSessionLocal
    finally:
        AuditBase.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(
    db_session: Session,
    risk_audit_session_factory: sessionmaker[Session],
) -> Generator[TestClient, None, None]:
    AUTH_RATE_LIMITER.clear()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    def override_get_audit_db() -> Generator[Session, None, None]:
        audit_session = risk_audit_session_factory()
        try:
            yield audit_session
        finally:
            audit_session.close()

    app.dependency_overrides[get_db] = override_get_db
    risk_engine_app.dependency_overrides[get_app_db] = override_get_db
    risk_engine_app.dependency_overrides[get_audit_db] = override_get_audit_db
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
    risk_audit_session_factory: sessionmaker[Session],
) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.get("/risk-engine/admin/dashboard")

    assert response.status_code == 200
    assert "Risk Engine" in response.text
    with risk_audit_session_factory() as audit_db:
        audit = audit_db.scalar(
            select(RiskAuditLog).where(RiskAuditLog.action == "risk_engine.admin_access")
        )
    assert audit is not None
    assert audit.resource == "risk_dashboard"
    details = json.loads(audit.details or "{}")
    assert details["admin_user_id"] == admin.id
    assert details["admin_email"] == admin.email
    assert details["admin_role"] == UserRole.ADMIN.value
    assert details["auth_source"] == "main_app_admin_session"
    assert details["page"] == "dashboard"
    assert "ip_address" in details
    assert "user_agent" in details
    assert "admin_login" not in audit.action
    second_response = client.get("/risk-engine/admin/dashboard")
    assert second_response.status_code == 200
    with risk_audit_session_factory() as audit_db:
        access_count = audit_db.scalar(
            select(func.count(RiskAuditLog.id)).where(RiskAuditLog.action == "risk_engine.admin_access")
        )
    assert access_count == 1


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


def test_risk_admin_logout_endpoint_is_not_exposed(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = create_user(db_session, email="admin-no-risk-logout@example.com", role=UserRole.ADMIN)
    login(client, email=admin.email, password=ADMIN_PASSWORD)
    dashboard_response = client.get("/risk-engine/admin/dashboard")
    assert dashboard_response.status_code == 200
    assert client.cookies.get("risk_engine_admin_session") is not None

    response = client.post(
        "/risk-engine/admin/logout",
        follow_redirects=False,
    )

    assert response.status_code == 404
    assert client.get("/risk-engine/admin/dashboard").status_code == 200


def test_risk_admin_navigation_only_dashboard_links_to_main_admin(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = create_user(db_session, email="admin-nav@example.com", role=UserRole.ADMIN)
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    dashboard_response = client.get("/risk-engine/admin/dashboard")
    config_response = client.get("/risk-engine/admin/config-page")
    audit_response = client.get("/risk-engine/admin/audit-logs")

    assert dashboard_response.status_code == 200
    assert config_response.status_code == 200
    assert audit_response.status_code == 200
    assert 'href="/admin"' in dashboard_response.text
    assert 'href="/admin"' not in config_response.text
    assert 'href="/admin"' not in audit_response.text


def test_risk_audit_logs_render_friendly_details_and_support_filters(
    client: TestClient,
    db_session: Session,
    risk_audit_session_factory: sessionmaker[Session],
) -> None:
    admin = create_user(db_session, email="admin-audit@example.com", role=UserRole.ADMIN)
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    with risk_audit_session_factory() as audit_db:
        for index in range(6):
            audit_db.add(
                RiskAuditLog(
                    timestamp=datetime.utcnow(),
                    action="risk_engine.admin_access",
                    resource="risk_dashboard",
                    status="success",
                    details=json.dumps(
                        {
                            "admin_user_id": admin.id,
                            "admin_email": admin.email,
                            "admin_role": UserRole.ADMIN.value,
                            "page": "dashboard",
                        }
                    ),
                )
            )
        audit_db.add(
            RiskAuditLog(
                timestamp=datetime(2026, 1, 1, 0, 0, 0),
                action="risk_engine.config_update",
                resource="risk_config",
                status="success",
                details=json.dumps(
                    {
                        "admin_user_id": admin.id,
                        "admin_email": admin.email,
                        "admin_role": UserRole.ADMIN.value,
                        "change_count": 1,
                        "changes": [
                            {
                                "setting": "Block threshold",
                                "old_value": 60,
                                "new_value": 70,
                                "summary": "Block threshold changed from 60 to 70",
                            }
                        ],
                    }
                ),
            )
        )
        audit_db.commit()

    response = client.get(
        "/risk-engine/admin/audit-logs",
        params={"action": "risk_engine.config_update", "page_size": 5},
    )

    assert response.status_code == 200
    assert "Time (SGT)" in response.text
    assert "2026-01-01 08:00:00" in response.text
    assert "2026-01-01 08:00:00 SGT" not in response.text
    assert "Risk configuration changed" in response.text
    assert "Block threshold changed from 60 to 70" in response.text
    assert admin.email in response.text
    assert "<td>risk_dashboard</td>" not in response.text
    assert "<pre" not in response.text
    assert '"changes"' not in response.text
    assert "{&quot;" not in response.text

    page_one = client.get("/risk-engine/admin/audit-logs", params={"page_size": 5})
    assert page_one.status_code == 200
    assert "Showing page 1 of 2" in page_one.text
    assert "Next" in page_one.text
