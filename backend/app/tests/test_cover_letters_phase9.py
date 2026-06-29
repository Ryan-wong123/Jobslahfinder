from datetime import date
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.config import get_settings
from app.core.rate_limit import AUTH_RATE_LIMITER
from app.main import app
from app.models.account import User, UserProfile
from app.models.activity import ApplicationHistory, CoverLetter
from app.models.audit import AuditLog
from app.models.enums import ProcessingStatus, UploadStatus, UserRole
from app.models.job import JobPosting, JobSource
from app.models.resume import Resume, ResumeExtraction
from app.security.passwords import hash_password
from app.services import activity as activity_service


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
    title: str = "Python Security Engineer",
    description: str = "Build secure APIs with Python and FastAPI.",
    is_active: bool = True,
    is_suspicious: bool = False,
) -> JobPosting:
    job = JobPosting(
        source_id=source.id,
        external_job_id=title,
        title=title,
        company="Secure Co",
        location="Singapore",
        category="Engineering",
        description=description,
        job_url=f"https://sg.jobstreet.com/job/{title.lower().replace(' ', '-')}",
        posting_date=date(2026, 4, 30),
        is_active=is_active,
        is_suspicious=is_suspicious,
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
    extracted_text: str = "secret full resume text should never be logged",
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
        skills_json={"items": ["Python", "FastAPI", "PostgreSQL"]},
        experience_json={"items": [{"title": "Backend Developer", "company": "Platform Ltd"}]},
        education_json={"items": [{"credential": "Degree", "field": "Computer Science"}]},
        years_experience=4.0,
        processing_status=ProcessingStatus.COMPLETED.value,
    )
    db_session.add(resume)
    db_session.add(extraction)
    db_session.commit()
    db_session.refresh(extraction)
    return extraction


def test_successful_cover_letter_generation_stores_draft_history_and_metadata_only_audit(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    user = create_user(db_session, email="cover@example.com")
    extraction = create_completed_extraction(db_session, user, extracted_text="unique-private-resume")
    job = create_job(
        db_session,
        source,
        description="confidential full job description with Python and FastAPI details",
    )
    login(client, email=user.email)

    response = client.post(f"/jobs/{job.id}/cover-letter")

    assert response.status_code == 201
    body = response.json()
    assert body["job"]["id"] == job.id
    assert body["resume_id"] == extraction.resume_id
    assert body["version_no"] == 1
    assert "draft" in body["generated_text"].casefold()
    assert "Python" in body["generated_text"]

    stored = db_session.scalar(select(CoverLetter).where(CoverLetter.user_id == user.id))
    assert stored is not None
    assert stored.job_id == job.id
    assert stored.resume_id == extraction.resume_id

    history = db_session.scalar(
        select(ApplicationHistory).where(
            ApplicationHistory.user_id == user.id,
            ApplicationHistory.cover_letter_id == stored.id,
            ApplicationHistory.action_type == "cover_letter_generated",
        )
    )
    assert history is not None

    audit = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.event_type == "cover_letter.generate", AuditLog.user_id == user.id)
        .order_by(AuditLog.id.desc())
    )
    assert audit is not None
    assert audit.outcome == "SUCCESS"
    details = str(audit.details_json)
    assert "unique-private-resume" not in details
    assert "confidential full job description" not in details
    assert body["generated_text"] not in details
    assert audit.details_json["job_id"] == job.id
    assert audit.details_json["resume_id"] == extraction.resume_id


def test_gemini_cover_letter_generation_uses_bounded_context_and_not_raw_resume_text(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = create_source(db_session)
    user = create_user(db_session, email="gemini-cover@example.com")
    extraction = create_completed_extraction(db_session, user, extracted_text="raw-resume-secret")
    job = create_job(db_session, source, description="Build secure products with Python.")
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "cover_letter_generation_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-gemini-key"))

    called: dict[str, object] = {}

    def fake_gemini(*, extraction: ResumeExtraction, job: JobPosting, settings) -> str:
        context = activity_service.cover_letter_prompt_context(extraction=extraction, job=job)
        called["used"] = True
        called["model"] = settings.gemini_cover_letter_model
        assert "raw-resume-secret" not in context
        assert "Python" in context
        assert "<untrusted_profile_data>" in context
        assert "<untrusted_job_data>" in context
        return "Gemini generated plain text draft for review."

    monkeypatch.setattr(activity_service, "generate_cover_letter_with_gemini", fake_gemini)
    login(client, email=user.email)

    response = client.post(f"/jobs/{job.id}/cover-letter")

    assert response.status_code == 201
    body = response.json()
    assert body["generated_text"] == "Gemini generated plain text draft for review."
    assert called == {"used": True, "model": settings.gemini_cover_letter_model}
    audit = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.event_type == "cover_letter.generate", AuditLog.user_id == user.id)
        .order_by(AuditLog.id.desc())
    )
    assert audit is not None
    assert audit.details_json["generator_version"] == "gemini-cover-letter-v1"
    assert "Gemini generated plain text draft" not in str(audit.details_json)


