from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import hashlib
from pathlib import Path
import re
import uuid
from zipfile import BadZipFile, ZipFile

from fastapi import Request, UploadFile
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.account import User
from app.models.enums import AuditOutcome, ProcessingStatus, UploadStatus
from app.models.resume import Resume, ResumeExtraction
from app.schemas.resumes import ResumeExtractionResponse, ResumeListResponse, ResumeResponse
from app.security.auth import log_authorization_denied
from app.services.audit import create_audit_log


ALLOWED_EXTENSIONS = {".pdf", ".docx"}
ALLOWED_MIME_TYPES = {
    ".pdf": {"application/pdf"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
}
SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._() \-]{0,254}$")
GENERIC_UPLOAD_ERROR = "Unable to upload resume. Please provide a valid PDF or DOCX file."


class ResumeValidationError(ValueError):
    def __init__(self, reason: str) -> None:
        super().__init__(GENERIC_UPLOAD_ERROR)
        self.reason = reason


class ResumeNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedResumeFile:
    original_filename: str
    extension: str
    mime_type: str
    content: bytes
    file_size_bytes: int
    file_hash: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_original_filename(filename: str | None) -> tuple[str, str]:
    if not filename:
        raise ResumeValidationError("missing_filename")
    cleaned = filename.strip()
    if len(cleaned) > 255 or "\x00" in cleaned:
        raise ResumeValidationError("unsafe_filename")
    if "/" in cleaned or "\\" in cleaned or cleaned in {".", ".."} or ".." in Path(cleaned).parts:
        raise ResumeValidationError("path_traversal_filename")
    if not SAFE_FILENAME_PATTERN.fullmatch(cleaned):
        raise ResumeValidationError("unsafe_filename")

    extension = Path(cleaned).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ResumeValidationError("unsupported_extension")
    return cleaned, extension


def validate_mime_type(extension: str, mime_type: str | None) -> str:
    normalized = (mime_type or "").strip().lower()
    if normalized not in ALLOWED_MIME_TYPES[extension]:
        raise ResumeValidationError("unsupported_mime_type")
    return normalized


def validate_pdf_signature(content: bytes) -> None:
    if not content.startswith(b"%PDF-"):
        raise ResumeValidationError("invalid_file_signature")


def validate_docx_structure(content: bytes) -> None:
    try:
        with ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise ResumeValidationError("invalid_file_signature")
    except (BadZipFile, OSError) as exc:
        raise ResumeValidationError("invalid_file_signature") from exc


def validate_file_signature(content: bytes, extension: str) -> None:
    if extension == ".pdf":
        validate_pdf_signature(content)
        return
    if extension == ".docx":
        validate_docx_structure(content)
        return
    raise ResumeValidationError("unsupported_extension")


async def validate_upload_file(file: UploadFile, settings: Settings) -> ValidatedResumeFile:
    original_filename, extension = validate_original_filename(file.filename)
    mime_type = validate_mime_type(extension, file.content_type)

    content = await file.read(settings.max_upload_bytes + 1)
    if not content:
        raise ResumeValidationError("empty_file")
    if len(content) > settings.max_upload_bytes:
        raise ResumeValidationError("file_too_large")

    validate_file_signature(content, extension)
    return ValidatedResumeFile(
        original_filename=original_filename,
        extension=extension,
        mime_type=mime_type,
        content=content,
        file_size_bytes=len(content),
        file_hash=hashlib.sha256(content).hexdigest(),
    )


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def get_protected_storage_dir(settings: Settings) -> Path:
    storage_dir = settings.upload_dir.expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[3]
    public_roots = [
        repo_root / "frontend" / "public",
        repo_root / "frontend" / ".next",
        repo_root / "frontend" / "out",
        repo_root / "infra" / "nginx" / "html",
    ]
    if any(storage_dir == root.resolve() or is_relative_to(storage_dir, root.resolve()) for root in public_roots):
        raise RuntimeError("Resume storage is configured inside a public web directory.")
    storage_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    return storage_dir


