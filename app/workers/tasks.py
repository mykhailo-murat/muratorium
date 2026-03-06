import logging
from datetime import datetime, timedelta, timezone
from html import escape

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.db.models import ClusterItem, NewsItem, PublishedMessage, Source, StoryCluster
from app.db.session import SessionLocal
from app.services.clustering import assign_item_to_cluster
from app.services.digest_llm import DigestCandidate, select_digest_items
from app.services.llm_scoring import ScoreInput, score_batch
from app.services.publish_guard import mark_published, was_published
from app.services.rss_collector import fetch_rss_items, to_news_item
from app.services.scoring import calc_score
from app.workers.celery_app import celery
from app.workers.publisher import build_digest_message, publish_to_telegram, send_telegram_text

logger = logging.getLogger(__name__)


def _to_final_score(importance: int, urgency: int, source_count: int, avg_trust: float) -> int:
    base = int(((importance * 0.6) + (urgency * 0.4)) * 10)
    source_bonus = min(max(source_count - 1, 0) * 5, 15)
    trust_bonus = min(int(avg_trust * 2), 20)
    return min(base + source_bonus + trust_bonus, 100)


def _urgent_slots_left(db) -> int:
    if settings.urgent_rate_limit_per_hour <= 0:
        return 0
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    published_last_hour = db.scalar(
        select(func.count(PublishedMessage.id)).where(
            PublishedMessage.mode == "urgent",
            PublishedMessage.created_at >= since,
        )
    )
    return max(settings.urgent_rate_limit_per_hour - int(published_last_hour or 0), 0)


@celery.task(name="app.workers.tasks.poll_rss")
def poll_rss() -> int:
    created = 0
    with SessionLocal() as db:
        sources = db.scalars(
            select(Source).where(Source.kind == "rss", Source.is_enabled == True)  # noqa: E712
        ).all()
        logger.info("RSS polling cycle started: enabled_sources=%s", len(sources))

        for src in sources:
            fetched_for_source = 0
            created_for_source = 0
            duplicates_for_source = 0
            for raw in fetch_rss_items(src):
                fetched_for_source += 1
                item = to_news_item(src, raw)
                item.final_score = calc_score(src.trust_score, item.title, item.content)
                db.add(item)
                try:
                    db.flush()
                    assign_item_to_cluster(db, item=item, source=src)
                    db.commit()
                    created += 1
                    created_for_source += 1
                except IntegrityError:
                    db.rollback()
                    duplicates_for_source += 1
                    continue
            logger.info(
                "RSS source processed: source_id=%s source_name=%s fetched=%s created=%s duplicates=%s",
                src.id,
                src.name,
                fetched_for_source,
                created_for_source,
                duplicates_for_source,
            )
    logger.info("RSS polling cycle completed: created_total=%s", created)
    return created


@celery.task(name="app.workers.tasks.backfill_clusters")
def backfill_clusters(limit: int = 5000) -> int:
    created_links = 0
    with SessionLocal() as db:
        rows = db.execute(
            select(NewsItem, Source)
            .join(Source, Source.id == NewsItem.source_id)
            .outerjoin(ClusterItem, ClusterItem.news_item_id == NewsItem.id)
            .where(ClusterItem.id.is_(None))
            .order_by(NewsItem.id.asc())
            .limit(limit)
        ).all()

        for item, source in rows:
            assign_item_to_cluster(db, item=item, source=source)
            created_links += 1
        db.commit()
    return created_links


def _build_digest_lines(items, item_map: dict[int, NewsItem]) -> list[str]:
    lines: list[str] = []
    for idx, analyzed in enumerate(items, start=1):
        original = item_map.get(analyzed.news_item_id)
        if not original:
            continue
        line = (
            f"{idx}. Score: {analyzed.score}/100\n"
            f"Category: {escape(analyzed.category)}\n"
            f"{escape(analyzed.title_uk)}\n"
            f"{escape(analyzed.summary_uk)}"
        )
        if original.url:
            line += f'\n<a href="{escape(original.url, quote=True)}">source</a>'
        lines.append(line)
    return lines