def test_gemini_failure_falls_back_without_logging_sensitive_content(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = create_source(db_session)
    user = create_user(db_session, email="gemini-fallback@example.com")
    create_completed_extraction(db_session, user, extracted_text="private-resume-content")
    job = create_job(db_session, source, description="sensitive job detail")
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "cover_letter_generation_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-gemini-key"))

    def failing_gemini(*, extraction: ResumeExtraction, job: JobPosting, settings) -> str:
        raise RuntimeError("503 unavailable")

    monkeypatch.setattr(activity_service, "generate_cover_letter_with_gemini", failing_gemini)
    login(client, email=user.email)

    response = client.post(f"/jobs/{job.id}/cover-letter")

    assert response.status_code == 201
    audit = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.event_type == "cover_letter.generate", AuditLog.user_id == user.id)
        .order_by(AuditLog.id.desc())
    )
    assert audit is not None
    details = str(audit.details_json)
    assert audit.details_json["generator_version"] == "deterministic-cover-letter-v1"
    assert audit.details_json["fallback_reason"] == "ai_provider_unavailable"
    assert "private-resume-content" not in details
    assert "sensitive job detail" not in details


def test_generation_without_completed_extraction_fails_safely_and_audits(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    user = create_user(db_session, email="missing-cover@example.com")
    job = create_job(db_session, source)
    login(client, email=user.email)

    response = client.post(f"/jobs/{job.id}/cover-letter")

    assert response.status_code == 400
    assert response.json() == {"detail": "No completed resume extraction is available."}
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "cover_letter.generate"))
    assert audit is not None
    assert audit.outcome == "FAILURE"
    assert audit.details_json == {"reason": "no_completed_extraction", "job_id": job.id}


def test_inactive_or_suspicious_jobs_are_rejected_for_generation(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    user = create_user(db_session, email="job-state@example.com")
    create_completed_extraction(db_session, user)
    inactive_job = create_job(db_session, source, title="Inactive Engineer", is_active=False)
    suspicious_job = create_job(db_session, source, title="Suspicious Engineer", is_suspicious=True)
    login(client, email=user.email)

    assert client.post(f"/jobs/{inactive_job.id}/cover-letter").status_code == 404
    assert client.post(f"/jobs/{suspicious_job.id}/cover-letter").status_code == 404
    assert db_session.scalars(select(CoverLetter)).all() == []


def test_cover_letters_are_user_owned_for_read_and_update(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    owner = create_user(db_session, email="owner-cover@example.com")
    other = create_user(db_session, email="other-cover@example.com")
    create_completed_extraction(db_session, owner)
    job = create_job(db_session, source)
    login(client, email=owner.email)
    created = client.post(f"/jobs/{job.id}/cover-letter").json()

    login(client, email=other.email)

    assert client.get(f"/cover-letters/{created['id']}").status_code == 404
    blocked_update = client.patch(
        f"/cover-letters/{created['id']}",
        json={"edited_text": "Edited by another user."},
    )
    assert blocked_update.status_code == 404
    assert client.get("/cover-letters").json()["items"] == []

    db_session.expire_all()
    stored = db_session.get(CoverLetter, created["id"])
    assert stored is not None
    assert stored.edited_text is None
    denial = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.event_type == "authorization.denied", AuditLog.target_id == created["id"])
        .order_by(AuditLog.id.desc())
    )
    assert denial is not None


def test_cover_letter_edit_validation_and_history(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    user = create_user(db_session, email="edit-cover@example.com")
    create_completed_extraction(db_session, user)
    job = create_job(db_session, source)
    login(client, email=user.email)
    created = client.post(f"/jobs/{job.id}/cover-letter").json()

    invalid = client.patch(
        f"/cover-letters/{created['id']}",
        json={"edited_text": "unsafe\u0001control"},
    )
    assert invalid.status_code == 422

    response = client.patch(
        f"/cover-letters/{created['id']}",
        json={"edited_text": "Reviewed and tailored draft."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["edited_text"] == "Reviewed and tailored draft."
    assert body["version_no"] == 2
    history = db_session.scalar(
        select(ApplicationHistory).where(
            ApplicationHistory.cover_letter_id == created["id"],
            ApplicationHistory.action_type == "cover_letter_edited",
        )
    )
    assert history is not None
    audit = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.event_type == "cover_letter.edit", AuditLog.user_id == user.id)
        .order_by(AuditLog.id.desc())
    )
    assert audit is not None
    details = str(audit.details_json)
    assert "Reviewed and tailored draft" not in details
    assert audit.details_json["version_no"] == 2


def test_generation_rate_limiting_applies(client: TestClient, db_session: Session) -> None:
    AUTH_RATE_LIMITER.clear()
    source = create_source(db_session)
    user = create_user(db_session, email="cover-limit@example.com")
    create_completed_extraction(db_session, user)
    job = create_job(db_session, source)
    login(client, email=user.email)

    statuses = [client.post(f"/jobs/{job.id}/cover-letter").status_code for _ in range(6)]

    assert statuses[:5] == [201, 201, 201, 201, 201]
    assert statuses[5] == 429
