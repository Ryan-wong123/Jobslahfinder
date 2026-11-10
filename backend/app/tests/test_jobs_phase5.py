from collections.abc import Generator
from types import SimpleNamespace
import time

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
from app.models.enums import ScrapingRunStatus, UserRole
from app.models.job import JobPosting, JobSource, ScrapingRun
from app.security.passwords import hash_password
from app.services.jobs import (
    JobSourceValidationError,
    JobValidationError,
    MAX_EXTERNAL_JOB_URL_LENGTH,
    find_duplicate_job,
    normalize_job,
    seed_approved_job_sources,
    store_normalized_job,
    validate_job_url_for_source,
    validate_source_base_url,
)
from app.services.scraping import GENERIC_SCRAPING_ERROR, run_scraper_for_source
from app.services.scraping import SCRAPER_ADAPTERS
from app.workers import tasks as worker_tasks
from app.workers.celery_app import celery_app


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
    if response.json().get("requires_2fa_setup"):
        setup_response = client.get("/auth/2fa/setup")
        assert setup_response.status_code == 200
        code = pyotp.TOTP(setup_response.json()["secret"]).now()
        confirm_response = client.post("/auth/2fa/confirm", json={"code": code})
        assert confirm_response.status_code == 200


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
    assert validate_source_base_url("JobsLah", "https://www.jobslah.com/sg", settings)
    assert validate_source_base_url("FastJobs", "https://www.fastjobs.sg", settings)

    with pytest.raises(JobSourceValidationError):
        validate_source_base_url("UnknownPortal", "https://sg.jobstreet.com", settings)

    with pytest.raises(JobSourceValidationError):
        validate_source_base_url("JobStreet", "https://evil.example.com", settings)

    with pytest.raises(JobSourceValidationError):
        validate_source_base_url("JobStreet", "http://sg.jobstreet.com", settings)


def test_external_job_url_validation_rejects_unsafe_values(db_session: Session) -> None:
    source = jobstreet_source(db_session)
    mcf_source = JobSource(
        source_name="MyCareersFuture",
        base_url="https://www.mycareersfuture.gov.sg",
        is_enabled=True,
    )
    db_session.add(mcf_source)
    db_session.commit()

    allowed = validate_job_url_for_source(
        "https://sg.jobstreet.com/job/security-engineer?tracking=approved",
        source,
    )
    assert allowed == "https://sg.jobstreet.com/job/security-engineer?tracking=approved"

    mismatched_allowed_source_url = "https://www.mycareersfuture.gov.sg/job/software-engineer"
    with pytest.raises(JobValidationError):
        validate_job_url_for_source(mismatched_allowed_source_url, source)
    assert validate_job_url_for_source(mismatched_allowed_source_url, mcf_source) == mismatched_allowed_source_url

    long_url = f"https://sg.jobstreet.com/{'a' * MAX_EXTERNAL_JOB_URL_LENGTH}"
    unsafe_urls = [
        "https://user:password@sg.jobstreet.com/job/security-engineer",
        "https://evil.example.com@sg.jobstreet.com/job/security-engineer",
        "https://sg.jobstreet.com.evil.example/job/security-engineer",
        "javascript:alert(1)",
        "http://sg.jobstreet.com/job/security-engineer",
        "https:///job/security-engineer",
        "https://sg.jobstreet.com:badport/job/security-engineer",
        "https://sg.jobstreet.com/job/security engineer",
        "https://sg.jobstreet.com\\@evil.example/job/security-engineer",
        "https://sg.jobstreet.com/job/security\x00engineer",
        long_url,
    ]

    for unsafe_url in unsafe_urls:
        with pytest.raises(JobValidationError):
            validate_job_url_for_source(unsafe_url, source)


