from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import UTC, datetime
import inspect
import threading
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.enums import AuditOutcome, ScrapingRunStatus
from app.models.job import JobSource, ScrapingRun
from app.scrapers.fastjobs import fetch_fastjobs_jobs
from app.scrapers.jobslah import fetch_jobslah_jobs
from app.scrapers.jobstreet import fetch_jobstreet_jobs
from app.scrapers.mycareersfuture import fetch_mycareersfuture_jobs
from app.services.audit import create_audit_log
from app.services.jobs import JobValidationError, normalize_job, store_normalized_job, validate_source_base_url


GENERIC_SCRAPING_ERROR = "Scraping failed for source."
DEFAULT_SCRAPER_TIMEOUT_SECONDS = 15


class ScrapingError(RuntimeError):
    pass


ScraperFetcher = Callable[..., list[dict[str, Any]]]
SCRAPER_ADAPTERS: dict[str, ScraperFetcher] = {
    "JobStreet": fetch_jobstreet_jobs,
    "MyCareersFuture": fetch_mycareersfuture_jobs,
    "JobsLah": fetch_jobslah_jobs,
    "FastJobs": fetch_fastjobs_jobs,
}
LIVE_BROWSER_SOURCES = frozenset(SCRAPER_ADAPTERS)
LIVE_BROWSER_SOURCE_LOCKS = {source_name: threading.Lock() for source_name in LIVE_BROWSER_SOURCES}


def utc_now() -> datetime:
    return datetime.now(UTC)


def mock_jobs_for_source(source: JobSource) -> list[dict[str, Any]]:
    adapter = SCRAPER_ADAPTERS.get(source.source_name)
    if adapter is not None:
        return call_fetcher(adapter, source, timeout_seconds=DEFAULT_SCRAPER_TIMEOUT_SECONDS)
    raise ScrapingError("No mock scraper is configured for this source.")


def call_fetcher(fetcher: ScraperFetcher, source: JobSource, *, timeout_seconds: int) -> list[dict[str, Any]]:
    signature = inspect.signature(fetcher)
    has_source = "source" in signature.parameters
    has_timeout = "timeout_seconds" in signature.parameters
    if has_source and has_timeout:
        return fetcher(source=source, timeout_seconds=timeout_seconds)
    if has_timeout:
        return fetcher(timeout_seconds=timeout_seconds)
    if has_source:
        return fetcher(source=source)
    return fetcher(source)


def fetch_with_timeout(fetcher: ScraperFetcher, source: JobSource, *, timeout_seconds: int) -> list[dict[str, Any]]:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(call_fetcher, fetcher, source, timeout_seconds=timeout_seconds)
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        future.cancel()
        raise ScrapingError("Scraper request timed out.") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def fetch_with_retry(
    fetcher: ScraperFetcher,
    source: JobSource,
    *,
    timeout_seconds: int,
    max_retries: int,
) -> tuple[list[dict[str, Any]], int]:
    attempts = 0
    while attempts <= max_retries:
        attempts += 1
        try:
            return fetch_with_timeout(fetcher, source, timeout_seconds=timeout_seconds), attempts
        except Exception as exc:
            if attempts > max_retries:
                raise ScrapingError("Scraper failed after retry limit.") from exc
    raise ScrapingError("Scraper failed after retry limit.")


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


def has_running_scrape_for_source(db: Session, *, source: JobSource) -> bool:
    running_run = db.scalar(
        select(ScrapingRun.id).where(
            ScrapingRun.source_id == source.id,
            ScrapingRun.status == ScrapingRunStatus.RUNNING.value,
        )
    )
    return running_run is not None


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
    fetcher: ScraperFetcher | None = None,
    request: Any | None = None,
    user_id: int | None = None,
    settings: Settings | None = None,
    timeout_seconds: int | None = None,
    max_retries: int | None = None,
) -> ScrapingRun:
    if not source.is_enabled:
        raise ScrapingError("Source is disabled.")
    active_settings = settings or get_settings()
    try:
        validate_source_base_url(source.source_name, source.base_url, active_settings)
    except Exception as exc:
        raise ScrapingError("Source is not approved for scraping.") from exc

    selected_fetcher = fetcher or SCRAPER_ADAPTERS.get(source.source_name)
    if selected_fetcher is None:
        raise ScrapingError("No scraper adapter is configured for this source.")
    is_live_browser_scraper = fetcher is None and source.source_name in LIVE_BROWSER_SOURCES

    request_timeout = timeout_seconds or active_settings.scraping_request_timeout_seconds
    retry_limit = (
        active_settings.scraping_max_retries
        if max_retries is None
        else max(0, min(max_retries, 5))
    )
    if is_live_browser_scraper:
        retry_limit = 0

    if has_running_scrape_for_source(db, source=source):
        raise ScrapingError("A scraping run is already running for this source.")

    run = start_scraping_run(db, source=source)
    lock_acquired = False
    source_lock = LIVE_BROWSER_SOURCE_LOCKS.get(source.source_name)
    try:
        if is_live_browser_scraper and source_lock is not None:
            lock_acquired = source_lock.acquire(blocking=False)
            if not lock_acquired:
                raise ScrapingError("A live browser scrape is already running for this source.")
            raw_jobs = call_fetcher(selected_fetcher, source, timeout_seconds=request_timeout)
            attempts = 1
        else:
            raw_jobs, attempts = fetch_with_retry(
                selected_fetcher,
                source,
                timeout_seconds=request_timeout,
                max_retries=retry_limit,
            )
        jobs_retrieved = 0
        for raw_job in raw_jobs:
            try:
                normalized = normalize_job(raw_job, source)
            except JobValidationError:
                continue
            store_normalized_job(db, source=source, normalized_job=normalized, request=request)
            jobs_retrieved += 1
        run = complete_scraping_run(
            db,
            run=run,
            jobs_retrieved=jobs_retrieved,
            request=request,
            user_id=user_id,
        )
        create_audit_log(
            db,
            event_type="scraping_run.retry_policy",
            outcome=AuditOutcome.SUCCESS,
            request=request,
            user_id=user_id,
            target_type="scraping_run",
            target_id=run.id,
            details={
                "source_id": run.source_id,
                "attempts": attempts,
                "max_retries": retry_limit,
                "timeout_seconds": request_timeout,
            },
        )
        db.commit()
        db.refresh(run)
        return run
    except Exception:
        db.rollback()
        run = db.merge(run)
        return fail_scraping_run(db, run=run, request=request, user_id=user_id)
    finally:
        if lock_acquired and source_lock is not None:
            source_lock.release()


def get_scraping_run(db: Session, run_id: int) -> ScrapingRun | None:
    return db.scalar(select(ScrapingRun).where(ScrapingRun.id == run_id))
