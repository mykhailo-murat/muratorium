from sqlalchemy import String, Text, DateTime, Integer, Boolean, func, UniqueConstraint
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
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
