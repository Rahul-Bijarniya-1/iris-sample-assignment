"""
Discovery decides which projects exist. Two sources disagree in practice:
the listing page omits two projects the sitemap has (Seiltausch Höllental,
Schaltanlage Obermooweiler) and the sitemap omits one the listing has
(Stalldorf / Main-Tauber). Both must be read, compared and reported.

A redesigned listing must yield no cards rather than a guess built from
arbitrary links, so the empty-response gate can stop the run.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.transnetbw.discovery import (
    DEFAULT_DENYLIST,
    discovery_diff,
    parse_listing,
    parse_sitemap,
    project_slugs_from_sitemap,
)
from app.transnetbw.errors import ParseError


FIXTURES = Path("fixtures/transnetbw")

BASE = "https://www.transnetbw.de"


@pytest.fixture(scope="module")
def cards():
    html = (FIXTURES / "pages/alle-projekte.html").read_text(encoding="utf-8")
    return parse_listing(html, BASE)


@pytest.fixture(scope="module")
def lastmods():
    return parse_sitemap((FIXTURES / "sitemap.xml").read_bytes())


def test_every_project_card_on_the_listing_is_found(cards):
    assert len(cards) == 23


def test_a_card_carries_slug_title_category_and_absolute_url(cards):
    card = next(card for card in cards if card.slug == "umspannwerk-pulverdingen")

    assert card.title == "Umspannwerk Pulverdingen"
    # The source label carries a trailing &nbsp; that must not survive.
    assert card.category_label == "Erweiterung"
    assert card.url == f"{BASE}/de/netzentwicklung/projekte/umspannwerk-pulverdingen"
    assert card.section == "Instandhaltung, Erweiterung und Neubau"


def test_cards_in_the_completed_section_are_marked_completed(cards):
    completed = {card.slug for card in cards if card.completed}

    assert completed == {"umspannwerk-schwoerstadt", "stalldorf-main-tauber"}


def test_a_redesigned_listing_yields_no_cards_rather_than_a_guess():
    redesigned = """
    <main>
      <div class="project-teaser">
        <a href="/de/netzentwicklung/projekte/umspannwerk-pulverdingen">Umspannwerk Pulverdingen</a>
      </div>
    </main>
    """

    assert parse_listing(redesigned, BASE) == []


def test_sitemap_lastmod_is_read_as_an_aware_timestamp(lastmods):
    lastmod = lastmods[f"{BASE}/de/netzentwicklung/projekte/umspannwerk-pulverdingen"]

    assert lastmod == datetime(2024, 1, 30, 16, 11, 17, tzinfo=timezone(timedelta(hours=1)))


def test_sitemap_project_slugs_exclude_overview_pages_and_subpages(lastmods):
    slugs = project_slugs_from_sitemap(lastmods, BASE, DEFAULT_DENYLIST)

    assert "umspannwerk-pulverdingen" in slugs
    assert "seiltausch-hoellental" in slugs
    assert not {"alle-projekte", "netzausbau", "umspannwerke", "abgeschlossene-projekte"} & set(slugs)
    assert all("/" not in slug for slug in slugs)
    assert len(slugs) == 24


def test_the_listing_and_sitemap_disagreement_is_reported(cards, lastmods):
    sitemap_slugs = project_slugs_from_sitemap(lastmods, BASE, DEFAULT_DENYLIST)

    listing_only, sitemap_only = discovery_diff({card.slug for card in cards}, set(sitemap_slugs))

    assert listing_only == {"stalldorf-main-tauber"}
    assert sitemap_only == {"seiltausch-hoellental", "schaltanlage-obermooweiler"}


def test_a_malformed_sitemap_is_a_parse_error():
    with pytest.raises(ParseError):
        parse_sitemap(b"<urlset><url><loc>https://www.transnetbw.de/de</loc>")


def test_a_sitemap_without_urls_is_a_parse_error():
    """
    An HTML error page served with status 200 is not an empty sitemap.
    """

    with pytest.raises(ParseError):
        parse_sitemap(b"<html><body>Wartungsarbeiten</body></html>")
