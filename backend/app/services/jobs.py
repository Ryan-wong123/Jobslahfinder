from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import html
import re
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.enums import AuditOutcome
from app.models.job import JobPosting, JobSource
from app.services.audit import create_audit_log


MAX_TEXT_LENGTH = 20_000
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
WHITESPACE_PATTERN = re.compile(r"\s+")


class JobSourceValidationError(ValueError):
    pass


class JobValidationError(ValueError):
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


def clean_text(value: Any, *, max_length: int) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = TAG_PATTERN.sub(" ", text)
    text = WHITESPACE_PATTERN.sub(" ", text).strip()
    return text[:max_length]


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
