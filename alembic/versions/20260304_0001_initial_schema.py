"""initial schema

Revision ID: 20260304_0001
Revises:
Create Date: 2026-03-04 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260304_0001"
down_revision = None
branch_labels = None
depends_on = None


def _table_exists(inspector: sa.Inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def _column_exists(inspector: sa.Inspector, table: str, column: str) -> bool:
    return any(col["name"] == column for col in inspector.get_columns(table))


def _index_exists(inspector: sa.Inspector, table: str, index_name: str) -> bool:
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table))


def _unique_exists(inspector: sa.Inspector, table: str, unique_name: str) -> bool:
    return any(uc["name"] == unique_name for uc in inspector.get_unique_constraints(table))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _table_exists(inspector, "sources"):
        op.create_table(
            "sources",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("url", sa.String(length=512), nullable=False),
            sa.Column("trust_score", sa.Integer(), nullable=False, server_default="7"),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint("name", name="uq_sources_name"),
        )
        op.create_index("ix_sources_kind", "sources", ["kind"])
    else:
        if not _index_exists(inspector, "sources", "ix_sources_kind"):
            op.create_index("ix_sources_kind", "sources", ["kind"])

    if not _table_exists(inspector, "news_items"):
        op.create_table(
            "news_items",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("source_id", sa.Integer(), nullable=False),
            sa.Column("external_id", sa.String(length=256), nullable=False),
            sa.Column("title", sa.String(length=512), nullable=False),
            sa.Column("url", sa.String(length=1024), nullable=True),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.Column("ingested_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("final_score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("importance", sa.Integer(), nullable=True),
            sa.Column("urgency", sa.Integer(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("category", sa.String(length=64), nullable=True),
            sa.Column("short_summary", sa.String(length=512), nullable=True),
            sa.Column("llm_reason", sa.String(length=512), nullable=True),
            sa.Column("llm_model", sa.String(length=128), nullable=True),
            sa.Column("llm_scored_at", sa.DateTime(), nullable=True),
            sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("published_to_telegram_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("source_id", "external_id", name="uq_news_source_external"),
        )
        op.create_index("ix_news_items_source_id", "news_items", ["source_id"])
        op.create_index("ix_news_items_external_id", "news_items", ["external_id"])
        op.create_index("ix_news_items_content_hash", "news_items", ["content_hash"])
    else:
        optional_columns: list[tuple[str, sa.types.TypeEngine]] = [
            ("importance", sa.Integer()),
            ("urgency", sa.Integer()),
            ("confidence", sa.Float()),
            ("category", sa.String(length=64)),
            ("short_summary", sa.String(length=512)),
            ("llm_reason", sa.String(length=512)),
            ("llm_model", sa.String(length=128)),
            ("llm_scored_at", sa.DateTime()),
            ("published_to_telegram_at", sa.DateTime()),
        ]
        for column_name, column_type in optional_columns:
            if not _column_exists(inspector, "news_items", column_name):
                op.add_column("news_items", sa.Column(column_name, column_type, nullable=True))

        if not _index_exists(inspector, "news_items", "ix_news_items_source_id"):
            op.create_index("ix_news_items_source_id", "news_items", ["source_id"])
        if not _index_exists(inspector, "news_items", "ix_news_items_external_id"):
            op.create_index("ix_news_items_external_id", "news_items", ["external_id"])
        if not _index_exists(inspector, "news_items", "ix_news_items_content_hash"):
            op.create_index("ix_news_items_content_hash", "news_items", ["content_hash"])
        if not _unique_exists(inspector, "news_items", "uq_news_source_external"):
            op.create_unique_constraint(
                "uq_news_source_external",
                "news_items",
                ["source_id", "external_id"],
            )


def downgrade() -> None:
    op.drop_index("ix_news_items_content_hash", table_name="news_items")
    op.drop_index("ix_news_items_external_id", table_name="news_items")
    op.drop_index("ix_news_items_source_id", table_name="news_items")
    op.drop_table("news_items")
    op.drop_index("ix_sources_kind", table_name="sources")
    op.drop_table("sources")
