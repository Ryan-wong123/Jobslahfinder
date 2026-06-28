from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.rate_limit import AUTH_RATE_LIMITER
from app.main import app
from app.models.account import PasswordResetToken, Session as UserSession, User, UserProfile
from app.models.audit import AuditLog
from app.models.resume import Resume, ResumeExtraction
from app.services import resumes as resume_service
from app.services.resumes import GEMINI_RESUME_SCHEMA
from app.services.resumes import run_resume_extraction
from app.security.passwords import hash_password


USER_PASSWORD = "StrongPass123"
PDF_CONTENT = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        User.__table__,
        UserProfile.__table__,
        UserSession.__table__,
        PasswordResetToken.__table__,
        AuditLog.__table__,
        Resume.__table__,
        ResumeExtraction.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine, tables=tables)
        engine.dispose()


@pytest.fixture()
def client(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> Generator[TestClient, None, None]:
    AUTH_RATE_LIMITER.clear()
    upload_dir = Path(__file__).resolve().parent / "upload_tmp"
    for existing_file in upload_dir.glob("*"):
        if existing_file.name != ".gitkeep":
            existing_file.unlink(missing_ok=True)
    monkeypatch.setattr(get_settings(), "upload_dir", upload_dir)
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 1024 * 1024)
    monkeypatch.setattr(get_settings(), "app_env", "test")
    monkeypatch.setattr(get_settings(), "resume_extraction_provider", "local")

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    AUTH_RATE_LIMITER.clear()
    for existing_file in upload_dir.glob("*"):
        if existing_file.name != ".gitkeep":
            existing_file.unlink(missing_ok=True)


def create_user(db_session: Session, *, email: str) -> User:
    user = User(
        email=email,
        password_hash=hash_password(USER_PASSWORD),
        role="USER",
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


def docx_content(text: str = "") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr(
            "word/document.xml",
            (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
            ),
        )
    return buffer.getvalue()


def upload(
    client: TestClient,
    *,
    filename: str = "resume.pdf",
    content: bytes = PDF_CONTENT,
    mime_type: str = "application/pdf",
):
    return client.post("/resumes", files={"file": (filename, content, mime_type)})


def test_valid_pdf_upload_creates_resume_and_pending_extraction(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="user@example.com")
    login(client, email="user@example.com")

    response = upload(client)

    assert response.status_code == 201
    body = response.json()
    assert body["original_filename"] == "resume.pdf"
    assert body["mime_type"] == "application/pdf"
    assert body["file_size_bytes"] == len(PDF_CONTENT)
    assert body["upload_status"] == "STORED"
    assert "file_path" not in body
    assert "stored_filename" not in body

    resume = db_session.scalar(select(Resume))
    assert resume is not None
    assert resume.stored_filename != "resume.pdf"
    assert Path(resume.file_path).is_file()
    assert get_settings().upload_dir in Path(resume.file_path).parents

    extraction = db_session.scalar(select(ResumeExtraction))
    assert extraction is not None
    assert extraction.resume_id == resume.id
    assert extraction.processing_status == "PENDING"


def test_valid_docx_upload_is_accepted(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="user@example.com")
    login(client, email="user@example.com")

    response = upload(
        client,
        filename="resume.docx",
        content=docx_content(),
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert response.status_code == 201
    assert response.json()["mime_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.mark.parametrize(
    ("filename", "content", "mime_type"),
    [
        ("resume.txt", PDF_CONTENT, "application/pdf"),
        ("resume.pdf", PDF_CONTENT, "text/plain"),
        ("resume.pdf", b"not a pdf", "application/pdf"),
        ("resume.pdf", b"", "application/pdf"),
        ("../resume.pdf", PDF_CONTENT, "application/pdf"),
    ],
)
def test_invalid_uploads_are_rejected_with_safe_error(
    client: TestClient,
    db_session: Session,
    filename: str,
    content: bytes,
    mime_type: str,
) -> None:
    create_user(db_session, email="user@example.com")
    login(client, email="user@example.com")

    response = upload(client, filename=filename, content=content, mime_type=mime_type)

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Unable to upload resume. Please provide a valid PDF or DOCX file."
    }
    assert db_session.scalar(select(Resume)) is None


def test_oversized_upload_is_rejected(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 10)
    create_user(db_session, email="user@example.com")
    login(client, email="user@example.com")

    response = upload(client, content=PDF_CONTENT)

    assert response.status_code == 400
    assert db_session.scalar(select(Resume)) is None


def test_unauthenticated_resume_access_is_blocked(client: TestClient) -> None:
    assert client.get("/resumes").status_code == 401
    assert upload(client).status_code == 401
    assert client.get("/resumes/1").status_code == 401
    assert client.get("/resumes/1/extraction").status_code == 401
    assert client.delete("/resumes/1").status_code == 401


def test_resume_ownership_isolated_and_denial_is_audited(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="owner@example.com")
    create_user(db_session, email="other@example.com")
    login(client, email="owner@example.com")
    created = upload(client)
    assert created.status_code == 201
    resume_id = created.json()["id"]
    client.post("/auth/logout")

    login(client, email="other@example.com")
    detail = client.get(f"/resumes/{resume_id}")
    extraction = client.get(f"/resumes/{resume_id}/extraction")
    delete_response = client.delete(f"/resumes/{resume_id}")

    assert detail.status_code == 404
    assert extraction.status_code == 404
    assert delete_response.status_code == 404
    audits = db_session.scalars(
        select(AuditLog).where(AuditLog.event_type == "authorization.denied")
    ).all()
    assert audits
    assert all(audit.details_json == {"reason": "resume_owner_required"} for audit in audits)


def test_delete_resume_removes_file_and_records_audit(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="user@example.com")
    login(client, email="user@example.com")
    created = upload(client)
    resume_id = created.json()["id"]
    resume = db_session.get(Resume, resume_id)
    assert resume is not None
    stored_path = Path(resume.file_path)

    response = client.delete(f"/resumes/{resume_id}")

    assert response.status_code == 200
    assert response.json() == {"message": "Resume deleted."}
    assert db_session.get(Resume, resume_id) is None
    assert not stored_path.exists()
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "resume.delete"))
    assert audit is not None
    assert audit.outcome == "SUCCESS"


