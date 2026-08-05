from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.config import get_settings
from app.core.rate_limit import AUTH_RATE_LIMITER
from app.main import app
from app.models.account import PasswordResetToken, Session as UserSession, User, UserProfile
from app.models.activity import ApplicationHistory, CoverLetter, Recommendation, SavedJob
from app.models.audit import AuditLog
from app.models.enums import AuditOutcome, ScrapingRunStatus, UserRole
from app.models.job import JobPosting, JobSource, ScrapingRun
from app.models.resume import Resume, ResumeExtraction
from app.security.passwords import hash_password
from app.security.tokens import hash_token
from app.services.audit import create_audit_log


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


def create_job(db_session: Session, source: JobSource) -> JobPosting:
    job = JobPosting(
        source_id=source.id,
        external_job_id="phase11-1",
        title="<b>Security Engineer</b>",
        company="Example <script>bad()</script>",
        location="Singapore",
        category="Security",
        description="<img src=x onerror=alert(1)> secret description",
        job_url="https://sg.jobstreet.com/job/phase11-1",
        content_hash="phase11-hash",
        is_active=True,
        is_suspicious=True,
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def assert_no_sensitive_fields(value: object) -> None:
    serialized = str(value)
    blocked = [
        "password_hash",
        "session_token_hash",
        "token_hash",
        "raw-resume-secret",
        "cover-letter-secret",
        "full-prompt-secret",
        "api-key-secret",
        "Traceback",
    ]
    for token in blocked:
        assert token not in serialized


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("get", "/admin/users", None),
        ("get", "/admin/users/1", None),
        ("patch", "/admin/users/1", {"is_active": False}),
        ("get", "/admin/jobs", None),
        ("patch", "/admin/jobs/1", {"is_active": False}),
        ("delete", "/admin/jobs/1", None),
        ("get", "/admin/job-sources", None),
        ("post", "/admin/job-sources/seed", None),
        ("patch", "/admin/job-sources/1", {"is_enabled": False}),
        ("get", "/admin/scraping-runs", None),
        ("get", "/admin/scraping-runs/1", None),
        ("post", "/admin/scraping-runs", {"source_id": 1}),
        ("get", "/admin/audit-logs", None),
        ("get", "/admin/health", None),
    ],
)
def test_admin_routes_reject_unauthenticated_requests(
    client: TestClient, method: str, path: str, json_body: dict | None
) -> None:
    response = getattr(client, method)(path, json=json_body) if json_body else getattr(client, method)(path)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}


@pytest.mark.parametrize(
    "method,path,json_body",
    [
        ("get", "/admin/users", None),
        ("get", "/admin/users/1", None),
        ("patch", "/admin/users/1", {"is_active": False}),
        ("get", "/admin/jobs", None),
        ("patch", "/admin/jobs/1", {"is_active": False}),
        ("delete", "/admin/jobs/1", None),
        ("get", "/admin/job-sources", None),
        ("post", "/admin/job-sources/seed", None),
        ("patch", "/admin/job-sources/1", {"is_enabled": False}),
        ("get", "/admin/scraping-runs", None),
        ("get", "/admin/scraping-runs/1", None),
        ("post", "/admin/scraping-runs", {"source_id": 1}),
        ("get", "/admin/audit-logs", None),
        ("get", "/admin/health", None),
    ],
)
def test_normal_user_cannot_access_admin_routes_and_denials_are_audited(
    client: TestClient, db_session: Session, method: str, path: str, json_body: dict | None
) -> None:
    user = create_user(db_session, email="user@example.com")
    login(client, email=user.email, password=USER_PASSWORD)

    response = getattr(client, method)(path, json=json_body) if json_body else getattr(client, method)(path)

    assert response.status_code == 403
    assert response.json() == {"detail": "Access denied."}
    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.event_type == "authorization.denied").order_by(AuditLog.id.desc())
    )
    assert audit is not None
    assert audit.user_id == user.id
    assert audit.target_type == "admin"
    assert audit.outcome == "DENIED"


def test_admin_can_list_users_with_safe_fields_only(client: TestClient, db_session: Session) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    user = create_user(db_session, email="target@example.com")
    db_session.add(
        UserSession(
            user_id=user.id,
            session_token_hash="stored-session-token-hash",
            expires_at=admin.created_at,
        )
    )
    db_session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash="stored-reset-token-hash",
            expires_at=admin.created_at,
        )
    )
    db_session.commit()
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.get("/admin/users?page=1&page_size=20")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {"id", "email", "role", "is_active", "created_at", "last_login_at"} == set(body["items"][0])
    assert_no_sensitive_fields(body)


