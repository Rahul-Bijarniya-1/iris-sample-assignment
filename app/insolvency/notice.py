"""
The normalised insolvency notice.

A notice is the published court record of an insolvency event. It is NOT a
statement about property: nothing here says a debtor's site is available, for
sale, or lettable. Downstream consumers must not infer that.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum


class NoticeStatus(Enum):
    """
    The lifecycle state a notice reports.

    Only OPENED describes a live insolvency. Anything else — lifted,
    withdrawn, dismissed — or an unrecognised value must not read as one,
    which is why `is_active` whitelists rather than blacklists.
    """

    OPENED = "opened"
    LIFTED = "lifted"
    WITHDRAWN = "withdrawn"
    DISMISSED = "dismissed"
    UNKNOWN = "unknown"

    @classmethod
    def from_source(cls, value: str | None) -> "NoticeStatus":

        mapping = {
            "eroeffnet": cls.OPENED,
            "eröffnet": cls.OPENED,
            "aufgehoben": cls.LIFTED,
            "eingestellt": cls.LIFTED,
            "zurueckgenommen": cls.WITHDRAWN,
            "zurückgenommen": cls.WITHDRAWN,
            "abgewiesen": cls.DISMISSED,
        }

        if not value:
            return cls.UNKNOWN

        return mapping.get(value.strip().lower(), cls.UNKNOWN)


@dataclass(frozen=True)
class Address:
    """
    A postal address. Every field is optional: notices frequently omit the
    address, and that absence is meaningful rather than an error.
    """

    street: str | None = None
    postal_code: str | None = None
    city: str | None = None

    @property
    def is_empty(self) -> bool:
        return not any((self.street, self.postal_code, self.city))


@dataclass(frozen=True)
class Notice:
    """
    One normalised notice.

    `notice_id` is the publisher's stable identifier and the dedup key.
    `retrieved_at` is when this copy was fetched — it is deliberately excluded
    from `content_fingerprint` so replaying an unchanged notice does not look
    like a change.
    """

    notice_id: str
    court: str
    case_number: str
    entity_name: str
    entity_registry_id: str | None
    entity_address: Address
    published_on: date | None
    event_on: date | None
    status: NoticeStatus
    source_reference: str
    retrieved_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.status is NoticeStatus.OPENED

    @property
    def content_fingerprint(self) -> str:
        """
        Stable hash of the notice's substance, used to tell a replay from a
        genuine update. Retrieval time is excluded on purpose.
        """

        payload = {
            "notice_id": self.notice_id,
            "court": self.court,
            "case_number": self.case_number,
            "entity_name": self.entity_name,
            "entity_registry_id": self.entity_registry_id,
            "entity_address": asdict(self.entity_address),
            "published_on": (
                self.published_on.isoformat()
                if self.published_on
                else None
            ),
            "event_on": (
                self.event_on.isoformat() if self.event_on else None
            ),
            "status": self.status.value,
            "source_reference": self.source_reference,
        }

        encoded = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")

        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict:

        return {
            "notice_id": self.notice_id,
            "court": self.court,
            "case_number": self.case_number,
            "entity_name": self.entity_name,
            "entity_registry_id": self.entity_registry_id,
            "entity_address": asdict(self.entity_address),
            "published_on": (
                self.published_on.isoformat()
                if self.published_on
                else None
            ),
            "event_on": (
                self.event_on.isoformat() if self.event_on else None
            ),
            "status": self.status.value,
            "source_reference": self.source_reference,
            "retrieved_at": (
                self.retrieved_at.isoformat()
                if self.retrieved_at
                else None
            ),
            "content_fingerprint": self.content_fingerprint,
        }
