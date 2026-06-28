from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "secure_job_platform",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    beat_schedule={
        "weekly-approved-source-scraping": {
            "task": "app.workers.tasks.run_weekly_scraping",
            "schedule": crontab(minute=0, hour=18, day_of_week="sun"),
        },
    },
)