def test_admin_user_detail_returns_safe_metadata_counts(client: TestClient, db_session: Session) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    user = create_user(db_session, email="target@example.com")
    source = create_source(db_session)
    job = create_job(db_session, source)
    db_session.add(SavedJob(user_id=user.id, job_id=job.id))
    db_session.add(
        Resume(
            user_id=user.id,
            original_filename="resume.pdf",
            stored_filename="stored-detail.pdf",
            file_path="/protected/stored-detail.pdf",
            file_hash="detail-hash",
            mime_type="application/pdf",
            file_size_bytes=100,
            upload_status="STORED",
        )
    )
    db_session.commit()
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.get(f"/admin/users/{user.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == user.email
    assert body["resume_count"] == 1
    assert body["saved_job_count"] == 1
    assert_no_sensitive_fields(body)


def test_admin_can_deactivate_and_reactivate_user_with_audit(
    client: TestClient, db_session: Session
) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    user = create_user(db_session, email="target@example.com")
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    deactivate = client.patch(f"/admin/users/{user.id}", json={"is_active": False})
    reactivate = client.patch(f"/admin/users/{user.id}", json={"is_active": True})

    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False
    assert reactivate.status_code == 200
    assert reactivate.json()["is_active"] is True
    audits = db_session.scalars(select(AuditLog).where(AuditLog.event_type == "admin.user.update")).all()
    assert len(audits) == 2
    assert all(audit.user_id == admin.id for audit in audits)
    assert_no_sensitive_fields([audit.details_json for audit in audits])


def test_admin_cannot_deactivate_self_or_last_admin(client: TestClient, db_session: Session) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.patch(f"/admin/users/{admin.id}", json={"is_active": False})

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid admin update."}


def test_admin_can_list_and_moderate_jobs_safely(client: TestClient, db_session: Session) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    source = create_source(db_session)
    job = create_job(db_session, source)
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    list_response = client.get("/admin/jobs?is_suspicious=true")
    patch_response = client.patch(f"/admin/jobs/{job.id}", json={"is_active": False, "is_suspicious": False})

    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["total_items"] == 1
    assert "<script>" not in list_body["items"][0]["company"]
    assert "description" not in list_body["items"][0]
    assert patch_response.status_code == 200
    assert patch_response.json()["is_active"] is False
    assert patch_response.json()["is_suspicious"] is False
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "admin.job.update"))
    assert audit is not None
    assert audit.target_id == job.id
    assert_no_sensitive_fields([list_body, patch_response.json(), audit.details_json])


def test_anonymous_users_cannot_use_admin_job_moderation_filters(client: TestClient) -> None:
    response = client.get("/admin/jobs?is_active=false&is_suspicious=true")

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required."}
    assert_no_sensitive_fields(response.json())


def test_normal_users_cannot_use_admin_job_moderation_filters_and_denial_is_audited(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="user@example.com")
    login(client, email=user.email, password=USER_PASSWORD)

    response = client.get("/admin/jobs?is_active=false&is_suspicious=true")

    assert response.status_code == 403
    assert response.json() == {"detail": "Access denied."}
    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.event_type == "authorization.denied").order_by(AuditLog.id.desc())
    )
    assert audit is not None
    assert audit.user_id == user.id
    assert audit.target_type == "admin"
    assert audit.outcome == "DENIED"
    assert_no_sensitive_fields([response.json(), audit.details_json])


