from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.job import JobSource, ScrapingRun
from app.models.enums import ScrapingRunStatus
from app.services.resumes import run_resume_extraction
from app.services.scraping import ScrapingError, run_scraper_for_source


MAX_WEEKLY_SCRAPE_WORKERS = 3


@celery_app.task(name="app.workers.tasks.run_pending_scraping")
def run_pending_scraping():
    with SessionLocal() as db:
        run = db.scalar(select(ScrapingRun).where(ScrapingRun.status == ScrapingRunStatus.PENDING.value)
            .order_by(ScrapingRun.id).with_for_update(skip_locked=True).limit(1))
        if run is None:
            return
        run.status = ScrapingRunStatus.RUNNING.value
        db.commit()
        source = db.get(JobSource, run.source_id)
        try:
            run_scraper_for_source(db, source=source, existing_run=run)
        except Exception:
            from app.services.scraping import fail_scraping_run
            db.rollback()
            fail_scraping_run(db, run=run)


@celery_app.task(name="app.workers.tasks.deliver_mail", ignore_result=True)
def deliver_mail() -> None:
    if get_settings().service_role not in {"api", "worker"}:
        raise PermissionError("Task not permitted for this service")
    from app.services.mail_outbox import deliver_pending_mail
    with SessionLocal() as db:
        deliver_pending_mail(db, get_settings())


@celery_app.task(name="app.workers.tasks.healthcheck")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@celery_app.task(name="app.workers.tasks.run_mock_scraper")
def run_mock_scraper(source_id: int) -> dict[str, int | str]:
    with SessionLocal() as db:
        source = db.get(JobSource, source_id)
        if source is None:
            return {"status": "not_found", "source_id": source_id}
        run = run_scraper_for_source(db, source=source)
        return {"status": run.status, "source_id": source_id, "scraping_run_id": run.id}


@celery_app.task(name="app.workers.tasks.run_weekly_scraping")
def run_weekly_scraping() -> dict[str, int | list[dict[str, int | str]]]:
    with SessionLocal() as db:
        sources = list(
            db.scalars(
                select(JobSource)
                .where(JobSource.is_enabled.is_(True))
                .order_by(JobSource.source_name)
            ).all()
        )

    def scrape_source(source_id: int) -> dict[str, int | str]:
        with SessionLocal() as source_db:
            source = source_db.get(JobSource, source_id)
            if source is None:
                return {"source_id": source_id, "status": "not_found"}
            try:
                run = run_scraper_for_source(source_db, source=source)
                return {
                    "source_id": source.id,
                    "scraping_run_id": run.id,
                    "status": run.status,
                }
            except ScrapingError:
                return {"source_id": source.id, "status": "skipped"}

    results: list[dict[str, int | str]] = []
    if sources:
        max_workers = min(MAX_WEEKLY_SCRAPE_WORKERS, len(sources))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_source_id = {
                executor.submit(scrape_source, source.id): source.id for source in sources
            }
            for future in as_completed(future_to_source_id):
                source_id = future_to_source_id[future]
                try:
                    results.append(future.result())
                except Exception:
                    results.append({"source_id": source_id, "status": "skipped"})

    results.sort(key=lambda result: int(result["source_id"]))
    return {"sources_checked": len(results), "results": results}


@celery_app.task(
    name="app.workers.tasks.extract_resume",
    soft_time_limit=get_settings().resume_parser_timeout_seconds + 5,
    time_limit=get_settings().resume_parser_timeout_seconds + 15,
)
def extract_resume(resume_id: int) -> dict[str, int | str]:
    if get_settings().service_role not in {"api", "worker"}:
        raise PermissionError("Task not permitted for this service")
    with SessionLocal() as db:
        return run_resume_extraction(db, resume_id=resume_id, settings=get_settings())
