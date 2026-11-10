from pathlib import Path

from celery import Celery
from celery.schedules import crontab
from celery.signals import after_setup_logger, after_setup_task_logger, after_task_publish

from app.core.config import get_settings

settings = get_settings()
SCHEDULER_HEARTBEAT = Path("/tmp/celerybeat-heartbeat")


@after_task_publish.connect
def record_scheduler_dispatch(**kwargs):
    if settings.service_role == "beat":
        SCHEDULER_HEARTBEAT.touch(mode=0o600)


@after_setup_logger.connect
@after_setup_task_logger.connect
def configure_worker_logging(**kwargs):
    from app.core.logging import configure_logging
    configure_logging(settings.app_env)

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
    # Persist dispatch state for recovery; liveness uses a separate successful-
    # publication heartbeat because database backends can buffer file metadata.
    beat_sync_every=1,
    task_time_limit=600,
    task_soft_time_limit=540,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="private",
    task_routes={
        "app.workers.tasks.run_pending_scraping": {"queue": "scraping"},
        "app.workers.tasks.run_weekly_scraping": {"queue": "scraping"},
        "app.workers.tasks.run_mock_scraper": {"queue": "scraping"},
    },
    result_expires=settings.celery_result_expires_seconds,
    broker_transport_options={"visibility_timeout": 3600},
    beat_schedule={
        "process-queued-scraping": {"task": "app.workers.tasks.run_pending_scraping", "schedule": 30.0},
        "deliver-account-mail": {
            "task": "app.workers.tasks.deliver_mail", "schedule": 30.0,
        },
        "weekly-approved-source-scraping": {
            "task": "app.workers.tasks.run_weekly_scraping",
            "schedule": crontab(minute=0, hour=18, day_of_week="sun"),
        },
    },
)
