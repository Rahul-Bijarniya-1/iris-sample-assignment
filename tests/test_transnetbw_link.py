"""
Linking a press release to a project says "this release is about that
project". A wrong link misattributes a milestone, so links come only from
curated project names — never from a bare place name, because one
substation serves several projects (Kupferzell: the Netzbooster and the
Grafenrheinfeld–Kupferzell–Großgartach reinforcement).
"""

import pytest

from app.transnetbw.link import load_aliases, link_project


@pytest.fixture(scope="module")
def aliases():
    return load_aliases()


@pytest.mark.parametrize(
    "text, slug",
    [
        (
            "Netzverstärkung Badische Rheinschiene (NBR): Teilbeschluss ebnet Weg",
            "netzverstaerkung-badische-rheinschiene",
        ),
        (
            "TransnetBW feierte heute die offizielle Eröffnung der Netzbooster-Baustelle in Kupferzell.",
            "netzbooster-kupferzell",
        ),
        (
            "Spatenstich am Umspannwerk Beuren: TransnetBW startet Bauarbeiten für das Projekt Hochrhein",
            "hochrhein",
        ),
        (
            "symbolische Inbetriebnahme der Netzverstärkung Grafenrheinfeld – Kupferzell – Großgartach",
            "grafenrheinfeld-kupferzell-grossgartach",
        ),
        (
            "Modernisierung des Umspannwerkes Schwörstadt abgeschlossen",
            "umspannwerk-schwoerstadt",
        ),
    ],
)
def test_a_named_project_is_linked(aliases, text, slug):
    result = link_project(text, aliases)

    assert result.slug == slug
    assert result.ambiguous is False


@pytest.mark.parametrize(
    "text",
    [
        "Der Netzbooster soll in der Nähe des bestehenden Umspannwerks errichtet werden.",
        "Besucherinnen und Besucher beim Festakt in Kupferzell",
        "Hybride Netzbooster haben großes Potenzial",
        "Die Leitung verläuft durch den Neckar-Odenwald-Kreis.",
    ],
)
def test_a_place_name_or_generic_term_alone_links_nothing(aliases, text):
    result = link_project(text, aliases)

    assert result.slug is None
    assert result.ambiguous is False


def test_two_different_projects_named_together_link_neither(aliases):
    text = (
        "Neben dem Netzbooster Kupferzell schreitet auch die Netzverstärkung "
        "Grafenrheinfeld – Kupferzell – Großgartach voran."
    )

    result = link_project(text, aliases)

    assert result.slug is None
    assert result.ambiguous is True
    assert set(result.candidates) == {"netzbooster-kupferzell", "grafenrheinfeld-kupferzell-grossgartach"}


def test_every_alias_names_a_project_discovery_finds(aliases):
    """
    A typo in an alias key would silently never link; check the keys against
    the projects the listing and sitemap fixtures actually contain.
    """

    from pathlib import Path

    from app.transnetbw.discovery import parse_listing, parse_sitemap, project_slugs_from_sitemap

    fixtures = Path("fixtures/transnetbw")
    base = "https://www.transnetbw.de"

    listing = {card.slug for card in parse_listing((fixtures / "pages/alle-projekte.html").read_text(encoding="utf-8"), base)}
    sitemap = set(project_slugs_from_sitemap(parse_sitemap((fixtures / "sitemap.xml").read_bytes()), base))

    assert aliases
    assert set(aliases) <= listing | sitemap