@celery.task(name="app.workers.tasks.cleanup_old_records")
def cleanup_old_records() -> int:
    if not settings.cleanup_enabled:
        return 0

    now_utc = datetime.now(timezone.utc)
    published_cutoff = now_utc - timedelta(days=settings.cleanup_keep_published_days)
    unpublished_cutoff = now_utc - timedelta(days=settings.cleanup_keep_unpublished_days)
    messages_cutoff = now_utc - timedelta(days=settings.cleanup_keep_messages_days)

    with SessionLocal() as db:
        old_news_ids = db.scalars(
            select(NewsItem.id)
            .where(
                (
                    (NewsItem.is_published == True)  # noqa: E712
                    & (NewsItem.published_to_telegram_at.is_not(None))
                    & (NewsItem.published_to_telegram_at < published_cutoff)
                )
                | (
                    (NewsItem.is_published == False)  # noqa: E712
                    & (NewsItem.ingested_at < unpublished_cutoff)
                )
            )
            .limit(settings.cleanup_batch_size)
        ).all()

        deleted_news = 0
        deleted_clusters = 0
        deleted_messages = 0

        if old_news_ids:
            db.execute(delete(ClusterItem).where(ClusterItem.news_item_id.in_(old_news_ids)))
            deleted_news = db.execute(
                delete(NewsItem).where(NewsItem.id.in_(old_news_ids))
            ).rowcount or 0

            orphan_cluster_ids = db.scalars(
                select(StoryCluster.id)
                .outerjoin(ClusterItem, ClusterItem.cluster_id == StoryCluster.id)
                .group_by(StoryCluster.id)
                .having(func.count(ClusterItem.id) == 0)
                .limit(settings.cleanup_batch_size)
            ).all()
            if orphan_cluster_ids:
                deleted_clusters = db.execute(
                    delete(StoryCluster).where(StoryCluster.id.in_(orphan_cluster_ids))
                ).rowcount or 0

        deleted_messages = db.execute(
            delete(PublishedMessage).where(PublishedMessage.created_at < messages_cutoff)
        ).rowcount or 0

        db.commit()

    return int(deleted_news + deleted_clusters + deleted_messages)


