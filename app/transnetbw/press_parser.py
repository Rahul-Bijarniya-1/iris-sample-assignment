"""
Press releases: the JSON feed the newsroom page loads, and each article's
HTML.

The feed is used for discovery only. An article's publication date is read
from the article page and compared with the feed by the harvester, so a
record's date is verified rather than assumed.

Article text is cut at the press-contact section and stripped of any
paragraph carrying an e-mail address or phone number: names and numbers of
press officers have no place in a signal record.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date

from bs4 import BeautifulSoup

from app.transnetbw.errors import ParseError
from app.transnetbw.htmltext import element_text, is_boilerplate
from app.transnetbw.normalize import clean_text


MONTHS = {
    "januar": 1, "jan": 1,
    "februar": 2, "feb": 2,
    "märz": 3, "maerz": 3, "mär": 3, "mrz": 3,
    "april": 4, "apr": 4,
    "mai": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "dez": 12,
}

LONG_DATE = re.compile(r"^(\d{1,2})\.\s*([A-Za-zÄÖÜäöü]+)\.?\s+(\d{4})$")

NUMERIC_DATE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$")

# A dateline is one or more place segments, each ending in ". ", before the
# first sentence: "Stuttgart / Bayreuth.", "Oerlenbach. Stuttgart.",
# "Beuren an der Aach, Singen (Hohentwiel).". Words are capitalized;
# lower-case connectors are allowed between them; digits never are.
_WORD = r"[A-ZÄÖÜ][a-zäöüß]+(?:-[A-ZÄÖÜ]?[a-zäöüß]+)*"
_CONNECTOR = r"(?:an|am|der|die|im|in|bei|ob|vor|auf|unter)"
_PLACE = rf"{_WORD}(?:\s+(?:{_CONNECTOR}\s+)*{_WORD})*(?:\s+\({_WORD}(?:\s+{_WORD})*\))?"
_SEGMENT = rf"{_PLACE}(?:\s*(?:/|,)\s*{_PLACE})*"

DATELINE = re.compile(rf"^({_SEGMENT}(?:\.\s+{_SEGMENT})*)\.\s+(?=\S)")

DATELINE_MAX = 80

# Abbreviations that look like a one-word dateline ("Dr. Werner Götz …").
ABBREVIATIONS = frozenset(
    {"Dr", "Prof", "Dipl", "Ing", "St", "Nr", "Hr", "Fr", "Ca", "Mio", "Mrd", "Bzw", "Ggf", "Inkl", "Evtl", "Abs", "Art"}
)

CONTACT_HEADING = re.compile(
    r"^(?:Für weitere Informationen|Pressekontakt|Ansprechpartner|Ihr Kontakt|Kontakt\s*:)",
    re.IGNORECASE,
)

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

PHONE = re.compile(r"\b(?:Telefon|Tel\.|Fax|Mobil)\b|\+\d{2}[\s\d/()-]{6,}")


def parse_german_date(text: str | None) -> date | None:
    """
    "15. Oktober 2026" or "15.10.2026" → date. Anything else, including an
    impossible calendar date, is None: a wrong date is worse than none.
    """

    text = clean_text(text)

    if not text:
        return None

    match = LONG_DATE.match(text)

    if match:

        day, month_name, year = match.groups()

        month = MONTHS.get(month_name.lower())

        if month is None:
            return None

    else:

        match = NUMERIC_DATE.match(text)

        if not match:
            return None

        day, month, year = match.groups()

    try:
        return date(int(year), int(month), int(day))

    except ValueError:
        return None


def strip_dateline(paragraph: str) -> tuple[str | None, str]:
    """
    (dateline, rest) — or (None, paragraph) when it does not open with one.
    """

    match = DATELINE.match(paragraph)

    if not match:
        return None, paragraph

    dateline = match.group(1)

    words = set(re.findall(r"[A-Za-zÄÖÜäöüß]+", dateline))

    if len(dateline) > DATELINE_MAX or words & ABBREVIATIONS:
        return None, paragraph

    return dateline, paragraph[match.end():]


# =========================================================
# FEED
# =========================================================


@dataclass(frozen=True)
class FeedItem:

    url: str

    slug: str

    title: str

    date: date | None

    types: tuple[str, ...]

    raw_date: str | None = None


@dataclass
class FeedParse:

    items: list[FeedItem] = field(default_factory=list)

    duplicates: list[dict] = field(default_factory=list)

    malformed: list[dict] = field(default_factory=list)


def _feed_date(raw) -> date | None:

    try:
        return date.fromisoformat(str(raw).strip())

    except (TypeError, ValueError):
        return None


def parse_feed(text: str, url: str | None = None) -> FeedParse:
    """
    Validate and deduplicate the press-release feed.

    A URL listed more than once keeps its most recent date; the conflict is
    reported in `duplicates`. Items without a URL or title are reported in
    `malformed` and dropped; an unreadable date is reported but the item is
    kept with date None, because the article page may still supply one.
    """

    try:
        data = json.loads(text)

    except json.JSONDecodeError as exc:
        raise ParseError(url, f"press feed is not JSON ({exc.msg})") from exc

    if not isinstance(data, list):
        raise ParseError(url, f"press feed is a JSON {type(data).__name__}, not a list")

    result = FeedParse()

    by_url: dict[str, FeedItem] = {}

    dates_by_url: dict[str, list[str]] = {}

    for index, raw in enumerate(data):

        if not isinstance(raw, dict):
            result.malformed.append({"index": index, "url": None, "reason": "not an object"})
            continue

        item_url = clean_text(raw.get("url"))

        if not item_url:
            result.malformed.append({"index": index, "url": None, "reason": "missing url"})
            continue

        title = clean_text(raw.get("title"))

        if not title:
            result.malformed.append({"index": index, "url": item_url, "reason": "missing title"})
            continue

        raw_date = raw.get("date")

        published = _feed_date(raw_date)

        if published is None:
            result.malformed.append(
                {"index": index, "url": item_url, "reason": f"unreadable date {str(raw_date)!r}"}
            )

        item = FeedItem(
            url=item_url,
            slug=item_url.rstrip("/").rsplit("/", 1)[-1],
            title=title,
            date=published,
            types=tuple(clean_text(value) for value in (raw.get("type") or []) if clean_text(value)),
            raw_date=None if raw_date is None else str(raw_date),
        )

        dates_by_url.setdefault(item_url, []).append(published.isoformat() if published else str(raw_date))

        held = by_url.get(item_url)

        if held is None or (published and (held.date is None or published > held.date)):
            by_url[item_url] = item

    order = {}

    for index, raw in enumerate(data):

        if isinstance(raw, dict):
            order.setdefault(clean_text(raw.get("url")), index)

    result.items = sorted(by_url.values(), key=lambda item: order[item.url])

    result.duplicates = [
        {"url": item_url, "dates": sorted(dates, reverse=True)}
        for item_url, dates in dates_by_url.items()
        if len(dates) > 1
    ]

    return result


# =========================================================
# ARTICLE
# =========================================================


@dataclass
class PressArticle:

    url: str

    title: str

    date: date | None

    date_text: str | None

    dateline: str | None

    subheads: list[str]

    lead: str | None

    paragraphs: list[str]

    def text(self) -> str:
        return " ".join(part for part in (self.title, *self.subheads, *self.paragraphs) if part)


def _is_personal(paragraph_tag, text: str) -> bool:

    return bool(
        EMAIL.search(text)
        or PHONE.search(text)
        or paragraph_tag.select_one('a[href^="mailto:"]') is not None
    )


def parse_article(html: str, url: str) -> PressArticle:

    soup = BeautifulSoup(html, "lxml")

    main = soup.find("main") or soup.body

    if main is None:
        raise ParseError(url, "no page body")

    title = element_text(main.select_one("h1"))

    if not title:
        raise ParseError(url, "no page title")

    date_text = element_text(main.select_one("p.header__overline"))

    blocks = [
        block
        for block in main.select(".neos-contentcollection .text")
        if not is_boilerplate(block)
    ]

    subheads = []

    if blocks:
        subheads = [text for text in (element_text(li) for li in blocks[0].find_all("li")) if text]

    paragraphs = []

    stopped = False

    for block in blocks:

        for paragraph in block.find_all("p"):

            text = element_text(paragraph)

            if not text:
                continue

            if CONTACT_HEADING.match(text):
                stopped = True
                break

            if _is_personal(paragraph, text):
                continue

            paragraphs.append(text)

        if stopped:
            break

    dateline = None

    lead = None

    if paragraphs:

        dateline, first = strip_dateline(paragraphs[0])

        paragraphs[0] = first

        lead = first

    return PressArticle(
        url=url,
        title=title,
        date=parse_german_date(date_text),
        date_text=date_text,
        dateline=dateline,
        subheads=subheads,
        lead=lead,
        paragraphs=paragraphs,
    )
