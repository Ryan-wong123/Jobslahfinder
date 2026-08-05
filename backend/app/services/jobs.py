from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
from app.models.enums import AuditOutcome, EmploymentType, SeniorityLevel, WorkplaceType
from app.models.job import JobPosting, JobSource
from app.schemas.jobs import (
    JobDetailResponse,
    JobListResponse,
    JobSourcePublicResponse,
    JobSummaryResponse,
    SalaryTrendPointResponse,
    SalaryTrendResponse,
    SavedJobListResponse,
    SavedJobResponse,
)
from app.security.text import HTML_TAG_PATTERN, sanitize_text
from app.services.application_history import add_application_history
from app.services.audit import create_audit_log


MAX_TEXT_LENGTH = 20_000
MAX_JOB_DESCRIPTION_RESPONSE_LENGTH = 20_000
MAX_JOB_FIELD_RESPONSE_LENGTH = 255
MAX_EXTERNAL_JOB_URL_LENGTH = 2048
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
    "JobsLah": {
        "base_url": "https://www.jobslah.com/sg",
        "domains": ("www.jobslah.com",),
    },
    "FastJobs": {
        "base_url": "https://www.fastjobs.sg",
        "domains": ("www.fastjobs.sg",),
    },
}
SALARY_ROLE_KEYWORD_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "software engineer": ("software engineer", "software developer", "programmer", "full stack", "full-stack"),
    "backend developer": ("backend developer", "backend engineer", "back-end", "api developer", "server engineer"),
    "frontend developer": ("frontend developer", "frontend engineer", "front-end", "react developer", "ui developer"),
    "data analyst": ("data analyst", "business analyst", "analytics analyst", "reporting analyst", "bi analyst"),
    "data engineer": ("data engineer", "etl developer", "pipeline engineer"),
    "security analyst": ("security analyst", "cybersecurity analyst", "soc analyst", "information security analyst"),
    "devops engineer": ("devops engineer", "sre", "site reliability engineer", "cloud engineer", "platform engineer"),
    "product manager": ("product manager", "product owner"),
    "project manager": ("project manager", "program manager", "programme manager"),
    "marketing executive": ("marketing executive", "digital marketing", "seo", "sem"),
    "sales executive": ("sales executive", "business development", "account executive"),
    "customer service officer": ("customer service", "customer support", "call centre", "call center"),
    "human resources executive": ("human resources", "hr executive", "recruiter", "talent acquisition"),
    "finance executive": ("finance executive", "accounting", "accounts executive", "audit"),
    "operations executive": ("operations executive", "admin executive", "administrator"),
}

SALARY_NUMBER_PATTERN = re.compile(r"(?i)(\d+(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)\s*(k)?")


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
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_period: str | None
    minimum_experience: str | None
    minimum_experience_years: int | None
    employment_type: str | None
    workplace_type: str | None
    seniority_level: str | None
    skills: list[str] | None
    expires_at: date | None
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
    cleaned = str(url).strip()
    if not cleaned or len(cleaned) > MAX_EXTERNAL_JOB_URL_LENGTH:
        raise JobSourceValidationError("Job URL length is not allowed.")
    if "\\" in cleaned or any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in cleaned):
        raise JobSourceValidationError("Job URL is malformed.")
    try:
        parsed = urlsplit(cleaned)
        hostname = normalize_hostname(parsed.hostname)
        _ = parsed.port
    except ValueError as exc:
        raise JobSourceValidationError("Job URL is malformed.") from exc

    if parsed.username is not None or parsed.password is not None:
        raise JobSourceValidationError("Job URL credentials are not allowed.")
    hostname = normalize_hostname(parsed.hostname)
    if parsed.scheme.lower() != "https" or not hostname:
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
    try:
        cleaned = validate_https_url(job_url)
    except JobSourceValidationError as exc:
        raise JobValidationError("Job URL is not approved for the source.") from exc
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
    cleaned = sanitize_text(
        value,
        field_name="text",
        max_length=max_length,
        empty_to_none=True,
        html_policy="strip",
        overflow="truncate",
        control_policy="strip",
        collapse_whitespace=True,
        reject_placeholders=True,
    )
    return cleaned or ""


