"""
Drift canary: do the parsers still understand the live site?

The fixtures freeze TransnetBW's markup as captured on 2026-10-27, so the
offline suite stays green after a redesign. This test reads the live site —
robots.txt, the sitemap, the listing, one project page and the newest press
article: five polite requests — and checks that every parser still finds
what the quality gates require.

Opt-in only: uv run pytest --run-live -m live
"""

import re

import pytest

from app.transnetbw.config import TransnetBWSettings
from app.transnetbw.discovery import discovery_diff, parse_listing, parse_sitemap, project_slugs_from_sitemap
from app.transnetbw.fetch import LiveFetcher
from app.transnetbw.press_parser import parse_article
from app.transnetbw.project_parser import parse_project_page


ARTICLE = re.compile(r"/de/newsroom/news/[a-z0-9]+(?:-[a-z0-9]+){3,}$", re.IGNORECASE)


@pytest.mark.live
def test_the_live_site_still_matches_the_parsers():
    settings = TransnetBWSettings()
    fetcher = LiveFetcher(settings)

    lastmods = parse_sitemap(fetcher.fetch(settings.url(settings.sitemap_path), "xml").content)
    sitemap_slugs = project_slugs_from_sitemap(lastmods, settings.base_url)

    cards = parse_listing(fetcher.fetch(settings.url(settings.listing_path)).text, settings.base_url)

    assert len(cards) >= settings.gate_min_listing_cards
    assert len(sitemap_slugs) >= settings.gate_min_listing_cards

    listing_only, sitemap_only = discovery_diff({card.slug for card in cards}, set(sitemap_slugs))

    assert len(listing_only) + len(sitemap_only) <= settings.gate_max_discovery_gap

    project = parse_project_page(fetcher.fetch(cards[0].url).text, cards[0].url, settings.base_url)

    assert project.title
    assert project.sections

    newest = max(
        (url for url, lastmod in lastmods.items() if lastmod and ARTICLE.search(url)),
        key=lambda url: lastmods[url],
    )

    article = parse_article(fetcher.fetch(newest).text, newest)

    assert article.title
    assert article.date is not None, f"no readable date on {newest}"
    assert article.paragraphs

    assert fetcher.request_count == 5
