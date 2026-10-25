"""
Parse raw notice batches into normalised Notice records.

Source batches use German portal field names. Keys beginning with "_" are
fixture annotations (controls, provenance notes) and are ignored.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from app.insolvency.notice import Address, Notice, NoticeStatus


class NoticeParser:
    """
    Turns a notice batch file into Notice records.

    A record missing the publisher's notice id is skipped rather than
    assigned a synthetic one: without a stable id there is no safe dedup
    key, and inventing one would create duplicates on the next batch.
    """

    NOTICES_KEY = "bekanntmachungen"

    def parse(self, file_path: str | Path) -> list[Notice]:

        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(
                f"Notice batch not found: {file_path}"
            )

        with file_path.open("r", encoding="utf-8") as handle:
            batch = json.load(handle)

        retrieved_at = self._parse_datetime(
            batch.get("retrieved_at")
        )

        batch_source = batch.get("source_reference", str(file_path))

        notices = []

        for raw in batch.get(self.NOTICES_KEY, []):

            notice = self._build(raw, retrieved_at, batch_source)

            if notice is not None:
                notices.append(notice)

        return notices

    # ------------------------------------------------------------------

    def _build(
        self,
        raw: dict,
        retrieved_at: datetime | None,
        batch_source: str,
    ) -> Notice | None:

        notice_id = (raw.get("id") or "").strip()

        if not notice_id:
            return None

        debtor = raw.get("schuldner") or {}
        address = debtor.get("anschrift") or {}

        return Notice(
            notice_id=notice_id,
            court=(raw.get("gericht") or "").strip(),
            case_number=(raw.get("aktenzeichen") or "").strip(),
            entity_name=(debtor.get("name") or "").strip(),
            entity_registry_id=self._clean(
                debtor.get("registernummer")
            ),
            entity_address=Address(
                street=self._clean(address.get("strasse")),
                postal_code=self._clean(address.get("plz")),
                city=self._clean(address.get("ort")),
            ),
            published_on=self._parse_date(
                raw.get("bekanntmachung_am")
            ),
            event_on=self._parse_date(raw.get("ereignis_am")),
            status=NoticeStatus.from_source(raw.get("status")),
            source_reference=(
                raw.get("quelle") or batch_source
            ),
            retrieved_at=retrieved_at,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _clean(value: str | None) -> str | None:

        if value is None:
            return None

        cleaned = str(value).strip()

        return cleaned or None

    @staticmethod
    def _parse_date(value: str | None) -> date | None:

        if not value:
            return None

        try:
            return date.fromisoformat(str(value).strip())
        except ValueError:
            return None

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:

        if not value:
            return None

        try:
            return datetime.fromisoformat(str(value).strip())
        except ValueError:
            return None
