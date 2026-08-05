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
from app.models.activity import SavedJob
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.models.job import JobPosting, JobSource
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


def create_source(db_session: Session, *, name: str = "JobStreet") -> JobSource:
    base_url = "https://sg.jobstreet.com"
    if name == "MyCareersFuture":
        base_url = "https://www.mycareersfuture.gov.sg"
    source = JobSource(source_name=name, base_url=base_url, is_enabled=True)
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def create_job(
    db_session: Session,
    source: JobSource,
    *,
    title: str,
    company: str = "Secure Co",
    location: str = "Singapore",
    category: str = "Security",
    description: str = "Build secure systems.",
    job_url: str | None = None,
    salary_min: float | None = None,
    salary_max: float | None = None,
    salary_period: str | None = None,
    is_active: bool = True,
    is_suspicious: bool = False,
) -> JobPosting:
    hostname = "sg.jobstreet.com"
    if source.source_name == "MyCareersFuture":
        hostname = "www.mycareersfuture.gov.sg"
    job = JobPosting(
        source_id=source.id,
        external_job_id=f"{title}-{company}",
        title=title,
        company=company,
        location=location,
        category=category,
        description=description,
        job_url=job_url or f"https://{hostname}/job/{title.lower().replace(' ', '-')}",
        posting_date=date(2026, 4, 30),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency="SGD" if salary_min is not None or salary_max is not None else None,
        salary_period=salary_period,
        is_active=is_active,
        is_suspicious=is_suspicious,
        content_hash=f"hash-{title}-{company}",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def test_job_search_filters_and_public_visibility(client: TestClient, db_session: Session) -> None:
    jobstreet = create_source(db_session)
    mcf = create_source(db_session, name="MyCareersFuture")
    create_job(
        db_session,
        jobstreet,
        title="Security Engineer",
        company="Alpha",
        location="Singapore",
        category="Cybersecurity",
    )
    create_job(
        db_session,
        mcf,
        title="Data Analyst",
        company="Beta",
        location="Jurong",
        category="Analytics",
    )
    inactive = create_job(
        db_session,
        jobstreet,
        title="Inactive Security Engineer",
        company="Alpha",
        is_active=False,
    )

    search_response = client.get("/jobs", params={"keyword": "security"})
    assert search_response.status_code == 200
    search_body = search_response.json()
    assert search_body["total"] == 1
    assert search_body["items"][0]["title"] == "Security Engineer"

    filter_response = client.get(
        "/jobs",
        params={
            "company": "Beta",
            "location": "Jurong",
            "category": "Analytics",
            "source": "MyCareersFuture",
        },
    )
    assert filter_response.status_code == 200
    filter_body = filter_response.json()
    assert filter_body["total"] == 1
    assert filter_body["items"][0]["source"]["source_name"] == "MyCareersFuture"

    default_response = client.get("/jobs")
    assert default_response.status_code == 200
    default_ids = {item["id"] for item in default_response.json()["items"]}
    assert inactive.id not in default_ids

    include_inactive_response = client.get("/jobs", params={"active_only": "false"})
    assert include_inactive_response.status_code == 200
    include_inactive_ids = {item["id"] for item in include_inactive_response.json()["items"]}
    assert inactive.id not in include_inactive_ids


def test_pagination_limits_are_enforced(client: TestClient, db_session: Session) -> None:
    source = create_source(db_session)
    for index in range(3):
        create_job(db_session, source, title=f"Security Engineer {index}")

    response = client.get("/jobs", params={"page": 2, "page_size": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["page_size"] == 1
    assert body["total"] == 3
    assert len(body["items"]) == 1

    oversized = client.get("/jobs", params={"page_size": 51})
    assert oversized.status_code == 422


def test_salary_trends_use_monthly_salary_samples(client: TestClient, db_session: Session) -> None:
    source = create_source(db_session)
    create_job(
        db_session,
        source,
        title="Software Engineer",
        salary_min=5000,
        salary_max=7000,
        salary_period="month",
    )
    create_job(
        db_session,
        source,
        title="Software Engineer Contract",
        salary_min=120000,
        salary_max=120000,
        salary_period="year",
    )

    response = client.get("/salary-trends", params={"role": "Software Engineer", "months": 12})

    assert response.status_code == 200
    body = response.json()
    assert body["sample_size"] == 2
    assert body["points"] == [{"period": "2026-04", "average_salary": 8000.0, "sample_count": 2}]


def test_salary_comparison_returns_two_to_four_role_trends(
    client: TestClient,
    db_session: Session,
) -> None:
    source = create_source(db_session)
    create_job(
        db_session,
        source,
        title="Software Engineer",
        salary_min=5000,
        salary_max=7000,
        salary_period="month",
    )
    create_job(
        db_session,
        source,
        title="Data Analyst",
        salary_min=72000,
        salary_max=72000,
        salary_period="year",
    )

    response = client.get(
        "/jobs/salary-comparison",
        params=[("roles", " Software Engineer "), ("roles", "Data Analyst"), ("months", "6")],
    )

    assert response.status_code == 200
    assert response.json() == {
        "comparisons": [
            {
                "role": "Software Engineer",
                "currency": "SGD",
                "period": "month",
                "points": [{"period": "2026-04", "average_salary": 6000.0, "sample_count": 1}],
                "sample_size": 1,
            },
            {
                "role": "Data Analyst",
                "currency": "SGD",
                "period": "month",
                "points": [{"period": "2026-04", "average_salary": 6000.0, "sample_count": 1}],
                "sample_size": 1,
            },
        ],
        "months": 6,
    }


def test_salary_comparison_validates_role_count_and_unique_safe_roles(client: TestClient) -> None:
    assert client.get("/jobs/salary-comparison", params={"roles": "Software Engineer"}).status_code == 422
    assert (
        client.get(
            "/jobs/salary-comparison",
            params=[("roles", "Software Engineer"), ("roles", "software engineer")],
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/jobs/salary-comparison",
            params=[("roles", "Software Engineer"), ("roles", "<script>alert(1)</script>")],
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/jobs/salary-comparison",
            params=[("roles", f"Role {index}") for index in range(5)],
        ).status_code
        == 422
    )


def test_job_role_catalog_and_detail_are_derived_from_visible_jobs(client: TestClient, db_session: Session) -> None:
    source = create_source(db_session)
    create_job(
        db_session,
        source,
        title="Software Developer",
        salary_min=4000,
        salary_max=6000,
        salary_period="month",
    )

    list_response = client.get("/job-roles")

    assert list_response.status_code == 200
    role = list_response.json()["items"][0]
    assert role["slug"] == "software-engineer"
    assert role["name"] == "Software Engineer"
    assert role["job_count"] == 1
    assert role["typical_monthly_salary"] == 5000.0

    response = client.get("/job-roles/software-engineer")
    assert response.status_code == 200
    body = response.json()
    assert body["job_count"] == 1
    assert body["typical_monthly_salary"] == 5000.0
    assert body["salary_points"] == [{"period": "2026-04", "average_salary": 5000.0, "sample_count": 1}]
    assert body["latest_jobs"][0]["title"] == "Software Developer"


def test_public_jobs_never_include_suspicious_jobs_even_when_requested(
    client: TestClient,
    db_session: Session,
) -> None:
    source = create_source(db_session)
    suspicious = create_job(
        db_session,
        source,
        title="Suspicious Job",
        description="<script>alert(1)</script>",
        is_suspicious=True,
    )

    default_response = client.get("/jobs")
    assert default_response.status_code == 200
    assert suspicious.id not in {item["id"] for item in default_response.json()["items"]}

    included_response = client.get("/jobs", params={"include_suspicious": "true"})
    assert included_response.status_code == 200
    assert suspicious.id not in {item["id"] for item in included_response.json()["items"]}


def test_public_jobs_never_include_inactive_or_suspicious_jobs_with_query_flags(
    client: TestClient,
    db_session: Session,
) -> None:
    source = create_source(db_session)
    visible = create_job(db_session, source, title="Visible Security Job")
    inactive = create_job(db_session, source, title="Inactive Security Job", is_active=False)
    suspicious = create_job(db_session, source, title="Suspicious Security Job", is_suspicious=True)
    inactive_suspicious = create_job(
        db_session,
        source,
        title="Inactive Suspicious Security Job",
        is_active=False,
        is_suspicious=True,
    )

    response = client.get(
        "/jobs",
        params={
            "keyword": "Security",
            "active_only": "false",
            "include_suspicious": "true",
            "is_active": "false",
            "is_suspicious": "true",
        },
    )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["items"]}
    assert visible.id in ids
    assert inactive.id not in ids
    assert suspicious.id not in ids
    assert inactive_suspicious.id not in ids


def test_job_detail_uses_safe_404_for_missing_inactive_suspicious_and_invalid_links(
    client: TestClient,
    db_session: Session,
) -> None:
    source = create_source(db_session)
    visible = create_job(db_session, source, title="Visible Job")
    inactive = create_job(db_session, source, title="Inactive Job", is_active=False)
    suspicious = create_job(db_session, source, title="Suspicious Job", is_suspicious=True)
    invalid_url = create_job(
        db_session,
        source,
        title="Invalid Link Job",
        job_url="https://evil.example.com/job",
    )

    ok_response = client.get(f"/jobs/{visible.id}")
    assert ok_response.status_code == 200
    assert ok_response.json()["job_url"].startswith("https://sg.jobstreet.com/")

    for job in (inactive, suspicious, invalid_url):
        response = client.get(f"/jobs/{job.id}")
        assert response.status_code == 404
        assert response.json() == {"detail": "Resource not found."}

    missing = client.get("/jobs/999999")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Resource not found."}


def test_xss_payloads_are_not_returned_as_renderable_html(
    client: TestClient,
    db_session: Session,
) -> None:
    source = create_source(db_session)
    job = create_job(
        db_session,
        source,
        title="<img src=x onerror=alert(1)>Security Engineer",
        company="<b>Company</b>",
        description="<script>alert(1)</script><p>Protect platforms.</p>",
    )

    response = client.get(f"/jobs/{job.id}")
    assert response.status_code == 200
    body = response.json()
    assert "<script>" not in body["description"]
    assert "<p>" not in body["description"]
    assert "Protect platforms." in body["description"]
    assert "<img" not in body["title"]
    assert "<b>" not in body["company"]


def test_save_unsave_and_audit_logging(client: TestClient, db_session: Session) -> None:
    source = create_source(db_session)
    user = create_user(db_session, email="user@example.com")
    job = create_job(db_session, source, title="Security Engineer")
    login(client, email=user.email)

    save_response = client.post(f"/jobs/{job.id}/save")
    assert save_response.status_code == 201
    assert save_response.json()["job"]["id"] == job.id
    assert db_session.get(SavedJob, {"user_id": user.id, "job_id": job.id}) is not None

    saved_response = client.get("/saved-jobs")
    assert saved_response.status_code == 200
    assert saved_response.json()["total"] == 1
    assert saved_response.json()["items"][0]["job"]["id"] == job.id

    unsave_response = client.delete(f"/jobs/{job.id}/save")
    assert unsave_response.status_code == 200
    assert db_session.get(SavedJob, {"user_id": user.id, "job_id": job.id}) is None

    audit_events = [row.event_type for row in db_session.scalars(select(AuditLog)).all()]
    assert "saved_job.save" in audit_events
    assert "saved_job.unsave" in audit_events


def test_saved_jobs_are_isolated_by_owner(client: TestClient, db_session: Session) -> None:
    source = create_source(db_session)
    owner = create_user(db_session, email="owner@example.com")
    other = create_user(db_session, email="other@example.com")
    owner_job = create_job(db_session, source, title="Owner Job")
    other_job = create_job(db_session, source, title="Other Job")
    db_session.add(SavedJob(user_id=owner.id, job_id=owner_job.id))
    db_session.add(SavedJob(user_id=other.id, job_id=other_job.id))
    db_session.commit()

    login(client, email=owner.email)
    response = client.get("/saved-jobs")

    assert response.status_code == 200
    saved_ids = {item["job"]["id"] for item in response.json()["items"]}
    assert saved_ids == {owner_job.id}

    unsave_other = client.delete(f"/jobs/{other_job.id}/save")
    assert unsave_other.status_code == 404
    assert db_session.get(SavedJob, {"user_id": other.id, "job_id": other_job.id}) is not None


def test_unauthenticated_saved_job_access_is_blocked(
    client: TestClient,
    db_session: Session,
) -> None:
    source = create_source(db_session)
    job = create_job(db_session, source, title="Security Engineer")

    assert client.get("/saved-jobs").status_code == 401
    assert client.post(f"/jobs/{job.id}/save").status_code == 401
    assert client.delete(f"/jobs/{job.id}/save").status_code == 401

def test_salary_trends_groups_active_safe_monthly_salary_data(
    client: TestClient,
    db_session: Session,
) -> None:
    source = create_source(db_session)

    create_job(
        db_session,
        source,
        title="Security Engineer",
        company="Secure Co A",
        salary_min=4000,
        salary_max=6000,
        salary_period="month",
    )
    create_job(
        db_session,
        source,
        title="Security Engineer",
        company="Secure Co B",
        salary_min=5000,
        salary_max=7000,
        salary_period="month",
    )
    create_job(
        db_session,
        source,
        title="Security Engineer",
        company="Suspicious Co",
        salary_min=9000,
        salary_max=11000,
        salary_period="month",
        is_suspicious=True,
    )

    response = client.get("/salary-trends?role=Security%20Engineer&months=12")

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "Security Engineer"
    assert body["currency"] == "SGD"
    assert body["period"] == "month"
    assert body["sample_size"] == 2
    assert body["points"][0]["average_salary"] == 5500
