"""
Audit output for entity-notice matching.

Two artefacts, deliberately:

  - CSV, one row per notice, for a reviewer to sort and filter. Candidate
    sets are summarised here rather than expanded, so the file stays
    readable in a spreadsheet.
  - JSON, the complete record including every candidate considered, for
    anyone auditing a specific decision.

Both carry the rationale, the as-of date of the underlying notice, and the
human-review flag. None of the fields describe the debtor's property: an
insolvency notice is a court record and says nothing about availability.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from app.insolvency.notice_store import IngestResult
from app.insolvency.resolver import MatchResult


CSV_COLUMNS = [
    "notice_id",
    "entity_name",
    "registry_id",
    "method",
    "confidence",
    "auto_matched",
    "human_review",
    "address_agreement",
    "notice_status",
    "notice_is_active",
    "as_of",
    "candidate_count",
    "rationale",
]


def summarise(matches: list[MatchResult]) -> dict:

    return {
        "total": len(matches),
        "auto_matched": sum(1 for m in matches if m.auto_matched),
        "human_review": sum(1 for m in matches if m.human_review),
        "unmatched": sum(1 for m in matches if m.registry_id is None),
        "active_notices": sum(
            1 for m in matches if m.notice_is_active
        ),
    }


def write_audit(
    matches: list[MatchResult],
    csv_path: str | Path,
    json_path: str | Path,
    ingest: IngestResult | None = None,
    sources: dict | None = None,
) -> dict:
    """
    Write both audit artefacts and return the summary.
    """

    csv_path = Path(csv_path)
    json_path = Path(json_path)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    _write_csv(matches, csv_path)

    summary = summarise(matches)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources or {},
        "summary": summary,
        "matches": [match.to_dict() for match in matches],
    }

    if ingest is not None:
        payload["ingest"] = ingest.to_dict()

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

    return summary


def _write_csv(matches: list[MatchResult], path: Path) -> None:

    with path.open("w", newline="", encoding="utf-8") as handle:

        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)

        writer.writeheader()

        for match in matches:

            writer.writerow(
                {
                    "notice_id": match.notice_id,
                    "entity_name": match.entity_name,
                    "registry_id": match.registry_id or "",
                    "method": match.method.value,
                    "confidence": f"{match.confidence:.2f}",
                    "auto_matched": match.auto_matched,
                    "human_review": match.human_review,
                    "address_agreement": (
                        ""
                        if match.address_agreement is None
                        else match.address_agreement
                    ),
                    "notice_status": match.notice_status,
                    "notice_is_active": match.notice_is_active,
                    "as_of": (
                        match.as_of.isoformat() if match.as_of else ""
                    ),
                    "candidate_count": len(match.candidates),
                    "rationale": match.rationale,
                }
            )
