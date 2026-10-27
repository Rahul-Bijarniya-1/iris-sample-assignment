"""
iris_staging — the landing zone for external signals.

signal_ingest is source-agnostic: every harvester writes one row per source
record, keyed by (source_system, source_record_id), with source-specific
facts in `attributes`. The TransnetBW Project Radar (IRIS-SIG-30) is the
first writer.

Around it:

    signal_ingest_version   one row per distinct content version of a record
    ingest_run              one row per harvester run, written even when the
                            run's data is rolled back
    ingest_issue            every error, warning and exclusion of a run
    source_document         fetch ledger: what was fetched when, and the
                            sitemap lastmod it was fetched at — the basis of
                            incremental runs
    ref_region              reference boundaries; signal geometry must lie
                            inside its region (enforced by a trigger, see the
                            migration)

The schema is created by alembic/versions/c41f7a2e9b10_create_iris_staging.py.
"""

import uuid
from datetime import date, datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.database.entity import BaseEntity


SCHEMA = "iris_staging"

RECORD_KINDS = ("project", "press_release")

SIGNAL_TYPES = ("grid_capacity_constraint", "transformer_modernization")

PROJECT_STAGES = ("planning", "approval", "construction", "in_operation", "unknown")

REVIEW_STATUSES = ("auto", "needs_review")

LOCATION_STATUSES = ("resolved", "ambiguous", "unresolved", "invalid_coordinates")

LOCATION_PRECISIONS = ("substation", "municipality")

LOCATION_METHODS = ("gazetteer", "nominatim", "via_project")

RUN_MODES = ("live", "offline")

RUN_STATUSES = ("running", "succeeded", "partial", "failed", "refused")

ISSUE_SEVERITIES = ("error", "warning", "info")

DOC_KINDS = (
    "robots",
    "sitemap",
    "listing",
    "feed",
    "project_overview",
    "project_portrait",
    "press_article",
)

DOC_OUTCOMES = ("parsed", "excluded", "error")


def one_of(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class RefRegion(Base):

    __tablename__ = "ref_region"

    __table_args__ = (
        Index("idx_ref_region_geom", "geom", postgresql_using="gist"),
        {"schema": SCHEMA},
    )

    region_code: Mapped[str] = mapped_column(Text, primary_key=True)

    name: Mapped[str] = mapped_column(Text, nullable=False)

    geom = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=25832, spatial_index=False),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(Text, nullable=False)

    licence: Mapped[str] = mapped_column(Text, nullable=False)

    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class IngestRun(Base):

    __tablename__ = "ingest_run"

    __table_args__ = (
        CheckConstraint(one_of("mode", RUN_MODES), name="ck_ingest_run_mode"),
        CheckConstraint(one_of("status", RUN_STATUSES), name="ck_ingest_run_status"),
        Index("idx_ingest_run_source_started", "source_system", "started_at"),
        {"schema": SCHEMA},
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    source_system: Mapped[str] = mapped_column(Text, nullable=False)

    mode: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(Text, nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    exit_code: Mapped[int | None] = mapped_column(Integer)

    stats: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)

    gates: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)

    config: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)

    code_version: Mapped[str | None] = mapped_column(Text)


