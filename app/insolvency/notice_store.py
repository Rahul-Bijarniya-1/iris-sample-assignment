"""
Replay-safe incremental notice store.

A notice feed is re-read on a schedule and mostly returns records already
seen. Two properties matter:

  - Ingesting the same content twice changes nothing (idempotent on content).
  - When content does change, the previous version is kept, never overwritten.

Change is detected by Notice.content_fingerprint, which excludes retrieval
time — otherwise every replay would look like an update.

The store is a JSON file so the whole pipeline runs against fixtures with no
database access, as the brief requires.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from app.insolvency.notice import Address, Notice, NoticeStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class NoticeRecord:
    """
    Everything the store knows about one notice id.

    `versions` holds each distinct content version ordered by publication
    date, so `current` is the most recently published one regardless of the
    order the batches happened to arrive in.
    """

    notice_id: str
    versions: list[Notice] = field(default_factory=list)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None

    @property
    def current(self) -> Notice:
        return self.versions[-1]

    @property
    def fingerprints(self) -> set[str]:
        return {version.content_fingerprint for version in self.versions}

    @property
    def is_superseded(self) -> bool:
        return len(self.versions) > 1


@dataclass
class IngestResult:
    """
    What one ingest pass did. `unchanged` is the replay count — on a healthy
    schedule it is the overwhelming majority.
    """

    inserted: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def total(self) -> int:
        return self.inserted + self.updated + self.unchanged

    def to_dict(self) -> dict:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "total": self.total,
        }


class NoticeStore:

    def __init__(self, path: str | Path):

        self.path = Path(path)

        self._records: dict[str, NoticeRecord] = {}

        self._load()

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    def ingest(self, notices: list[Notice]) -> IngestResult:
        """
        Merge a batch. Safe to call with the same batch any number of times.
        """

        result = IngestResult()

        seen_at = _now()

        for notice in notices:

            record = self._records.get(notice.notice_id)

            if record is None:

                self._records[notice.notice_id] = NoticeRecord(
                    notice_id=notice.notice_id,
                    versions=[notice],
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                )

                result.inserted += 1

                continue

            record.last_seen_at = seen_at

            # Compared against every version ever held, not just the latest.
            # A batch that is re-read will present content this notice has
            # already had; treating that as a change would re-append the
            # older version and let the history oscillate and grow on every
            # pass.
            if notice.content_fingerprint in record.fingerprints:
                result.unchanged += 1

                continue

            record.versions.append(notice)

            # Keep publication order so `current` is the latest notice, not
            # whichever batch happened to be ingested last.
            record.versions.sort(key=self._version_sort_key)

            result.updated += 1

        self._save()

        return result

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, notice_id: str) -> NoticeRecord | None:
        return self._records.get(notice_id)

    def records(self) -> list[NoticeRecord]:
        return list(self._records.values())

    def count(self) -> int:
        return len(self._records)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:

        if not self.path.exists():
            return

        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        for notice_id, raw in payload.get("notices", {}).items():

            self._records[notice_id] = NoticeRecord(
                notice_id=notice_id,
                versions=[
                    self._notice_from_dict(version)
                    for version in raw.get("versions", [])
                ],
                first_seen_at=self._parse_dt(raw.get("first_seen_at")),
                last_seen_at=self._parse_dt(raw.get("last_seen_at")),
            )

    def _save(self) -> None:

        self.path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "notices": {
                record.notice_id: {
                    "first_seen_at": (
                        record.first_seen_at.isoformat()
                        if record.first_seen_at
                        else None
                    ),
                    "last_seen_at": (
                        record.last_seen_at.isoformat()
                        if record.last_seen_at
                        else None
                    ),
                    "versions": [
                        version.to_dict()
                        for version in record.versions
                    ],
                }
                for record in self._records.values()
            }
        }

        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------

    @staticmethod
    def _version_sort_key(notice: Notice) -> tuple[date, date]:
        """
        Order versions by when they were published, then by event date.
        Missing dates sort first so an undated version never displaces a
        dated one as current.
        """

        return (
            notice.published_on or date.min,
            notice.event_on or date.min,
        )

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:

        if not value:
            return None

        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @classmethod
    def _notice_from_dict(cls, raw: dict) -> Notice:

        address = raw.get("entity_address") or {}

        return Notice(
            notice_id=raw["notice_id"],
            court=raw.get("court", ""),
            case_number=raw.get("case_number", ""),
            entity_name=raw.get("entity_name", ""),
            entity_registry_id=raw.get("entity_registry_id"),
            entity_address=Address(
                street=address.get("street"),
                postal_code=address.get("postal_code"),
                city=address.get("city"),
            ),
            published_on=cls._parse_date(raw.get("published_on")),
            event_on=cls._parse_date(raw.get("event_on")),
            status=NoticeStatus(raw.get("status", "unknown")),
            source_reference=raw.get("source_reference", ""),
            retrieved_at=cls._parse_dt(raw.get("retrieved_at")),
        )

    @staticmethod
    def _parse_date(value: str | None):

        from datetime import date

        if not value:
            return None

        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
