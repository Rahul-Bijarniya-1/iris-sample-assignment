"""
The store is where "does not duplicate on re-run" is won or lost.

Properties under test, all against a freshly migrated scratch database:

  - the same content twice is one row and one version ("unchanged");
  - changed content updates the row, keeps its first-seen facts and adds
    a version; flipping back reuses the old version ("reverted");
  - a page edit that leaves the signal alone is audit-only;
  - one record the database rejects does not take the others with it;
  - records disappear only by soft retirement, and come back un-retired;
  - derived cross-record facts never change a content hash;
  - two runs cannot overlap, and fixture runs cannot mix with live runs;
  - run bookkeeping survives a rolled-back run.
"""

from dataclasses import replace
from datetime import date, datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError

from app.transnetbw.normalize import SignalRecord
from app.transnetbw.store import RunLog, SignalStore
from tests.conftest import scratch_url


SOURCE = "transnetbw"

NOW = datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)

LATER = datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc)

# Umspannwerk Pulverdingen (OSM point, EPSG:25832) — inside BW.
PULVERDINGEN = (503_335.5, 5_416_666.9)

# Strasbourg Cathedral (EPSG:25832) — outside BW, inside its bounding box.
STRASBOURG = (407_876.1, 5_381_721.3)


@pytest.fixture
def engine(migrated_database):
    engine = sa.create_engine(scratch_url(migrated_database))
    yield engine
    engine.dispose()


@pytest.fixture
def runlog(engine):
    log = RunLog(engine, SOURCE)
    yield log
    log.close()


def project(**changes) -> SignalRecord:
    base = SignalRecord(
        source_system=SOURCE,
        source_record_id="project:umspannwerk-pulverdingen",
        record_kind="project",
        signal_type="transformer_modernization",
        title="Umspannwerk Pulverdingen",
        source_url="https://www.transnetbw.de/de/netzentwicklung/projekte/umspannwerk-pulverdingen",
        project_stage="construction",
        summary="Seit Langem trägt das Umspannwerk in Pulverdingen zur sicheren Stromversorgung bei.",
        location_text="Pulverdingen",
        location_status="resolved",
        location_precision="substation",
        location_method="gazetteer",
        x=PULVERDINGEN[0],
        y=PULVERDINGEN[1],
        attributes={"category_label": "Erweiterung"},
        raw_sha256="a" * 64,
    )
    return replace(base, **changes)


def press(**changes) -> SignalRecord:
    base = SignalRecord(
        source_system=SOURCE,
        source_record_id="press:spatenstich-pulverdingen",
        record_kind="press_release",
        signal_type="transformer_modernization",
        title="Spatenstich am Umspannwerk Pulverdingen",
        source_url="https://www.transnetbw.de/de/newsroom/news/spatenstich-pulverdingen",
        project_stage="construction",
        published_at=date(2023, 3, 1),
        published_at_verified=True,
        location_status="unresolved",
        attributes={"related_project": "project:umspannwerk-pulverdingen"},
    )
    return replace(base, **changes)


def run_once(engine, runlog, records, now=NOW):
    """
    One committed run writing `records`; returns (run_id, outcomes).
    """

    run_id = runlog.start("offline", {}, "test")

    outcomes = []

    with engine.begin() as conn:

        store = SignalStore(conn, SOURCE)

        for record in records:
            outcomes.append(store.upsert(record, run_id, now))

    return run_id, outcomes


def scalar(engine, sql, **params):
    with engine.connect() as conn:
        return conn.execute(sa.text(sql), params).scalar_one()


# =========================================================
# IDEMPOTENCY
# =========================================================


@pytest.mark.integration
def test_a_new_record_is_inserted_with_its_point_and_first_version(engine, runlog):
    _, outcomes = run_once(engine, runlog, [project()])

    assert outcomes[0].action == "inserted"
    assert scalar(engine, "select count(*) from iris_staging.signal_ingest") == 1
    assert scalar(engine, "select ST_SRID(geom) from iris_staging.signal_ingest") == 25832
    assert scalar(engine, "select round(ST_X(geom)::numeric, 1) from iris_staging.signal_ingest") == pytest.approx(PULVERDINGEN[0])
    assert scalar(engine, "select count(*) from iris_staging.signal_ingest_version") == 1


