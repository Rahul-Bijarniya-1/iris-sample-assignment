"""
Settings for the TransnetBW Project Radar harvester (IRIS-SIG-30).

Every value can be overridden with a TRANSNETBW_* environment variable or the
project's .env file. Nothing here is a credential: the database URL comes
from the environment, and public_dict() masks its password before the
configuration is stored alongside a run.
"""

from datetime import date
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_USER_AGENT = (
    "IRIS-ProjectRadar/0.1 "
    "(+https://github.com/Rahul-Bijarniya-1/iris-sample-assignment)"
)


class TransnetBWSettings(BaseSettings):
    """
    Harvester configuration.

    database_url prefers TRANSNETBW_DATABASE_URL and falls back to the
    dashboard's DATABASE_URL, so the harvester can run against its own
    PostgreSQL 16 database without repointing the rest of the project.
    """

    model_config = SettingsConfigDict(
        env_prefix="TRANSNETBW_",
        env_file=".env",
        extra="ignore",
    )

    # =====================================================
    # SOURCE
    # =====================================================

    base_url: str = "https://www.transnetbw.de"

    listing_path: str = "/de/netzentwicklung/projekte/alle-projekte"

    sitemap_path: str = "/de/sitemap.xml"

    press_feed_path: str = "/de/api/press-releases"

    # =====================================================
    # POLITENESS
    # =====================================================

    user_agent: str = DEFAULT_USER_AGENT

    request_delay_s: float = Field(default=1.5, ge=0)

    timeout_s: float = Field(default=30, gt=0)

    max_retries: int = Field(default=3, ge=0)

    # =====================================================
    # SCOPE AND LIFECYCLE
    # =====================================================

    since: date = date(2020, 1, 1)

    retire_after_misses: int = Field(default=2, ge=1)

    # =====================================================
    # QUALITY GATES
    # =====================================================

    gate_min_listing_cards: int = Field(default=15, ge=0)

    gate_max_fetch_failure_ratio: float = Field(default=0.30, ge=0, le=1)

    gate_min_resolved: int = Field(default=1, ge=0)

    gate_max_discovery_gap: int = Field(default=5, ge=0)

    # Below this, the press feed is treated as truncated: its items are
    # still processed, but nothing is retired on the strength of it.
    gate_min_feed_items: int = Field(default=100, ge=0)

    # =====================================================
    # GEOCODING
    # =====================================================

    enable_nominatim: bool = False

    # =====================================================
    # STORAGE
    # =====================================================

    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "TRANSNETBW_DATABASE_URL",
            "DATABASE_URL",
        ),
    )

    raw_dir: Path = Path("data/raw/transnetbw")

    artifacts_dir: Path = Path("artifacts/transnetbw")

    fixtures_dir: Path = Path("fixtures/transnetbw")

    # =====================================================
    # DERIVED
    # =====================================================

    def url(self, path: str) -> str:
        """
        Absolute URL for a site path.
        """

        return self.base_url.rstrip("/") + path

    def public_dict(self) -> dict:
        """
        The configuration as stored in iris_staging.ingest_run.config.

        Passwords are masked: run records are shared, credentials are not.
        """

        values = self.model_dump(mode="json")

        values["database_url"] = mask_password(self.database_url)

        return values


def mask_password(url: str | None) -> str | None:
    """
    Replace the password in a database URL with ***.
    """

    if not url:
        return url

    parts = urlsplit(url)

    if parts.password is None:
        return url

    host = parts.hostname or ""

    if parts.port:
        host = f"{host}:{parts.port}"

    user = parts.username or ""

    return urlunsplit(
        (
            parts.scheme,
            f"{user}:***@{host}",
            parts.path,
            parts.query,
            parts.fragment,
        )
    )
