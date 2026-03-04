import httpx
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import NewsItem

from app.workers.celery_app import celery


def format_post(item: NewsItem) -> str:
    # Minimal MVP format
    parts = [
        f"🇺🇦 {item.final_score}/100",
        item.title,
    ]
    if item.url:
        parts.append(item.url)
    return "\n\n".join(parts)


@celery.task
def publish_to_telegram(news_item_id: int) -> None:
    # Note: Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID
    if not settings.telegram_bot_token or not settings.telegram_channel_id:
        return

    with SessionLocal() as db:
        item = db.scalar(select(NewsItem).where(NewsItem.id == news_item_id))
        if not item or item.is_published:
            return

        text = format_post(item)

        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = {"chat_id": settings.telegram_channel_id, "text": text, "disable_web_page_preview": False}

        with httpx.Client(timeout=10) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()

        item.is_published = True
        db.commit()