@pytest.mark.integration
def test_the_same_content_again_is_unchanged_and_adds_nothing(engine, runlog):
    first_run, _ = run_once(engine, runlog, [project()])
    second_run, outcomes = run_once(engine, runlog, [project()], now=LATER)

    assert outcomes[0].action == "unchanged"
    assert scalar(engine, "select count(*) from iris_staging.signal_ingest") == 1
    assert scalar(engine, "select count(*) from iris_staging.signal_ingest_version") == 1
    assert scalar(engine, "select first_seen_run_id::text from iris_staging.signal_ingest") == str(first_run)
    assert scalar(engine, "select last_seen_run_id::text from iris_staging.signal_ingest") == str(second_run)


@pytest.mark.integration
def test_changed_content_updates_the_row_and_keeps_its_history(engine, runlog):
    run_once(engine, runlog, [project()])
    _, outcomes = run_once(engine, runlog, [project(project_stage="in_operation")], now=LATER)

    assert outcomes[0].action == "updated"
    assert scalar(engine, "select project_stage from iris_staging.signal_ingest") == "in_operation"
    assert scalar(engine, "select first_seen_at from iris_staging.signal_ingest") == NOW
    assert scalar(engine, "select count(*) from iris_staging.signal_ingest_version") == 2


@pytest.mark.integration
def test_content_flipping_back_reuses_its_old_version(engine, runlog):
    run_once(engine, runlog, [project()])
    run_once(engine, runlog, [project(project_stage="in_operation")])
    _, outcomes = run_once(engine, runlog, [project()])

    assert outcomes[0].action == "reverted"
    assert scalar(engine, "select project_stage from iris_staging.signal_ingest") == "construction"
    assert scalar(engine, "select count(*) from iris_staging.signal_ingest_version") == 2


@pytest.mark.integration
def test_a_page_edit_without_a_signal_change_is_audit_only(engine, runlog):
    run_once(engine, runlog, [project()])
    _, outcomes = run_once(engine, runlog, [project(raw_sha256="b" * 64)], now=LATER)

    assert outcomes[0].action == "unchanged"
    assert outcomes[0].page_changed is True
    assert scalar(engine, "select raw_sha256 from iris_staging.signal_ingest") == "b" * 64
    assert scalar(engine, "select count(*) from iris_staging.signal_ingest_version") == 1


# =========================================================
# ISOLATION
# =========================================================


@pytest.mark.integration
def test_one_rejected_record_does_not_block_the_others(engine, runlog):
    run_id = runlog.start("offline", {}, "test")

    rejected = project(
        source_record_id="project:strasbourg",
        x=STRASBOURG[0],
        y=STRASBOURG[1],
    )

    errors = []

    with engine.begin() as conn:

        store = SignalStore(conn, SOURCE)

        for record in [rejected, project()]:

            try:
                with store.savepoint():
                    store.upsert(record, run_id, NOW)

            except DBAPIError as exc:
                errors.append((record.source_record_id, str(exc.orig)))

    assert [key for key, _ in errors] == ["project:strasbourg"]
    assert "outside region DE-BW" in errors[0][1]
    assert scalar(engine, "select count(*) from iris_staging.signal_ingest") == 1


# =========================================================
# LIFECYCLE
# =========================================================


def missing_run(engine, runlog, seen_keys, retire_after=2):
    run_id = runlog.start("offline", {}, "test")

    with engine.begin() as conn:
        store = SignalStore(conn, SOURCE)
        store.mark_seen("project", seen_keys, run_id, LATER)
        return store.mark_missing("project", seen_keys, retire_after)


@pytest.mark.integration
def test_a_record_is_retired_only_after_consecutive_misses(engine, runlog):
    run_once(engine, runlog, [project()])

    first = missing_run(engine, runlog, set())
    assert first == (1, 0)
    assert scalar(engine, "select retired_at is null from iris_staging.signal_ingest") is True

    second = missing_run(engine, runlog, set())
    assert second == (1, 1)
    assert scalar(engine, "select retired_at is not null from iris_staging.signal_ingest") is True


