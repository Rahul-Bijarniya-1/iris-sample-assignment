"""
The artifacts are what a reviewer sees without database access: a sample
of the staging rows (CSV in EPSG:25832, GeoJSON in WGS84 as RFC 7946
requires), a quality report, and validation queries.

The validation queries are executable claims: every query that says
"expect: 0 rows" is run here against a harvested database.
"""

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.transnetbw.config import TransnetBWSettings
from app.transnetbw.fetch import FixtureFetcher, load_fixture_index
from app.transnetbw.harvester import Harvester
from app.transnetbw.report import write_artifacts
from tests.conftest import scratch_url


FIXTURES = Path("fixtures/transnetbw")

QUERIES = Path("artifacts/transnetbw/validation_queries.sql")

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def harvested(migrated_database, tmp_path):
    engine = sa.create_engine(scratch_url(migrated_database))
    settings = TransnetBWSettings(_env_file=None, gate_min_feed_items=10, artifacts_dir=tmp_path / "artifacts")

    result = Harvester(
        settings=settings,
        fetcher=FixtureFetcher(load_fixture_index(FIXTURES / "index.json")),
        engine=engine,
        mode="offline",
        clock=lambda: NOW,
    ).run()

    report = write_artifacts(engine, settings, result)

    yield engine, settings.artifacts_dir, report

    engine.dispose()


@pytest.mark.integration
def test_the_geojson_is_wgs84_points_inside_bw(harvested):
    _, artifacts, _ = harvested

    collection = json.loads((artifacts / "sample_signal_ingest.geojson").read_text(encoding="utf-8"))

    assert collection["type"] == "FeatureCollection"
    assert len(collection["features"]) == 14

    points = [feature for feature in collection["features"] if feature["geometry"]]

    assert points
    for feature in points:
        lon, lat = feature["geometry"]["coordinates"]
        assert 7.4 < lon < 10.6 and 47.4 < lat < 49.9, feature["properties"]["source_record_id"]

    pulverdingen = next(
        feature for feature in points
        if feature["properties"]["source_record_id"] == "project:umspannwerk-pulverdingen"
    )

    # OSM point of the substation, WGS84.
    lon, lat = pulverdingen["geometry"]["coordinates"]
    assert abs(lon - 9.045515) < 1e-5 and abs(lat - 48.902937) < 1e-5


@pytest.mark.integration
def test_unlocated_records_are_in_the_geojson_without_geometry(harvested):
    _, artifacts, _ = harvested

    collection = json.loads((artifacts / "sample_signal_ingest.geojson").read_text(encoding="utf-8"))

    suedlink = next(
        feature for feature in collection["features"]
        if feature["properties"]["source_record_id"] == "project:suedlink"
    )

    assert suedlink["geometry"] is None
    assert suedlink["properties"]["location_status"] == "unresolved"


@pytest.mark.integration
def test_the_csv_keeps_the_native_25832_coordinates(harvested):
    _, artifacts, _ = harvested

    with (artifacts / "sample_signal_ingest.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 14

    pulverdingen = next(row for row in rows if row["source_record_id"] == "project:umspannwerk-pulverdingen")

    assert abs(float(pulverdingen["x_25832"]) - 503_335.5) < 1
    assert pulverdingen["wkt_25832"].startswith("POINT(503335")


@pytest.mark.integration
def test_the_quality_report_lists_every_record_without_a_point(harvested):
    engine, artifacts, report = harvested

    data = json.loads((artifacts / "quality_report.json").read_text(encoding="utf-8"))

    with engine.connect() as conn:
        unlocated = set(
            conn.execute(
                sa.text("select source_record_id from iris_staging.signal_ingest where location_status <> 'resolved'")
            ).scalars()
        )

    assert unlocated
    assert {row["source_record_id"] for row in data["locations"]["not_resolved"]} == unlocated
    assert all(row["note"] for row in data["locations"]["not_resolved"])
    assert data["records"]["by_kind"] == {"press_release": 7, "project": 7}
    assert report.name == "quality_report.md"
    text = report.read_text(encoding="utf-8")
    assert "Unresolved and ambiguous locations" in text
    # Hand-verified facts are dated; this run's own numbers sit next to them.
    assert "checked by hand on 2026-10-27" in text
    assert "this run: listing 23 cards" in text


@pytest.mark.integration
def test_the_quality_report_shows_exclusions_and_gates(harvested):
    _, artifacts, _ = harvested

    data = json.loads((artifacts / "quality_report.json").read_text(encoding="utf-8"))

    reasons = {row["code"] for row in data["exclusions"]}

    assert reasons == {"excluded_out_of_scope_maintenance", "excluded_out_of_scope_policy", "excluded_outside_bw"}
    assert data["run"]["status"] == "succeeded"
    assert all(gate["passed"] for gate in data["run"]["gates"].values())


def zero_row_queries() -> list[tuple[str, str]]:
    blocks = re.split(r"^-- \[(V\d+)\]", QUERIES.read_text(encoding="utf-8"), flags=re.MULTILINE)

    checks = []

    for label, body in zip(blocks[1::2], blocks[2::2]):

        header, sql = body.split("\n", 1)

        if "expect: 0 rows" in header:
            checks.append((label, sql))

    return checks


def test_the_validation_queries_declare_zero_row_checks():
    assert len(zero_row_queries()) >= 6


@pytest.mark.integration
def test_every_zero_row_validation_query_returns_no_rows(harvested):
    engine, _, _ = harvested

    with engine.connect() as conn:

        for label, sql in zero_row_queries():

            found = conn.execute(sa.text(sql)).all()

            assert found == [], f"{label} returned {found[:3]}"
