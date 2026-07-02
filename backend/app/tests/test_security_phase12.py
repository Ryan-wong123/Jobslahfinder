from collections.abc import Generator
from datetime import date, datetime
from io import BytesIO
import logging
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile
import sys

import pyotp
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.core.logging import RedactingFilter
from app.core.rate_limit import AUTH_RATE_LIMITER, get_client_ip
from app.main import app
from app.models.account import User, UserProfile
from app.models.activity import CoverLetter
from app.models.audit import AuditLog
from app.models.enums import AuditOutcome, ProcessingStatus, UploadStatus, UserRole
from app.models.job import JobPosting, JobSource
from app.models.resume import Resume, ResumeExtraction
from app.security.passwords import hash_password
from app.security.text import sanitize_required_text, sanitize_text
from app.services import activity as activity_service
from app.services.accounts import profile_to_response
from app.services.audit import (
    AUDIT_DETAIL_TRUNCATED_MARKER,
    MAX_AUDIT_DETAIL_CONTAINER_ITEMS,
    MAX_AUDIT_DETAIL_TEXT_LENGTH,
    MAX_AUDIT_USER_AGENT_LENGTH,
    create_audit_log,
)
from app.services.resumes import run_resume_extraction
from app.services.resumes import extraction_to_response


USER_PASSWORD = "StrongPass123"


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/test",
            "headers": [
                (b"user-agent", ("phase13-agent-" + "x" * 1200).encode()),
                (b"x-forwarded-for", b"203.0.113.10, 10.0.0.5"),
            ],
            "client": ("198.51.100.2", 12345),
        }
    )


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


