from collections.abc import Generator

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
from app.models.enums import ScrapingRunStatus, UserRole
from app.models.job import JobPosting, JobSource, ScrapingRun
from app.security.passwords import hash_password
from app.services.jobs import (
    JobSourceValidationError,
    JobValidationError,
    find_duplicate_job,
    normalize_job,
    seed_approved_job_sources,
    store_normalized_job,
    validate_source_base_url,
)
from app.services.scraping import GENERIC_SCRAPING_ERROR, run_scraper_for_source


USER_PASSWORD = "StrongPass123"
ADMIN_PASSWORD = "AdminPass123"


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


def jobstreet_source(db_session: Session) -> JobSource:
    source = JobSource(
        source_name="JobStreet",
        base_url="https://sg.jobstreet.com",
        is_enabled=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def test_source_allowlist_enforcement_rejects_unapproved_domains() -> None:
    settings = get_settings()

    assert validate_source_base_url("JobStreet", "https://sg.jobstreet.com", settings)

    with pytest.raises(JobSourceValidationError):
        validate_source_base_url("UnknownPortal", "https://sg.jobstreet.com", settings)

    with pytest.raises(JobSourceValidationError):
        validate_source_base_url("JobStreet", "https://evil.example.com", settings)

    with pytest.raises(JobSourceValidationError):
        validate_source_base_url("JobStreet", "http://sg.jobstreet.com", settings)


def test_job_normalization_strips_html_and_validates_source_domain(db_session: Session) -> None:
    source = jobstreet_source(db_session)

    normalized = normalize_job(
        {
            "external_job_id": "job-1",
            "title": "  Security Engineer  ",
            "company": "Example <b>Company</b>",
            "description": "<script>alert(1)</script><p>Build secure services.</p>",
            "job_url": "https://sg.jobstreet.com/job/security-engineer",
            "posting_date": "2026-04-30",
        },
        source,
    )

    assert normalized.title == "Security Engineer"
    assert normalized.company == "Example Company"
    assert "<script>" not in (normalized.description or "")
    assert "Build secure services." in (normalized.description or "")
    assert normalized.is_suspicious is True
    assert "html_stripped" in normalized.suspicious_reasons
    assert len(normalized.content_hash) == 64

    with pytest.raises(JobValidationError):
        normalize_job(
            {
                "external_job_id": "job-2",
                "title": "Phishing Role",
                "company": "Bad Co",
                "job_url": "https://example.com/job/phishing",
            },
            source,
        )


def test_duplicate_detection_uses_external_job_id_and_content_hash(db_session: Session) -> None:
    source = jobstreet_source(db_session)
    raw_job = {
        "external_job_id": "job-1",
        "title": "Security Engineer",
        "company": "Example Company",
        "description": "Build secure services.",
        "job_url": "https://sg.jobstreet.com/job/security-engineer",
    }
    normalized = normalize_job(raw_job, source)
    first_posting, created, duplicate_reason = store_normalized_job(
        db_session,
        source=source,
        normalized_job=normalized,
    )
    db_session.commit()

    assert created is True
    assert duplicate_reason is None
    assert first_posting.id is not None

    duplicate_by_external_id = normalize_job({**raw_job, "title": "Updated title"}, source)
    existing, reason = find_duplicate_job(
        db_session,
        source=source,
        normalized_job=duplicate_by_external_id,
    )

    assert existing is not None
    assert existing.id == first_posting.id
    assert reason == "source_external_job_id"

    duplicate_by_hash = normalize_job({**raw_job, "external_job_id": None}, source)
    existing, reason = find_duplicate_job(
        db_session,
        source=source,
        normalized_job=duplicate_by_hash,
    )

    assert existing is not None
    assert existing.id == first_posting.id
    assert reason == "content_hash"


def test_suspicious_job_flagging_is_stored_and_audited(db_session: Session) -> None:
    source = jobstreet_source(db_session)
    normalized = normalize_job(
        {
            "external_job_id": "job-suspicious",
            "title": "Analyst",
            "company": "",
            "description": "<p>Investigate alerts.</p>",
            "job_url": "https://sg.jobstreet.com/job/analyst",
        },
        source,
    )

    posting, created, _duplicate_reason = store_normalized_job(
        db_session,
        source=source,
        normalized_job=normalized,
    )
    db_session.commit()

    assert created is True
    assert posting.is_suspicious is True
    assert posting.company == "Unknown company"
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "job.suspicious_flagged"))
    assert audit is not None
    assert audit.outcome == "SUCCESS"
    assert audit.target_id == posting.id
    assert "missing_company" in audit.details_json["reasons"]


def test_scraping_failure_handling_records_safe_run_and_audit(db_session: Session) -> None:
    source = jobstreet_source(db_session)

    def broken_fetcher(_source: JobSource) -> list[dict[str, str]]:
        raise RuntimeError("network stack trace with private details")

    run = run_scraper_for_source(db_session, source=source, fetcher=broken_fetcher)

    assert run.status == ScrapingRunStatus.FAILED.value
    assert run.jobs_retrieved == 0
    assert run.error_message == GENERIC_SCRAPING_ERROR
    assert "network stack trace" not in (run.error_message or "")
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "scraping_run.failed"))
    assert audit is not None
    assert audit.outcome == "FAILURE"
    assert audit.details_json == {"source_id": source.id, "reason": "scraper_error"}


def test_admin_can_seed_sources_and_trigger_mock_scraping(
    client: TestClient,
    db_session: Session,
) -> None:
    create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    login(client, email="admin@example.com", password=ADMIN_PASSWORD)

    seed_response = client.post("/admin/job-sources/seed")

    assert seed_response.status_code == 200
    assert {source["source_name"] for source in seed_response.json()} == {
        "JobStreet",
        "MyCareersFuture",
    }
    source = db_session.scalar(select(JobSource).where(JobSource.source_name == "JobStreet"))
    assert source is not None

    run_response = client.post("/admin/scraping-runs", json={"source_id": source.id})

    assert run_response.status_code == 201
    assert run_response.json()["status"] == ScrapingRunStatus.SUCCESS.value
    assert run_response.json()["jobs_retrieved"] == 2
    assert db_session.scalar(select(JobPosting).where(JobPosting.source_id == source.id)) is not None

    audit_events = {
        row.event_type for row in db_session.scalars(select(AuditLog)).all()
    }
    assert "admin.job_source.seed" in audit_events
    assert "scraping_run.completed" in audit_events
