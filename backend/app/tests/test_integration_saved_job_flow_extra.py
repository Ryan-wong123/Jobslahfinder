from collections.abc import Generator

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.rate_limit import AUTH_RATE_LIMITER
from app.main import app
from app.models.activity import ApplicationHistory, SavedJob
from app.models.audit import AuditLog
from app.models.job import JobPosting, JobSource


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


def register_and_finish_login(client: TestClient) -> None:
    register_response = client.post(
        "/auth/register",
        json={"email": "flow-user@example.com", "password": USER_PASSWORD},
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/auth/login",
        json={"email": "flow-user@example.com", "password": USER_PASSWORD},
    )
    assert login_response.status_code == 200

    setup_response = client.get("/auth/2fa/setup")
    assert setup_response.status_code == 200
    code = pyotp.TOTP(setup_response.json()["secret"]).now()
    confirm_response = client.post("/auth/2fa/confirm", json={"code": code})
    assert confirm_response.status_code == 200


def seed_visible_job(db_session: Session) -> JobPosting:
    source = JobSource(
        source_name="JobStreet",
        base_url="https://sg.jobstreet.com",
        is_enabled=True,
    )
    db_session.add(source)
    db_session.flush()
    job = JobPosting(
        source_id=source.id,
        external_job_id="integration-001",
        title="Backend Security Engineer",
        company="Secure Apps Pte Ltd",
        location="Singapore",
        category="Security",
        description="Build secure backend APIs and review application controls.",
        job_url="https://sg.jobstreet.com/job/integration-001",
        salary_min=5000,
        salary_max=7000,
        salary_period="month",
        salary_currency="SGD",
        content_hash="integration-visible-job",
        is_active=True,
        is_suspicious=False,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_integration_user_can_save_list_and_unsave_visible_job(
    client: TestClient, db_session: Session
) -> None:
    job = seed_visible_job(db_session)
    register_and_finish_login(client)

    save_response = client.post(f"/jobs/{job.id}/save")
    assert save_response.status_code == 201
    assert save_response.json()["job"]["id"] == job.id

    saved_response = client.get("/saved-jobs")
    assert saved_response.status_code == 200
    assert saved_response.json()["total"] == 1
    assert saved_response.json()["items"][0]["job"]["title"] == "Backend Security Engineer"

    duplicate_save_response = client.post(f"/jobs/{job.id}/save")
    assert duplicate_save_response.status_code == 201
    assert len(db_session.scalars(select(SavedJob)).all()) == 1

    unsave_response = client.delete(f"/jobs/{job.id}/save")
    assert unsave_response.status_code == 200
    assert db_session.scalars(select(SavedJob)).all() == []

    history_actions = [
        row.action_type
        for row in db_session.scalars(
            select(ApplicationHistory).order_by(ApplicationHistory.id)
        ).all()
    ]
    assert history_actions == ["job_saved", "job_unsaved"]

    audit_events = [
        row.event_type
        for row in db_session.scalars(select(AuditLog).order_by(AuditLog.id)).all()
    ]
    assert "auth.registration" in audit_events
    assert "saved_job.save" in audit_events
    assert "saved_job.unsave" in audit_events