def create_job(db_session: Session, source: JobSource, *, title: str, company: str) -> JobPosting:
    job = JobPosting(
        source_id=source.id,
        external_job_id=f"{title}-{company}",
        title=title,
        company=company,
        location="Singapore",
        category="Security",
        description="Build secure systems.",
        job_url="https://sg.jobstreet.com/job/security",
        posting_date=date(2026, 4, 30),
        is_active=True,
        is_suspicious=False,
        content_hash=f"hash-{title}-{company}",
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    return job


def docx_content(text: str) -> bytes:
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


def create_completed_extraction(
    db_session: Session,
    user: User,
    *,
    raw_resume_text: str = "raw resume text",
) -> ResumeExtraction:
    resume = Resume(
        user_id=user.id,
        original_filename="resume.pdf",
        stored_filename=f"phase12-{user.id}-resume.pdf",
        file_path=f"/tmp/phase12-{user.id}-resume.pdf",
        file_hash=f"phase12-hash-{user.id}",
        mime_type="application/pdf",
        file_size_bytes=128,
        upload_status=UploadStatus.STORED.value,
    )
    extraction = ResumeExtraction(
        resume=resume,
        extracted_text=raw_resume_text,
        skills_json={"items": ["Python", "FastAPI"]},
        experience_json={"items": [{"title": "Backend Developer", "company": "Secure Co"}]},
        education_json={"items": [{"credential": "Degree", "field": "Computer Science"}]},
        years_experience=4,
        processing_status=ProcessingStatus.COMPLETED.value,
    )
    db_session.add(resume)
    db_session.add(extraction)
    db_session.commit()
    db_session.refresh(extraction)
    return extraction


def assert_sensitive_sentinels_absent(
    *,
    sentinels: list[str],
    audits: list[AuditLog],
    log_text: str,
    stdout: str,
    stderr: str,
) -> None:
    audit_text = "\n".join(str(audit.details_json) for audit in audits)
    combined = "\n".join([audit_text, log_text, stdout, stderr])
    for sentinel in sentinels:
        assert sentinel not in combined


def test_job_search_sql_injection_payload_is_parameterized(
    client: TestClient,
    db_session: Session,
) -> None:
    source = create_source(db_session)
    create_job(db_session, source, title="Security Engineer", company="Alpha")
    create_job(db_session, source, title="Data Analyst", company="Beta")

    response = client.get("/jobs", params={"keyword": "%' OR 1=1 --"})

    assert response.status_code == 422
    assert db_session.scalar(select(JobPosting).where(JobPosting.company == "Alpha")) is not None
    assert db_session.scalar(select(JobPosting).where(JobPosting.company == "Beta")) is not None


def test_saved_job_sql_injection_path_parameter_is_rejected(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="user@example.com")
    login(client, email=user.email)

    response = client.post("/jobs/1 OR 1=1/save")

    assert response.status_code == 422
    assert db_session.scalars(select(JobPosting)).all() == []


def test_audit_details_redact_api_keys_prompts_resume_text_tokens_and_passwords(
    db_session: Session,
) -> None:
    create_audit_log(
        db_session,
        event_type="security.redaction_test",
        outcome=AuditOutcome.SUCCESS,
        details={
            "api_key": "real-api-key",
            "gemini_api_key": "real-gemini-key",
            "prompt": "full prompt with personal data",
            "resume_text": "full resume text",
            "generated_text": "cover letter body",
            "token": "raw-token",
            "password": "plaintext-password",
            "nested": {"session_token": "raw-session-token"},
            "safe_count": 3,
        },
    )
    db_session.commit()

    audit = db_session.scalar(select(AuditLog).where(AuditLog.event_type == "security.redaction_test"))

    assert audit is not None
    assert audit.details_json == {
        "api_key": "[REDACTED]",
        "gemini_api_key": "[REDACTED]",
        "prompt": "[REDACTED]",
        "resume_text": "[REDACTED]",
        "generated_text": "[REDACTED]",
        "token": "[REDACTED]",
        "password": "[REDACTED]",
        "nested": {"session_token": "[REDACTED]"},
        "safe_count": 3,
    }


def test_audit_helper_records_request_metadata_and_redacts_nested_sensitive_details(
    db_session: Session,
) -> None:
    audit = create_audit_log(
        db_session,
        event_type="phase13.audit_helper",
        outcome=AuditOutcome.SUCCESS,
        request=make_request(),
        user_id=123,
        target_type="cover_letter",
        target_id=456,
        details={
            "safe_count": 2,
            "prompt": "full prompt should not persist",
            "nested": {
                "session_token_hash": "stored-token-hash",
                "items": [{"password": "plaintext-password"}, {"safe": "kept"}],
            },
        },
    )
    db_session.commit()

    stored = db_session.scalar(select(AuditLog).where(AuditLog.id == audit.id))

    assert stored is not None
    assert stored.ip_address == "198.51.100.2"
    assert stored.user_agent is not None
    assert len(stored.user_agent) == 1024
    assert stored.details_json == {
        "safe_count": 2,
        "prompt": "[REDACTED]",
        "nested": {
            "session_token_hash": "[REDACTED]",
            "items": [{"password": "[REDACTED]"}, {"safe": "kept"}],
        },
    }


def test_client_ip_does_not_trust_forwarded_for_by_default() -> None:
    request = make_request()

    assert get_client_ip(request) == "198.51.100.2"


def test_client_ip_uses_forwarded_for_only_when_proxy_headers_and_proxy_are_trusted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = make_request()
    settings = SimpleNamespace(trust_proxy_headers=True)
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "198.51.100.2/32,10.0.0.0/8")

    assert get_client_ip(request, settings=settings) == "203.0.113.10"


def test_client_ip_ignores_forwarded_for_from_untrusted_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = make_request()
    settings = SimpleNamespace(trust_proxy_headers=True)
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "127.0.0.1/32")

    assert get_client_ip(request, settings=settings) == "198.51.100.2"


def test_audit_helper_normalizes_audit_visible_text_and_strips_controls(
    db_session: Session,
) -> None:
    audit = create_audit_log(
        db_session,
        event_type="phase12.audit_text",
        outcome=AuditOutcome.SUCCESS,
        request=make_request(),
        details={
            "message": "Ｆｕｌｌｗｉｄｔｈ\u202e value\u0000\nnext line",
            "nested": {"label": "Cafe\u0301\u200b"},
        },
    )
    db_session.commit()

    stored = db_session.scalar(select(AuditLog).where(AuditLog.id == audit.id))

    assert stored is not None
    assert "\u202e" not in stored.details_json["message"]
    assert "\u0000" not in stored.details_json["message"]
    assert stored.details_json["message"] == "Fullwidth  value \nnext line"
    assert stored.details_json["nested"]["label"] == "Café"


