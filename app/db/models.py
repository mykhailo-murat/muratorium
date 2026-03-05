from sqlalchemy import (
    String,
    Text,
    DateTime,
    Integer,
    Boolean,
    Float,
    ForeignKey,
    func,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # "rss" | "telegram"
    name: Mapped[str] = mapped_column(String(128), unique=True)
    url: Mapped[str] = mapped_column(String(512))
    trust_score: Mapped[int] = mapped_column(Integer, default=7)  # 1..10
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class NewsItem(Base):
    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_news_source_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, index=True)

    # external_id = guid for RSS, message_id for Telegram, etc.
    external_id: Mapped[str] = mapped_column(String(256), index=True)

    title: Mapped[str] = mapped_column(String(512))
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content: Mapped[str] = mapped_column(Text)

    published_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    ingested_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    # Normalization / ranking
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    final_score: Mapped[int] = mapped_column(Integer, default=0)  # 0..100
    importance: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0..10
    urgency: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0..10
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..1
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    short_summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    llm_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    llm_scored_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)

    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    published_to_telegram_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)


class StoryCluster(Base):
    __tablename__ = "story_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    representative_news_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    avg_trust_score: Mapped[float] = mapped_column(Float, default=0.0)
    first_seen_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    last_scored_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    last_urgency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ClusterItem(Base):
    __tablename__ = "cluster_items"
    __table_args__ = (
        UniqueConstraint("cluster_id", "news_item_id", name="uq_cluster_news_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("story_clusters.id"), index=True)
    news_item_id: Mapped[int] = mapped_column(ForeignKey("news_items.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())


class PublishedMessage(Base):
    __tablename__ = "published_messages"
    __table_args__ = (
        UniqueConstraint("channel", "message_key", name="uq_published_channel_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel: Mapped[str] = mapped_column(String(64), index=True)
    message_key: Mapped[str] = mapped_column(String(128), index=True)
    mode: Mapped[str] = mapped_column(String(32), index=True)  # urgent | digest
    payload_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
