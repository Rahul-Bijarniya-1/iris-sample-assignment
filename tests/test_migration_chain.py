"""
Fresh-database migration tests.

`alembic upgrade head` must succeed against a genuinely empty database. The
root revision (dda1cbd31839) creates tables in the `app` schema, so some
migration has to create that schema before using it.

These tests create and drop their own uniquely-named scratch database. They
never touch the project database.
"""

import os
import subprocess
import uuid
from pathlib import Path

import psycopg
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]

PG_HOST = "localhost"
PG_PORT = 5433
PG_USER = "postgres"
PG_PASSWORD = "postgres"

ADMIN_URL = (
    f"postgresql://{PG_USER}:{PG_PASSWORD}"
    f"@{PG_HOST}:{PG_PORT}/postgres"
)

EXPECTED_IRIS_CORE_TABLES = {
    "energy_assets",
    "facilities",
    "land_values",
    "news_articles",
    "news_matches",
    "osm_infrastructure",
    "power_infrastructure",
}


def scratch_url(database: str) -> str:
    return (
        f"postgresql://{PG_USER}:{PG_PASSWORD}"
        f"@{PG_HOST}:{PG_PORT}/{database}"
    )


@pytest.fixture
def scratch_database():
    """
    Create an empty PostGIS-enabled database, yield its name, then drop it.
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


def table_names(database: str, schema: str) -> set[str]:
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


@pytest.mark.integration
def test_upgrade_head_succeeds_on_a_fresh_database(scratch_database):
    """
    The whole chain applies cleanly with no manual schema preparation.
    """

    result = run_alembic_upgrade(scratch_database)

    assert result.returncode == 0, (
        "alembic upgrade head failed on a fresh database:\n"
        f"{result.stdout[-2000:]}\n{result.stderr[-3000:]}"
    )


@pytest.mark.integration
def test_upgrade_head_creates_the_application_tables(scratch_database):
    """
    A fresh migration run produces the iris_core tables the models target.
    """

    result = run_alembic_upgrade(scratch_database)
    assert result.returncode == 0, result.stderr[-3000:]

    assert EXPECTED_IRIS_CORE_TABLES <= table_names(
        scratch_database, "iris_core"
    )
