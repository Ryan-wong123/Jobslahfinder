from collections.abc import Generator
from datetime import datetime, timezone

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
from app.models.account import User, UserProfile
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.security.passwords import hash_password
from app.services.two_factor import encrypt_totp_secret
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


def enable_totp(db_session: Session, user: User) -> None:
    secret = pyotp.random_base32()
    settings = get_settings()
    user.totp_secret_encrypted = encrypt_totp_secret(settings, secret)
    user.totp_enabled = True
    user.totp_confirmed_at = datetime.now(timezone.utc)
    db_session.commit()


def login(client: TestClient, *, email: str, password: str) -> None:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


def test_risk_admin_dashboard_rejects_anonymous_users(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.get("/risk-engine/admin/dashboard")

    assert response.status_code == 401
    assert "Please sign in with an administrator account" in response.text
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "authorization.denied"))
    assert audit is not None
    assert audit.target_type == "risk_engine_admin"


def test_risk_admin_dashboard_rejects_normal_users(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="user@example.com")
    login(client, email=user.email, password=USER_PASSWORD)
    enable_totp(db_session, user)

    response = client.get("/risk-engine/admin/dashboard")

    assert response.status_code == 403
    assert "permission" in response.text


def test_risk_admin_dashboard_allows_admin_with_two_factor(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    login(client, email=admin.email, password=ADMIN_PASSWORD)
    enable_totp(db_session, admin)

    response = client.get("/risk-engine/admin/dashboard")

    assert response.status_code == 200
    assert "Risk Engine" in response.text
