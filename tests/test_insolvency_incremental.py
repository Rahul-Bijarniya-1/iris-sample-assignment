"""
Acceptance test 1: repeated batches create zero duplicate notices, and a
changed notice keeps its history.

This is the replay-safety guarantee. A notice feed is re-read on a schedule
and overwhelmingly returns records already seen; ingesting must be
idempotent on content, and an update must never silently overwrite what the
record said before.
"""

from app.insolvency.notice import NoticeStatus
from app.insolvency.notice_parser import NoticeParser
from app.insolvency.notice_store import NoticeStore


BATCH_1 = "fixtures/insolvency/notices/batch_001.json"
BATCH_2 = "fixtures/insolvency/notices/batch_002.json"


def _store(tmp_path):
    return NoticeStore(tmp_path / "notices.json")


def _parse(path):
    return NoticeParser().parse(path)


def test_first_ingest_inserts_every_notice(tmp_path):
    store = _store(tmp_path)

    result = store.ingest(_parse(BATCH_1))

    assert result.inserted == 5
    assert result.updated == 0
    assert result.unchanged == 0
    assert store.count() == 5


def test_replaying_the_same_batch_creates_no_duplicates(tmp_path):
    """
    The core guarantee: the second pass must add nothing at all.
    """

    store = _store(tmp_path)

    store.ingest(_parse(BATCH_1))
    result = store.ingest(_parse(BATCH_1))

    assert store.count() == 5, "replay duplicated notices"
    assert result.inserted == 0
    assert result.updated == 0
    assert result.unchanged == 5


def test_replay_survives_a_reload_from_disk(tmp_path):
    """
    Replay safety must hold across process restarts, not just within one
    store instance — the scheduled reader is a fresh process each run.
    """

    path = tmp_path / "notices.json"

    NoticeStore(path).ingest(_parse(BATCH_1))
    NoticeStore(path).ingest(_parse(BATCH_1))

    assert NoticeStore(path).count() == 5


def test_replaying_the_whole_batch_sequence_adds_no_versions(tmp_path):
    """
    NOT-2026-000105 appears in both batches with different content. Replaying
    the sequence must not re-record either version: content already seen for
    a notice is a replay, even when it is not the latest version.

    Without this, every pass appends the older content as a "change" and the
    record oscillates and grows without bound.
    """

    path = tmp_path / "notices.json"

    for _ in range(3):
        store = NoticeStore(path)
        store.ingest(_parse(BATCH_1))
        store.ingest(_parse(BATCH_2))

    record = NoticeStore(path).get("NOT-2026-000105")

    assert len(record.versions) == 2, (
        "replaying the batch sequence grew the version history to "
        f"{len(record.versions)}"
    )


def test_replay_of_a_sequence_reports_everything_as_unchanged(tmp_path):
    path = tmp_path / "notices.json"

    NoticeStore(path).ingest(_parse(BATCH_1))
    NoticeStore(path).ingest(_parse(BATCH_2))

    second = NoticeStore(path)
    first_again = second.ingest(_parse(BATCH_1))
    second_again = second.ingest(_parse(BATCH_2))

    assert first_again.updated == 0
    assert second_again.updated == 0
    assert first_again.inserted == 0
    assert second_again.inserted == 0


def test_the_current_version_is_the_most_recently_published(tmp_path):
    """
    Batch order must not decide which version is current. Ingesting the
    newer batch first must still leave the later publication as current.
    """

    store = _store(tmp_path)

    store.ingest(_parse(BATCH_2))
    store.ingest(_parse(BATCH_1))

    record = store.get("NOT-2026-000105")

    assert record.current.status is NoticeStatus.LIFTED


def test_a_changed_notice_keeps_its_earlier_version(tmp_path):
    """
    NOT-2026-000105 advances from eroeffnet to aufgehoben in batch 2. The
    record must carry both, so a reviewer can see what it said before.
    """

    store = _store(tmp_path)

    store.ingest(_parse(BATCH_1))
    result = store.ingest(_parse(BATCH_2))

    assert result.updated == 1

    record = store.get("NOT-2026-000105")

    assert len(record.versions) == 2
    assert record.versions[0].status is NoticeStatus.OPENED
    assert record.versions[-1].status is NoticeStatus.LIFTED
    assert record.current.status is NoticeStatus.LIFTED


def test_an_update_does_not_duplicate_the_notice(tmp_path):
    store = _store(tmp_path)

    store.ingest(_parse(BATCH_1))
    store.ingest(_parse(BATCH_2))

    ids = [r.notice_id for r in store.records()]

    assert len(ids) == len(set(ids)), f"duplicate notice ids: {ids}"


def test_a_new_notice_in_a_later_batch_is_inserted(tmp_path):
    store = _store(tmp_path)

    store.ingest(_parse(BATCH_1))
    result = store.ingest(_parse(BATCH_2))

    assert result.inserted == 2  # NOT-...106 withdrawn, NOT-...107 new
    assert store.get("NOT-2026-000107") is not None


def test_tracks_first_and_last_seen_for_freshness(tmp_path):
    """
    The audit output reports an as-of date, so the store has to know when a
    notice was first seen and when it was last confirmed.
    """

    store = _store(tmp_path)

    store.ingest(_parse(BATCH_1))
    store.ingest(_parse(BATCH_2))

    record = store.get("NOT-2026-000101")

    assert record.first_seen_at is not None
    assert record.last_seen_at is not None
    assert record.last_seen_at >= record.first_seen_at
