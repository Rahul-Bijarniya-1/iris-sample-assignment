"""
The pgvector migration must apply cleanly on a fresh database.

Mirrors test_migration_chain.py: `alembic upgrade head` on a genuinely
empty database must create the `vector` extension, the embedding columns
on `news_articles`, the HNSW index, and the `news_signals` table.
"""

import pytest


@pytest.mark.integration
def test_vector_extension_is_created(migrated_database, pg_query):
    rows = pg_query(
        migrated_database,
        "select extname from pg_extension where extname = 'vector'",
    )

    assert rows, "CREATE EXTENSION IF NOT EXISTS vector did not run"


@pytest.mark.integration
def test_news_articles_has_embedding_columns(migrated_database, pg_query):
    rows = pg_query(
        migrated_database,
        """
        select column_name
        from information_schema.columns
        where table_schema = 'iris_core' and table_name = 'news_articles'
        """,
    )

    columns = {row[0] for row in rows}

    assert {
        "title_en",
        "summary_en",
        "embedding",
        "embedding_model",
        "embedding_hash",
        "embedded_at",
    } <= columns


@pytest.mark.integration
def test_embedding_has_an_hnsw_cosine_index(migrated_database, pg_query):
    rows = pg_query(
        migrated_database,
        """
        select indexdef
        from pg_indexes
        where schemaname = 'iris_core'
          and tablename = 'news_articles'
          and indexdef ilike '%%hnsw%%'
        """,
    )

    assert rows, "no HNSW index found on news_articles"
    assert "vector_cosine_ops" in rows[0][0]


@pytest.mark.integration
def test_news_signals_table_exists(migrated_database, schema_tables):
    assert "news_signals" in schema_tables(migrated_database, "iris_core")


@pytest.mark.integration
def test_news_signals_has_expected_columns(migrated_database, pg_query):
    rows = pg_query(
        migrated_database,
        """
        select column_name
        from information_schema.columns
        where table_schema = 'iris_core' and table_name = 'news_signals'
        """,
    )

    columns = {row[0] for row in rows}

    assert {
        "article_id",
        "expansion",
        "power",
        "renewable",
        "retrofit",
        "investment",
        "capacity_mw",
        "confidence",
        "city",
        "company",
    } <= columns
