"""add news embeddings and signals

Revision ID: d88d670b067f
Revises: b18ad888465f
Create Date: 2026-10-25 00:00:00
"""

from typing import Sequence, Union

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d88d670b067f"

down_revision: Union[str, Sequence[str], None] = (
    "b18ad888465f"
)

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "news_articles",
        sa.Column("title_en", sa.Text(), nullable=True),
        schema="iris_core",
    )

    op.add_column(
        "news_articles",
        sa.Column("summary_en", sa.Text(), nullable=True),
        schema="iris_core",
    )

    op.add_column(
        "news_articles",
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(1536),
            nullable=True,
        ),
        schema="iris_core",
    )

    op.add_column(
        "news_articles",
        sa.Column(
            "embedding_model", sa.String(100), nullable=True
        ),
        schema="iris_core",
    )

    op.add_column(
        "news_articles",
        sa.Column(
            "embedding_hash", sa.String(64), nullable=True
        ),
        schema="iris_core",
    )

    op.add_column(
        "news_articles",
        sa.Column(
            "embedded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        schema="iris_core",
    )

    op.execute(
        """
        CREATE INDEX ix_news_articles_embedding_hnsw
        ON iris_core.news_articles
        USING hnsw (embedding vector_cosine_ops)
        """
    )

    op.create_table(
        "news_signals",
        sa.Column(
            "id", sa.Integer(), primary_key=True, autoincrement=True
        ),
        sa.Column(
            "article_id",
            sa.String(36),
            sa.ForeignKey(
                "iris_core.news_articles.id",
                ondelete="CASCADE",
            ),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "expansion", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "power", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "renewable", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "retrofit", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "investment", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("capacity_mw", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="iris_core",
    )


def downgrade() -> None:

    op.drop_table("news_signals", schema="iris_core")

    op.execute(
        "DROP INDEX IF EXISTS iris_core.ix_news_articles_embedding_hnsw"
    )

    op.drop_column("news_articles", "embedded_at", schema="iris_core")
    op.drop_column("news_articles", "embedding_hash", schema="iris_core")
    op.drop_column("news_articles", "embedding_model", schema="iris_core")
    op.drop_column("news_articles", "embedding", schema="iris_core")
    op.drop_column("news_articles", "summary_en", schema="iris_core")
    op.drop_column("news_articles", "title_en", schema="iris_core")
