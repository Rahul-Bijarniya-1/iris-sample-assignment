"""
Shared test fixtures.

Database tests create and drop their own uniquely-named scratch databases on
the local PostgreSQL server. They never touch the project database.
"""

import os
import subprocess
import uuid
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[1]

PG_HOST = "localhost"
PG_PORT = 5433
PG_USER = "postgres"
PG_PASSWORD = "postgres"

ADMIN_URL = (
    f"postgresql://{PG_USER}:{PG_PASSWORD}"
    f"@{PG_HOST}:{PG_PORT}/postgres"
)


def scratch_url(database: str) -> str:
    return (
        f"postgresql://{PG_USER}:{PG_PASSWORD}"
        f"@{PG_HOST}:{PG_PORT}/{database}"
    )


def run_alembic_upgrade(database: str) -> subprocess.CompletedProcess:
    """
    Run `alembic upgrade head` against the given database.

    alembic/env.py calls load_dotenv(), which does not override variables
    already present in the environment, so DATABASE_URL set here wins.
    """

    return subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": scratch_url(database)},
        capture_output=True,
        text=True,
    )


@pytest.fixture
def scratch_database():
    """
    An empty PostGIS-enabled database. No migrations applied.
    """

    try:
        admin = psycopg.connect(ADMIN_URL, autocommit=True)
    except psycopg.OperationalError as exc:
        pytest.skip(f"No PostgreSQL server at {PG_HOST}:{PG_PORT} ({exc})")

    name = f"nrw_dc_bi_migtest_{uuid.uuid4().hex[:8]}"

    with admin:
        admin.execute(f'CREATE DATABASE "{name}"')

    try:
        with psycopg.connect(scratch_url(name), autocommit=True) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")

        yield name

    finally:
        with psycopg.connect(ADMIN_URL, autocommit=True) as cleanup:
            cleanup.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def migrated_database(scratch_database):
    """
    A scratch database with the full migration chain applied.
    """

    result = run_alembic_upgrade(scratch_database)

    assert result.returncode == 0, (
        "migrations failed while preparing the test database:\n"
        f"{result.stderr[-3000:]}"
    )

    return scratch_database


@pytest.fixture
def alembic_upgrade():
    """
    Callable: run `alembic upgrade head` against a named database.
    """

    return run_alembic_upgrade


@pytest.fixture
def schema_tables():
    """
    Callable: the set of table names in a given database schema.
    """

    def _schema_tables(database: str, schema: str) -> set[str]:
        with psycopg.connect(scratch_url(database)) as conn:
            rows = conn.execute(
                """
                select table_name
                from information_schema.tables
                where table_schema = %s
                """,
                (schema,),
            ).fetchall()

        return {row[0] for row in rows}

    return _schema_tables


@pytest.fixture
def db_session(migrated_database):
    """
    A SQLAlchemy session bound to a freshly migrated scratch database.

    Built directly rather than through app.database.session.SessionLocal,
    which binds its engine to DATABASE_URL at import time.
    """

    engine = create_engine(scratch_url(migrated_database))

    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
    )

    session = session_factory()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()