def test_audit_detail_keys_do_not_collapse_to_empty_strings(db_session: Session) -> None:
    audit = create_audit_log(
        db_session,
        event_type="phase13.audit_empty_key",
        outcome=AuditOutcome.SUCCESS,
        details={"\u0000": "kept"},
    )
    db_session.commit()

    stored = db_session.scalar(select(AuditLog).where(AuditLog.id == audit.id))

    assert stored is not None
    assert stored.details_json == {"detail": "kept"}


def test_audit_details_bound_nested_strings_lists_and_preserve_scalars(
    db_session: Session,
) -> None:
    long_text = "A" * (MAX_AUDIT_DETAIL_TEXT_LENGTH + 500)
    long_list = [f"item-{index}" for index in range(MAX_AUDIT_DETAIL_CONTAINER_ITEMS + 5)]

    audit = create_audit_log(
        db_session,
        event_type="phase12.audit_bounds",
        outcome=AuditOutcome.SUCCESS,
        details={
            "nested": {
                "safe_long_text": long_text,
                "list": long_list,
                "deep": [{"token": "raw-token", "safe": "kept"}],
            },
            "count": 7,
            "enabled": True,
            "ratio": 3.5,
            "missing": None,
        },
    )
    db_session.commit()

    stored = db_session.scalar(select(AuditLog).where(AuditLog.id == audit.id))

    assert stored is not None
    nested = stored.details_json["nested"]
    assert len(nested["safe_long_text"]) == MAX_AUDIT_DETAIL_TEXT_LENGTH
    assert nested["safe_long_text"] == "A" * MAX_AUDIT_DETAIL_TEXT_LENGTH
    assert len(nested["list"]) == MAX_AUDIT_DETAIL_CONTAINER_ITEMS + 1
    assert nested["list"][-1] == AUDIT_DETAIL_TRUNCATED_MARKER
    assert nested["deep"] == [{"token": "[REDACTED]", "safe": "kept"}]
    assert stored.details_json["count"] == 7
    assert stored.details_json["enabled"] is True
    assert stored.details_json["ratio"] == 3.5
    assert stored.details_json["missing"] is None


def test_audit_details_bound_nested_dicts_and_long_keys(
    db_session: Session,
) -> None:
    details = {
        "outer": {f"field-{index}": index for index in range(MAX_AUDIT_DETAIL_CONTAINER_ITEMS + 3)},
        "k" * 200: "safe",
    }

    audit = create_audit_log(
        db_session,
        event_type="phase12.audit_dict_bounds",
        outcome=AuditOutcome.SUCCESS,
        details=details,
    )
    db_session.commit()

    stored = db_session.scalar(select(AuditLog).where(AuditLog.id == audit.id))

    assert stored is not None
    outer = stored.details_json["outer"]
    assert len(outer) == MAX_AUDIT_DETAIL_CONTAINER_ITEMS + 1
    assert outer[AUDIT_DETAIL_TRUNCATED_MARKER] == "3 omitted"
    assert max(len(key) for key in stored.details_json) <= 128


def test_audit_user_agent_is_safely_truncated(
    db_session: Session,
) -> None:
    audit = create_audit_log(
        db_session,
        event_type="phase12.audit_user_agent",
        outcome=AuditOutcome.SUCCESS,
        request=make_request(),
    )
    db_session.commit()

    stored = db_session.scalar(select(AuditLog).where(AuditLog.id == audit.id))

    assert stored is not None
    assert stored.user_agent is not None
    assert len(stored.user_agent) == MAX_AUDIT_USER_AGENT_LENGTH
    assert "\n" not in stored.user_agent


