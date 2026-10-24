"""
Fresh-database migration tests.

`alembic upgrade head` must succeed against a genuinely empty database. The
root revision (dda1cbd31839) creates tables in the `app` schema, so some
migration has to create that schema before using it.

Setting this project up originally required running
`CREATE SCHEMA IF NOT EXISTS app` by hand first; these tests exist so that
stays fixed.
"""

import pytest


EXPECTED_IRIS_CORE_TABLES = {
    "energy_assets",
    "facilities",
    "land_values",
    "news_articles",
    "news_matches",
    "osm_infrastructure",
    "power_infrastructure",
}


@pytest.mark.integration
def test_upgrade_head_succeeds_on_a_fresh_database(
    scratch_database,
    alembic_upgrade,
):
    """
    The whole chain applies cleanly with no manual schema preparation.
    """

    result = alembic_upgrade(scratch_database)

    assert result.returncode == 0, (
        "alembic upgrade head failed on a fresh database:\n"
        f"{result.stdout[-2000:]}\n{result.stderr[-3000:]}"
    )


@pytest.mark.integration
def test_upgrade_head_creates_the_application_tables(
    migrated_database,
    schema_tables,
):
    """
    A fresh migration run produces the iris_core tables the models target.
    """

    assert EXPECTED_IRIS_CORE_TABLES <= schema_tables(
        migrated_database,
        "iris_core",
    )
