from celery import Celery
from celery.schedules import crontab
from app.core.config import settings
from app.core.logging import setup_logging

celery = Celery(
    "muratorium",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks", "app.workers.publisher"],
)

celery.conf.timezone = "Europe/Kyiv"
celery.conf.beat_schedule = {
    "poll-rss-every-5-min": {
        "task": "app.workers.tasks.poll_rss",
        "schedule": 300.0,
    },
    "digest-at-15-00": {
        "task": "app.workers.tasks.analyze_and_publish_digest",
        "schedule": crontab(hour=15, minute=0),
    },
    "digest-at-21-00": {
        "task": "app.workers.tasks.analyze_and_publish_digest",
        "schedule": crontab(hour=21, minute=0),
    },
}

setup_logging()