def test_runtime_log_filter_redacts_secrets(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("app.tests.phase12.redaction")
    logger.addFilter(RedactingFilter())

    with caplog.at_level(logging.INFO):
        logger.info(
            "provider failure api_key=real-api-key token=raw-token",
            extra={"details": {"password": "plaintext-password"}},
        )

    output = caplog.text
    assert "real-api-key" not in output
    assert "raw-token" not in output
    assert "api_key=[REDACTED]" in output
    assert "token=[REDACTED]" in output


def test_audit_creation_redacts_resume_prompts_generated_and_edited_cover_letters(
    db_session: Session,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sentinels = [
        "PHASE12_FULL_RESUME_TEXT_SENTINEL_81f4",
        "PHASE12_AI_PROMPT_SENTINEL_7c22",
        "PHASE12_GENERATED_COVER_LETTER_SENTINEL_ba90",
        "PHASE12_EDITED_COVER_LETTER_SENTINEL_4ad1",
    ]

    with caplog.at_level(logging.INFO):
        create_audit_log(
            db_session,
            event_type="security.sensitive_logging_regression",
            outcome=AuditOutcome.SUCCESS,
            details={
                "full_resume_text": sentinels[0],
                "ai_prompt": sentinels[1],
                "generated_cover_letter": sentinels[2],
                "edited_text": sentinels[3],
                "safe_count": 4,
            },
        )
        db_session.commit()

    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.event_type == "security.sensitive_logging_regression")
    )
    stdio = capsys.readouterr()

    assert audit is not None
    assert audit.details_json == {
        "full_resume_text": "[REDACTED]",
        "ai_prompt": "[REDACTED]",
        "generated_cover_letter": "[REDACTED]",
        "edited_text": "[REDACTED]",
        "safe_count": 4,
    }
    assert_sensitive_sentinels_absent(
        sentinels=sentinels,
        audits=[audit],
        log_text=caplog.text,
        stdout=stdio.out,
        stderr=stdio.err,
    )


def test_resume_extraction_success_and_failure_do_not_log_full_resume_text(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "resume_extraction_provider", "local")
    user = create_user(db_session, email="resume-log-regression@example.com")
    success_sentinel = "PHASE12_RESUME_SUCCESS_SENTINEL_3537"
    failure_sentinel = "PHASE12_RESUME_FAILURE_SENTINEL_9712"
    success_path = tmp_path / "success.docx"
    failure_path = tmp_path / "failure.pdf"
    success_path.write_bytes(
        docx_content(
            f"{success_sentinel} Python developer with 6 years experience at Singapore University."
        )
    )
    failure_path.write_bytes(b"%PDF-1.4\n" + failure_sentinel.encode() + b"\n%%EOF\n")
    success_resume = Resume(
        user_id=user.id,
        original_filename="success.docx",
        stored_filename="success.docx",
        file_path=str(success_path),
        file_hash="phase12-success-hash",
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        file_size_bytes=success_path.stat().st_size,
        upload_status=UploadStatus.STORED.value,
    )
    failure_resume = Resume(
        user_id=user.id,
        original_filename="failure.pdf",
        stored_filename="failure.pdf",
        file_path=str(failure_path),
        file_hash="phase12-failure-hash",
        mime_type="application/pdf",
        file_size_bytes=failure_path.stat().st_size,
        upload_status=UploadStatus.STORED.value,
    )
    db_session.add_all([success_resume, failure_resume])
    db_session.commit()

    with caplog.at_level(logging.INFO):
        success_result = run_resume_extraction(db_session, resume_id=success_resume.id, settings=settings)
        failure_result = run_resume_extraction(db_session, resume_id=failure_resume.id, settings=settings)

    audits = db_session.scalars(select(AuditLog).where(AuditLog.event_type == "resume.extraction")).all()
    stdio = capsys.readouterr()

    assert success_result == {"status": "completed", "resume_id": success_resume.id}
    assert failure_result == {"status": "failed", "resume_id": failure_resume.id}
    assert len(audits) == 2
    assert {audit.outcome for audit in audits} == {AuditOutcome.SUCCESS.value, AuditOutcome.FAILURE.value}
    assert any(audit.details_json["skills_count"] >= 1 for audit in audits if audit.outcome == "SUCCESS")
    assert any(audit.details_json == {"reason": "parser_failed"} for audit in audits if audit.outcome == "FAILURE")
    assert_sensitive_sentinels_absent(
        sentinels=[success_sentinel, failure_sentinel],
        audits=audits,
        log_text=caplog.text,
        stdout=stdio.out,
        stderr=stdio.err,
    )


