"""
End to end over the committed fixtures: discovery → fetch → parse →
classify → link → geocode → load, against a freshly migrated scratch
database, with no network access.

The expectations are worked out by hand from the fixtures (8 projects and
9 articles captured on 2026-10-27; the listing and sitemap name 25
projects, so 17 are reported as not captured).
"""

import json
import shutil
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.transnetbw.config import TransnetBWSettings
from app.transnetbw.fetch import FixtureFetcher, load_fixture_index
from app.transnetbw.harvester import Harvester, needs_fetch
from app.transnetbw.store import LedgerEntry, RunLog
from tests.conftest import scratch_url


FIXTURES = Path("fixtures/transnetbw")

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)

BASE = "https://www.transnetbw.de"

LISTING = f"{BASE}/de/netzentwicklung/projekte/alle-projekte"


@pytest.fixture
def engine(migrated_database):
    engine = sa.create_engine(scratch_url(migrated_database))
    yield engine
    engine.dispose()


def settings(**overrides) -> TransnetBWSettings:
    # The fixture feed is a 15-item subset; offline runs accept it.
    return TransnetBWSettings(_env_file=None, gate_min_feed_items=10, **overrides)


def harvest(engine, index=None, *, full=False, dry_run=False, **overrides):
    harvester = Harvester(
        settings=settings(**overrides),
        fetcher=FixtureFetcher(index or load_fixture_index(FIXTURES / "index.json")),
        engine=engine,
        mode="offline",
        clock=lambda: NOW,
    )
    return harvester.run(full=full, dry_run=dry_run)


