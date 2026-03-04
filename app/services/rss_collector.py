import feedparser
from datetime import datetime
from typing import Iterable

from app.db.models import NewsItem, Source
from app.services.dedup import make_content_hash


def parse_datetime(entry) -> datetime | None:
    # feedparser provides "published_parsed" sometimes
    if getattr(entry, "published_parsed", None):
        return datetime(*entry.published_parsed[:6])
    return None


def fetch_rss_items(source: Source) -> Iterable[dict]:
    feed = feedparser.parse(source.url)
    for entry in feed.entries:
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