def write_protected_file(settings: Settings, validated: ValidatedResumeFile) -> tuple[str, Path]:
    storage_dir = get_protected_storage_dir(settings)
    stored_filename = f"{uuid.uuid4().hex}{validated.extension}"
    destination = (storage_dir / stored_filename).resolve()
    if not is_relative_to(destination, storage_dir):
        raise RuntimeError("Invalid resume storage path.")
    destination.write_bytes(validated.content)
    try:
        destination.chmod(0o600)
    except OSError:
        pass
    return stored_filename, destination


def resume_to_response(resume: Resume) -> ResumeResponse:
    return ResumeResponse.model_validate(resume)


def extraction_to_response(extraction: ResumeExtraction) -> ResumeExtractionResponse:
    return ResumeExtractionResponse.model_validate(extraction)


def safe_upload_audit_details(
    *,
    reason: str | None = None,
    extension: str | None = None,
    mime_type: str | None = None,
    file_size_bytes: int | None = None,
    file_hash: str | None = None,
) -> dict[str, str | int]:
    details: dict[str, str | int] = {}
    if reason:
        details["reason"] = reason
    if extension:
        details["extension"] = extension[:20]
    if mime_type:
        details["mime_type"] = mime_type[:100]
    if file_size_bytes is not None:
        details["file_size_bytes"] = file_size_bytes
    if file_hash:
        details["file_hash"] = file_hash
    return details


def enqueue_resume_extraction(resume_id: int, settings: Settings) -> bool:
    if settings.app_env.lower() == "test":
        return False
    try:
        from app.workers.tasks import extract_resume

        extract_resume.delay(resume_id)
        return True
    except Exception:
        return False


async def create_resume_upload(
    db: Session,
    request: Request,
    *,
    user: User,
    file: UploadFile,
    settings: Settings,
) -> ResumeResponse:
    try:
        validated = await validate_upload_file(file, settings)
        stored_filename, destination = write_protected_file(settings, validated)
    except ResumeValidationError as exc:
        create_audit_log(
            db,
            event_type="resume.upload",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=user.id,
            target_type="resume",
            details=safe_upload_audit_details(
                reason=exc.reason,
                extension=Path(file.filename or "").suffix.lower() or None,
                mime_type=file.content_type,
            ),
        )
        db.commit()
        raise
    except Exception as exc:
        create_audit_log(
            db,
            event_type="resume.upload",
            outcome=AuditOutcome.FAILURE,
            request=request,
            user_id=user.id,
            target_type="resume",
            details={"reason": "storage_error"},
        )
        db.commit()
        raise ResumeValidationError("storage_error") from exc

    resume = Resume(
        user_id=user.id,
        original_filename=validated.original_filename,
        stored_filename=stored_filename,
        file_path=str(destination),
        file_hash=validated.file_hash,
        mime_type=validated.mime_type,
        file_size_bytes=validated.file_size_bytes,
        upload_status=UploadStatus.STORED.value,
    )
    extraction = ResumeExtraction(
        resume=resume,
        processing_status=ProcessingStatus.PENDING.value,
    )
    db.add(resume)
    db.add(extraction)
    try:
        db.flush()
        create_audit_log(
            db,
            event_type="resume.upload",
            outcome=AuditOutcome.SUCCESS,
            request=request,
            user_id=user.id,
            target_type="resume",
            target_id=resume.id,
            details=safe_upload_audit_details(
                extension=validated.extension,
                mime_type=validated.mime_type,
                file_size_bytes=validated.file_size_bytes,
                file_hash=validated.file_hash,
            ),
        )
        db.commit()
    except Exception:
        db.rollback()
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    db.refresh(resume)
    enqueue_resume_extraction(resume.id, settings)
    return resume_to_response(resume)


def list_resumes_for_user(db: Session, *, user_id: int) -> ResumeListResponse:
    resumes = list(
        db.scalars(
            select(Resume)
            .where(Resume.user_id == user_id, Resume.upload_status != UploadStatus.DELETED.value)
            .order_by(desc(Resume.uploaded_at), desc(Resume.id))
        ).all()
    )
    return ResumeListResponse(items=[resume_to_response(resume) for resume in resumes], total=len(resumes))


