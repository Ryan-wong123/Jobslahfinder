from collections.abc import Generator

import pyotp
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.rate_limit import AUTH_RATE_LIMITER
from app.main import app
from app.models.account import PasswordResetToken, Session as UserSession, User, UserProfile
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.models.job import JobPosting, JobSource, ScrapingRun
from app.security.auth import assert_owner_or_admin
from app.security.passwords import hash_password


USER_PASSWORD = "StrongPass123"
ADMIN_PASSWORD = "AdminPass123"


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        User.__table__,
        UserProfile.__table__,
        UserSession.__table__,
        PasswordResetToken.__table__,
        AuditLog.__table__,
        JobSource.__table__,
        ScrapingRun.__table__,
        JobPosting.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine, tables=tables)
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


def create_user(db_session: Session, *, email: str, role: UserRole) -> User:
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


def test_admin_route_requires_authentication(client: TestClient) -> None:
    response = client.get("/admin/health")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


def test_normal_user_cannot_access_admin_route_and_denial_is_audited(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="user@example.com", role=UserRole.USER)
    login(client, email="user@example.com", password=USER_PASSWORD)

    response = client.get("/admin/health")

    assert response.status_code == 403
    assert response.json() == {"detail": "Access denied."}
    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.event_type == "authorization.denied")
    )
    assert audit is not None
    assert audit.outcome == "DENIED"
    assert audit.target_type == "admin"
    assert audit.details_json == {"reason": "admin_role_required"}


def test_admin_can_access_admin_route(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    login(client, email="admin@example.com", password=ADMIN_PASSWORD)

    response = client.get("/admin/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "backend"
    assert body["access"] == "admin"
    assert "timestamp" in body


def test_profile_routes_are_scoped_to_current_user(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, email="owner@example.com", role=UserRole.USER)
    other_user = create_user(db_session, email="other@example.com", role=UserRole.USER)
    assert owner.profile is not None
    assert other_user.profile is not None
    owner.profile.full_name = "Owner Name"
    other_user.profile.full_name = "Other Name"
    db_session.commit()

    login(client, email=owner.email, password=USER_PASSWORD)

    response = client.get("/me/profile")

    assert response.status_code == 200
    assert response.json()["user_id"] == owner.id
    assert response.json()["full_name"] == "Owner Name"

    update_response = client.patch("/me/profile", json={"full_name": "Owner Updated"})
    assert update_response.status_code == 200
    db_session.refresh(other_user.profile)
    assert other_user.profile.full_name == "Other Name"


def test_assert_owner_or_admin_allows_owner_and_admin(db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", role=UserRole.USER)
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)

    assert_owner_or_admin(
        db_session,
        None,
        current_user=owner,
        owner_user_id=owner.id,
        target_type="user_profile",
        target_id=owner.id,
    )
    assert_owner_or_admin(
        db_session,
        None,
        current_user=admin,
        owner_user_id=owner.id,
        target_type="user_profile",
        target_id=owner.id,
    )


def test_assert_owner_or_admin_denies_other_user_and_audits(db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", role=UserRole.USER)
    other_user = create_user(db_session, email="other@example.com", role=UserRole.USER)

    with pytest.raises(HTTPException) as exc_info:
        assert_owner_or_admin(
            db_session,
            None,
            current_user=other_user,
            owner_user_id=owner.id,
            target_type="user_profile",
            target_id=owner.id,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Resource not found."
    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.event_type == "authorization.denied")
    )
    assert audit is not None
    assert audit.user_id == other_user.id
    assert audit.target_type == "user_profile"
    assert audit.target_id == owner.id
    assert audit.outcome == "DENIED"
