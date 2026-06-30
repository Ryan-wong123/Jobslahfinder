from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import re
from typing import Any
from urllib.parse import urlsplit

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.models.activity import SavedJob
from app.models.enums import AuditOutcome
from app.models.job import JobPosting, JobSource
from app.schemas.jobs import (
    JobDetailResponse,
    JobListResponse,
    JobSourcePublicResponse,
    JobSummaryResponse,
    SavedJobListResponse,
    SavedJobResponse,
)
from app.security.text import sanitize_text
from app.services.application_history import add_application_history
from app.services.audit import create_audit_log


MAX_TEXT_LENGTH = 20_000
MAX_JOB_DESCRIPTION_RESPONSE_LENGTH = 20_000
MAX_JOB_FIELD_RESPONSE_LENGTH = 255
MAX_SEARCH_TERM_LENGTH = 100
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
EXTERNAL_LINK_WARNING = "You are leaving this platform for an approved external job source."
APPROVED_JOB_SOURCES = {
    "JobStreet": {
        "base_url": "https://sg.jobstreet.com",
        "domains": ("sg.jobstreet.com",),
    },
    "MyCareersFuture": {
        "base_url": "https://www.mycareersfuture.gov.sg",
        "domains": ("www.mycareersfuture.gov.sg",),
    },
}

TAG_PATTERN = re.compile(r"<[^>]+>")


class JobSourceValidationError(ValueError):
    pass


class JobValidationError(ValueError):
    pass


class JobNotFoundError(ValueError):
    pass


@dataclass(frozen=True)
class NormalizedJob:
    external_job_id: str | None
    title: str
    company: str
    location: str | None
    category: str | None
    description: str | None
    job_url: str
    posting_date: date | None
    content_hash: str
    is_suspicious: bool
    suspicious_reasons: tuple[str, ...]


def normalize_hostname(hostname: str | None) -> str | None:
    if not hostname:
        return None
    return hostname.rstrip(".").lower()


def configured_allowed_domains(settings: Settings) -> set[str]:
    return {normalize_hostname(domain) for domain in settings.allowed_job_source_domain_list if domain}


def source_allowed_domains(source_name: str) -> tuple[str, ...]:
    source = APPROVED_JOB_SOURCES.get(source_name)
    if source is None:
        return ()
    return tuple(source["domains"])


def validate_https_url(url: str) -> str:
    cleaned = url.strip()
    parsed = urlsplit(cleaned)
    hostname = normalize_hostname(parsed.hostname)
    if parsed.scheme != "https" or not hostname:
        raise JobSourceValidationError("Only HTTPS URLs with a valid host are allowed.")
    return cleaned


def is_domain_allowed(hostname: str, allowed_domains: set[str] | tuple[str, ...]) -> bool:
    normalized = normalize_hostname(hostname)
    if normalized is None:
        return False
    return normalized in set(allowed_domains)