def test_gemini_cover_letter_prompt_construction_does_not_log_prompt_or_output(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_resume_sentinel = "PHASE12_RAW_RESUME_PROMPT_SENTINEL_6daa"
    prompt_sentinel = "PHASE12_AI_PROMPT_CONTENT_SENTINEL_24a7"
    generated_sentinel = "PHASE12_AI_GENERATED_OUTPUT_SENTINEL_62ef"
    user = create_user(db_session, email="prompt-regression@example.com")
    source = create_source(db_session)
    extraction = create_completed_extraction(db_session, user, raw_resume_text=raw_resume_sentinel)
    job = create_job(
        db_session,
        source,
        title="Prompt Safety Engineer",
        company="Secure Co",
    )
    job.description = f"Build secure APIs. {prompt_sentinel}"
    db_session.commit()
    settings = get_settings()
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-gemini-key"))
    captured: dict[str, object] = {}

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            captured["model"] = model
            captured["contents"] = contents
            captured["config"] = config
            return SimpleNamespace(text=generated_sentinel)

    class FakeClient:
        def __init__(self, *, api_key: str) -> None:
            captured["api_key"] = api_key
            self.models = FakeModels()

    fake_genai = SimpleNamespace(Client=FakeClient)
    monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

    with caplog.at_level(logging.INFO):
        generated = activity_service.generate_cover_letter_with_gemini(
            extraction=extraction,
            job=job,
            settings=settings,
        )

    stdio = capsys.readouterr()

    assert generated == generated_sentinel
    assert captured["api_key"] == "test-gemini-key"
    assert prompt_sentinel in str(captured["contents"])
    assert raw_resume_sentinel not in str(captured["contents"])
    assert "<untrusted_profile_data>" in str(captured["contents"])
    assert "<untrusted_job_data>" in str(captured["contents"])
    assert_sensitive_sentinels_absent(
        sentinels=[raw_resume_sentinel, prompt_sentinel, generated_sentinel],
        audits=[],
        log_text=caplog.text,
        stdout=stdio.out,
        stderr=stdio.err,
    )


def test_cover_letter_generation_and_editing_do_not_log_draft_texts_or_prompts(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw_resume_sentinel = "PHASE12_COVER_RAW_RESUME_SENTINEL_c64c"
    prompt_sentinel = "PHASE12_COVER_PROMPT_SENTINEL_d344"
    generated_sentinel = "PHASE12_GENERATED_DRAFT_SENTINEL_79fb"
    edited_sentinel = "PHASE12_EDITED_DRAFT_SENTINEL_0f2c"
    source = create_source(db_session)
    user = create_user(db_session, email="cover-log-regression@example.com")
    create_completed_extraction(db_session, user, raw_resume_text=raw_resume_sentinel)
    job = create_job(
        db_session,
        source,
        title="Secure Draft Engineer",
        company="Cover Co",
    )
    job.description = f"Sensitive job description used in prompt. {prompt_sentinel}"
    db_session.commit()
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "cover_letter_generation_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", SecretStr("test-gemini-key"))

    def fake_gemini(*, extraction: ResumeExtraction, job: JobPosting, settings) -> str:
        prompt_context = activity_service.cover_letter_prompt_context(extraction=extraction, job=job)
        assert prompt_sentinel in prompt_context
        assert raw_resume_sentinel not in prompt_context
        return generated_sentinel

    monkeypatch.setattr(activity_service, "generate_cover_letter_with_gemini", fake_gemini)
    login(client, email=user.email)

    with caplog.at_level(logging.INFO):
        generated_response = client.post(f"/jobs/{job.id}/cover-letter")
        assert generated_response.status_code == 201
        cover_letter_id = generated_response.json()["id"]
        edited_response = client.patch(
            f"/cover-letters/{cover_letter_id}",
            json={"edited_text": edited_sentinel},
        )

    audits = db_session.scalars(
        select(AuditLog).where(AuditLog.event_type.in_(["cover_letter.generate", "cover_letter.edit"]))
    ).all()
    stored = db_session.get(CoverLetter, cover_letter_id)
    stdio = capsys.readouterr()

    assert edited_response.status_code == 200
    assert stored is not None
    assert stored.generated_text == generated_sentinel
    assert stored.edited_text == edited_sentinel
    assert len(audits) == 2
    assert {audit.outcome for audit in audits} == {AuditOutcome.SUCCESS.value}
    assert any(
        audit.details_json.get("generator_version") == "gemini-cover-letter-v1"
        for audit in audits
    )
    assert any(audit.details_json.get("action") == "edited" for audit in audits)
    assert_sensitive_sentinels_absent(
        sentinels=[raw_resume_sentinel, prompt_sentinel, generated_sentinel, edited_sentinel],
        audits=audits,
        log_text=caplog.text,
        stdout=stdio.out,
        stderr=stdio.err,
    )


def test_frontend_sources_do_not_use_raw_html_rendering_for_untrusted_content() -> None:
    frontend_source = Path(__file__).resolve().parents[3] / "frontend" / "src"
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in frontend_source.rglob("*.tsx"))

    assert "dangerouslySetInnerHTML" not in source_text
    assert ".innerHTML" not in source_text