def test_admin_job_moderation_filters_support_active_and_suspicious_states(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    source = create_source(db_session)
    inactive_suspicious = create_job(db_session, source)
    inactive_suspicious.is_active = False
    active_suspicious = JobPosting(
        source_id=source.id,
        external_job_id="phase11-active-suspicious",
        title="Active Suspicious Job",
        company="Example",
        location="Singapore",
        category="Security",
        description="Needs review",
        job_url="https://sg.jobstreet.com/job/phase11-active-suspicious",
        content_hash="phase11-active-suspicious-hash",
        is_active=True,
        is_suspicious=True,
    )
    inactive_reviewed = JobPosting(
        source_id=source.id,
        external_job_id="phase11-inactive-reviewed",
        title="Inactive Reviewed Job",
        company="Example",
        location="Singapore",
        category="Security",
        description="Disabled but reviewed",
        job_url="https://sg.jobstreet.com/job/phase11-inactive-reviewed",
        content_hash="phase11-inactive-reviewed-hash",
        is_active=False,
        is_suspicious=False,
    )
    db_session.add_all([active_suspicious, inactive_reviewed])
    db_session.commit()
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    inactive_suspicious_response = client.get("/admin/jobs?is_active=false&is_suspicious=true")
    inactive_reviewed_response = client.get("/admin/jobs?is_active=false&is_suspicious=false")

    assert inactive_suspicious_response.status_code == 200
    inactive_suspicious_ids = {item["id"] for item in inactive_suspicious_response.json()["items"]}
    assert inactive_suspicious_ids == {inactive_suspicious.id}
    assert inactive_reviewed_response.status_code == 200
    inactive_reviewed_ids = {item["id"] for item in inactive_reviewed_response.json()["items"]}
    assert inactive_reviewed_ids == {inactive_reviewed.id}
    assert_no_sensitive_fields([inactive_suspicious_response.json(), inactive_reviewed_response.json()])


def test_admin_job_sources_include_safe_job_counts(client: TestClient, db_session: Session) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    sources = [
        JobSource(source_name="JobStreet", base_url="https://sg.jobstreet.com", is_enabled=True),
        JobSource(
            source_name="MyCareersFuture",
            base_url="https://www.mycareersfuture.gov.sg",
            is_enabled=True,
        ),
        JobSource(source_name="JobsLah", base_url="https://www.jobslah.com/sg", is_enabled=True),
        JobSource(source_name="FastJobs", base_url="https://www.fastjobs.sg", is_enabled=True),
    ]
    db_session.add_all(sources)
    db_session.flush()
    db_session.add_all(
        [
            JobPosting(
                source_id=sources[0].id,
                external_job_id="jobstreet-count-1",
                title="Security Engineer",
                company="Example",
                job_url="https://sg.jobstreet.com/job/count-1",
                content_hash="jobstreet-count-1",
            ),
            JobPosting(
                source_id=sources[0].id,
                external_job_id="jobstreet-count-2",
                title="Security Analyst",
                company="Example",
                job_url="https://sg.jobstreet.com/job/count-2",
                content_hash="jobstreet-count-2",
            ),
            JobPosting(
                source_id=sources[1].id,
                external_job_id="mcf-count-1",
                title="AppSec Engineer",
                company="Example",
                job_url="https://www.mycareersfuture.gov.sg/job/count-1",
                content_hash="mcf-count-1",
            ),
        ]
    )
    db_session.commit()
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.get("/admin/job-sources")

    assert response.status_code == 200
    counts_by_source = {source["source_name"]: source["job_count"] for source in response.json()}
    assert counts_by_source == {"FastJobs": 0, "JobStreet": 2, "JobsLah": 0, "MyCareersFuture": 1}
    assert_no_sensitive_fields(response.json())


def test_admin_can_update_job_source_enabled_status_with_audit(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    source = create_source(db_session)
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.patch(f"/admin/job-sources/{source.id}", json={"is_enabled": False})

    assert response.status_code == 200
    assert response.json()["id"] == source.id
    assert response.json()["is_enabled"] is False
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "admin.job_source.update"))
    assert audit is not None
    assert audit.user_id == admin.id
    assert audit.target_id == source.id
    assert_no_sensitive_fields([response.json(), audit.details_json])


@pytest.mark.parametrize("source_id", ["0", "-1", "not-an-int"])
def test_admin_job_source_path_id_must_be_positive_integer(
    client: TestClient,
    db_session: Session,
    source_id: str,
) -> None:
    admin = create_user(db_session, email=f"admin-{source_id}@example.com", role=UserRole.ADMIN)
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.patch(f"/admin/job-sources/{source_id}", json={"is_enabled": False})

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    assert_no_sensitive_fields(body)
    assert db_session.scalars(select(JobSource)).all() == []


