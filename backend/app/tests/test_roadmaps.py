from collections.abc import Generator

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
from app.models.roadmap import JobRoleRoadmap
from app.security.passwords import hash_password

USER_PASSWORD = "StrongPass123"


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


def create_user(db_session: Session, *, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password(USER_PASSWORD),
        role=UserRole.USER.value,
        is_active=True,
        failed_login_count=0,
    )
    user.profile = UserProfile()
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def login(client: TestClient, *, email: str) -> None:
    response = client.post("/auth/login", json={"email": email, "password": USER_PASSWORD})
    assert response.status_code == 200


def test_user_can_create_and_list_own_roadmap(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session, email="user@example.com")
    login(client, email=user.email)

    response = client.post(
        "/roadmaps",
        json={
            "target_role": "Security Analyst",
            "target_level": "JUNIOR",
            "timeline_months": 6,
            "current_skills": ["Python", "Linux", "Python"],
            "notes": "Focus on Singapore SOC roles.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["target_role"] == "Security Analyst"
    assert body["current_skills"] == ["Python", "Linux"]
    assert len(body["milestones"]) >= 3
    assert body["status"] == "ACTIVE"

    roadmap = db_session.scalar(select(JobRoleRoadmap))
    assert roadmap is not None
    assert roadmap.user_id == user.id

    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "job_role_roadmap.create"))
    assert audit is not None
    assert audit.details_json["skill_count"] == 2

    list_response = client.get("/roadmaps")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1


def test_roadmap_create_rejects_overlong_skill(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session, email="overlong-skill@example.com")
    login(client, email=user.email)

    response = client.post(
        "/roadmaps",
        json={
            "target_role": "Security Analyst",
            "target_level": "JUNIOR",
            "timeline_months": 6,
            "current_skills": ["A" * 81],
        },
    )

    assert response.status_code == 422


def test_roadmap_response_sanitizes_stored_json(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session, email="stored-roadmap@example.com")
    roadmap = JobRoleRoadmap(
        user_id=user.id,
        target_role="<b>Security Analyst</b>",
        target_level="JUNIOR",
        timeline_months=6,
        current_skills_json={"items": ["<script>alert(1)</script>Python", "Linux\u0000"]},
        roadmap_json={
            "milestones": [
                {
                    "month": 999,
                    "title": "<b>Foundation</b>",
                    "focus": "Threat modeling\u0000",
                    "actions": ["<script>alert(1)</script>Build lab"],
                    "evidence": ["Notes\u0000"],
                }
            ]
        },
        notes="<p>Review safely</p>",
        status="ACTIVE",
    )
    db_session.add(roadmap)
    db_session.commit()
    db_session.refresh(roadmap)
    login(client, email=user.email)

    response = client.get(f"/roadmaps/{roadmap.id}")

    assert response.status_code == 200
    body = response.json()
    assert "<" not in str(body)
    assert "\u0000" not in str(body)
    assert body["milestones"][0]["month"] == 6


def test_user_cannot_access_another_users_roadmap(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com")
    other = create_user(db_session, email="other@example.com")
    roadmap = JobRoleRoadmap(
        user_id=owner.id,
        target_role="Software Engineer",
        target_level="JUNIOR",
        timeline_months=6,
        current_skills_json={"items": []},
        roadmap_json={"milestones": []},
        status="ACTIVE",
    )
    db_session.add(roadmap)
    db_session.commit()
    db_session.refresh(roadmap)

    login(client, email=other.email)
    response = client.get(f"/roadmaps/{roadmap.id}")

    assert response.status_code == 404
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "authorization.denied"))
    assert audit is not None
    assert audit.target_type == "job_role_roadmap"


def test_user_can_archive_own_roadmap(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session, email="archive@example.com")
    roadmap = JobRoleRoadmap(
        user_id=user.id,
        target_role="Software Engineer",
        target_level="JUNIOR",
        timeline_months=6,
        current_skills_json={"items": ["Python"]},
        roadmap_json={"milestones": []},
        status="ACTIVE",
    )
    db_session.add(roadmap)
    db_session.commit()
    db_session.refresh(roadmap)

    login(client, email=user.email)

    response = client.patch(f"/roadmaps/{roadmap.id}", json={"status": "ARCHIVED"})

    assert response.status_code == 200
    assert response.json()["status"] == "ARCHIVED"
