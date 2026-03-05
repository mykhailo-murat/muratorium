import logging
from html import escape
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.models import NewsItem, Source
from app.db.session import SessionLocal
from app.services.digest_llm import DigestCandidate, select_digest_items
from app.services.rss_collector import fetch_rss_items, to_news_item
from app.services.scoring import calc_score
from app.workers.celery_app import celery
from app.workers.publisher import build_digest_message, publish_to_telegram, send_telegram_text

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.tasks.poll_rss")
def poll_rss() -> int:
    created = 0
    with SessionLocal() as db:
        sources = db.scalars(
            select(Source).where(Source.kind == "rss", Source.is_enabled == True)  # noqa: E712
        ).all()

        for src in sources:
            for raw in fetch_rss_items(src):
                item = to_news_item(src, raw)
                item.final_score = calc_score(src.trust_score, item.title, item.content)
                db.add(item)
                try:
                    db.commit()
                    created += 1
                except IntegrityError:
                    db.rollback()
                    continue
    return created


def _build_digest_lines(items, item_map: dict[int, NewsItem]) -> list[str]:
    lines: list[str] = []
    for idx, analyzed in enumerate(items, start=1):
        original = item_map.get(analyzed.news_item_id)
        if not original:
            continue
        line = (
            f"{idx}. Оцінка: {analyzed.score}/100\n"
            f"Категорія: {escape(analyzed.category)}\n"
            f"{escape(analyzed.title_uk)}\n"
            f"{escape(analyzed.summary_uk)}"
        )
        if original.url:
            line += f'\n<a href="{escape(original.url, quote=True)}">source</a>'
        lines.append(line)
    return lines


@celery.task(name="app.workers.tasks.analyze_and_publish_digest")
def analyze_and_publish_digest(test_mode: bool = False) -> int:
    if not settings.openai_api_key:
        logger.warning("OpenAI key is missing; digest is skipped")
        return 0
    if not (settings.llm_enabled or test_mode):
        logger.info("LLM is disabled; digest is skipped")
        return 0

    window_hours = settings.digest_window_hours if not test_mode else 48
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    with SessionLocal() as db:
        rows = db.execute(
            select(NewsItem, Source)
            .join(Source, Source.id == NewsItem.source_id)
            .where(
                NewsItem.ingested_at >= since,
                NewsItem.is_published == False,  # noqa: E712
            )
            .order_by(NewsItem.ingested_at.desc())
            .limit(settings.digest_max_candidates)
        ).all()

        if not rows:
            return 0

        deduped: list[tuple[NewsItem, Source]] = []
        seen_hashes: set[str] = set()
        for item, source in rows:
            if item.content_hash in seen_hashes:
                continue
            seen_hashes.add(item.content_hash)
            deduped.append((item, source))

        candidates = [
            DigestCandidate(
                news_item_id=item.id,
                source=source.name,
                title=item.title,
                content=item.content,
                url=item.url,
            )
            for item, source in deduped
        ]

        try:
            selected = select_digest_items(
                candidates,
                top_n=settings.digest_top_n,
                min_score=settings.digest_min_score,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Digest LLM processing failed: %s", exc)
            return 0

        if not selected:
            logger.info("Digest has no items >= %s", settings.digest_min_score)
            return 0

        item_map = {item.id: item for item, _ in deduped}
        digest_lines = _build_digest_lines(selected, item_map)
        digest_text = build_digest_message(digest_lines)
        send_telegram_text(digest_text, parse_mode="HTML")

        now_utc = datetime.now(timezone.utc)
        published_count = 0
        for analyzed in selected:
            item = item_map.get(analyzed.news_item_id)
            if not item:
                continue
            item.final_score = analyzed.score
            item.short_summary = analyzed.summary_uk[:512]
            item.category = analyzed.category[:64]
            item.llm_reason = analyzed.reason_uk[:512]
            item.llm_model = settings.openai_model[:128]
            item.llm_scored_at = now_utc
            item.is_published = True
            item.published_to_telegram_at = now_utc
            published_count += 1

        db.commit()
        return published_count


@celery.task(name="app.workers.tasks.publish_to_telegram")
def publish_to_telegram_task(news_item_id: int) -> None:
    publish_to_telegram.delay(news_item_id)
