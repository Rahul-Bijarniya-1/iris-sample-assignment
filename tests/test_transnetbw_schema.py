"""
iris_staging is the contract the harvester writes to, so the database
itself must refuse what the brief says may never be accepted silently:
coordinates outside Baden-Württemberg, "resolved" locations without a
geometry, and geometry in the wrong reference system.

These run against a freshly migrated scratch database on the server named
in DATABASE_URL (see tests/conftest.py).
"""

import json
import uuid

import psycopg
import pytest
from pyproj import Transformer

from tests.conftest import scratch_url


EXPECTED_TABLES = {
    "signal_ingest",
    "signal_ingest_version",
    "ingest_run",
    "ingest_issue",
    "source_document",
    "ref_region",
}

TO_UTM = Transformer.from_crs(4326, 25832, always_xy=True)

# Hand-picked reference points (WGS84 lon, lat).
PULVERDINGEN_SUBSTATION = (9.0237, 48.9059)   # inside BW
STRASBOURG_CATHEDRAL = (7.7509, 48.5818)      # France, inside BW's bounding box
NEU_ULM = (10.0110, 48.3920)                  # Bavaria, inside BW's bounding box


def utm(lon_lat):
    return TO_UTM.transform(*lon_lat)


@pytest.fixture
def staging(migrated_database):
    with psycopg.connect(scratch_url(migrated_database), autocommit=True) as conn:
        yield conn


def open_run(conn) -> uuid.UUID:
    return conn.execute(
        """
        insert into iris_staging.ingest_run (source_system, mode, status)
        values ('transnetbw', 'offline', 'running')
        returning run_id
        """
    ).fetchone()[0]


def insert_signal(conn, run_id, *, status="resolved", point=None, key="project:test"):
    """
    Insert one minimal signal row; `point` is a (lon, lat) pair or None.
    """

    geom_sql = "null"
    params = {
        "key": key,
        "status": status,
        "run": run_id,
        "precision": None,
        "method": None,
    }

    if point is not None:
        x, y = utm(point)
        geom_sql = "ST_SetSRID(ST_MakePoint(%(x)s, %(y)s), 25832)"
        params.update(x=x, y=y, precision="substation", method="gazetteer")

    conn.execute(
        f"""
        insert into iris_staging.signal_ingest (
            source_system, source_record_id, record_kind, signal_type,
            title, source_url, location_status, location_precision,
            location_method, geom, content_hash,
            first_seen_run_id, last_seen_run_id, first_seen_at, last_seen_at
        ) values (
            'transnetbw', %(key)s, 'project', 'transformer_modernization',
            'Umspannwerk Test', 'https://www.transnetbw.de/de/x',
            %(status)s, %(precision)s, %(method)s, {geom_sql}, repeat('0', 64),
            %(run)s, %(run)s, now(), now()
        )
        """,
        params,
    )


@pytest.mark.integration
def test_the_staging_tables_exist(migrated_database, schema_tables):
    assert EXPECTED_TABLES <= schema_tables(migrated_database, "iris_staging")


@pytest.mark.integration
def test_the_bw_boundary_is_seeded_in_25832(staging):
    srid, area_km2, licence = staging.execute(
        """
        select ST_SRID(geom), ST_Area(geom) / 1e6, licence
        from iris_staging.ref_region
        where region_code = 'DE-BW'
        """
    ).fetchone()

    assert srid == 25832
    # Official land area of Baden-Württemberg: 35,748 km².
    assert 35_500 < area_km2 < 36_000
    assert "dl-de/by-2-0" in licence


@pytest.mark.integration
def test_a_point_inside_bw_is_accepted(staging):
    run_id = open_run(staging)

    insert_signal(staging, run_id, point=PULVERDINGEN_SUBSTATION)

    count = staging.execute("select count(*) from iris_staging.signal_ingest").fetchone()[0]

    assert count == 1


@pytest.mark.integration
@pytest.mark.parametrize("point", [STRASBOURG_CATHEDRAL, NEU_ULM], ids=["strasbourg", "neu-ulm"])
def test_a_point_outside_bw_is_rejected_by_the_database(staging, point):
    """
    Both points sit inside BW's bounding box, so only a true point-in-polygon
    test against the reference boundary can reject them.
    """

    run_id = open_run(staging)

    with pytest.raises(psycopg.errors.CheckViolation, match="outside region DE-BW"):
        insert_signal(staging, run_id, point=point)


@pytest.mark.integration
def test_resolved_without_a_geometry_is_rejected(staging):
    run_id = open_run(staging)

    with pytest.raises(psycopg.errors.CheckViolation):
        insert_signal(staging, run_id, status="resolved", point=None)


@pytest.mark.integration
def test_unresolved_without_a_geometry_is_accepted(staging):
    run_id = open_run(staging)

    insert_signal(staging, run_id, status="ambiguous", point=None)

    status = staging.execute(
        "select location_status from iris_staging.signal_ingest"
    ).fetchone()[0]

    assert status == "ambiguous"


@pytest.mark.integration
def test_a_geometry_in_another_reference_system_is_rejected(staging):
    run_id = open_run(staging)

    with pytest.raises(psycopg.errors.DatabaseError, match="SRID"):
        staging.execute(
            """
            insert into iris_staging.signal_ingest (
                source_system, source_record_id, record_kind, signal_type,
                title, source_url, location_status, location_precision,
                location_method, geom, content_hash,
                first_seen_run_id, last_seen_run_id, first_seen_at, last_seen_at
            ) values (
                'transnetbw', 'project:wgs84', 'project', 'transformer_modernization',
                'x', 'https://www.transnetbw.de/x', 'resolved', 'substation',
                'gazetteer', ST_SetSRID(ST_MakePoint(9.02, 48.90), 4326), repeat('0', 64),
                %(run)s, %(run)s, now(), now()
            )
            """,
            {"run": run_id},
        )


@pytest.mark.integration
def test_a_nan_coordinate_is_rejected(staging):
    run_id = open_run(staging)

    with pytest.raises(psycopg.errors.DatabaseError):
        staging.execute(
            """
            insert into iris_staging.signal_ingest (
                source_system, source_record_id, record_kind, signal_type,
                title, source_url, location_status, location_precision,
                location_method, geom, content_hash,
                first_seen_run_id, last_seen_run_id, first_seen_at, last_seen_at
            ) values (
                'transnetbw', 'project:nan', 'project', 'transformer_modernization',
                'x', 'https://www.transnetbw.de/x', 'resolved', 'substation',
                'gazetteer', ST_SetSRID(ST_MakePoint('NaN'::float8, 5400000), 25832), repeat('0', 64),
                %(run)s, %(run)s, now(), now()
            )
            """,
            {"run": run_id},
        )


@pytest.mark.integration
def test_one_record_key_cannot_be_stored_twice(staging):
    run_id = open_run(staging)

    insert_signal(staging, run_id, status="unresolved", key="project:dup")

    with pytest.raises(psycopg.errors.UniqueViolation):
        insert_signal(staging, run_id, status="unresolved", key="project:dup")
