from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from rapidfuzz import fuzz

from app.core.config import settings
from app.db.models import ClusterItem, NewsItem, Source, StoryCluster
from app.services.dedup import normalize_text


def assign_item_to_cluster(db: Session, item: NewsItem, source: Source) -> StoryCluster:
    cluster = db.scalar(select(StoryCluster).where(StoryCluster.cluster_key == item.content_hash))
    if not cluster:
        cluster = _find_similar_cluster(db, title=item.title)
    now_utc = datetime.now(timezone.utc)

    if not cluster:
        cluster = StoryCluster(
            cluster_key=item.content_hash,
            representative_news_id=item.id,
            source_count=1,
            avg_trust_score=float(source.trust_score),
            first_seen_at=now_utc,
            last_seen_at=now_utc,
        )
        db.add(cluster)
        db.flush()
    else:
        cluster.last_seen_at = now_utc
        if not cluster.representative_news_id:
            cluster.representative_news_id = item.id

    exists = db.scalar(
        select(ClusterItem.id).where(
            ClusterItem.cluster_id == cluster.id,
            ClusterItem.news_item_id == item.id,
        )
    )
    if not exists:
        db.add(
            ClusterItem(
                cluster_id=cluster.id,
                news_item_id=item.id,
                source_id=source.id,
            )
        )
        db.flush()

    _refresh_cluster_metrics(db, cluster.id)
    return cluster


def _find_similar_cluster(db: Session, title: str) -> StoryCluster | None:
    probe = normalize_text(title)
    if not probe:
        return None

    rows = db.execute(
        select(StoryCluster, NewsItem.title)
        .join(NewsItem, NewsItem.id == StoryCluster.representative_news_id)
        .order_by(StoryCluster.last_seen_at.desc())
        .limit(500)
    ).all()
    for cluster, rep_title in rows:
        if not rep_title:
            continue
        score = fuzz.token_set_ratio(probe, normalize_text(rep_title))
        if score >= settings.fast_title_similarity:
            return cluster
    return None


def _refresh_cluster_metrics(db: Session, cluster_id: int) -> None:
    row = db.execute(
        select(
            func.count(func.distinct(ClusterItem.source_id)),
            func.coalesce(func.avg(Source.trust_score), 0.0),
        )
        .join(Source, Source.id == ClusterItem.source_id)
        .where(ClusterItem.cluster_id == cluster_id)
    ).one()
    source_count, avg_trust = row

    cluster = db.scalar(select(StoryCluster).where(StoryCluster.id == cluster_id))
    if not cluster:
        return
    cluster.source_count = int(source_count or 0)
    cluster.avg_trust_score = float(avg_trust or 0.0)
