from celery import Celery
from app.core.config import settings

celery = Celery(
    "muratorium",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.timezone = "Europe/Kyiv"
celery.conf.beat_schedule = {
    "poll-rss-every-2-min": {
        "task": "app.workers.tasks.poll_rss",
        "schedule": 300.0,
    },
}