def clean_job_url(value: Any) -> str:
    try:
        cleaned = sanitize_text(
            value,
            field_name="job URL",
            max_length=MAX_EXTERNAL_JOB_URL_LENGTH,
            empty_to_none=True,
            html_policy="reject",
            overflow="error",
            control_policy="reject",
            collapse_whitespace=False,
            allow_multiline=False,
            reject_placeholders=True,
        )
    except ValueError as exc:
        raise JobValidationError("Job posting has an invalid application link.") from exc
    return cleaned or ""


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
    text = clean_text(value, max_length=100)
    if not text:
        return None

    relative_match = re.search(r"(?i)(?:posted\s*)?(\d+)\s*(day|days|d|hour|hours|h|minute|minutes|min|m)\s*ago", text)
    if relative_match:
        amount = int(relative_match.group(1))
        unit = relative_match.group(2).lower()
        now = datetime.utcnow()
        if unit in {"day", "days", "d"}:
            return (now - timedelta(days=amount)).date()
        if unit in {"hour", "hours", "h"}:
            return (now - timedelta(hours=amount)).date()
        return now.date()

    cleaned = re.sub(r"(?i)^posted\s+", "", text).strip()
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(cleaned[:32], fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(cleaned[:10])
    except ValueError:
        return None


def parse_minimum_experience_years(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value if 0 <= value <= 60 else None
    text = clean_text(value, max_length=100)
    match = re.search(r"(?i)(\d{1,2})(?:\s*[-–]\s*\d{1,2})?\s*(?:\+\s*)?years?", text)
    if not match:
        return None
    years = int(match.group(1))
    return years if years <= 60 else None


def normalize_enum_value(value: Any, aliases: dict[str, str]) -> str | None:
    text = clean_text(value, max_length=100).lower().replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return aliases.get(text)


def normalize_skills(value: Any) -> list[str] | None:
    if value in (None, ""):
        return None
    candidates = value if isinstance(value, (list, tuple, set)) else re.split(r"[,;|\n]", str(value))
    skills: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        skill = clean_text(candidate, max_length=100)
        key = skill.casefold()
        if skill and key not in seen:
            skills.append(skill)
            seen.add(key)
        if len(skills) == 25:
            break
    return skills or None


def parse_salary_range(value: Any) -> tuple[float | None, float | None, str | None, str | None]:
    if value in (None, ""):
        return None, None, None, None
    text = clean_text(value, max_length=200).lower()
    if not text or any(marker in text for marker in ("not specified", "undisclosed", "negotiable")):
        return None, None, None, None

    currency = "SGD" if "$" in text or "sgd" in text or "s$" in text else None
    if "hour" in text or "/hr" in text:
        period = "hour"
    elif "year" in text or "annum" in text or "p.a" in text or "/yr" in text:
        period = "year"
    else:
        period = "month" if any(marker in text for marker in ("month", "p.m", "/mo", "$")) else None

    values: list[float] = []
    for match in SALARY_NUMBER_PATTERN.finditer(text):
        raw, thousands_marker = match.groups()
        try:
            amount = float(raw.replace(",", ""))
        except ValueError:
            continue
        if thousands_marker:
            amount *= 1000
        if 1 <= amount <= 1_000_000:
            values.append(amount)

    if not values:
        return None, None, currency, period
    salary_min = min(values)
    salary_max = max(values)
    if salary_max < 1000 and "k" not in text and period in {"month", "year"}:
        return None, None, currency, period
    return salary_min, salary_max, currency, period
def compute_content_hash(*parts: str | None) -> str:
    normalized = "\n".join((part or "").strip().lower() for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_job(raw_job: dict[str, Any], source: JobSource) -> NormalizedJob:
    suspicious_reasons: list[str] = []
    raw_description = raw_value(raw_job, "description", "Job Description")
    if raw_description is not None and HTML_TAG_PATTERN.search(str(raw_description)):
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
    job_url = clean_job_url(raw_value(raw_job, "job_url", "Job URL", "application_link"))
    posting_date = parse_posting_date(raw_value(raw_job, "posting_date", "Job Posting Date"))
    salary_min, salary_max, salary_currency, salary_period = parse_salary_range(
        raw_value(raw_job, "salary", "Job Salary Range", "salary_range")
    )
    minimum_experience = clean_text(
        raw_value(raw_job, "minimum_experience", "Job Minimum Experience", "job_minimum_experience"),
        max_length=100,
    ) or None
    minimum_experience_years = parse_minimum_experience_years(
        raw_value(raw_job, "minimum_experience_years", "minimum_experience", "Job Minimum Experience")
    )
    employment_type = normalize_enum_value(
        raw_value(raw_job, "employment_type", "Employment Type", "job_type"),
        {
            "full time": EmploymentType.FULL_TIME.value,
            "permanent": EmploymentType.FULL_TIME.value,
            "part time": EmploymentType.PART_TIME.value,
            "contract": EmploymentType.CONTRACT.value,
            "contractor": EmploymentType.CONTRACT.value,
            "temporary": EmploymentType.TEMPORARY.value,
            "internship": EmploymentType.INTERNSHIP.value,
            "intern": EmploymentType.INTERNSHIP.value,
        },
    )
    workplace_type = normalize_enum_value(
        raw_value(raw_job, "workplace_type", "Workplace Type", "work_arrangement"),
        {
            "onsite": WorkplaceType.ONSITE.value,
            "on site": WorkplaceType.ONSITE.value,
            "hybrid": WorkplaceType.HYBRID.value,
            "remote": WorkplaceType.REMOTE.value,
            "work from home": WorkplaceType.REMOTE.value,
        },
    )
    seniority_level = normalize_enum_value(
        raw_value(raw_job, "seniority_level", "Seniority Level", "seniority"),
        {member.value.lower(): member.value for member in SeniorityLevel}
        | {"entry level": SeniorityLevel.ENTRY.value, "mid level": SeniorityLevel.MID.value},
    )
    skills = normalize_skills(raw_value(raw_job, "skills", "Skills", "required_skills"))
    expires_at = parse_posting_date(raw_value(raw_job, "expires_at", "closing_date", "Closing Date"))

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
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        salary_period=salary_period,
        minimum_experience=minimum_experience,
        minimum_experience_years=minimum_experience_years,
        employment_type=employment_type,
        workplace_type=workplace_type,
        seniority_level=seniority_level,
        skills=skills,
        expires_at=expires_at,
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
    posting.salary_min = normalized_job.salary_min
    posting.salary_max = normalized_job.salary_max
    posting.salary_currency = normalized_job.salary_currency
    posting.salary_period = normalized_job.salary_period
    posting.minimum_experience = normalized_job.minimum_experience
    posting.minimum_experience_years = normalized_job.minimum_experience_years
    posting.employment_type = normalized_job.employment_type
    posting.workplace_type = normalized_job.workplace_type
    posting.seniority_level = normalized_job.seniority_level
    posting.skills = normalized_job.skills
    posting.expires_at = normalized_job.expires_at
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
        salary_min=float(job.salary_min) if job.salary_min is not None else None,
        salary_max=float(job.salary_max) if job.salary_max is not None else None,
        salary_currency=safe_response_text(job.salary_currency, max_length=10),
        salary_period=safe_response_text(job.salary_period, max_length=20),
        minimum_experience=safe_response_text(job.minimum_experience, max_length=100),
        minimum_experience_years=job.minimum_experience_years,
        employment_type=job.employment_type,
        workplace_type=job.workplace_type,
        seniority_level=job.seniority_level,
        skills=[safe_response_text(skill, max_length=100) for skill in (job.skills or []) if safe_response_text(skill, max_length=100)] or None,
        posted_at=job.posting_date,
        expires_at=job.expires_at,
        scraped_at=job.scraped_at,
        is_active=job.is_active,
        is_suspicious=job.is_suspicious,
        application_url_is_valid=is_job_url_valid_for_source(job),
    )


def salary_midpoint(job: JobPosting) -> float | None:
    if job.salary_min is None and job.salary_max is None:
        return None
    salary_min = float(job.salary_min) if job.salary_min is not None else None
    salary_max = float(job.salary_max) if job.salary_max is not None else None
    if salary_min is not None and salary_max is not None:
        return (salary_min + salary_max) / 2
    return salary_min if salary_min is not None else salary_max


def monthly_salary_midpoint(job: JobPosting) -> float | None:
    midpoint = salary_midpoint(job)
    if midpoint is None:
        return None
    period = (job.salary_period or "").lower()
    if period == "month":
        return midpoint
    if period == "year":
        return midpoint / 12
    if period == "hour":
        return midpoint * 173.33
    return None


def salary_search_keywords(role: str, role_keywords: tuple[str, ...] | None = None) -> tuple[str, ...]:
    cleaned_role = clean_text(role, max_length=100)
    if role_keywords:
        raw_keywords = (cleaned_role, *role_keywords)
    else:
        raw_keywords = (cleaned_role, *SALARY_ROLE_KEYWORD_EXPANSIONS.get(cleaned_role.lower(), ()))
    keywords = [clean_text(keyword, max_length=100) for keyword in raw_keywords]
    return tuple(dict.fromkeys(keyword for keyword in keywords if keyword))


def get_salary_trend(
    db: Session,
    *,
    role: str,
    role_keywords: tuple[str, ...] | None = None,
    months: int = 12,
) -> SalaryTrendResponse:
    cleaned_role = clean_text(role, max_length=100)
    if not cleaned_role:
        return SalaryTrendResponse(role="", currency="SGD", period="month", points=[], sample_size=0)

    keywords = salary_search_keywords(cleaned_role, role_keywords)
    patterns = [f"%{escape_like_term(clean_text(keyword, max_length=100))}%" for keyword in keywords]
    title_filters = [JobPosting.title.ilike(pattern, escape="\\") for pattern in patterns if pattern != "%%"]
    if not title_filters:
        return SalaryTrendResponse(role=cleaned_role, currency="SGD", period="month", points=[], sample_size=0)

    jobs = list(
        db.scalars(
            select(JobPosting)
            .where(
                JobPosting.is_active.is_(True),
                JobPosting.is_suspicious.is_(False),
                or_(*title_filters),
                JobPosting.salary_period.in_(("month", "year", "hour")),
                or_(JobPosting.salary_min.is_not(None), JobPosting.salary_max.is_not(None)),
            )
            .order_by(JobPosting.posting_date.desc().nullslast(), JobPosting.scraped_at.desc())
            .limit(500)
        ).all()
    )

    buckets: dict[str, list[float]] = {}
    for job in jobs:
        midpoint = monthly_salary_midpoint(job)
        if midpoint is None:
            continue
        bucket_date = job.posting_date or job.scraped_at.date()
        bucket = bucket_date.strftime("%Y-%m")
        buckets.setdefault(bucket, []).append(midpoint)

    sorted_buckets = sorted(buckets.items())[-months:]
    points = [
        SalaryTrendPointResponse(
            period=period,
            average_salary=round(sum(values) / len(values), 2),
            sample_count=len(values),
        )
        for period, values in sorted_buckets
    ]
    return SalaryTrendResponse(
        role=cleaned_role,
        currency="SGD",
        period="month",
        points=points,
        sample_size=sum(point.sample_count for point in points),
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
        total_items=total,
        total_pages=(total + page_size - 1) // page_size,
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
