import feedparser
from datetime import datetime
import logging
from typing import Iterable

from app.db.models import NewsItem, Source
from app.services.dedup import make_content_hash

logger = logging.getLogger(__name__)


def parse_datetime(entry) -> datetime | None:
    # feedparser provides "published_parsed" sometimes
    if getattr(entry, "published_parsed", None):
        return datetime(*entry.published_parsed[:6])
    return None


def fetch_rss_items(source: Source) -> Iterable[dict]:
    logger.info("RSS fetch started: source_id=%s source_name=%s", source.id, source.name)
    feed = feedparser.parse(source.url)
    if getattr(feed, "bozo", 0):
        logger.warning(
            "RSS parser warning: source_id=%s source_name=%s error=%s",
            source.id,
            source.name,
            getattr(feed, "bozo_exception", "unknown"),
        )

    entries = getattr(feed, "entries", []) or []
    logger.info(
        "RSS fetch completed: source_id=%s source_name=%s fetched_items=%s",
        source.id,
        source.name,
        len(entries),
    )

    for entry in entries:
        yield {
            "external_id": getattr(entry, "id", None) or getattr(entry, "guid", None) or entry.get("link", ""),
            "title": entry.get("title", "").strip(),
            "url": entry.get("link"),
            "content": (entry.get("summary") or "").strip(),
            "published_at": parse_datetime(entry),
        }


def to_news_item(source: Source, raw: dict) -> NewsItem:
    content_hash = make_content_hash(raw["title"], raw["content"])
    return NewsItem(
        source_id=source.id,
        external_id=raw["external_id"][:256],
        title=raw["title"][:512],
        url=(raw.get("url") or None),
        content=raw["content"],
        published_at=raw.get("published_at"),
        content_hash=content_hash,
    )