def test_upload_audit_logging_omits_file_contents(
    client: TestClient, db_session: Session
) -> None:
    sensitive_content = b"%PDF-1.4\nsecret-resume-content\n%%EOF\n"
    create_user(db_session, email="user@example.com")
    login(client, email="user@example.com")

    response = upload(client, content=sensitive_content)

    assert response.status_code == 201
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "resume.upload"))
    assert audit is not None
    assert audit.outcome == "SUCCESS"
    details = str(audit.details_json)
    assert "secret-resume-content" not in details
    assert "resume.pdf" not in details
    assert "file_hash" in audit.details_json


def test_extraction_worker_stores_structured_data_and_safe_audit(
    client: TestClient, db_session: Session
) -> None:
    content = docx_content(
        "Python developer with 6 years experience. Bachelor of Computing at Singapore University."
    )
    create_user(db_session, email="user@example.com")
    login(client, email="user@example.com")
    created = upload(
        client,
        filename="resume.docx",
        content=content,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    resume_id = created.json()["id"]

    result = run_resume_extraction(db_session, resume_id=resume_id)

    assert result == {"status": "completed", "resume_id": resume_id}
    extraction = db_session.scalar(select(ResumeExtraction).where(ResumeExtraction.resume_id == resume_id))
    assert extraction is not None
    assert extraction.processing_status == "COMPLETED"
    assert "python" in extraction.skills_json["items"]
    assert extraction.education_json["items"]
    assert extraction.experience_json["items"]
    assert float(extraction.years_experience) == 6.0
    assert extraction.extracted_text is None
    audit = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.event_type == "resume.extraction", AuditLog.outcome == "SUCCESS")
        .order_by(AuditLog.id.desc())
    )
    assert audit is not None
    details = str(audit.details_json)
    assert "Singapore University" not in details
    assert audit.details_json["skills_count"] >= 1


def test_extraction_worker_uses_gemini_flash_lite_when_configured(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = docx_content("Python developer with 6 years experience.")
    create_user(db_session, email="user@example.com")
    login(client, email="user@example.com")
    created = upload(
        client,
        filename="resume.docx",
        content=content,
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    resume_id = created.json()["id"]
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "resume_extraction_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-gemini-key"))
    monkeypatch.setattr(settings, "gemini_resume_model", "gemini-2.5-flash-lite")
    called: dict[str, object] = {}

    def fake_gemini_parser(content: bytes, extension: str, settings_arg):
        called["extension"] = extension
        called["model"] = settings_arg.gemini_resume_model
        assert b"test-gemini-key" not in content
        return {
            "skills": ["Python"],
            "experience": [{"title": "Developer", "years": 6}],
            "education": [],
            "years_experience": 6,
        }

    monkeypatch.setattr(resume_service, "parse_resume_with_gemini_timeout", fake_gemini_parser)

    result = run_resume_extraction(db_session, resume_id=resume_id, settings=settings)

    assert result == {"status": "completed", "resume_id": resume_id}
    assert called == {"extension": ".docx", "model": "gemini-2.5-flash-lite"}
    extraction = db_session.scalar(select(ResumeExtraction).where(ResumeExtraction.resume_id == resume_id))
    assert extraction is not None
    assert extraction.skills_json == {"items": ["Python"]}


