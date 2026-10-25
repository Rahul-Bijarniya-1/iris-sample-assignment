"""
The audit trail is the deliverable a reviewer actually reads.

Every row must carry why the decision was made, how fresh the underlying
notice is, and whether a human still needs to look at it.
"""

import csv
import json

from app.insolvency.audit import write_audit
from app.insolvency.notice_parser import NoticeParser
from app.insolvency.notice_store import NoticeStore
from app.insolvency.registry import CompanyRegistry
from app.insolvency.resolver import EntityResolver


BATCH_1 = "fixtures/insolvency/notices/batch_001.json"
REGISTRY = "fixtures/insolvency/registry/companies.json"

REQUIRED_COLUMNS = {
    "notice_id",
    "entity_name",
    "registry_id",
    "method",
    "confidence",
    "auto_matched",
    "human_review",
    "notice_status",
    "notice_is_active",
    "as_of",
    "rationale",
}


def _matches():
    resolver = EntityResolver(CompanyRegistry.load(REGISTRY))

    return [
        resolver.resolve(notice)
        for notice in NoticeParser().parse(BATCH_1)
    ]


def test_writes_one_csv_row_per_match(tmp_path):
    csv_path = tmp_path / "audit.csv"

    write_audit(_matches(), csv_path, tmp_path / "audit.json")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 5


def test_csv_carries_rationale_freshness_and_review_flag(tmp_path):
    csv_path = tmp_path / "audit.csv"

    write_audit(_matches(), csv_path, tmp_path / "audit.json")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        rows = list(reader)

    missing = REQUIRED_COLUMNS - columns

    assert not missing, f"audit CSV is missing columns: {missing}"

    for row in rows:
        assert row["rationale"], f"{row['notice_id']} has no rationale"


def test_json_reports_a_summary_a_reviewer_can_scan(tmp_path):
    json_path = tmp_path / "audit.json"

    write_audit(_matches(), tmp_path / "audit.csv", json_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))

    summary = payload["summary"]

    # 101 and 105 match on registry id, 102 on name plus postal code.
    # 103 is ambiguous and 104 has a conflicting address, so both are held
    # back for review.
    assert summary["total"] == 5
    assert summary["auto_matched"] == 3
    assert summary["human_review"] == 2
    assert summary["unmatched"] == 2


def test_json_keeps_the_candidate_set_for_ambiguous_notices(tmp_path):
    """
    An ambiguous decision is only reviewable if the alternatives are shown.
    """

    json_path = tmp_path / "audit.json"

    write_audit(_matches(), tmp_path / "audit.csv", json_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))

    ambiguous = next(
        row
        for row in payload["matches"]
        if row["notice_id"] == "NOT-2026-000103"
    )

    assert len(ambiguous["candidates"]) == 2


def test_audit_records_the_ingest_counts_when_given(tmp_path):
    """
    Dedup evidence belongs in the audit: how many records were new, changed
    and replayed on this pass.
    """

    store = NoticeStore(tmp_path / "notices.json")

    ingest = store.ingest(NoticeParser().parse(BATCH_1))

    json_path = tmp_path / "audit.json"

    write_audit(
        _matches(),
        tmp_path / "audit.csv",
        json_path,
        ingest=ingest,
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert payload["ingest"]["inserted"] == 5
    assert payload["ingest"]["unchanged"] == 0
