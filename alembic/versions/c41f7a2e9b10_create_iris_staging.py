"""create iris_staging: signal ingest, run audit, fetch ledger, reference regions

Revision ID: c41f7a2e9b10
Revises: b18ad888465f
Create Date: 2026-10-28 00:10:00

The landing zone for external signals (first writer: the TransnetBW Project
Radar harvester, IRIS-SIG-30). See app/database/models/signal_ingest.py for
what each table is for.

Two rules are enforced by the database itself, not only by the harvester:

  - a signal geometry must be a valid EPSG:25832 point, and a location is
    "resolved" exactly when there is one (CHECK constraints);
  - the point must lie inside the record's reference region (trigger
    against ref_region, failing closed when the region is unknown).

ref_region is seeded with Baden-Württemberg from the committed BKG VG250
extract, app/transnetbw/data/de_bw_boundary_25832.wkt (dl-de/by-2-0).
"""

import json
from pathlib import Path
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c41f7a2e9b10"

down_revision: Union[str, Sequence[str], None] = (
    "b18ad888465f"
)

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


SCHEMA = "iris_staging"

DATA_DIR = Path(__file__).resolve().parents[2] / "app" / "transnetbw" / "data"


def one_of(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


def jsonb_empty() -> sa.TextClause:
    return sa.text("'{}'::jsonb")


def upgrade() -> None:

    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    # =====================================================
    # REFERENCE REGIONS
    # =====================================================

    op.create_table(
        "ref_region",
        sa.Column("region_code", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(geometry_type="MULTIPOLYGON", srid=25832, spatial_index=False),
            nullable=False,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("licence", sa.Text(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema=SCHEMA,
    )

    op.create_index("idx_ref_region_geom", "ref_region", ["geom"], schema=SCHEMA, postgresql_using="gist")

    # =====================================================
    # RUN AUDIT
    # =====================================================

    op.create_table(
        "ingest_run",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("stats", postgresql.JSONB(), server_default=jsonb_empty(), nullable=False),
        sa.Column("gates", postgresql.JSONB(), server_default=jsonb_empty(), nullable=False),
        sa.Column("config", postgresql.JSONB(), server_default=jsonb_empty(), nullable=False),
        sa.Column("code_version", sa.Text(), nullable=True),
        sa.CheckConstraint(one_of("mode", ("live", "offline")), name="ck_ingest_run_mode"),
        sa.CheckConstraint(
            one_of("status", ("running", "succeeded", "partial", "failed", "refused")),
            name="ck_ingest_run_status",
        ),
        schema=SCHEMA,
    )

    op.create_index("idx_ingest_run_source_started", "ingest_run", ["source_system", "started_at"], schema=SCHEMA)

    op.create_table(
        "ingest_issue",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.ingest_run.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", postgresql.JSONB(), server_default=jsonb_empty(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(one_of("severity", ("error", "warning", "info")), name="ck_ingest_issue_severity"),
        schema=SCHEMA,
    )

    op.create_index("idx_ingest_issue_run", "ingest_issue", ["run_id"], schema=SCHEMA)

    op.create_index("idx_ingest_issue_code", "ingest_issue", ["code"], schema=SCHEMA)

    # =====================================================
    # FETCH LEDGER
    # =====================================================

    op.create_table(
        "source_document",
        sa.Column("url", sa.Text(), primary_key=True),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("doc_kind", sa.Text(), nullable=False),
        sa.Column("sitemap_lastmod", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_http_status", sa.Integer(), nullable=True),
        sa.Column("raw_sha256", sa.String(length=64), nullable=True),
        sa.Column("last_outcome", sa.Text(), nullable=True),
        sa.Column(
            "last_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.ingest_run.run_id"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            one_of(
                "doc_kind",
                ("robots", "sitemap", "listing", "feed", "project_overview", "project_portrait", "press_article"),
            ),
            name="ck_source_document_kind",
        ),
        sa.CheckConstraint(
            "last_outcome IS NULL OR " + one_of("last_outcome", ("parsed", "excluded", "error")),
            name="ck_source_document_outcome",
        ),
        schema=SCHEMA,
    )

    # =====================================================
    # SIGNALS
    # =====================================================

    op.create_table(
        "signal_ingest",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("source_system", sa.Text(), nullable=False),
        sa.Column("source_record_id", sa.Text(), nullable=False),
        sa.Column("record_kind", sa.Text(), nullable=False),
        sa.Column("signal_type", sa.Text(), nullable=False),
        sa.Column("project_stage", sa.Text(), server_default="unknown", nullable=False),
        sa.Column("review_status", sa.Text(), server_default="auto", nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), server_default="de", nullable=False),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("published_at_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source_last_modified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("country_code", sa.String(length=2), server_default="DE", nullable=False),
        sa.Column(
            "region_code",
            sa.Text(),
            sa.ForeignKey(f"{SCHEMA}.ref_region.region_code"),
            server_default="DE-BW",
            nullable=False,
        ),
        sa.Column("location_text", sa.Text(), nullable=True),
        sa.Column("location_status", sa.Text(), nullable=False),
        sa.Column("location_precision", sa.Text(), nullable=True),
        sa.Column("location_method", sa.Text(), nullable=True),
        sa.Column(
            "geom",
            geoalchemy2.types.Geometry(geometry_type="POINT", srid=25832, spatial_index=False),
            nullable=True,
        ),
        sa.Column("attributes", postgresql.JSONB(), server_default=jsonb_empty(), nullable=False),
        sa.Column("derived", postgresql.JSONB(), server_default=jsonb_empty(), nullable=False),
        sa.Column("quality_flags", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "first_seen_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.ingest_run.run_id"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.ingest_run.run_id"),
            nullable=False,
        ),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("missing_run_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("source_system", "source_record_id", name="uq_signal_ingest_source_record"),
        sa.CheckConstraint(one_of("record_kind", ("project", "press_release")), name="ck_signal_ingest_record_kind"),
        sa.CheckConstraint(
            one_of("signal_type", ("grid_capacity_constraint", "transformer_modernization")),
            name="ck_signal_ingest_signal_type",
        ),
        sa.CheckConstraint(
            one_of("project_stage", ("planning", "approval", "construction", "in_operation", "unknown")),
            name="ck_signal_ingest_project_stage",
        ),
        sa.CheckConstraint(one_of("review_status", ("auto", "needs_review")), name="ck_signal_ingest_review_status"),
        sa.CheckConstraint(
            one_of("location_status", ("resolved", "ambiguous", "unresolved", "invalid_coordinates")),
            name="ck_signal_ingest_location_status",
        ),
        sa.CheckConstraint(
            "location_precision IS NULL OR " + one_of("location_precision", ("substation", "municipality")),
            name="ck_signal_ingest_location_precision",
        ),
        sa.CheckConstraint(
            "location_method IS NULL OR " + one_of("location_method", ("gazetteer", "nominatim", "via_project")),
            name="ck_signal_ingest_location_method",
        ),
        sa.CheckConstraint(
            "(location_status = 'resolved') = (geom IS NOT NULL)",
            name="ck_signal_ingest_resolved_has_geom",
        ),
        sa.CheckConstraint(
            "(location_precision IS NULL) = (geom IS NULL) "
            "AND (location_method IS NULL) = (geom IS NULL)",
            name="ck_signal_ingest_geom_provenance",
        ),
        sa.CheckConstraint(
            "geom IS NULL OR (ST_SRID(geom) = 25832 AND ST_IsValid(geom))",
            name="ck_signal_ingest_geom_valid",
        ),
        sa.CheckConstraint(
            "summary IS NULL OR char_length(summary) <= 500",
            name="ck_signal_ingest_summary_length",
        ),
        schema=SCHEMA,
    )

    op.create_index("idx_signal_ingest_geom", "signal_ingest", ["geom"], schema=SCHEMA, postgresql_using="gist")

    op.create_index("idx_signal_ingest_signal_type", "signal_ingest", ["signal_type"], schema=SCHEMA)

    op.create_index("idx_signal_ingest_record_kind", "signal_ingest", ["record_kind"], schema=SCHEMA)

    op.create_index("idx_signal_ingest_published_at", "signal_ingest", ["published_at"], schema=SCHEMA)

    op.create_table(
        "signal_ingest_version",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "signal_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{SCHEMA}.signal_ingest.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.ingest_run.run_id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("signal_id", "content_hash", name="uq_signal_ingest_version_hash"),
        schema=SCHEMA,
    )

    # =====================================================
    # POINT-IN-REGION ENFORCEMENT
    # =====================================================
    #
    # A CHECK constraint cannot read another table, so the region test is a
    # trigger. It fails closed: an unknown region rejects the row rather
    # than letting an unchecked point through.

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {SCHEMA}.enforce_signal_geom()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            region geometry;
        BEGIN
            IF NEW.geom IS NULL THEN
                RETURN NEW;
            END IF;

            SELECT r.geom INTO region
            FROM {SCHEMA}.ref_region r
            WHERE r.region_code = NEW.region_code;

            IF region IS NULL THEN
                RAISE EXCEPTION 'no reference geometry for region %', NEW.region_code
                    USING ERRCODE = 'check_violation';
            END IF;

            IF NOT ST_Within(NEW.geom, region) THEN
                RAISE EXCEPTION 'point % lies outside region %',
                    ST_AsText(NEW.geom), NEW.region_code
                    USING ERRCODE = 'check_violation';
            END IF;

            RETURN NEW;
        END
        $$
        """
    )

    op.execute(
        f"""
        CREATE TRIGGER signal_ingest_geom_within_region
        BEFORE INSERT OR UPDATE OF geom, region_code
        ON {SCHEMA}.signal_ingest
        FOR EACH ROW
        EXECUTE FUNCTION {SCHEMA}.enforce_signal_geom()
        """
    )

    # =====================================================
    # SEED: BADEN-WÜRTTEMBERG
    # =====================================================

    metadata = json.loads((DATA_DIR / "de_bw_boundary.json").read_text(encoding="utf-8"))

    boundary_wkt = (DATA_DIR / "de_bw_boundary_25832.wkt").read_text(encoding="utf-8").strip()

    op.execute(
        sa.text(
            f"""
            INSERT INTO {SCHEMA}.ref_region (region_code, name, geom, source, licence)
            VALUES (
                :region_code,
                :name,
                ST_Multi(ST_GeomFromText(:wkt, 25832)),
                :source,
                :licence
            )
            """
        ).bindparams(
            region_code=metadata["region_code"],
            name=metadata["name"],
            wkt=boundary_wkt,
            source=f"{metadata['source']} ({metadata['layer']}, generalized to {metadata['generalization_tolerance_m']} m)",
            licence=f"{metadata['licence']} · {metadata['attribution']}",
        )
    )


def downgrade() -> None:
    """
    Drop what this revision created, and nothing else. The schema itself is
    left in place, as with iris_core and app: other writers may own objects
    in it by then.
    """

    op.execute(f"DROP TRIGGER IF EXISTS signal_ingest_geom_within_region ON {SCHEMA}.signal_ingest")

    op.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.enforce_signal_geom()")

    op.drop_table("signal_ingest_version", schema=SCHEMA)

    op.drop_table("signal_ingest", schema=SCHEMA)

    op.drop_table("source_document", schema=SCHEMA)

    op.drop_table("ingest_issue", schema=SCHEMA)

    op.drop_table("ingest_run", schema=SCHEMA)

    op.drop_table("ref_region", schema=SCHEMA)
