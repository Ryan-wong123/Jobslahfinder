from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
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


def docx_content() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", "<w:document></w:document>")
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
