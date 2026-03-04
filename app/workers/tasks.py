from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.workers.celery_app import celery
from app.db.session import SessionLocal
from app.db.models import Source, NewsItem
from app.services.rss_collector import fetch_rss_items, to_news_item
from app.services.scoring import calc_score, is_breaking
from app.services.publisher import publish_to_telegram


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

                # Fast lane
                if is_breaking(item.final_score):
                    publish_to_telegram.delay(item.id)

    return created


@celery.task(name="app.workers.tasks.publish_to_telegram")
def publish_to_telegram_task(news_item_id: int) -> None:
    publish_to_telegram(news_item_id)