"""
Text cleaning and the SignalRecord every later stage fills in.

SignalRecord.content_hash() decides whether a re-run is an update, so it
covers the signal and nothing else: fetch time, raw page bytes, sitemap
lastmod and cross-record derived values are deliberately left out (they are
stored, but as audit information).
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime


SOFT_HYPHEN = "­"

INVISIBLE = dict.fromkeys(map(ord, "­​‌‍﻿"), None)

SPACE_LIKE = re.compile(r"[\s   ]+")


def clean_text(value: str | None) -> str | None:
    """
    Decode HTML entities, drop soft hyphens and zero-width characters,
    normalize to NFC, collapse whitespace. Blank text becomes None.
    """

    if value is None:
        return None

    text = html.unescape(str(value))

    text = text.translate(INVISIBLE)

    text = unicodedata.normalize("NFC", text)

    text = SPACE_LIKE.sub(" ", text).strip()

    return text or None


def cap(text: str | None, limit: int) -> str | None:
    """
    Shorten to at most `limit` characters at a word boundary, marking the
    cut with an ellipsis.
    """

    if text is None or len(text) <= limit:
        return text

    cut = text[: limit - 1]

    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]

    return cut.rstrip(" ,;:–-") + "…"


def _round(value: float | None) -> float | None:
    """
    Coordinates are compared at decimetre resolution: reprojection noise
    is not a move.
    """

    return None if value is None else round(float(value), 1)


def _json_default(value):

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    raise TypeError(f"not JSON serializable: {type(value).__name__}")


HASHED_FIELDS = (
    "source_system",
    "source_record_id",
    "record_kind",
    "signal_type",
    "project_stage",
    "review_status",
    "title",
    "summary",
    "source_url",
    "language",
    "published_at",
    "published_at_verified",
    "country_code",
    "region_code",
    "location_text",
    "location_status",
    "location_precision",
    "location_method",
    "x",
    "y",
    "attributes",
    "quality_flags",
)


@dataclass
class SignalRecord:
    """
    One staging row in the making. x / y are EPSG:25832 metres.
    """

    source_system: str

    source_record_id: str

    record_kind: str

    signal_type: str

    title: str

    source_url: str

    project_stage: str = "unknown"

    review_status: str = "auto"

    summary: str | None = None

    published_at: date | None = None

    published_at_verified: bool = False

    source_last_modified: datetime | None = None

    location_text: str | None = None

    location_status: str = "unresolved"

    location_precision: str | None = None

    location_method: str | None = None

    x: float | None = None

    y: float | None = None

    attributes: dict = field(default_factory=dict)

    quality_flags: list[str] = field(default_factory=list)

    raw_sha256: str | None = None

    language: str = "de"

    country_code: str = "DE"

    region_code: str = "DE-BW"

    def signal_fields(self) -> dict:
        """
        The fields that make up the signal, in canonical form.
        """

        values = {name: getattr(self, name) for name in HASHED_FIELDS}

        values["x"] = _round(self.x)

        values["y"] = _round(self.y)

        values["quality_flags"] = sorted(set(self.quality_flags))

        return values

    def content_hash(self) -> str:

        canonical = json.dumps(
            self.signal_fields(),
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            default=_json_default,
        )

        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def payload(self) -> dict:
        """
        JSON-ready snapshot for signal_ingest_version.
        """

        return json.loads(
            json.dumps(
                {**self.signal_fields(), "content_hash": self.content_hash()},
                ensure_ascii=False,
                default=_json_default,
            )
        )
