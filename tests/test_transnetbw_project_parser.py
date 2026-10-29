"""
Project pages carry the facts a signal is built from — title, lead,
equipment, voltages, line identifiers — surrounded by boilerplate that
must never leak into a record: the contact form, hotline card, event
teasers and cross-links repeated on every page.
"""

from pathlib import Path

import pytest

from app.transnetbw.errors import ParseError
from app.transnetbw.project_parser import parse_project_page


PAGES = Path("fixtures/transnetbw/pages")

BASE = "https://www.transnetbw.de"

PROJECTS = f"{BASE}/de/netzentwicklung/projekte"


def page(name: str, url: str):
    return parse_project_page((PAGES / name).read_text(encoding="utf-8"), url, BASE)


@pytest.fixture(scope="module")
def pulverdingen():
    return page("project-umspannwerk-pulverdingen.html", f"{PROJECTS}/umspannwerk-pulverdingen")


@pytest.fixture(scope="module")
def pulverdingen_portrait():
    return page(
        "project-umspannwerk-pulverdingen--projektportraet.html",
        f"{PROJECTS}/umspannwerk-pulverdingen/projektportraet",
    )


def test_title_overline_and_lead_come_from_the_page_header(pulverdingen):
    assert pulverdingen.title == "Umspannwerk Pulverdingen"
    assert pulverdingen.overline == "erneuerung und erweiterung"
    assert pulverdingen.lead.startswith("Seit Langem trägt das Umspannwerk in Pulverdingen")


def test_the_portrait_page_is_found_through_the_chapter_navigation(pulverdingen):
    assert pulverdingen.portrait_url() == f"{PROJECTS}/umspannwerk-pulverdingen/projektportraet"


def test_the_portrait_slug_variant_is_followed_not_assumed():
    schwoerstadt = page("project-umspannwerk-schwoerstadt.html", f"{PROJECTS}/umspannwerk-schwoerstadt")

    assert schwoerstadt.portrait_url() == f"{PROJECTS}/umspannwerk-schwoerstadt/projektportrait"


def test_a_project_without_a_portrait_page_has_none():
    suedlink = page("project-suedlink.html", f"{PROJECTS}/suedlink")

    assert suedlink.portrait_url() is None


@pytest.mark.parametrize(
    "boilerplate",
    [
        "Datenschutzbestimmungen",    # contact form consent text
        "Hotline",                    # contact card
        "Treffen Sie uns live",       # event teaser
        "Ihr Vorname",                # form field label
    ],
)
def test_boilerplate_never_reaches_the_extracted_text(pulverdingen, pulverdingen_portrait, boilerplate):
    assert boilerplate not in pulverdingen.text()
    assert boilerplate not in pulverdingen_portrait.text()


def test_equipment_measures_are_extracted_with_their_voltages(pulverdingen_portrait):
    by_equipment = {}

    for measure in pulverdingen_portrait.measures():
        for equipment in measure["equipment"]:
            by_equipment.setdefault(equipment, []).append(measure)

    phase_shifters = by_equipment["phase_shifting_transformer"]

    assert phase_shifters[0]["text"] == "die Aufstellung von zwei 380-kV/380-kV-Phasenschiebertransformatoren"
    assert phase_shifters[0]["voltages_kv"] == [380]

    # "Phasenschiebertransformatoren" must not also count as a plain transformer.
    assert all("Phasenschieber" not in measure["text"] for measure in by_equipment["transformer"])
    assert any(measure["voltages_kv"] == [110, 380] for measure in by_equipment["transformer"])


def test_line_identifiers_are_normalized():
    seiltausch = page("project-seiltausch-hoellental.html", f"{PROJECTS}/seiltausch-hoellental")
    grafenrheinfeld = page(
        "project-grafenrheinfeld-kupferzell-grossgartach--projektportraet.html",
        f"{PROJECTS}/grafenrheinfeld-kupferzell-grossgartach/projektportraet",
    )

    assert seiltausch.line_ids == ["LA5120"]
    assert grafenrheinfeld.line_ids == ["LA0316", "LA0348", "LA0380"]


def test_voltage_levels_are_collected_from_the_content():
    weinheim = page(
        "project-netzverstaerkung-weinheim-karlsruhe--projektportraet.html",
        f"{PROJECTS}/netzverstaerkung-weinheim-karlsruhe/projektportraet",
    )

    assert weinheim.voltages_kv == [110, 220, 380]


def test_status_sections_keep_their_anchor_and_heading():
    weinheim = page(
        "project-netzverstaerkung-weinheim-karlsruhe--projektportraet.html",
        f"{PROJECTS}/netzverstaerkung-weinheim-karlsruhe/projektportraet",
    )

    status = next(section for section in weinheim.sections if section.anchor == "aktueller-stand")

    assert status.heading == "Aktueller Stand"
    assert "Antragskonferenz" in status.text


def test_a_page_without_a_title_is_a_parse_error():
    html = (PAGES / "project-umspannwerk-pulverdingen.html").read_text(encoding="utf-8")
    untitled = html.replace('<h1 class="header__headline">Umspannwerk Pulverdingen</h1>', "")

    with pytest.raises(ParseError, match="no page title"):
        parse_project_page(untitled, f"{PROJECTS}/umspannwerk-pulverdingen", BASE)