def test_admin_can_delete_job_with_dependent_records_and_audit(
    client: TestClient, db_session: Session
) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    user = create_user(db_session, email="user@example.com")
    source = create_source(db_session)
    job = create_job(db_session, source)
    cover_letter = CoverLetter(user_id=user.id, job_id=job.id, generated_text="private draft")
    db_session.add_all(
        [
            SavedJob(user_id=user.id, job_id=job.id),
            Recommendation(user_id=user.id, job_id=job.id, match_score=91.5, rank=1),
            cover_letter,
            ApplicationHistory(user_id=user.id, job_id=job.id, action_type="job_saved"),
        ]
    )
    db_session.flush()
    history = ApplicationHistory(
        user_id=user.id,
        job_id=job.id,
        cover_letter_id=cover_letter.id,
        action_type="cover_letter_generated",
    )
    db_session.add(history)
    db_session.commit()
    job_id = job.id
    history_id = history.id
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.delete(f"/admin/jobs/{job_id}")

    assert response.status_code == 200
    assert response.json() == {"message": "Job deleted."}
    assert db_session.get(JobPosting, job_id) is None
    assert db_session.scalar(select(SavedJob).where(SavedJob.job_id == job_id)) is None
    assert db_session.scalar(select(Recommendation).where(Recommendation.job_id == job_id)) is None
    assert db_session.scalar(select(CoverLetter).where(CoverLetter.job_id == job_id)) is None
    unlinked_history = db_session.get(ApplicationHistory, history_id)
    assert unlinked_history is not None
    assert unlinked_history.job_id is None
    assert unlinked_history.cover_letter_id is None
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "admin.job.delete"))
    assert audit is not None
    assert audit.user_id == admin.id
    assert audit.target_id == job_id
    assert audit.details_json == {
        "saved_jobs_deleted": 1,
        "recommendations_deleted": 1,
        "cover_letters_deleted": 1,
        "application_history_unlinked": 2,
    }
    assert_no_sensitive_fields([response.json(), audit.details_json])


def test_admin_can_list_scraping_runs_with_filter(client: TestClient, db_session: Session) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    source = create_source(db_session)
    db_session.add(
        ScrapingRun(
            source_id=source.id,
            status=ScrapingRunStatus.FAILED.value,
            jobs_retrieved=0,
            error_message="Scraping failed for source.",
        )
    )
    db_session.commit()
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.get("/admin/scraping-runs?status=FAILED&page=1&page_size=10")

    assert response.status_code == 200
    assert response.json()[0]["status"] == "FAILED"
    assert response.json()[0]["error_message"] == "Scraping failed for source."
    assert_no_sensitive_fields(response.json())


def test_admin_can_view_scraping_run_detail(client: TestClient, db_session: Session) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    source = create_source(db_session)
    run = ScrapingRun(
        source_id=source.id,
        status=ScrapingRunStatus.SUCCESS.value,
        jobs_retrieved=3,
        error_message=None,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.get(f"/admin/scraping-runs/{run.id}")

    assert response.status_code == 200
    assert response.json()["id"] == run.id
    assert response.json()["jobs_retrieved"] == 3
    assert_no_sensitive_fields(response.json())


def test_admin_can_list_audit_logs_with_safe_metadata_only(
    client: TestClient, db_session: Session
) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    user = create_user(db_session, email="target@example.com")
    source = create_source(db_session)
    job = create_job(db_session, source)
    resume = Resume(
        user_id=user.id,
        original_filename="resume.pdf",
        stored_filename="stored.pdf",
        file_path="/protected/stored.pdf",
        file_hash="hash",
        mime_type="application/pdf",
        file_size_bytes=100,
        upload_status="STORED",
    )
    db_session.add(resume)
    db_session.flush()
    db_session.add(
        ResumeExtraction(
            resume_id=resume.id,
            extracted_text="raw-resume-secret",
            processing_status="COMPLETED",
        )
    )
    db_session.add(
        CoverLetter(
            user_id=user.id,
            job_id=job.id,
            resume_id=resume.id,
            generated_text="cover-letter-secret",
        )
    )
    create_audit_log(
        db_session,
        event_type="cover_letter.generate",
        outcome=AuditOutcome.SUCCESS,
        user_id=user.id,
        target_type="job_posting",
        target_id=job.id,
        details={
            "token": "raw-token-secret",
            "password_hash": user.password_hash,
            "prompt": "metadata only",
            "result": "draft_created",
        },
    )
    db_session.commit()
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.get("/admin/audit-logs?event_type=cover_letter.generate&outcome=SUCCESS")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["details_json"] == {"result": "draft_created"}
    assert_no_sensitive_fields(body)


def test_admin_audit_logs_exclude_risk_engine_admin_events(
    client: TestClient, db_session: Session
) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    app_log = AuditLog(
        event_type="admin.user.update",
        outcome=AuditOutcome.SUCCESS.value,
        user_id=admin.id,
        target_type="user",
        target_id=admin.id,
    )
    risk_log = AuditLog(
        event_type="risk_engine.config_update",
        outcome=AuditOutcome.SUCCESS.value,
        user_id=admin.id,
        target_type="risk_config",
    )
    risk_assessment_log = AuditLog(
        event_type="auth.risk_engine_assessment",
        outcome=AuditOutcome.SUCCESS.value,
        user_id=admin.id,
        target_type="user",
        target_id=admin.id,
    )
    db_session.add_all([app_log, risk_log, risk_assessment_log])
    db_session.commit()
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.get("/admin/audit-logs?event_type=admin.user.update")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["event_type"] for item in body["items"]] == ["admin.user.update"]

    risk_response = client.get("/admin/audit-logs?event_type=risk_engine.config_update")
    assert risk_response.status_code == 200
    assert risk_response.json()["total"] == 0

    risk_assessment_response = client.get("/admin/audit-logs?event_type=auth.risk_engine_assessment")
    assert risk_assessment_response.status_code == 200
    assert risk_assessment_response.json()["total"] == 0


