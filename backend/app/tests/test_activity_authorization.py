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
from app.models.activity import ApplicationHistory, CoverLetter, Recommendation
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


def create_job(db_session: Session, source: JobSource, *, title: str) -> JobPosting:
    job = JobPosting(
        source_id=source.id,
        external_job_id=title,
        title=title,
        company="Secure Co",
        location="Singapore",
        category="Security",
        description="Build secure systems.",
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


def test_recommendations_are_isolated_by_owner(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    owner = create_user(db_session, email="owner@example.com")
    other = create_user(db_session, email="other@example.com")
    owner_job = create_job(db_session, source, title="Owner Recommendation")
    other_job = create_job(db_session, source, title="Other Recommendation")
    db_session.add_all(
        [
            Recommendation(
                user_id=owner.id,
                job_id=owner_job.id,
                match_score=91.50,
                rationale="Owner match",
            ),
            Recommendation(
                user_id=other.id,
                job_id=other_job.id,
                match_score=99.00,
                rationale="Other match",
            ),
        ]
    )
    db_session.commit()

    assert client.get("/recommendations").status_code == 401
    login(client, email=owner.email)

    response = client.get("/recommendations")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["job"]["id"] for item in body["items"]] == [owner_job.id]
    assert body["items"][0]["rationale"] == "Owner match"


def test_cover_letters_are_isolated_by_owner_and_denials_are_audited(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    owner = create_user(db_session, email="owner@example.com")
    other = create_user(db_session, email="other@example.com")
    owner_job = create_job(db_session, source, title="Owner Cover Letter")
    other_job = create_job(db_session, source, title="Other Cover Letter")
    owner_cover_letter = CoverLetter(
        user_id=owner.id,
        job_id=owner_job.id,
        generated_text="Owner draft",
    )
    other_cover_letter = CoverLetter(
        user_id=other.id,
        job_id=other_job.id,
        generated_text="Other draft",
    )
    db_session.add_all([owner_cover_letter, other_cover_letter])
    db_session.commit()
    db_session.refresh(owner_cover_letter)
    db_session.refresh(other_cover_letter)

    assert client.get("/cover-letters").status_code == 401
    assert client.get(f"/cover-letters/{owner_cover_letter.id}").status_code == 401
    login(client, email=owner.email)

    list_response = client.get("/cover-letters")
    detail_response = client.get(f"/cover-letters/{other_cover_letter.id}")
    patch_response = client.patch(
        f"/cover-letters/{other_cover_letter.id}",
        json={"edited_text": "Attempted overwrite"},
    )

    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["items"]] == [owner_cover_letter.id]
    assert detail_response.status_code == 404
    assert patch_response.status_code == 404
    db_session.refresh(other_cover_letter)
    assert other_cover_letter.edited_text is None

    own_patch = client.patch(
        f"/cover-letters/{owner_cover_letter.id}",
        json={"edited_text": "Owner edited draft"},
    )
    assert own_patch.status_code == 200
    assert own_patch.json()["edited_text"] == "Owner edited draft"

    denial_audits = db_session.scalars(
        select(AuditLog).where(
            AuditLog.event_type == "authorization.denied",
            AuditLog.target_type == "cover_letter",
            AuditLog.target_id == other_cover_letter.id,
        )
    ).all()
    assert len(denial_audits) == 2
    assert all(audit.details_json == {"reason": "owner_or_admin_required"} for audit in denial_audits)


def test_application_history_is_isolated_by_owner(
    client: TestClient, db_session: Session
) -> None:
    source = create_source(db_session)
    owner = create_user(db_session, email="owner@example.com")
    other = create_user(db_session, email="other@example.com")
    owner_job = create_job(db_session, source, title="Owner History")
    other_job = create_job(db_session, source, title="Other History")
    db_session.add_all(
        [
            ApplicationHistory(
                user_id=owner.id,
                job_id=owner_job.id,
                action_type="cover_letter_generated",
            ),
            ApplicationHistory(
                user_id=other.id,
                job_id=other_job.id,
                action_type="cover_letter_generated",
            ),
        ]
    )
    db_session.commit()

    assert client.get("/application-history").status_code == 401
    login(client, email=owner.email)

    response = client.get("/application-history")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["job"]["id"] for item in body["items"]] == [owner_job.id]