def test_source_base_url_validation_rejects_credentials_and_overlong_values() -> None:
    settings = get_settings()

    unsafe_base_urls = [
        "https://user:password@sg.jobstreet.com",
        "https://evil.example.com@sg.jobstreet.com",
        f"https://sg.jobstreet.com/{'a' * MAX_EXTERNAL_JOB_URL_LENGTH}",
    ]

    for base_url in unsafe_base_urls:
        with pytest.raises(JobSourceValidationError):
            validate_source_base_url("JobStreet", base_url, settings)


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
            "salary": "SGD 4,000 - 6,000 per month",
            "minimum_experience": "2 years",
        },
        source,
    )

    assert normalized.title == "Security Engineer"
    assert normalized.company == "Example Company"
    assert "<script>" not in (normalized.description or "")
    assert "Build secure services." in (normalized.description or "")
    assert normalized.salary_min == 4000
    assert normalized.salary_max == 6000
    assert normalized.salary_currency == "SGD"
    assert normalized.salary_period == "month"
    assert normalized.minimum_experience == "2 years"
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


def test_job_normalization_uses_shared_text_cleanup_for_controls_and_unicode(
    db_session: Session,
) -> None:
    source = jobstreet_source(db_session)

    normalized = normalize_job(
        {
            "external_job_id": "job-control",
            "title": "Cafe\u0301\u0001 Security <b>Engineer</b>",
            "company": "Example\u0002 Company",
            "description": "<p>Protect\u0003 platforms.</p>",
            "job_url": "https://sg.jobstreet.com/job/security-control",
        },
        source,
    )

    assert normalized.title == "Café Security Engineer"
    assert normalized.company == "Example Company"
    assert normalized.description == "Protect platforms."
    assert "html_stripped" in normalized.suspicious_reasons


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


def test_approved_source_adapters_are_registered_and_store_jobs(db_session: Session) -> None:
    sources = seed_approved_job_sources(db_session, get_settings())
    assert {"JobStreet", "MyCareersFuture", "JobsLah", "FastJobs"}.issubset(SCRAPER_ADAPTERS.keys())

    mcf_source = next(source for source in sources if source.source_name == "MyCareersFuture")

    def fake_mcf_fetcher(*, timeout_seconds: int) -> list[dict[str, str]]:
        assert timeout_seconds > 0
        return [
            {
                "external_job_id": "mcf-test-1",
                "title": "Software Engineer",
                "company": "Example Company",
                "job_url": "https://www.mycareersfuture.gov.sg/job/software-engineer-test",
                "Job Salary Range": "$5,500 to $7,500 Monthly",
                "Job Minimum Experience": "3 years exp",
            }
        ]

    run = run_scraper_for_source(db_session, source=mcf_source, fetcher=fake_mcf_fetcher)

    assert run.status == ScrapingRunStatus.SUCCESS.value
    assert run.jobs_retrieved == 1
    posting = db_session.scalar(
        select(JobPosting).where(JobPosting.source_id == mcf_source.id)
    )
    assert posting is not None
    assert posting.job_url.startswith("https://www.mycareersfuture.gov.sg/")
    assert float(posting.salary_min) == 5500
    assert float(posting.salary_max) == 7500
    assert posting.salary_currency == "SGD"
    assert posting.salary_period == "month"
    assert posting.minimum_experience == "3 years exp"


def test_scraper_retry_policy_retries_up_to_success(db_session: Session) -> None:
    source = jobstreet_source(db_session)
    attempts = 0

    def flaky_fetcher(_source: JobSource) -> list[dict[str, str]]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary upstream failure")
        return [
            {
                "external_job_id": "retry-job-1",
                "title": "Security Engineer",
                "company": "Example Company",
                "job_url": "https://sg.jobstreet.com/job/retry-job-1",
            }
        ]

    run = run_scraper_for_source(
        db_session,
        source=source,
        fetcher=flaky_fetcher,
        max_retries=1,
        timeout_seconds=1,
    )

    assert run.status == ScrapingRunStatus.SUCCESS.value
    assert run.jobs_retrieved == 1
    assert attempts == 2
    retry_audit = db_session.scalar(
        select(AuditLog).where(AuditLog.event_type == "scraping_run.retry_policy")
    )
    assert retry_audit is not None
    assert retry_audit.details_json["attempts"] == 2
    assert retry_audit.details_json["max_retries"] == 1


