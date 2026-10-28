"""
Project discovery: the listing page and the sitemap.

Neither is complete on its own — on 2026-10-27 the listing lacked two
projects the sitemap had and the sitemap lacked one the listing had — so
the harvester takes their union and reports the difference.

Listing cards are recognised only by the site's card markup
(a.card-project). A redesign therefore yields no cards, which the
empty-response gate turns into a failed run, instead of a guess assembled
from arbitrary links.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from app.transnetbw.errors import ParseError
from app.transnetbw.normalize import clean_text


SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

PROJECT_PATH = re.compile(r"^/de/netzentwicklung/projekte/([a-z0-9][a-z0-9-]*)/?$")

COMPLETED_SECTION = re.compile(r"abgeschlossen", re.IGNORECASE)

# Category and overview pages that live at the project path level but are
# not projects.
DEFAULT_DENYLIST = frozenset(
    {
        "alle-projekte",
        "alle-projekte-marker-interaktive-karte",
        "abgeschlossene-projekte",
        "instandhaltung-und-erweiterung",
        "netzausbau",
        "netzoptimierung",
        "netzverstaerkung",
        "umspannwerke",
    }
)


@dataclass(frozen=True)
class ListingCard:

    slug: str

    url: str

    title: str

    category_label: str | None

    teaser: str | None

    section: str | None

    @property
    def completed(self) -> bool:
        return bool(self.section and COMPLETED_SECTION.search(self.section))


# =========================================================
# SITEMAP
# =========================================================


def _parse_lastmod(value: str | None) -> datetime | None:

    value = (value or "").strip()

    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def parse_sitemap(content: bytes, url: str | None = None) -> dict[str, datetime | None]:
    """
    URL → lastmod for every <url> entry.
    """

    try:
        root = ElementTree.fromstring(content)

    except ElementTree.ParseError as exc:
        raise ParseError(url, f"malformed sitemap XML ({exc})") from exc

    if not root.tag.endswith("urlset"):
        raise ParseError(url, f"not a sitemap (root element <{root.tag}>)")

    entries = {}

    for entry in root.iter(f"{SITEMAP_NS}url"):

        loc = (entry.findtext(f"{SITEMAP_NS}loc") or "").strip()

        if loc:
            entries[loc] = _parse_lastmod(entry.findtext(f"{SITEMAP_NS}lastmod"))

    if not entries:
        raise ParseError(url, "sitemap contains no URLs")

    return entries


def project_slugs_from_sitemap(
    lastmods: dict[str, datetime | None],
    base_url: str,
    denylist: frozenset[str] = DEFAULT_DENYLIST,
) -> dict[str, datetime | None]:
    """
    Top-level project pages only: subpages (projektportraet, im-dialog…)
    and category pages are left out.
    """

    site = urlsplit(base_url).netloc

    slugs = {}

    for url, lastmod in lastmods.items():

        parts = urlsplit(url)

        if parts.netloc != site:
            continue

        match = PROJECT_PATH.match(parts.path)

        if match and match.group(1) not in denylist:
            slugs[match.group(1)] = lastmod

    return slugs


# =========================================================
# LISTING
# =========================================================


def _text(node) -> str | None:
    return clean_text(node.get_text(" ", strip=True)) if node is not None else None


def parse_listing(html: str, base_url: str) -> list[ListingCard]:

    soup = BeautifulSoup(html, "lxml")

    site = urlsplit(base_url).netloc

    cards: dict[str, ListingCard] = {}

    for link in soup.select("a.card-project[href]"):

        url = urljoin(base_url, link["href"])

        parts = urlsplit(url)

        match = PROJECT_PATH.match(parts.path)

        if parts.netloc != site or not match:
            continue

        title = _text(link.select_one(".card-project__headline"))

        if not title:
            continue

        slug = match.group(1)

        if slug in cards:
            continue

        section = link.find_previous("p", class_="h2--preheadline")

        cards[slug] = ListingCard(
            slug=slug,
            url=f"{base_url.rstrip('/')}/de/netzentwicklung/projekte/{slug}",
            title=title,
            category_label=_text(link.select_one(".card-project__preheadline")),
            teaser=_text(link.select_one(".card-project__copy")),
            section=_text(section),
        )

    return list(cards.values())


def discovery_diff(
    listing_slugs: set[str],
    sitemap_slugs: set[str],
) -> tuple[set[str], set[str]]:
    """
    (listing only, sitemap only).
    """

    return listing_slugs - sitemap_slugs, sitemap_slugs - listing_slugs