def rows(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(sa.text(sql), params).mappings().all()


def signal(engine, key):
    found = rows(
        engine,
        """
        select *, ST_X(geom) as x, ST_Y(geom) as y, ST_SRID(geom) as srid
        from iris_staging.signal_ingest where source_record_id = :key
        """,
        key=key,
    )
    return found[0] if found else None


def variant(tmp_path, edits: dict[str, str] | None = None, documents: dict | None = None):
    """
    A copy of the fixture set with `edits` applied as {file: new text} and
    index `documents` overridden. The originals stay untouched.
    """

    target = tmp_path / "fixtures"

    shutil.copytree(FIXTURES, target)

    for name, text in (edits or {}).items():
        (target / name).write_text(text, encoding="utf-8")

    index = load_fixture_index(target / "index.json")

    if documents:
        index = replace(index, documents={**index.documents, **documents})

    return index


# =========================================================
# A CLEAN OFFLINE RUN
# =========================================================


@pytest.mark.integration
def test_the_offline_run_loads_the_expected_records(engine):
    result = harvest(engine)

    assert (result.status, result.exit_code) == ("succeeded", 0)

    loaded = rows(engine, "select record_kind, count(*) as n from iris_staging.signal_ingest group by 1 order by 1")

    assert {row["record_kind"]: row["n"] for row in loaded} == {"press_release": 7, "project": 7}
    assert result.stats["load"]["inserted"] == 14


@pytest.mark.integration
def test_exclusions_are_logged_with_their_reasons(engine):
    harvest(engine)

    excluded = rows(
        engine,
        "select code, source_record_id from iris_staging.ingest_issue where code like 'excluded_%' order by 2",
    )

    assert {(row["code"], row["source_record_id"]) for row in excluded} == {
        ("excluded_out_of_scope_maintenance", "project:seiltausch-hoellental"),
        ("excluded_out_of_scope_policy", "press:freileitungsvorrang-staerkt-netzausbau-einschraenkungen-schaffen-unsicherheit"),
        ("excluded_outside_bw", "press:baustart-fur-suedlink-in-bayern"),
    }


@pytest.mark.integration
def test_pages_missing_from_the_fixture_set_are_reported_not_failed(engine):
    result = harvest(engine)

    assert result.stats["fetch"]["not_captured"] == 17
    assert result.stats["fetch"]["failed"] == 0

    not_captured = rows(engine, "select severity from iris_staging.ingest_issue where code = 'not_captured'")

    assert len(not_captured) == 17
    assert {row["severity"] for row in not_captured} == {"info"}


@pytest.mark.integration
def test_the_listing_and_sitemap_disagreement_is_logged(engine):
    harvest(engine)

    found = rows(
        engine,
        "select code, source_record_id from iris_staging.ingest_issue where code like 'discovery_%'",
    )

    assert {(row["code"], row["source_record_id"]) for row in found} == {
        ("discovery_listing_only", "project:stalldorf-main-tauber"),
        ("discovery_sitemap_only", "project:seiltausch-hoellental"),
        ("discovery_sitemap_only", "project:schaltanlage-obermooweiler"),
    }


@pytest.mark.integration
def test_a_substation_project_is_a_traceable_resolved_point(engine):
    harvest(engine)

    row = signal(engine, "project:umspannwerk-pulverdingen")

    assert row["signal_type"] == "transformer_modernization"
    assert row["project_stage"] == "construction"
    assert row["location_status"] == "resolved"
    assert row["location_precision"] == "substation"
    assert row["srid"] == 25832
    assert abs(row["x"] - 503_335.5) < 1 and abs(row["y"] - 5_416_666.9) < 1
    assert row["published_at"] is None
    assert row["source_last_modified"] is not None
    assert row["source_url"] == f"{BASE}/de/netzentwicklung/projekte/umspannwerk-pulverdingen"
    assert row["summary"].startswith("Seit Langem trägt das Umspannwerk in Pulverdingen")
    assert any("Phasenschieber" in measure["text"] for measure in row["attributes"]["measures"])


@pytest.mark.integration
def test_a_cross_border_line_is_loaded_without_a_point(engine):
    harvest(engine)

    row = signal(engine, "project:grafenrheinfeld-kupferzell-grossgartach")

    assert row["location_status"] == "ambiguous"
    assert row["geom"] is None
    assert "cross_border" in row["quality_flags"]
    assert [endpoint["name"] for endpoint in row["attributes"]["endpoints"]] == [
        "Grafenrheinfeld",
        "Kupferzell",
        "Großgartach",
    ]


@pytest.mark.integration
def test_press_dates_are_verified_against_the_article(engine):
    harvest(engine)

    row = signal(engine, "press:nbr-teilbeschluss-abschnitt-B3-ortenaukreis")

    assert str(row["published_at"]) == "2026-06-16"
    assert row["published_at_verified"] is True
    assert row["project_stage"] == "approval"
    assert row["attributes"]["related_project"] == "project:netzverstaerkung-badische-rheinschiene"


@pytest.mark.integration
def test_a_press_release_tied_to_nothing_is_held_for_review(engine):
    harvest(engine)

    row = signal(engine, "press:kleinstflexibilitaeten-als-beitrag-fuer-das-netzengpassmanagement")

    assert row["review_status"] == "needs_review"
    assert row["location_status"] == "unresolved"


@pytest.mark.integration
def test_project_rows_carry_their_latest_press_milestone(engine):
    harvest(engine)

    netzbooster = signal(engine, "project:netzbooster-kupferzell")
    schwoerstadt = signal(engine, "project:umspannwerk-schwoerstadt")

    assert netzbooster["derived"]["related_press_count"] == 2
    assert netzbooster["derived"]["first_reported_at"] == "2024-03-25"
    assert netzbooster["derived"]["latest_event"]["date"] == "2024-06-10"
    assert schwoerstadt["project_stage"] == "in_operation"
    assert schwoerstadt["derived"]["latest_event"]["stage"] == "in_operation"


@pytest.mark.integration
def test_a_press_release_naming_no_station_takes_its_project_point(engine):
    harvest(engine)

    project = signal(engine, "project:netzbooster-kupferzell")
    approval = signal(engine, "press:transnetbw-erhaelt-planfeststellungsbeschluss-fuer-den-netzbooster-in-kupferzell")

    assert approval["location_method"] == "via_project"
    assert approval["location_status"] == "resolved"
    assert (approval["x"], approval["y"]) == (project["x"], project["y"])
    assert approval["project_stage"] == "approval"


@pytest.mark.integration
def test_no_press_contact_reaches_the_staging_table(engine):
    harvest(engine)

    leaked = rows(
        engine,
        r"""
        select source_record_id from iris_staging.signal_ingest
        where concat_ws(' ', title, summary, attributes::text) ~ '[\w.+-]+@[\w-]+\.\w+|\+49 ?\d'
        """,
    )

    assert leaked == []


# =========================================================
# RE-RUNS
# =========================================================


@pytest.mark.integration
def test_a_rerun_refetches_nothing_and_changes_nothing(engine):
    harvest(engine)
    second = harvest(engine)

    assert second.stats["load"] == {**second.stats["load"], "inserted": 0, "updated": 0}
    assert second.stats["fetch"]["skipped_unchanged"] == 17
    assert len(rows(engine, "select 1 from iris_staging.signal_ingest")) == 14
    assert len(rows(engine, "select 1 from iris_staging.signal_ingest_version")) == 14


@pytest.mark.integration
def test_a_full_rerun_finds_every_record_unchanged(engine):
    harvest(engine)
    full = harvest(engine, full=True)

    assert full.stats["load"]["inserted"] == 0
    assert full.stats["load"]["updated"] == 0
    assert full.stats["load"]["unchanged"] == 14
    assert len(rows(engine, "select 1 from iris_staging.signal_ingest")) == 14


@pytest.mark.integration
def test_an_edited_page_with_a_newer_lastmod_updates_one_record(engine, tmp_path):
    harvest(engine)

    overview = "pages/project-umspannwerk-pulverdingen.html"
    html = (FIXTURES / overview).read_text(encoding="utf-8")
    sitemap = (FIXTURES / "sitemap.xml").read_text(encoding="utf-8")

    edited = variant(
        tmp_path,
        edits={
            overview: html.replace("Seit Langem trägt", "Seit Jahrzehnten trägt"),
            "sitemap.xml": sitemap.replace(
                "umspannwerk-pulverdingen</loc><lastmod>2024-01-30T16:11:17+01:00",
                "umspannwerk-pulverdingen</loc><lastmod>2026-10-28T08:00:00+01:00",
            ),
        },
    )

    first_seen = signal(engine, "project:umspannwerk-pulverdingen")["first_seen_at"]

    result = harvest(engine, edited)

    assert result.stats["load"]["updated"] == 1
    assert result.stats["load"]["inserted"] == 0
    row = signal(engine, "project:umspannwerk-pulverdingen")
    assert row["summary"].startswith("Seit Jahrzehnten trägt")
    assert row["first_seen_at"] == first_seen
    assert len(rows(engine, "select 1 from iris_staging.signal_ingest_version where signal_id = :id", id=row["id"])) == 2


@pytest.mark.integration
def test_a_dry_run_writes_no_signals(engine):
    result = harvest(engine, dry_run=True)

    assert result.stats["load"]["inserted"] == 14
    assert rows(engine, "select 1 from iris_staging.signal_ingest") == []


# =========================================================
# FAILURES
# =========================================================


@pytest.mark.integration
def test_a_listing_without_cards_fails_the_run_and_writes_nothing(engine, tmp_path):
    broken = variant(
        tmp_path,
        edits={"pages/alle-projekte.html": "<html><body><main><p>Wartungsarbeiten</p></main></body></html>"},
    )

    result = harvest(engine, broken)

    assert (result.status, result.exit_code) == ("failed", 1)
    assert rows(engine, "select 1 from iris_staging.signal_ingest") == []
    assert rows(engine, "select status from iris_staging.ingest_run")[0]["status"] == "failed"
    assert rows(engine, "select code from iris_staging.ingest_issue where severity = 'error'")[0]["code"] == "empty_response"


@pytest.mark.integration
def test_a_quality_gate_breach_rolls_back_and_retires_nothing(engine, tmp_path):
    harvest(engine)

    html = (FIXTURES / "pages/alle-projekte.html").read_text(encoding="utf-8")
    cards = html.split('<a class="card-project')
    three_cards = '<a class="card-project'.join(cards[:4]) + "</div></main></body></html>"

    shrunk = variant(tmp_path, edits={"pages/alle-projekte.html": three_cards})

    result = harvest(engine, shrunk, full=True)

    assert (result.status, result.exit_code) == ("failed", 1)
    assert result.gates["listing_cards"]["passed"] is False
    assert rows(engine, "select count(*) as n from iris_staging.signal_ingest where missing_run_count > 0")[0]["n"] == 0
    assert len(rows(engine, "select 1 from iris_staging.signal_ingest")) == 14


@pytest.mark.integration
def test_a_failed_article_fetch_is_partial_and_the_rest_still_loads(engine):
    index = load_fixture_index(FIXTURES / "index.json")
    url = f"{BASE}/de/newsroom/news/feierlicher-baubeginn-des-netzboosters"
    failing = replace(
        index,
        documents={**index.documents, url: replace(index.documents[url], status=503)},
    )

    result = harvest(engine, failing)

    assert (result.status, result.exit_code) == ("partial", 2)
    assert result.stats["fetch"]["failed"] == 1
    assert len(rows(engine, "select 1 from iris_staging.signal_ingest")) == 13
    assert rows(engine, "select code from iris_staging.ingest_issue where source_url = :url", url=url)[0]["code"] == "fetch_failed"


@pytest.mark.integration
def test_a_concurrent_run_is_refused_with_exit_3(engine):
    holder = RunLog(engine, "transnetbw")

    try:
        assert holder.acquire_lock()

        result = harvest(engine)

        assert (result.status, result.exit_code) == ("refused", 3)
        assert rows(engine, "select 1 from iris_staging.signal_ingest") == []

    finally:
        holder.close()


@pytest.mark.integration
def test_an_offline_run_refuses_a_database_with_live_runs(engine):
    log = RunLog(engine, "transnetbw")

    try:
        log.start("live", {}, "test")
    finally:
        log.close()

    result = harvest(engine)

    assert (result.status, result.exit_code) == ("refused", 1)
    assert rows(engine, "select 1 from iris_staging.signal_ingest") == []


# =========================================================
# FETCH DECISION
# =========================================================


LASTMOD = datetime(2024, 1, 30, 15, 11, 17, tzinfo=timezone.utc)


def ledger(outcome="parsed", lastmod=LASTMOD):
    return LedgerEntry("u", "project_overview", lastmod, outcome, "a" * 64)


@pytest.mark.parametrize(
    "entry, lastmod, full, expected",
    [
        (None, LASTMOD, False, True),                                       # never fetched
        (ledger(), LASTMOD, False, False),                                  # unchanged since
        (ledger(), LASTMOD.replace(year=2026), False, True),                # newer lastmod
        (ledger(outcome="error"), LASTMOD, False, True),                    # last attempt failed
        (ledger(), LASTMOD, True, True),                                    # --full
        (ledger(lastmod=None), None, False, False),                         # no lastmod: fetched once
        (ledger(outcome="excluded"), LASTMOD, False, False),                # excluded stays excluded
    ],
)
def test_a_document_is_fetched_only_when_it_may_have_changed(entry, lastmod, full, expected):
    assert needs_fetch(entry, lastmod, full) is expected


@pytest.mark.integration
def test_a_feed_title_that_disagrees_with_the_page_is_flagged(engine, tmp_path):
    feed = json.loads((FIXTURES / "press-releases.json").read_text(encoding="utf-8"))

    for item in feed:
        if item["url"].endswith("/feierlicher-baubeginn-des-netzboosters"):
            item["title"] = "Expertenkommission rät zur Überprüfung des Erdkabelvorrangs"

    changed = variant(tmp_path, edits={"press-releases.json": json.dumps(feed, ensure_ascii=False)})

    harvest(engine, changed)

    row = signal(engine, "press:feierlicher-baubeginn-des-netzboosters")

    # The page's own title is kept, and the disagreement is visible.
    assert row["title"] == "Feierlicher Baubeginn des Netzboosters"
    assert "feed_title_mismatch" in row["quality_flags"]