def test_scraper_timeout_records_safe_failure(db_session: Session) -> None:
    source = jobstreet_source(db_session)

    def slow_fetcher(_source: JobSource) -> list[dict[str, str]]:
        time.sleep(0.2)
        return []

    run = run_scraper_for_source(
        db_session,
        source=source,
        fetcher=slow_fetcher,
        max_retries=0,
        timeout_seconds=0.01,
    )

    assert run.status == ScrapingRunStatus.FAILED.value
    assert run.error_message == GENERIC_SCRAPING_ERROR
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "scraping_run.failed"))
    assert audit is not None
    assert audit.details_json == {"source_id": source.id, "reason": "scraper_error"}


def test_weekly_scraping_schedule_is_registered() -> None:
    schedule = celery_app.conf.beat_schedule["weekly-approved-source-scraping"]
    assert schedule["task"] == "app.workers.tasks.run_weekly_scraping"


def test_weekly_scraping_task_runs_enabled_sources_only(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sources = seed_approved_job_sources(db_session, get_settings())
    disabled_source = next(source for source in sources if source.source_name == "JobStreet")
    disabled_source.is_enabled = False
    db_session.commit()
    called_source_ids: list[int] = []

    class SessionContext:
        def __enter__(self) -> Session:
            return db_session

        def __exit__(self, *_args: object) -> None:
            return None

    def fake_session_local() -> SessionContext:
        return SessionContext()

    def fake_run_scraper(_db: Session, *, source: JobSource) -> SimpleNamespace:
        called_source_ids.append(source.id)
        return SimpleNamespace(id=99, status=ScrapingRunStatus.SUCCESS.value)

    monkeypatch.setattr(worker_tasks, "SessionLocal", fake_session_local)
    monkeypatch.setattr(worker_tasks, "run_scraper_for_source", fake_run_scraper)

    result = worker_tasks.run_weekly_scraping.run()

    enabled_source_ids = {source.id for source in sources if source.source_name != "JobStreet"}
    assert set(called_source_ids) == enabled_source_ids
    assert result["sources_checked"] == len(enabled_source_ids)
    assert result["results"][0]["status"] == ScrapingRunStatus.SUCCESS.value


def test_admin_can_seed_sources_and_trigger_mock_scraping(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    login(client, email="admin@example.com", password=ADMIN_PASSWORD)

    seed_response = client.post("/admin/job-sources/seed")

    assert seed_response.status_code == 200
    assert {source["source_name"] for source in seed_response.json()} == {
        "JobStreet",
        "MyCareersFuture",
        "JobsLah",
        "FastJobs",
    }
    source = db_session.scalar(select(JobSource).where(JobSource.source_name == "JobStreet"))
    assert source is not None

    def fake_jobstreet_fetcher(*, timeout_seconds: int) -> list[dict[str, str]]:
        assert timeout_seconds > 0
        return [
            {
                "external_job_id": "jobstreet-test-1",
                "title": "Security Analyst",
                "company": "Example Company",
                "job_url": "https://sg.jobstreet.com/job/security-analyst-test",
            },
            {
                "external_job_id": "jobstreet-test-2",
                "title": "Backend Developer",
                "company": "Example Company",
                "job_url": "https://sg.jobstreet.com/job/backend-developer-test",
            },
        ]

    monkeypatch.setitem(SCRAPER_ADAPTERS, "JobStreet", fake_jobstreet_fetcher)

    run_response = client.post("/admin/scraping-runs", json={"source_id": source.id})

    assert run_response.status_code == 201
    assert run_response.json()["status"] == ScrapingRunStatus.PENDING.value
    assert run_response.json()["jobs_retrieved"] == 0
    pending = db_session.get(ScrapingRun, run_response.json()["id"])
    assert pending is not None
    completed = run_scraper_for_source(db_session, source=source, existing_run=pending)
    assert completed.status == ScrapingRunStatus.SUCCESS.value
    assert db_session.scalar(select(JobPosting).where(JobPosting.source_id == source.id)) is not None

    audit_events = {
        row.event_type for row in db_session.scalars(select(AuditLog)).all()
    }
    assert "admin.job_source.seed" in audit_events
    assert "scraping_run.completed" in audit_events
