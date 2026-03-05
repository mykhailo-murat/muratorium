"""add fast lane tables

Revision ID: 20260305_0002
Revises: 20260304_0001
Create Date: 2026-03-05 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260305_0002"
down_revision = "20260304_0001"
branch_labels = None
depends_on = None


def _table_exists(inspector: sa.Inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def _index_exists(inspector: sa.Inspector, table: str, index_name: str) -> bool:
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "story_clusters"):
        op.create_table(
            "story_clusters",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("cluster_key", sa.String(length=64), nullable=False),
            sa.Column("representative_news_id", sa.Integer(), nullable=True),
            sa.Column("source_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("avg_trust_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("last_scored_at", sa.DateTime(), nullable=True),
            sa.Column("last_urgency", sa.Integer(), nullable=True),
            sa.Column("last_confidence", sa.Float(), nullable=True),
            sa.Column("last_score", sa.Integer(), nullable=True),
            sa.UniqueConstraint("cluster_key", name="uq_story_cluster_key"),
        )
        op.create_index("ix_story_clusters_cluster_key", "story_clusters", ["cluster_key"])

    if not _table_exists(inspector, "cluster_items"):
        op.create_table(
            "cluster_items",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("cluster_id", sa.Integer(), nullable=False),
            sa.Column("news_item_id", sa.Integer(), nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["cluster_id"], ["story_clusters.id"]),
            sa.ForeignKeyConstraint(["news_item_id"], ["news_items.id"]),
            sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
            sa.UniqueConstraint("cluster_id", "news_item_id", name="uq_cluster_news_item"),
        )
        op.create_index("ix_cluster_items_cluster_id", "cluster_items", ["cluster_id"])
        op.create_index("ix_cluster_items_news_item_id", "cluster_items", ["news_item_id"])
        op.create_index("ix_cluster_items_source_id", "cluster_items", ["source_id"])

    if not _table_exists(inspector, "published_messages"):
        op.create_table(
            "published_messages",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("channel", sa.String(length=64), nullable=False),
            sa.Column("message_key", sa.String(length=128), nullable=False),
            sa.Column("mode", sa.String(length=32), nullable=False),
            sa.Column("payload_ref", sa.String(length=128), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("channel", "message_key", name="uq_published_channel_key"),
        )
        op.create_index("ix_published_messages_channel", "published_messages", ["channel"])
        op.create_index("ix_published_messages_message_key", "published_messages", ["message_key"])
        op.create_index("ix_published_messages_mode", "published_messages", ["mode"])

    inspector = sa.inspect(bind)
    if _table_exists(inspector, "story_clusters") and not _index_exists(
        inspector, "story_clusters", "ix_story_clusters_cluster_key"
    ):
        op.create_index("ix_story_clusters_cluster_key", "story_clusters", ["cluster_key"])


def downgrade() -> None:
    op.drop_index("ix_published_messages_mode", table_name="published_messages")
    op.drop_index("ix_published_messages_message_key", table_name="published_messages")
    op.drop_index("ix_published_messages_channel", table_name="published_messages")
    op.drop_table("published_messages")

    op.drop_index("ix_cluster_items_source_id", table_name="cluster_items")
    op.drop_index("ix_cluster_items_news_item_id", table_name="cluster_items")
    op.drop_index("ix_cluster_items_cluster_id", table_name="cluster_items")
    op.drop_table("cluster_items")

    op.drop_index("ix_story_clusters_cluster_key", table_name="story_clusters")
    op.drop_table("story_clusters")
