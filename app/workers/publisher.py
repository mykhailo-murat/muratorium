from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.db.models import NewsItem
from app.db.session import SessionLocal
from app.workers.celery_app import celery

TELEGRAM_MAX_TEXT = 4096
SAFE_CHUNK = 3800


def format_post(item: NewsItem) -> str:
    parts = [f"UA {item.final_score}/100", item.title]
    if item.short_summary:
        parts.append(item.short_summary)
    if item.url:
        parts.append(item.url)
    return "\n\n".join(parts)


def build_digest_message(lines: list[str]) -> str:
    now_local = datetime.now(ZoneInfo("Europe/Kyiv"))
    header = f"Дайджест {now_local.strftime('%d.%m.%Y %H:%M')} (AI)"
    body = "\n\n".join(lines) if lines else "Релевантних новин для публікації не знайдено."
    return f"{header}\n\n{body}"


def _split_telegram_text(text: str, chunk_size: int = SAFE_CHUNK) -> list[str]:
    if len(text) <= TELEGRAM_MAX_TEXT:
        return [text]

    parts: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            parts.append(current)
        if len(block) <= chunk_size:
            current = block
            continue
        start = 0
        while start < len(block):
            end = start + chunk_size
            parts.append(block[start:end])
            start = end
        current = ""
    if current:
        parts.append(current)
    return parts


def send_telegram_text(text: str, parse_mode: str | None = None) -> None:
    if not settings.telegram_bot_token or not settings.telegram_channel_id:
        raise RuntimeError("Telegram credentials are not configured")

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_channel_id,
        "text": text,
        "disable_web_page_preview": False,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    with httpx.Client(timeout=20) as client:
        for part in _split_telegram_text(text):
            payload["text"] = part
            response = client.post(url, json=payload)
            response.raise_for_status()


@celery.task(
    name="app.workers.publisher.publish_to_telegram",
    autoretry_for=(httpx.HTTPError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def publish_to_telegram(news_item_id: int) -> None:
    if not settings.telegram_bot_token or not settings.telegram_channel_id:
        return

    with SessionLocal() as db:
        item = db.scalar(select(NewsItem).where(NewsItem.id == news_item_id))
        if not item or item.is_published:
            return

        send_telegram_text(format_post(item))

        item.is_published = True
        item.published_to_telegram_at = datetime.now(timezone.utc)
        db.commit()