@celery.task(name="app.workers.tasks.process_urgent_candidates")
def process_urgent_candidates() -> int:
    if not settings.fast_lane_enabled:
        return 0
    if not settings.openai_api_key:
        logger.warning("OpenAI key is missing; urgent lane is skipped")
        return 0
    if not settings.llm_enabled:
        logger.info("LLM is disabled; urgent lane is skipped")
        return 0

    published_now = 0
    with SessionLocal() as db:
        slots_left = _urgent_slots_left(db)
        logger.info("Urgent processing cycle started: slots_left=%s", slots_left)
        if slots_left <= 0:
            logger.info("Urgent processing skipped: no rate-limit slots left")
            return 0

        candidates = db.execute(
            select(StoryCluster, NewsItem)
            .join(NewsItem, NewsItem.id == StoryCluster.representative_news_id)
            .where(
                StoryCluster.source_count >= settings.fast_min_sources,
                NewsItem.is_published == False,  # noqa: E712
            )
            .order_by(StoryCluster.last_seen_at.desc())
            .limit(max(settings.llm_batch_size, 20))
        ).all()
        logger.info("Urgent candidates selected: count=%s", len(candidates))
        if not candidates:
            return 0

        score_inputs = [
            ScoreInput(
                cluster_id=cluster.id,
                source="cluster",
                title=item.title,
                content=item.content,
            )
            for cluster, item in candidates
        ]
        try:
            logger.info("Sending urgent candidates to OpenAI: batch_size=%s", len(score_inputs))
            scores = score_batch(score_inputs)
            logger.info("OpenAI urgent scoring result received: scored_clusters=%s", len(scores))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Urgent LLM scoring failed: %s", exc)
            return 0

        for cluster, item in candidates:
            if published_now >= slots_left:
                break

            msg_key = f"urgent:cluster:{cluster.id}"
            if was_published(db, channel="telegram", message_key=msg_key):
                continue

            scored = scores.get(cluster.id)
            if not scored:
                logger.warning("No LLM score for cluster=%s", cluster.id)
                continue

            final_score = _to_final_score(
                scored.importance,
                scored.urgency,
                cluster.source_count,
                cluster.avg_trust_score,
            )
            cluster.last_scored_at = datetime.now(timezone.utc)
            cluster.last_urgency = scored.urgency
            cluster.last_confidence = scored.confidence
            cluster.last_score = final_score
            item.title = scored.title_uk[:512]
            item.short_summary = scored.summary_uk[:512]
            item.category = scored.category[:64]
            item.importance = scored.importance
            item.urgency = scored.urgency
            item.confidence = scored.confidence
            item.llm_reason = scored.reason[:512]
            item.llm_model = settings.openai_model[:128]
            item.llm_scored_at = datetime.now(timezone.utc)
            item.final_score = final_score
            logger.info(
                "Urgent score computed: cluster=%s importance=%s urgency=%s confidence=%.2f final_score=%s category=%s",
                cluster.id,
                scored.importance,
                scored.urgency,
                scored.confidence,
                final_score,
                scored.category,
            )

            if (
                scored.urgency < settings.urgent_threshold
                or scored.confidence < settings.confidence_threshold
                or final_score < settings.fast_score_threshold
            ):
                logger.info(
                    "Urgent publish skipped by thresholds: cluster=%s urgency=%s/%s confidence=%.2f/%.2f final_score=%s/%s",
                    cluster.id,
                    scored.urgency,
                    settings.urgent_threshold,
                    scored.confidence,
                    settings.confidence_threshold,
                    final_score,
                    settings.fast_score_threshold,
                )
                continue

            try:
                publish_to_telegram(item.id)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Urgent publish failed for cluster=%s: %s", cluster.id, exc)
                db.rollback()
                continue

            now_utc = datetime.now(timezone.utc)
            for linked_item in db.scalars(
                select(NewsItem)
                .join(ClusterItem, ClusterItem.news_item_id == NewsItem.id)
                .where(ClusterItem.cluster_id == cluster.id)
            ).all():
                if linked_item.id != item.id:
                    linked_item.category = item.category
                    linked_item.llm_model = item.llm_model
                    linked_item.llm_scored_at = item.llm_scored_at
                linked_item.is_published = True
                linked_item.published_to_telegram_at = now_utc

            mark_published(
                db,
                channel="telegram",
                message_key=msg_key,
                mode="urgent",
                payload_ref=str(cluster.id),
            )
            db.commit()
            published_now += 1
            logger.info("Urgent cluster published: cluster=%s published_now=%s", cluster.id, published_now)

    logger.info("Urgent processing cycle completed: published_now=%s", published_now)
    return published_now


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

        now_utc = datetime.now(timezone.utc)
        digest_key = f"digest:{now_utc.strftime('%Y%m%d%H%M')}"
        if was_published(db, channel="telegram", message_key=digest_key):
            return 0

        item_map = {item.id: item for item, _ in deduped}
        digest_lines = _build_digest_lines(selected, item_map)
        digest_text = build_digest_message(digest_lines)
        send_telegram_text(digest_text, parse_mode="HTML")

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

        mark_published(
            db,
            channel="telegram",
            message_key=digest_key,
            mode="digest",
            payload_ref=str(published_count),
        )
        db.commit()
        return published_count


@celery.task(name="app.workers.tasks.publish_to_telegram")
def publish_to_telegram_task(news_item_id: int) -> None:
    publish_to_telegram.delay(news_item_id)
