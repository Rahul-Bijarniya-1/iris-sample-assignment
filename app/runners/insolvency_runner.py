"""
Run the insolvency notice slice end to end, against fixtures only.

Reads every notice batch in order, merges them into the replay-safe store,
resolves each notice's current version against the corporate registry, and
writes the audit artefacts.

Safe to run repeatedly: ingestion is idempotent on content, so a second run
reports the notices as unchanged rather than duplicating them.

No database and no network access. The brief requires the slice to run
against fixtures without project production access.
"""

from __future__ import annotations

from pathlib import Path

from app.insolvency.audit import write_audit
from app.insolvency.notice_parser import NoticeParser
from app.insolvency.notice_store import IngestResult, NoticeStore
from app.insolvency.registry import CompanyRegistry
from app.insolvency.resolver import EntityResolver


NOTICES_DIR = Path("fixtures/insolvency/notices")
REGISTRY_FILE = Path("fixtures/insolvency/registry/companies.json")
OUTPUT_DIR = Path("artifacts/insolvency")


def run(
    notices_dir: Path | str = NOTICES_DIR,
    registry_file: Path | str = REGISTRY_FILE,
    output_dir: Path | str = OUTPUT_DIR,
    reset: bool = False,
) -> dict:

    notices_dir = Path(notices_dir)
    output_dir = Path(output_dir)

    store_path = output_dir / "notice_store.json"

    if reset and store_path.exists():
        store_path.unlink()

    store = NoticeStore(store_path)

    parser = NoticeParser()

    batches = sorted(notices_dir.glob("*.json"))

    if not batches:
        raise FileNotFoundError(
            f"No notice batches found in {notices_dir}"
        )

    print("--------------------------------")
    print("Insolvency notice ingestion")
    print("--------------------------------")

    totals = IngestResult()

    for batch in batches:

        notices = parser.parse(batch)

        result = store.ingest(notices)

        totals.inserted += result.inserted
        totals.updated += result.updated
        totals.unchanged += result.unchanged

        print(
            f"{batch.name:16} "
            f"read {len(notices):3}  "
            f"new {result.inserted:3}  "
            f"changed {result.updated:3}  "
            f"replayed {result.unchanged:3}"
        )

    print("--------------------------------")
    print(f"Notices held : {store.count()}")
    print(
        f"Superseded   : "
        f"{sum(1 for r in store.records() if r.is_superseded)}"
    )

    # ------------------------------------------------------------------
    # Resolve the current version of every notice
    # ------------------------------------------------------------------

    registry = CompanyRegistry.load(registry_file)

    resolver = EntityResolver(registry)

    matches = [
        resolver.resolve(record.current)
        for record in sorted(
            store.records(),
            key=lambda r: r.notice_id,
        )
    ]

    summary = write_audit(
        matches,
        output_dir / "audit.csv",
        output_dir / "audit.json",
        ingest=totals,
        sources={
            "notices": [str(b) for b in batches],
            "registry": str(registry_file),
            "registry_companies": len(registry),
        },
    )

    print("--------------------------------")
    print(f"Registry companies : {len(registry)}")
    print(f"Auto-matched       : {summary['auto_matched']}")
    print(f"Needs review       : {summary['human_review']}")
    print(f"Unmatched          : {summary['unmatched']}")
    print(f"Active notices     : {summary['active_notices']}")
    print("--------------------------------")
    print(f"Audit CSV  : {output_dir / 'audit.csv'}")
    print(f"Audit JSON : {output_dir / 'audit.json'}")
    print("--------------------------------")

    return {
        "ingest": totals.to_dict(),
        "summary": summary,
        "notices_held": store.count(),
    }
