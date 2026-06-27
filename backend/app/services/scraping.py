from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import AuditOutcome, ScrapingRunStatus
from app.models.job import JobSource, ScrapingRun
from app.services.audit import create_audit_log
from app.services.jobs import JobValidationError, normalize_job, store_normalized_job


GENERIC_SCRAPING_ERROR = "Scraping failed for source."


class ScrapingError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


def mock_jobs_for_source(source: JobSource) -> list[dict[str, Any]]:
    if source.source_name == "JobStreet":
        return [
            {
                "external_job_id": "jobstreet-demo-1",
                "title": "Security Analyst",
                "company": "SecureWorks SG",
                "location": "Singapore",
                "category": "Information & Communication Technology",
                "description": "Monitor alerts, investigate incidents, and support secure operations.",
                "job_url": "https://sg.jobstreet.com/job/secure-analyst-demo",
                "posting_date": "2026-04-30",
            },
            {
                "external_job_id": "jobstreet-demo-2",
                "title": "Backend Developer",
                "company": "Cloud Apps Pte Ltd",
                "location": "Singapore",
                "category": "Information & Communication Technology",
                "description": "<p>Build APIs and handle untrusted job data safely.</p>",
                "job_url": "https://sg.jobstreet.com/job/backend-developer-demo",
                "posting_date": "2026-04-29",
            },
        ]

    if source.source_name == "MyCareersFuture":
        return [
            {
                "external_job_id": "mcf-demo-1",
                "title": "Software Engineer",
                "company": "GovTech Partner",
                "location": "Singapore",
                "category": "Engineering",
                "description": "Develop secure web services and collaborate with product teams.",
                "job_url": "https://www.mycareersfuture.gov.sg/job/software-engineer-demo",
                "posting_date": "2026-04-28",
            },
        ]
    raise ScrapingError("No mock scraper is configured for this source.")


def start_scraping_run(db: Session, *, source: JobSource) -> ScrapingRun:
    run = ScrapingRun(
        source_id=source.id,
        status=ScrapingRunStatus.RUNNING.value,
        jobs_retrieved=0,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def complete_scraping_run(
    db: Session,
    *,
    run: ScrapingRun,
    jobs_retrieved: int,
    request: Any | None = None,
    user_id: int | None = None,
) -> ScrapingRun:
    run.status = ScrapingRunStatus.SUCCESS.value
    run.completed_at = utc_now()
    run.jobs_retrieved = jobs_retrieved
    run.error_message = None
    create_audit_log(
        db,
        event_type="scraping_run.completed",
        outcome=AuditOutcome.SUCCESS,
        request=request,
        user_id=user_id,
        target_type="scraping_run",
        target_id=run.id,
        details={"source_id": run.source_id, "jobs_retrieved": jobs_retrieved},
    )
    db.commit()
    db.refresh(run)
    return run


def fail_scraping_run(
    db: Session,
    *,
    run: ScrapingRun,
    request: Any | None = None,
    user_id: int | None = None,
) -> ScrapingRun:
    run.status = ScrapingRunStatus.FAILED.value
    run.completed_at = utc_now()
    run.jobs_retrieved = 0
    run.error_message = GENERIC_SCRAPING_ERROR
    create_audit_log(
        db,
        event_type="scraping_run.failed",
        outcome=AuditOutcome.FAILURE,
        request=request,
        user_id=user_id,
        target_type="scraping_run",
        target_id=run.id,
        details={"source_id": run.source_id, "reason": "scraper_error"},
    )
    db.commit()
    db.refresh(run)
    return run


def run_scraper_for_source(
    db: Session,
    *,
    source: JobSource,
    fetcher: Callable[[JobSource], list[dict[str, Any]]] = mock_jobs_for_source,
    request: Any | None = None,
    user_id: int | None = None,
) -> ScrapingRun:
    if not source.is_enabled:
        raise ScrapingError("Source is disabled.")

    run = start_scraping_run(db, source=source)
    try:
        raw_jobs = fetcher(source)
        jobs_retrieved = 0
        for raw_job in raw_jobs:
            try:
                normalized = normalize_job(raw_job, source)
            except JobValidationError:
                continue
            store_normalized_job(db, source=source, normalized_job=normalized, request=request)
            jobs_retrieved += 1
        return complete_scraping_run(
            db,
            run=run,
            jobs_retrieved=jobs_retrieved,
            request=request,
            user_id=user_id,
        )
    except Exception:
        db.rollback()
        run = db.merge(run)
        return fail_scraping_run(db, run=run, request=request, user_id=user_id)


def get_scraping_run(db: Session, run_id: int) -> ScrapingRun | None:
    return db.scalar(select(ScrapingRun).where(ScrapingRun.id == run_id))
