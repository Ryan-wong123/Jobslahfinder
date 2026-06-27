from app.workers.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.job import JobSource
from app.services.resumes import run_resume_extraction
from app.services.scraping import run_scraper_for_source


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


@celery_app.task(name="app.workers.tasks.extract_resume")
def extract_resume(resume_id: int) -> dict[str, int | str]:
    with SessionLocal() as db:
        return run_resume_extraction(db, resume_id=resume_id)