def test_shared_text_helper_rejects_or_strips_html_and_controls() -> None:
    assert sanitize_text(
        "  Cafe\u0301 analyst  ",
        field_name="summary",
        max_length=40,
        empty_to_none=True,
    ) == "Café analyst"

    with pytest.raises(ValueError, match="Invalid summary"):
        sanitize_text("<script>alert(1)</script>", field_name="summary", max_length=40)

    assert sanitize_required_text(
        "<b>Hello</b>\u0001 world",
        field_name="generated_text",
        max_length=40,
        html_policy="strip",
        control_policy="strip",
        collapse_whitespace=True,
    ) == "Hello world"

    with pytest.raises(ValueError, match="Invalid summary"):
        sanitize_text("x" * 41, field_name="summary", max_length=40)


def test_shared_text_helper_normalizes_nfkc_and_rejects_hidden_controls() -> None:
    assert sanitize_text(
        "  Ｓｅｃｕｒｉｔｙ analyst  ",
        field_name="summary",
        max_length=40,
        empty_to_none=True,
    ) == "Security analyst"

    with pytest.raises(ValueError, match="Invalid summary"):
        sanitize_text("safe\u0000text", field_name="summary", max_length=40)

    with pytest.raises(ValueError, match="Invalid summary"):
        sanitize_text("safe\u202etext", field_name="summary", max_length=40)

    assert sanitize_text(
        "line one\nline two\tkept",
        field_name="summary",
        max_length=40,
        empty_to_none=True,
    ) == "line one\nline two\tkept"

    with pytest.raises(ValueError, match="Invalid summary"):
        sanitize_text(
            "line one\nline two",
            field_name="summary",
            max_length=40,
            allow_multiline=False,
        )

    assert sanitize_text(
        "one\u202etwo\u0000three",
        field_name="summary",
        max_length=40,
        control_policy="strip",
        collapse_whitespace=True,
    ) == "one two three"


def test_profile_response_normalizes_legacy_text_fields() -> None:
    profile = UserProfile(
        user_id=1,
        full_name="Ｆｕｌｌ Name\u202e",
        phone="+65 1234 5678\u0000",
        location="Cafe\u0301",
        summary="line one\nline two",
        skills_json={"items": ["Ｐｙｔｈｏｎ", "Python", "Secure\u200b Coding"]},
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 2),
    )

    response = profile_to_response(profile)

    assert response.full_name == "Full Name"
    assert response.phone == "+65 1234 5678"
    assert response.location == "Café"
    assert response.summary == "line one\nline two"
    assert response.skills == ["Python", "Secure Coding"]


def test_resume_extraction_response_normalizes_legacy_json_text() -> None:
    extraction = ResumeExtraction(
        id=1,
        resume_id=2,
        processing_status=ProcessingStatus.COMPLETED.value,
        skills_json={"items": ["ＦａｓｔＡＰＩ\u202e", "SQL\u0000"]},
        experience_json={
            "items": [
                {
                    "title": "Engineer\u200b",
                    "company": "<b>Secure Co</b>",
                    "description": "line one\nline two",
                }
            ]
        },
        education_json={"items": [{"institution": "Cafe\u0301 University"}]},
    )

    response = extraction_to_response(extraction)

    assert response.skills == ["FastAPI", "SQL"]
    assert response.skills_json == {"items": ["FastAPI", "SQL"]}
    assert response.experience == [
        {
            "title": "Engineer",
            "company": "Secure Co",
            "description": "line one\nline two",
        }
    ]
    assert response.education == [{"institution": "Café University"}]
