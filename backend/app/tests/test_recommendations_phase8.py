from datetime import date
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.rate_limit import AUTH_RATE_LIMITER
from app.main import app
from app.models.account import User, UserProfile
from app.models.activity import Recommendation
from app.models.audit import AuditLog
from app.models.enums import ProcessingStatus, UploadStatus, UserRole
from app.models.job import JobPosting, JobSource
from app.models.resume import Resume, ResumeExtraction
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


def create_source(db_session: Session) -> JobSource:
    source = JobSource(
        source_name="JobStreet",
        base_url="https://sg.jobstreet.com",
        is_enabled=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def create_job(
    db_session: Session,
    source: JobSource,
    *,
    title: str,
    description: str,
    category: str = "Engineering",
) -> JobPosting:
    job = JobPosting(
        source_id=source.id,
        external_job_id=title,
        title=title,
        company="Secure Co",
        location="Singapore",
        category=category,
        description=description,
        job_url=f"https://sg.jobstreet.com/job/{title.lower().replace(' ', '-')}",
        posting_date=date(2026, 4, 30),
        is_active=True,
        is_suspicious=False,
        content_hash=f"hash-{title}",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def create_completed_extraction(
    db_session: Session,
    user: User,
    *,
    skills: list[str],
    experience_title: str = "Security Developer",
    education_field: str = "Computer Science",
    years_experience: float = 5.0,
    extracted_text: str = "secret-resume-content",
) -> ResumeExtraction:
    resume = Resume(
        user_id=user.id,
        original_filename="resume.pdf",
        stored_filename=f"{user.id}-resume.pdf",
        file_path=f"/tmp/{user.id}-resume.pdf",
        file_hash=f"hash-{user.id}",
        mime_type="application/pdf",
        file_size_bytes=128,
        upload_status=UploadStatus.STORED.value,
    )
    extraction = ResumeExtraction(
        resume=resume,
        extracted_text=extracted_text,
        skills_json={"items": skills},
        experience_json={"items": [{"title": experience_title, "description": "Built secure APIs."}]},
        education_json={"items": [{"credential": "Degree", "field": education_field}]},
        years_experience=years_experience,
        processing_status=ProcessingStatus.COMPLETED.value,
    )
    db_session.add(resume)
    db_session.add(extraction)
    db_session.commit()
    db_session.refresh(extraction)
    return extraction


def test_authenticated_recommendation_refresh_scores_and_stores_ranked_results(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    user = create_user(db_session, email="user@example.com")
    extraction = create_completed_extraction(db_session, user, skills=["Python", "FastAPI", "Docker"])
    best_job = create_job(
        db_session,
        source,
        title="Senior Python FastAPI Developer",
        description="Build secure APIs with Python, FastAPI, Docker, and PostgreSQL.",
    )
    weak_job = create_job(
        db_session,
        source,
        title="Security Analyst",
        description="Review secure systems and write risk reports.",
        category="Cybersecurity",
    )
    create_job(
        db_session,
        source,
        title="Cafe Supervisor",
        description="Prepare drinks and manage shifts.",
        category="Hospitality",
    )
    login(client, email=user.email)

    response = client.post("/recommendations/refresh")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["rank"] for item in body["items"]] == [1, 2]
    assert body["items"][0]["job"]["id"] == best_job.id
    assert body["items"][0]["match_score"] > body["items"][1]["match_score"]
    assert body["items"][0]["resume_id"] == extraction.resume_id
    assert body["items"][0]["metadata"]["scoring_version"] == "deterministic-v1"
    assert "Python" in body["items"][0]["rationale"] or "python" in body["items"][0]["rationale"]
    assert body["items"][1]["job"]["id"] == weak_job.id

    stored = db_session.scalars(
        select(Recommendation).where(Recommendation.user_id == user.id).order_by(Recommendation.rank)
    ).all()
    assert [item.rank for item in stored] == [1, 2]


def test_recommendation_refresh_after_extraction_update_replaces_results(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    user = create_user(db_session, email="profile-refresh@example.com")
    extraction = create_completed_extraction(
        db_session,
        user,
        skills=["Python", "FastAPI"],
        experience_title="Backend Developer",
        years_experience=5.0,
    )
    python_job = create_job(
        db_session,
        source,
        title="Senior Python FastAPI Developer",
        description="Build secure APIs with Python, FastAPI, PostgreSQL, and Docker.",
    )
    react_job = create_job(
        db_session,
        source,
        title="Junior React TypeScript Engineer",
        description="Build user interfaces with React, TypeScript, accessibility, and frontend testing.",
        category="Frontend Engineering",
    )
    login(client, email=user.email)

    first_refresh = client.post("/recommendations/refresh")

    assert first_refresh.status_code == 200
    first_body = first_refresh.json()
    assert first_body["total"] == 1
    assert first_body["items"][0]["job"]["id"] == python_job.id
    assert first_body["items"][0]["rank"] == 1
    assert first_body["items"][0]["match_score"] > 0
    assert "python" in first_body["items"][0]["rationale"].casefold()
    first_stored_count = db_session.scalar(
        select(func.count()).select_from(Recommendation).where(Recommendation.user_id == user.id)
    )
    assert first_stored_count == first_body["total"]

    update_response = client.patch(
        f"/resumes/{extraction.resume_id}/extraction",
        json={
            "skills": ["React", "TypeScript", "Accessibility"],
            "experience": [
                {
                    "title": "Frontend Engineer",
                    "company": "Interface Studio",
                    "description": "Built accessible React and TypeScript interfaces.",
                    "years": 1.5,
                }
            ],
            "education": [{"credential": "Diploma", "field": "Interaction Design"}],
            "years_experience": 1.5,
        },
    )
    assert update_response.status_code == 200

    second_refresh = client.post("/recommendations/refresh")

    assert second_refresh.status_code == 200
    second_body = second_refresh.json()
    assert second_body["total"] == 2
    assert second_body["items"][0]["job"]["id"] == react_job.id
    assert [item["rank"] for item in second_body["items"]] == [1, 2]
    assert second_body["items"][0]["match_score"] > second_body["items"][1]["match_score"]
    assert second_body["items"][0]["match_score"] > first_body["items"][0]["match_score"] / 2
    assert "react" in second_body["items"][0]["rationale"].casefold()

    stored = db_session.scalars(
        select(Recommendation).where(Recommendation.user_id == user.id).order_by(Recommendation.rank)
    ).all()
    assert len(stored) == second_body["total"]
    assert [item.rank for item in stored] == [1, 2]
    assert stored[0].job_id == react_job.id
    assert len({item.job_id for item in stored}) == second_body["total"]


def test_recommendation_endpoints_require_authentication(client: TestClient) -> None:
    assert client.get("/recommendations").status_code == 401
    assert client.post("/recommendations/refresh").status_code == 401


def test_recommendations_are_user_owned_and_do_not_leak_between_users(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    owner = create_user(db_session, email="owner@example.com")
    other = create_user(db_session, email="other@example.com")
    create_completed_extraction(db_session, owner, skills=["Python"])
    create_completed_extraction(db_session, other, skills=["React"])
    python_job = create_job(
        db_session,
        source,
        title="Python Developer",
        description="Build services with Python.",
    )
    react_job = create_job(
        db_session,
        source,
        title="React Developer",
        description="Build interfaces with React.",
    )

    login(client, email=owner.email)
    assert client.post("/recommendations/refresh").status_code == 200
    login(client, email=other.email)
    assert client.post("/recommendations/refresh").status_code == 200

    other_body = client.get("/recommendations").json()
    assert [item["job"]["id"] for item in other_body["items"]] == [react_job.id]

    login(client, email=owner.email)
    owner_body = client.get("/recommendations").json()
    assert [item["job"]["id"] for item in owner_body["items"]] == [python_job.id]


def test_refresh_audit_log_is_created_without_sensitive_resume_or_job_text(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    user = create_user(db_session, email="audit@example.com")
    create_completed_extraction(
        db_session,
        user,
        skills=["Python"],
        extracted_text="secret-resume-content unique-private-history",
    )
    create_job(
        db_session,
        source,
        title="Python Developer",
        description="confidential job description payload",
    )
    login(client, email=user.email)

    response = client.post("/recommendations/refresh")

    assert response.status_code == 200
    audit = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.event_type == "recommendation.refresh", AuditLog.user_id == user.id)
        .order_by(AuditLog.id.desc())
    )
    assert audit is not None
    assert audit.outcome == "SUCCESS"
    details = str(audit.details_json)
    assert "secret-resume-content" not in details
    assert "unique-private-history" not in details
    assert "confidential job description payload" not in details
    assert audit.details_json["recommendation_count"] == 1


def test_refresh_rate_limiting_applies(client: TestClient, db_session: Session) -> None:
    AUTH_RATE_LIMITER.clear()
    source = create_source(db_session)
    user = create_user(db_session, email="limited@example.com")
    create_completed_extraction(db_session, user, skills=["Python"])
    create_job(db_session, source, title="Python Developer", description="Build Python systems.")
    login(client, email=user.email)

    statuses = [client.post("/recommendations/refresh").status_code for _ in range(6)]

    assert statuses[:5] == [200, 200, 200, 200, 200]
    assert statuses[5] == 429


def test_refresh_without_completed_extraction_fails_safely_and_audits(
    client: TestClient, db_session: Session
) -> None:
    user = create_user(db_session, email="missing@example.com")
    login(client, email=user.email)

    response = client.post("/recommendations/refresh")

    assert response.status_code == 400
    assert response.json() == {"detail": "No completed resume extraction is available."}
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "recommendation.refresh"))
    assert audit is not None
    assert audit.outcome == "FAILURE"
    assert audit.details_json == {"reason": "no_completed_extraction"}