class IngestIssue(Base):

    __tablename__ = "ingest_issue"

    __table_args__ = (
        CheckConstraint(one_of("severity", ISSUE_SEVERITIES), name="ck_ingest_issue_severity"),
        Index("idx_ingest_issue_run", "run_id"),
        Index("idx_ingest_issue_code", "code"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.ingest_run.run_id", ondelete="CASCADE"),
        nullable=False,
    )

    severity: Mapped[str] = mapped_column(Text, nullable=False)

    code: Mapped[str] = mapped_column(Text, nullable=False)

    source_record_id: Mapped[str | None] = mapped_column(Text)

    source_url: Mapped[str | None] = mapped_column(Text)

    message: Mapped[str] = mapped_column(Text, nullable=False)

    context: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class SourceDocument(Base):

    __tablename__ = "source_document"

    __table_args__ = (
        CheckConstraint(one_of("doc_kind", DOC_KINDS), name="ck_source_document_kind"),
        CheckConstraint(
            f"last_outcome IS NULL OR {one_of('last_outcome', DOC_OUTCOMES)}",
            name="ck_source_document_outcome",
        ),
        {"schema": SCHEMA},
    )

    url: Mapped[str] = mapped_column(Text, primary_key=True)

    source_system: Mapped[str] = mapped_column(Text, nullable=False)

    doc_kind: Mapped[str] = mapped_column(Text, nullable=False)

    sitemap_lastmod: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    last_http_status: Mapped[int | None] = mapped_column(Integer)

    raw_sha256: Mapped[str | None] = mapped_column(String(64))

    last_outcome: Mapped[str | None] = mapped_column(Text)

    last_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.ingest_run.run_id"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class SignalIngest(BaseEntity):

    __tablename__ = "signal_ingest"

    __table_args__ = (
        UniqueConstraint("source_system", "source_record_id", name="uq_signal_ingest_source_record"),
        CheckConstraint(one_of("record_kind", RECORD_KINDS), name="ck_signal_ingest_record_kind"),
        CheckConstraint(one_of("signal_type", SIGNAL_TYPES), name="ck_signal_ingest_signal_type"),
        CheckConstraint(one_of("project_stage", PROJECT_STAGES), name="ck_signal_ingest_project_stage"),
        CheckConstraint(one_of("review_status", REVIEW_STATUSES), name="ck_signal_ingest_review_status"),
        CheckConstraint(one_of("location_status", LOCATION_STATUSES), name="ck_signal_ingest_location_status"),
        CheckConstraint(
            f"location_precision IS NULL OR {one_of('location_precision', LOCATION_PRECISIONS)}",
            name="ck_signal_ingest_location_precision",
        ),
        CheckConstraint(
            f"location_method IS NULL OR {one_of('location_method', LOCATION_METHODS)}",
            name="ck_signal_ingest_location_method",
        ),
        CheckConstraint(
            "(location_status = 'resolved') = (geom IS NOT NULL)",
            name="ck_signal_ingest_resolved_has_geom",
        ),
        CheckConstraint(
            "(location_precision IS NULL) = (geom IS NULL) "
            "AND (location_method IS NULL) = (geom IS NULL)",
            name="ck_signal_ingest_geom_provenance",
        ),
        CheckConstraint(
            "geom IS NULL OR (ST_SRID(geom) = 25832 AND ST_IsValid(geom))",
            name="ck_signal_ingest_geom_valid",
        ),
        CheckConstraint(
            "summary IS NULL OR char_length(summary) <= 500",
            name="ck_signal_ingest_summary_length",
        ),
        Index("idx_signal_ingest_geom", "geom", postgresql_using="gist"),
        Index("idx_signal_ingest_signal_type", "signal_type"),
        Index("idx_signal_ingest_record_kind", "record_kind"),
        Index("idx_signal_ingest_published_at", "published_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)

    source_system: Mapped[str] = mapped_column(Text, nullable=False)

    source_record_id: Mapped[str] = mapped_column(Text, nullable=False)

    record_kind: Mapped[str] = mapped_column(Text, nullable=False)

    signal_type: Mapped[str] = mapped_column(Text, nullable=False)

    project_stage: Mapped[str] = mapped_column(Text, server_default="unknown", nullable=False)

    review_status: Mapped[str] = mapped_column(Text, server_default="auto", nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)

    summary: Mapped[str | None] = mapped_column(Text)

    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    language: Mapped[str] = mapped_column(Text, server_default="de", nullable=False)

    published_at: Mapped[date | None] = mapped_column(Date)

    published_at_verified: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        nullable=False,
    )

    source_last_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    country_code: Mapped[str] = mapped_column(String(2), server_default="DE", nullable=False)

    region_code: Mapped[str] = mapped_column(
        Text,
        ForeignKey(f"{SCHEMA}.ref_region.region_code"),
        server_default="DE-BW",
        nullable=False,
    )

    location_text: Mapped[str | None] = mapped_column(Text)

    location_status: Mapped[str] = mapped_column(Text, nullable=False)

    location_precision: Mapped[str | None] = mapped_column(Text)

    location_method: Mapped[str | None] = mapped_column(Text)

    geom = mapped_column(
        Geometry(geometry_type="POINT", srid=25832, spatial_index=False),
        nullable=True,
    )

    attributes: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)

    derived: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)

    quality_flags: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        server_default=text("'{}'::text[]"),
        nullable=False,
    )

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    raw_sha256: Mapped[str | None] = mapped_column(String(64))

    first_seen_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.ingest_run.run_id"),
        nullable=False,
    )

    last_seen_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.ingest_run.run_id"),
        nullable=False,
    )

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    missing_run_count: Mapped[int] = mapped_column(
        Integer,
        server_default=text("0"),
        nullable=False,
    )

    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SignalIngestVersion(Base):

    __tablename__ = "signal_ingest_version"

    __table_args__ = (
        UniqueConstraint("signal_id", "content_hash", name="uq_signal_ingest_version_hash"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)

    signal_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(f"{SCHEMA}.signal_ingest.id", ondelete="CASCADE"),
        nullable=False,
    )

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{SCHEMA}.ingest_run.run_id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
