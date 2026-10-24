"""
Shared test fixtures.

Database tests create and drop their own uniquely-named scratch databases on
the server named in DATABASE_URL. They never touch the project database.

The server details are derived from DATABASE_URL rather than hardcoded, so
the suite follows whatever the project is configured against instead of
skipping on any machine that does not happen to use the same port.
"""

import os
import subprocess
import uuid
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import psycopg
import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


REPO_ROOT = Path(__file__).resolve().parents[1]

# Mirrors app/database/session.py and alembic/env.py, which both read
# DATABASE_URL after loading .env.
load_dotenv()

DEFAULT_PG_PORT = 5432


def server_params(url: str | None) -> dict | None:
    """
    Connection details for the server a DATABASE_URL points at.

    Returns None when there is no URL to read, so the database fixtures can
    skip instead of guessing a host and port.
    """

    if not url:
        return None

    parsed = urlsplit(url)

    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or DEFAULT_PG_PORT,
        "user": unquote(parsed.username) if parsed.username else "postgres",
        "password": (
            unquote(parsed.password) if parsed.password else ""
        ),
    }


def server_url(database: str) -> str | None:
    """
    A URL for `database` on the configured server, or None if unconfigured.
    """

    params = server_params(os.getenv("DATABASE_URL"))

    if params is None:
        return None

    # Re-encode: credentials were decoded by server_params, and a password
    # containing reserved characters would otherwise produce a broken URL.
    user = quote(params["user"], safe="")
    password = quote(params["password"], safe="")

    return (
        "postgresql://"
        f"{user}:{password}"
        f"@{params['host']}:{params['port']}/{database}"
    )


def require_server_url(database: str) -> str:
    url = server_url(database)

    if url is None:
        pytest.skip("DATABASE_URL is not set, so there is no server to test")

    return url


def scratch_url(database: str) -> str:
    return require_server_url(database)


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

    admin_url = require_server_url("postgres")

    try:
        admin = psycopg.connect(admin_url, autocommit=True)
    except psycopg.OperationalError as exc:
        params = server_params(os.getenv("DATABASE_URL"))
        pytest.skip(
            f"No reachable PostgreSQL server at "
            f"{params['host']}:{params['port']} ({exc})"
        )

    name = f"nrw_dc_bi_migtest_{uuid.uuid4().hex[:8]}"

    with admin:
        admin.execute(f'CREATE DATABASE "{name}"')

    try:
        with psycopg.connect(scratch_url(name), autocommit=True) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")

        yield name

    finally:
        with psycopg.connect(admin_url, autocommit=True) as cleanup:
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
def server_params_from_url():
    """
    Callable: parse server connection details out of a DATABASE_URL.
    """

    return server_params


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