def test_admin_audit_log_date_filters(client: TestClient, db_session: Session) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    old_log = AuditLog(
        event_type="old.event",
        outcome=AuditOutcome.SUCCESS.value,
        created_at=datetime.now(UTC) - timedelta(days=3),
    )
    new_log = AuditLog(
        event_type="auth.logout",
        outcome=AuditOutcome.SUCCESS.value,
        created_at=datetime.now(UTC),
    )
    db_session.add_all([old_log, new_log])
    db_session.commit()
    login(client, email=admin.email, password=ADMIN_PASSWORD)
    created_from = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    response = client.get("/admin/audit-logs", params={"created_from": created_from})

    assert response.status_code == 200
    body = response.json()
    event_types = {item["event_type"] for item in body["items"]}
    assert "auth.logout" in event_types
    assert "old.event" not in event_types


def test_admin_health_returns_safe_dependency_statuses(client: TestClient, db_session: Session) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.get("/admin/health")

    assert response.status_code == 200
    body = response.json()
    assert body["database"]["status"] in {"ok", "unavailable"}
    assert body["redis"]["status"] in {"ok", "unavailable"}
    assert body["worker"]["status"] in {"ok", "unavailable"}
    assert_no_sensitive_fields(body)


def test_stale_admin_session_is_rejected_and_audited(client: TestClient, db_session: Session) -> None:
    settings = get_settings()
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    admin.totp_enabled = True
    admin.totp_confirmed_at = datetime.now(UTC)
    token = "stale-admin-session-token"
    db_session.add(
        UserSession(
            user_id=admin.id,
            session_token_hash=hash_token(token, settings.session_secret),
            created_at=datetime.now(UTC) - timedelta(minutes=settings.admin_session_max_age_minutes + 1),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db_session.commit()
    client.cookies.set(settings.session_cookie_name, token)

    response = client.get("/admin/health")

    assert response.status_code == 401
    assert response.json() == {"detail": "Admin authentication required."}
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "authorization.denied"))
    assert audit is not None
    assert audit.details_json == {"reason": "admin_recent_session_required"}


@pytest.mark.parametrize(
    "path",
    [
        "/admin/users?page=0",
        "/admin/jobs?page_size=500",
        "/admin/scraping-runs?status=INVALID",
        "/admin/audit-logs?user_id=-1",
        "/admin/audit-logs?created_from=2026-01-02T00:00:00Z&created_to=2026-01-01T00:00:00Z",
    ],
)
def test_admin_list_endpoint_pagination_and_filters_are_validated(
    client: TestClient, db_session: Session, path: str
) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.get(path)

    assert response.status_code == 422
    assert_no_sensitive_fields(response.json())

def test_admin_can_disable_job_source_with_audit(
    client: TestClient,
    db_session: Session,
) -> None:
    admin = create_user(db_session, email="admin@example.com", role=UserRole.ADMIN)
    source = create_source(db_session)

    login(client, email=admin.email, password=ADMIN_PASSWORD)

    response = client.patch(
        f"/admin/job-sources/{source.id}",
        json={"is_enabled": False},
    )

    assert response.status_code == 200
    assert response.json()["is_enabled"] is False

    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "admin.job_source.update"))
    assert audit is not None
    assert audit.outcome == "SUCCESS"