@pytest.mark.integration
def test_a_retired_record_seen_again_is_unretired(engine, runlog):
    run_once(engine, runlog, [project()])
    missing_run(engine, runlog, set())
    missing_run(engine, runlog, set())

    missing_run(engine, runlog, {"project:umspannwerk-pulverdingen"})

    assert scalar(engine, "select retired_at is null from iris_staging.signal_ingest") is True
    assert scalar(engine, "select missing_run_count from iris_staging.signal_ingest") == 0


@pytest.mark.integration
def test_derived_facts_are_set_without_touching_the_content_hash(engine, runlog):
    run_once(engine, runlog, [project(), press()])

    before = scalar(
        engine,
        "select content_hash from iris_staging.signal_ingest where record_kind = 'project'",
    )

    with engine.begin() as conn:
        refreshed = SignalStore(conn, SOURCE).refresh_derived()

    assert refreshed == 1

    derived = scalar(engine, "select derived from iris_staging.signal_ingest where record_kind = 'project'")

    assert derived["first_reported_at"] == "2023-03-01"
    assert derived["latest_event"]["stage"] == "construction"
    assert derived["related_press_count"] == 1
    assert scalar(
        engine,
        "select content_hash from iris_staging.signal_ingest where record_kind = 'project'",
    ) == before

    with engine.begin() as conn:
        assert SignalStore(conn, SOURCE).refresh_derived() == 0


# =========================================================
# RUN CONTROL
# =========================================================


@pytest.mark.integration
def test_a_second_concurrent_run_cannot_take_the_lock(engine):
    first = RunLog(engine, SOURCE)
    second = RunLog(engine, SOURCE)

    try:
        assert first.acquire_lock() is True
        assert second.acquire_lock() is False

        first.release_lock()
        assert second.acquire_lock() is True

    finally:
        first.close()
        second.close()


@pytest.mark.integration
def test_fixture_runs_and_live_runs_cannot_share_a_database(engine, runlog):
    assert runlog.other_mode_present("offline") is False

    runlog.start("live", {}, "test")

    assert runlog.other_mode_present("offline") is True
    assert runlog.other_mode_present("live") is False


@pytest.mark.integration
def test_run_bookkeeping_survives_a_rolled_back_run(engine, runlog):
    run_id = runlog.start("offline", {"since": "2020-01-01"}, "test")

    with pytest.raises(RuntimeError):

        with engine.begin() as conn:
            SignalStore(conn, SOURCE).upsert(project(), run_id, NOW)
            runlog.issue(run_id, "error", "gate_failed", "listing_cards 3 < 15")
            raise RuntimeError("quality gate failed")

    runlog.finish(run_id, "failed", 1, {"inserted": 0}, {"listing_cards": {"value": 3, "passed": False}})

    assert scalar(engine, "select count(*) from iris_staging.signal_ingest") == 0
    assert scalar(engine, "select status from iris_staging.ingest_run") == "failed"
    assert scalar(engine, "select code from iris_staging.ingest_issue") == "gate_failed"


@pytest.mark.integration
def test_the_fetch_ledger_remembers_what_was_fetched(engine, runlog):
    run_id = runlog.start("offline", {}, "test")
    url = "https://www.transnetbw.de/de/netzentwicklung/projekte/umspannwerk-pulverdingen"
    lastmod = datetime(2024, 1, 30, 15, 11, 17, tzinfo=timezone.utc)

    with engine.begin() as conn:
        SignalStore(conn, SOURCE).record_document(
            url=url,
            doc_kind="project_overview",
            sitemap_lastmod=lastmod,
            http_status=200,
            raw_sha256="c" * 64,
            outcome="parsed",
            run_id=run_id,
            fetched_at=NOW,
        )

    with engine.begin() as conn:
        ledger = SignalStore(conn, SOURCE).ledger()

    assert ledger[url].sitemap_lastmod == lastmod
    assert ledger[url].last_outcome == "parsed"