def escape_like_term(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def validate_source_base_url(source_name: str, base_url: str, settings: Settings) -> str:
    if source_name not in APPROVED_JOB_SOURCES:
        raise JobSourceValidationError("Job source is not approved.")

    cleaned = validate_https_url(base_url)
    hostname = normalize_hostname(urlsplit(cleaned).hostname)
    configured_domains = configured_allowed_domains(settings)
    source_domains = source_allowed_domains(source_name)
    if hostname is None or hostname not in configured_domains or hostname not in source_domains:
        raise JobSourceValidationError("Job source domain is not allowed.")
    return cleaned.rstrip("/")


def validate_job_url_for_source(job_url: str, source: JobSource) -> str:
    cleaned = validate_https_url(job_url)
    hostname = normalize_hostname(urlsplit(cleaned).hostname)
    if hostname is None or not is_domain_allowed(hostname, source_allowed_domains(source.source_name)):
        raise JobValidationError("Job URL domain is not approved for the source.")
    return cleaned


def is_job_url_valid_for_source(job: JobPosting) -> bool:
    try:
        validate_job_url_for_source(job.job_url, job.source)
    except (JobSourceValidationError, JobValidationError):
        return False
    return True


def clean_text(value: Any, *, max_length: int) -> str:
    if value is None:
        return ""
    return (
        sanitize_text(
            value,
            field_name="job text",
            max_length=max_length,
            html_policy="strip",
            overflow="truncate",
            control_policy="strip",
            collapse_whitespace=True,
            empty_to_none=True,
        )
        or ""
    )


def safe_response_text(value: Any, *, max_length: int = MAX_JOB_FIELD_RESPONSE_LENGTH) -> str | None:
    cleaned = clean_text(value, max_length=max_length)
    return cleaned or None


def raw_value(raw_job: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw_job:
            return raw_job[key]
    return None


def parse_posting_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def compute_content_hash(*parts: str | None) -> str:
    normalized = "\n".join((part or "").strip().lower() for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_job(raw_job: dict[str, Any], source: JobSource) -> NormalizedJob:
    suspicious_reasons: list[str] = []
    raw_description = raw_value(raw_job, "description", "Job Description")
    if raw_description is not None and TAG_PATTERN.search(str(raw_description)):
        suspicious_reasons.append("html_stripped")

    external_job_id = clean_text(
        raw_value(raw_job, "external_job_id", "Job Id", "job_id"),
        max_length=255,
    ) or None
    title = clean_text(raw_value(raw_job, "title", "Job Title"), max_length=255)
    company = clean_text(raw_value(raw_job, "company", "Company"), max_length=255)
    location = clean_text(raw_value(raw_job, "location", "Job Location"), max_length=255) or None
    category = clean_text(raw_value(raw_job, "category", "Job Industry"), max_length=100) or None
    description = clean_text(raw_description, max_length=MAX_TEXT_LENGTH) or None
    job_url = clean_text(raw_value(raw_job, "job_url", "Job URL", "application_link"), max_length=2048)
    posting_date = parse_posting_date(raw_value(raw_job, "posting_date", "Job Posting Date"))

    if not title:
        title = "Untitled job"
        suspicious_reasons.append("missing_title")
    if not company:
        company = "Unknown company"
        suspicious_reasons.append("missing_company")
    if not job_url:
        raise JobValidationError("Job posting is missing an application link.")

    try:
        validated_job_url = validate_job_url_for_source(job_url, source)
    except (JobSourceValidationError, JobValidationError) as exc:
        raise JobValidationError("Job posting has an invalid application link.") from exc

    content_hash = compute_content_hash(
        source.source_name,
        title,
        company,
        location,
        category,
        description,
        validated_job_url,
    )
    return NormalizedJob(
        external_job_id=external_job_id,
        title=title,
        company=company,
        location=location,
        category=category,
        description=description,
        job_url=validated_job_url,
        posting_date=posting_date,
        content_hash=content_hash,
        is_suspicious=bool(suspicious_reasons),
        suspicious_reasons=tuple(dict.fromkeys(suspicious_reasons)),
    )


def seed_approved_job_sources(
    db: Session,
    settings: Settings,
    *,
    request: Any | None = None,
    admin_user_id: int | None = None,
) -> list[JobSource]:
    seeded: list[JobSource] = []
    for source_name, source_config in APPROVED_JOB_SOURCES.items():
        base_url = validate_source_base_url(source_name, source_config["base_url"], settings)
        source = db.scalar(select(JobSource).where(JobSource.source_name == source_name))
        if source is None:
            source = JobSource(source_name=source_name, base_url=base_url, is_enabled=True)
            db.add(source)
        else:
            source.base_url = base_url
        seeded.append(source)

    db.flush()
    if admin_user_id is not None:
        create_audit_log(
            db,
            event_type="admin.job_source.seed",
            outcome=AuditOutcome.SUCCESS,
            request=request,
            user_id=admin_user_id,
            target_type="job_source",
            details={"sources": [source.source_name for source in seeded]},
        )
    db.commit()
    return seeded


def update_job_source_enabled(
    db: Session,
    *,
    source: JobSource,
    is_enabled: bool,
    request: Any | None = None,
    admin_user_id: int | None = None,
) -> JobSource:
    source.is_enabled = is_enabled
    if admin_user_id is not None:
        create_audit_log(
            db,
            event_type="admin.job_source.update",
            outcome=AuditOutcome.SUCCESS,
            request=request,
            user_id=admin_user_id,
            target_type="job_source",
            target_id=source.id,
            details={"is_enabled": is_enabled},
        )
    db.commit()
    db.refresh(source)
    return source


def find_duplicate_job(db: Session, *, source: JobSource, normalized_job: NormalizedJob) -> tuple[JobPosting | None, str | None]:
    if normalized_job.external_job_id:
        existing = db.scalar(
            select(JobPosting).where(
                JobPosting.source_id == source.id,
                JobPosting.external_job_id == normalized_job.external_job_id,
            )
        )
        if existing is not None:
            return existing, "source_external_job_id"

    existing = db.scalar(
        select(JobPosting).where(
            JobPosting.source_id == source.id,
            JobPosting.content_hash == normalized_job.content_hash,
        )
    )
    if existing is not None:
        return existing, "content_hash"
    return None, None


def apply_normalized_job(posting: JobPosting, normalized_job: NormalizedJob) -> None:
    posting.external_job_id = normalized_job.external_job_id
    posting.title = normalized_job.title
    posting.company = normalized_job.company
    posting.location = normalized_job.location
    posting.category = normalized_job.category
    posting.description = normalized_job.description
    posting.job_url = normalized_job.job_url
    posting.posting_date = normalized_job.posting_date
    posting.content_hash = normalized_job.content_hash
    posting.is_suspicious = normalized_job.is_suspicious


def store_normalized_job(
    db: Session,
    *,
    source: JobSource,
    normalized_job: NormalizedJob,
    request: Any | None = None,
) -> tuple[JobPosting, bool, str | None]:
    existing, duplicate_reason = find_duplicate_job(db, source=source, normalized_job=normalized_job)
    created = existing is None
    posting = existing or JobPosting(source_id=source.id)
    apply_normalized_job(posting, normalized_job)
    if created:
        db.add(posting)
    db.flush()

    if normalized_job.is_suspicious:
        create_audit_log(
            db,
            event_type="job.suspicious_flagged",
            outcome=AuditOutcome.SUCCESS,
            request=request,
            target_type="job_posting",
            target_id=posting.id,
            details={"reasons": list(normalized_job.suspicious_reasons), "source_id": source.id},
        )
    return posting, created, duplicate_reason


def job_to_summary_response(job: JobPosting) -> JobSummaryResponse:
    return JobSummaryResponse(
        id=job.id,
        title=safe_response_text(job.title) or "Untitled job",
        company=safe_response_text(job.company) or "Unknown company",
        location=safe_response_text(job.location),
        category=safe_response_text(job.category, max_length=100),
        source=JobSourcePublicResponse(id=job.source.id, source_name=job.source.source_name),
        posting_date=job.posting_date,
        scraped_at=job.scraped_at,
        is_active=job.is_active,
        is_suspicious=job.is_suspicious,
        application_url_is_valid=is_job_url_valid_for_source(job),
    )


def job_to_detail_response(job: JobPosting) -> JobDetailResponse:
    summary = job_to_summary_response(job)
    return JobDetailResponse(
        **summary.model_dump(),
        description=safe_response_text(
            job.description,
            max_length=MAX_JOB_DESCRIPTION_RESPONSE_LENGTH,
        ),
        job_url=validate_job_url_for_source(job.job_url, job.source),
        external_link_warning=EXTERNAL_LINK_WARNING,
    )


def visible_job_filters(*, active_only: bool, include_suspicious: bool) -> list[Any]:
    filters: list[Any] = []
    if active_only:
        filters.append(JobPosting.is_active.is_(True))
    if not include_suspicious:
        filters.append(JobPosting.is_suspicious.is_(False))
    return filters


def list_jobs(
    db: Session,
    *,
    keyword: str | None = None,
    company: str | None = None,
    location: str | None = None,
    category: str | None = None,
    source: str | None = None,
    active_only: bool = True,
    include_suspicious: bool = False,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> JobListResponse:
    filters = visible_job_filters(active_only=active_only, include_suspicious=include_suspicious)

    if keyword:
        pattern = f"%{escape_like_term(keyword.strip())}%"
        filters.append(
            or_(
                JobPosting.title.ilike(pattern, escape="\\"),
                JobPosting.company.ilike(pattern, escape="\\"),
                JobPosting.location.ilike(pattern, escape="\\"),
                JobPosting.category.ilike(pattern, escape="\\"),
                JobPosting.description.ilike(pattern, escape="\\"),
            )
        )
    if company:
        filters.append(JobPosting.company.ilike(f"%{escape_like_term(company.strip())}%", escape="\\"))
    if location:
        filters.append(JobPosting.location.ilike(f"%{escape_like_term(location.strip())}%", escape="\\"))
    if category:
        filters.append(JobPosting.category.ilike(f"%{escape_like_term(category.strip())}%", escape="\\"))
    if source:
        filters.append(JobSource.source_name == source)

    base_stmt = select(JobPosting).join(JobPosting.source).where(*filters)
    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
    jobs = list(
        db.scalars(
            base_stmt.options(selectinload(JobPosting.source))
            .order_by(JobPosting.posting_date.desc().nullslast(), JobPosting.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return JobListResponse(
        items=[job_to_summary_response(job) for job in jobs],
        page=page,
        page_size=page_size,
        total=total,
    )


def get_visible_job_detail(db: Session, *, job_id: int) -> JobDetailResponse:
    job = db.scalar(
        select(JobPosting)
        .options(selectinload(JobPosting.source))
        .where(
            JobPosting.id == job_id,
            JobPosting.is_active.is_(True),
            JobPosting.is_suspicious.is_(False),
        )
    )
    if job is None or not is_job_url_valid_for_source(job):
        raise JobNotFoundError("Resource not found.")
    return job_to_detail_response(job)


def get_saveable_job(db: Session, *, job_id: int) -> JobPosting:
    job = db.scalar(
        select(JobPosting)
        .options(selectinload(JobPosting.source))
        .where(
            JobPosting.id == job_id,
            JobPosting.is_active.is_(True),
            JobPosting.is_suspicious.is_(False),
        )
    )
    if job is None or not is_job_url_valid_for_source(job):
        raise JobNotFoundError("Resource not found.")
    return job


def save_job_for_user(
    db: Session,
    request: Request,
    *,
    user_id: int,
    job_id: int,
) -> SavedJobResponse:
    job = get_saveable_job(db, job_id=job_id)
    saved_job = db.scalar(select(SavedJob).where(SavedJob.user_id == user_id, SavedJob.job_id == job.id))
    if saved_job is None:
        saved_job = SavedJob(user_id=user_id, job_id=job.id)
        db.add(saved_job)
        try:
            db.flush()
            audit_details = {"action": "saved"}
            add_application_history(db, user_id=user_id, job_id=job.id, action_type="job_saved")
        except IntegrityError:
            db.rollback()
            saved_job = db.scalar(
                select(SavedJob).where(SavedJob.user_id == user_id, SavedJob.job_id == job.id)
            )
            if saved_job is None:
                raise
            audit_details = {"action": "already_saved"}
    else:
        audit_details = {"action": "already_saved"}

    create_audit_log(
        db,
        event_type="saved_job.save",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user_id,
        target_type="job_posting",
        target_id=job.id,
        details=audit_details,
    )
    db.commit()
    db.refresh(saved_job)
    saved_job.job = job
    return SavedJobResponse(job=job_to_summary_response(job), saved_at=saved_job.saved_at)


def unsave_job_for_user(
    db: Session,
    request: Request,
    *,
    user_id: int,
    job_id: int,
) -> None:
    saved_job = db.scalar(select(SavedJob).where(SavedJob.user_id == user_id, SavedJob.job_id == job_id))
    if saved_job is None:
        raise JobNotFoundError("Resource not found.")

    db.delete(saved_job)
    add_application_history(db, user_id=user_id, job_id=job_id, action_type="job_unsaved")
    create_audit_log(
        db,
        event_type="saved_job.unsave",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user_id,
        target_type="job_posting",
        target_id=job_id,
        details={"action": "unsaved"},
    )
    db.commit()


def list_saved_jobs_for_user(
    db: Session,
    *,
    user_id: int,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> SavedJobListResponse:
    filters = (
        SavedJob.user_id == user_id,
        JobPosting.is_active.is_(True),
        JobPosting.is_suspicious.is_(False),
    )
    base_stmt = select(SavedJob).join(SavedJob.job).join(JobPosting.source).where(*filters)
    total = db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0
    saved_jobs = list(
        db.scalars(
            base_stmt.options(selectinload(SavedJob.job).selectinload(JobPosting.source))
            .order_by(SavedJob.saved_at.desc(), SavedJob.job_id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return SavedJobListResponse(
        items=[
            SavedJobResponse(job=job_to_summary_response(saved_job.job), saved_at=saved_job.saved_at)
            for saved_job in saved_jobs
            if is_job_url_valid_for_source(saved_job.job)
        ],
        page=page,
        page_size=page_size,
        total=total,
    )