def test_gemini_resume_schema_leaves_limits_to_backend_validation() -> None:
    schema_text = str(GEMINI_RESUME_SCHEMA)

    assert "maxItems" not in schema_text
    assert GEMINI_RESUME_SCHEMA["required"] == [
        "skills",
        "experience",
        "education",
        "years_experience",
    ]


def test_extraction_failure_handling_is_safe_and_audited(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="user@example.com")
    login(client, email="user@example.com")
    created = upload(client)
    resume_id = created.json()["id"]
    resume = db_session.get(Resume, resume_id)
    assert resume is not None
    Path(resume.file_path).write_bytes(b"not a valid pdf containing secret-resume-content")

    result = run_resume_extraction(db_session, resume_id=resume_id)

    assert result == {"status": "failed", "resume_id": resume_id}
    extraction = db_session.scalar(select(ResumeExtraction).where(ResumeExtraction.resume_id == resume_id))
    assert extraction is not None
    assert extraction.processing_status == "FAILED"
    audit = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.event_type == "resume.extraction", AuditLog.outcome == "FAILURE")
        .order_by(AuditLog.id.desc())
    )
    assert audit is not None
    assert audit.details_json == {"reason": "parser_failed"}
    assert "secret-resume-content" not in str(audit.details_json)


def test_view_and_edit_extracted_profile_with_audit(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="user@example.com")
    login(client, email="user@example.com")
    created = upload(client)
    resume_id = created.json()["id"]

    view_response = client.get(f"/resumes/{resume_id}/extraction")
    assert view_response.status_code == 200
    assert view_response.json()["skills"] == []

    edit_response = client.patch(
        f"/resumes/{resume_id}/extraction",
        json={
            "skills": ["Python", "python", "FastAPI"],
            "experience": [{"title": "Developer", "company": "Acme", "years": 3}],
            "education": [{"institution": "NUS", "credential": "Degree", "year": 2022}],
            "years_experience": 3,
        },
    )

    assert edit_response.status_code == 200
    body = edit_response.json()
    assert body["skills"] == ["Python", "FastAPI"]
    assert body["experience"][0]["title"] == "Developer"
    assert body["education"][0]["institution"] == "NUS"
    assert body["years_experience"] == 3.0
    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "resume.extraction.update"))
    assert audit is not None
    assert audit.outcome == "SUCCESS"
    assert audit.details_json["skills_count"] == 2
    assert "Developer" not in str(audit.details_json)


def test_extracted_profile_edit_requires_ownership(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="owner@example.com")
    create_user(db_session, email="other@example.com")
    login(client, email="owner@example.com")
    created = upload(client)
    resume_id = created.json()["id"]
    client.post("/auth/logout")
    login(client, email="other@example.com")

    response = client.patch(
        f"/resumes/{resume_id}/extraction",
        json={"skills": ["Python"], "experience": [], "education": [], "years_experience": 1},
    )

    assert response.status_code == 404
    audit = db_session.scalar(
        select(AuditLog)
        .where(AuditLog.event_type == "authorization.denied")
        .order_by(AuditLog.id.desc())
    )
    assert audit is not None
    assert audit.details_json == {"reason": "resume_owner_required"}


@pytest.mark.parametrize(
    "payload",
    [
        {"skills": ["x" * 81], "experience": [], "education": [], "years_experience": 1},
        {"skills": [], "experience": [{"title": "x" * 121}], "education": [], "years_experience": 1},
        {"skills": [], "experience": [], "education": [{"year": 1800}], "years_experience": 1},
        {"skills": [], "experience": [], "education": [], "years_experience": 100},
        {
            "skills": [],
            "experience": [],
            "education": [],
            "years_experience": 1,
            "unexpected": "blocked",
        },
    ],
)
def test_extracted_profile_edit_validation(client: TestClient, db_session: Session, payload: dict) -> None:
    create_user(db_session, email="user@example.com")
    login(client, email="user@example.com")
    created = upload(client)
    resume_id = created.json()["id"]

    response = client.patch(f"/resumes/{resume_id}/extraction", json=payload)

    assert response.status_code == 422