def get_resume_for_user_or_404(
    db: Session,
    request: Request | None,
    *,
    user: User,
    resume_id: int,
) -> Resume:
    resume = db.get(Resume, resume_id)
    if resume is None or resume.upload_status == UploadStatus.DELETED.value:
        raise ResumeNotFoundError("Resource not found.")
    if resume.user_id != user.id:
        log_authorization_denied(
            db,
            request,
            user=user,
            target_type="resume",
            target_id=resume_id,
            reason="resume_owner_required",
        )
        raise ResumeNotFoundError("Resource not found.")
    return resume


def get_resume_detail(db: Session, request: Request, *, user: User, resume_id: int) -> ResumeResponse:
    return resume_to_response(get_resume_for_user_or_404(db, request, user=user, resume_id=resume_id))


def get_resume_extraction(
    db: Session,
    request: Request,
    *,
    user: User,
    resume_id: int,
) -> ResumeExtractionResponse:
    resume = get_resume_for_user_or_404(db, request, user=user, resume_id=resume_id)
    extraction = db.scalar(
        select(ResumeExtraction)
        .where(ResumeExtraction.resume_id == resume.id)
        .order_by(desc(ResumeExtraction.id))
    )
    if extraction is None:
        raise ResumeNotFoundError("Resource not found.")
    return extraction_to_response(extraction)


def delete_resume_for_user(db: Session, request: Request, *, user: User, resume_id: int) -> None:
    resume = get_resume_for_user_or_404(db, request, user=user, resume_id=resume_id)
    file_path = Path(resume.file_path)
    file_deleted = False
    try:
        file_path.unlink(missing_ok=True)
        file_deleted = True
    except OSError:
        file_deleted = False

    db.delete(resume)
    create_audit_log(
        db,
        event_type="resume.delete",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user.id,
        target_type="resume",
        target_id=resume.id,
        details={"file_deleted": file_deleted},
    )
    db.commit()


def run_resume_extraction(db: Session, *, resume_id: int) -> dict[str, str | int]:
    resume = db.get(Resume, resume_id)
    if resume is None or resume.upload_status != UploadStatus.STORED.value:
        return {"status": "not_found", "resume_id": resume_id}

    extraction = db.scalar(
        select(ResumeExtraction)
        .where(ResumeExtraction.resume_id == resume.id)
        .order_by(desc(ResumeExtraction.id))
    )
    if extraction is None:
        extraction = ResumeExtraction(resume_id=resume.id)
        db.add(extraction)

    extraction.processing_status = ProcessingStatus.PROCESSING.value
    db.commit()

    try:
        content = Path(resume.file_path).read_bytes()
        validate_file_signature(content, Path(resume.stored_filename).suffix.lower())
        extraction.skills_json = {"items": []}
        extraction.experience_json = {"items": []}
        extraction.education_json = {"items": []}
        extraction.years_experience = None
        extraction.extracted_text = None
        extraction.processing_status = ProcessingStatus.COMPLETED.value
        extraction.processed_at = utc_now()
        create_audit_log(
            db,
            event_type="resume.extraction",
            outcome=AuditOutcome.SUCCESS,
            user_id=resume.user_id,
            target_type="resume",
            target_id=resume.id,
            details={"status": "completed"},
        )
        db.commit()
        return {"status": "completed", "resume_id": resume.id}
    except Exception:
        extraction.processing_status = ProcessingStatus.FAILED.value
        extraction.processed_at = utc_now()
        create_audit_log(
            db,
            event_type="resume.extraction",
            outcome=AuditOutcome.FAILURE,
            user_id=resume.user_id,
            target_type="resume",
            target_id=resume.id,
            details={"reason": "parser_failed"},
        )
        db.commit()
        return {"status": "failed", "resume_id": resume.id}
