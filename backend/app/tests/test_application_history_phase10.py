from collections.abc import Generator
from datetime import date

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
from app.models.activity import ApplicationHistory, CoverLetter
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
    if response.json().get("requires_2fa_setup"):
        setup_response = client.get("/auth/2fa/setup")
        assert setup_response.status_code == 200
        code = pyotp.TOTP(setup_response.json()["secret"]).now()
        confirm_response = client.post("/auth/2fa/confirm", json={"code": code})
        assert confirm_response.status_code == 200


def create_source(db_session: Session) -> JobSource:
    source = JobSource(source_name="JobStreet", base_url="https://sg.jobstreet.com", is_enabled=True)
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def create_job(db_session: Session, source: JobSource, *, title: str = "Security Engineer") -> JobPosting:
    job = JobPosting(
        source_id=source.id,
        external_job_id=title,
        title=title,
        company="Secure Co",
        location="Singapore",
        category="Security",
        description="Build secure systems with private-job-details.",
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


def create_completed_extraction(db_session: Session, user: User) -> ResumeExtraction:
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
        extracted_text="secret-resume-content-never-in-history",
        skills_json={"items": ["Python", "FastAPI"]},
        experience_json={"items": [{"title": "Security Developer", "description": "Built APIs"}]},
        education_json={"items": [{"credential": "Degree", "field": "Computer Science"}]},
        years_experience=3.0,
        processing_status=ProcessingStatus.COMPLETED.value,
    )
    db_session.add_all([resume, extraction])
    db_session.commit()
    db_session.refresh(extraction)
    return extraction


def test_authenticated_user_can_list_own_history_and_other_users_are_isolated(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    owner = create_user(db_session, email="owner@example.com")
    other = create_user(db_session, email="other@example.com")
    owner_job = create_job(db_session, source, title="Owner History")
    other_job = create_job(db_session, source, title="Other History")
    db_session.add_all(
        [
            ApplicationHistory(user_id=owner.id, job_id=owner_job.id, action_type="job_saved"),
            ApplicationHistory(user_id=other.id, job_id=other_job.id, action_type="job_saved"),
        ]
    )
    db_session.commit()

    assert client.get("/application-history").status_code == 401
    login(client, email=owner.email)

    response = client.get("/application-history")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["job"]["id"] == owner_job.id
    assert "Other History" not in str(body)


def test_history_pagination_and_filters_are_validated(client: TestClient, db_session: Session) -> None:
    source = create_source(db_session)
    user = create_user(db_session, email="filters@example.com")
    first_job = create_job(db_session, source, title="First Job")
    second_job = create_job(db_session, source, title="Second Job")
    db_session.add_all(
        [
            ApplicationHistory(user_id=user.id, job_id=first_job.id, action_type="job_saved"),
            ApplicationHistory(user_id=user.id, job_id=second_job.id, action_type="cover_letter_generated"),
        ]
    )
    db_session.commit()
    login(client, email=user.email)

    page_response = client.get("/application-history", params={"page": 2, "page_size": 1})
    action_response = client.get("/application-history", params={"action_type": "job_saved"})
    job_response = client.get("/application-history", params={"job_id": second_job.id})
    invalid_page = client.get("/application-history", params={"page_size": 51})
    invalid_action = client.get("/application-history", params={"action_type": "unsafe_action"})
    invalid_job = client.get("/application-history", params={"job_id": 0})

    assert page_response.status_code == 200
    assert page_response.json()["total"] == 2
    assert len(page_response.json()["items"]) == 1
    assert action_response.status_code == 200
    assert action_response.json()["items"][0]["action_type"] == "job_saved"
    assert job_response.status_code == 200
    assert job_response.json()["items"][0]["job"]["id"] == second_job.id
    assert invalid_page.status_code == 422
    assert invalid_action.status_code == 422
    assert invalid_job.status_code == 422


def test_cover_letter_generate_and_edit_appear_in_history_without_sensitive_text(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    user = create_user(db_session, email="cover-history@example.com")
    create_completed_extraction(db_session, user)
    job = create_job(db_session, source)
    login(client, email=user.email)

    created = client.post(f"/jobs/{job.id}/cover-letter")
    assert created.status_code == 201
    edited = client.patch(
        f"/cover-letters/{created.json()['id']}",
        json={"edited_text": "Edited draft with private-cover-letter-content"},
    )
    assert edited.status_code == 200

    response = client.get("/application-history")

    assert response.status_code == 200
    body = response.json()
    assert [item["action_type"] for item in body["items"]] == [
        "cover_letter_edited",
        "cover_letter_generated",
    ]
    assert {item["cover_letter_id"] for item in body["items"]} == {created.json()["id"]}
    serialized = str(body)
    assert "private-cover-letter-content" not in serialized
    assert "secret-resume-content-never-in-history" not in serialized
    assert "private-job-details" not in serialized


def test_saved_unsaved_and_recommendation_refresh_history(client: TestClient, db_session: Session) -> None:
    source = create_source(db_session)
    user = create_user(db_session, email="actions@example.com")
    create_completed_extraction(db_session, user)
    job = create_job(db_session, source, title="Python FastAPI Security")
    login(client, email=user.email)

    assert client.post(f"/jobs/{job.id}/save").status_code == 201
    assert client.post(f"/jobs/{job.id}/save").status_code == 201
    assert client.delete(f"/jobs/{job.id}/save").status_code == 200
    assert client.post("/recommendations/refresh").status_code == 200

    history = db_session.scalars(
        select(ApplicationHistory).where(ApplicationHistory.user_id == user.id).order_by(ApplicationHistory.id)
    ).all()

    assert [item.action_type for item in history] == [
        "job_saved",
        "job_unsaved",
        "recommendations_refreshed",
    ]
    assert history[0].job_id == job.id
    assert history[1].job_id == job.id
    assert history[2].job_id is None


def test_history_cover_letter_id_is_only_returned_for_owned_history(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    owner = create_user(db_session, email="owned-draft@example.com")
    other = create_user(db_session, email="other-draft@example.com")
    job = create_job(db_session, source)
    cover_letter = CoverLetter(user_id=owner.id, job_id=job.id, generated_text="Owner private draft")
    other_cover_letter = CoverLetter(user_id=other.id, job_id=job.id, generated_text="Other private draft")
    db_session.add_all([cover_letter, other_cover_letter])
    db_session.flush()
    db_session.add_all(
        [
            ApplicationHistory(
                user_id=owner.id,
                job_id=job.id,
                cover_letter_id=cover_letter.id,
                action_type="cover_letter_generated",
            ),
            ApplicationHistory(
                user_id=other.id,
                job_id=job.id,
                cover_letter_id=other_cover_letter.id,
                action_type="cover_letter_generated",
            ),
        ]
    )
    db_session.commit()
    login(client, email=owner.email)

    response = client.get("/application-history")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["cover_letter_id"] == cover_letter.id
    assert "Other private draft" not in str(body)
