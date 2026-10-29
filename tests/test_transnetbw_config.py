"""
Harvester settings: where the harvester writes, and what it records about
itself.

The harvester must never silently fall onto the dashboard database when a
dedicated staging database is configured, and the configuration it stores in
iris_staging.ingest_run must never carry a password.
"""

from datetime import date

import pytest
from pydantic import ValidationError

from app.transnetbw.config import TransnetBWSettings


STAGING_URL = "postgresql://postgres:s3cret@localhost:5434/iris_signals"
DASHBOARD_URL = "postgresql://postgres:postgres@localhost:5433/nrw_dc_bi"


@pytest.fixture
def clean_env(monkeypatch):
    """
    tests/conftest.py loads .env into the process environment, so every
    TRANSNETBW_* and DATABASE_URL value from this machine is visible here.
    """

    monkeypatch.delenv("TRANSNETBW_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    return monkeypatch


def test_the_staging_url_wins_over_the_dashboard_url(clean_env):
    clean_env.setenv("DATABASE_URL", DASHBOARD_URL)
    clean_env.setenv("TRANSNETBW_DATABASE_URL", STAGING_URL)

    settings = TransnetBWSettings(_env_file=None)

    assert settings.database_url == STAGING_URL


def test_the_dashboard_url_is_the_fallback(clean_env):
    clean_env.setenv("DATABASE_URL", DASHBOARD_URL)

    settings = TransnetBWSettings(_env_file=None)

    assert settings.database_url == DASHBOARD_URL


def test_no_database_url_at_all_is_allowed_for_offline_parsing(clean_env):
    """
    Parsing and classifying fixtures needs no database, so missing
    configuration must not fail at construction time.
    """

    settings = TransnetBWSettings(_env_file=None)

    assert settings.database_url is None


def test_since_is_read_as_a_calendar_date(clean_env):
    clean_env.setenv("TRANSNETBW_SINCE", "2022-03-01")

    settings = TransnetBWSettings(_env_file=None)

    assert settings.since == date(2022, 3, 1)


@pytest.mark.parametrize(
    "variable, value",
    [
        ("TRANSNETBW_REQUEST_DELAY_S", "-1"),
        ("TRANSNETBW_GATE_MAX_FETCH_FAILURE_RATIO", "1.5"),
        ("TRANSNETBW_RETIRE_AFTER_MISSES", "0"),
    ],
)
def test_nonsensical_values_are_rejected(clean_env, variable, value):
    """
    A negative politeness delay, a failure ratio above 100 % or retiring
    records on the very first miss would each defeat a safety property.
    """

    clean_env.setenv(variable, value)

    with pytest.raises(ValidationError):
        TransnetBWSettings(_env_file=None)


def test_the_recorded_configuration_hides_the_password(clean_env):
    clean_env.setenv("TRANSNETBW_DATABASE_URL", STAGING_URL)

    recorded = TransnetBWSettings(_env_file=None).public_dict()

    assert "s3cret" not in str(recorded)
    assert recorded["database_url"] == (
        "postgresql://postgres:***@localhost:5434/iris_signals"
    )
