"""
Press releases are the only dated records TransnetBW publishes, so their
dates are verified from the article itself, not taken from the feed.

The feed carries real defects (one URL listed twice with two different
dates, literal HTML entities in titles); articles open with datelines naming
the issuing office ("Stuttgart / Bayreuth.") that must not be mistaken for
the project's location; and every article ends in press contacts — names,
phone numbers, e-mail addresses — that must never reach a staging record.
"""

from datetime import date
from pathlib import Path

import pytest

from app.transnetbw.errors import ParseError
from app.transnetbw.press_parser import (
    parse_article,
    parse_feed,
    parse_german_date,
    strip_dateline,
)


FIXTURES = Path("fixtures/transnetbw")

NEWS = "https://www.transnetbw.de/de/newsroom/news"


def article(prefix: str):
    path = next((FIXTURES / "pages").glob(f"press-{prefix}*.html"))
    return parse_article(path.read_text(encoding="utf-8"), f"{NEWS}/{prefix}")


# =========================================================
# DATES
# =========================================================


@pytest.mark.parametrize(
    "text, expected",
    [
        ("15. Oktober 2026", date(2026, 10, 15)),
        ("1. März 2024", date(2024, 3, 1)),
        ("25. Juli 2025", date(2025, 7, 25)),
        ("15.10.2026", date(2026, 10, 15)),
        ("  30. September 2024 ", date(2024, 9, 30)),
    ],
)
def test_german_dates_are_parsed(text, expected):
    assert parse_german_date(text) == expected


@pytest.mark.parametrize(
    "text",
    ["15. Oktobr 2026", "31. Februar 2025", "Oktober 2026", "", None, "15. Oktober 26"],
)
def test_unreadable_or_impossible_dates_are_none_not_guessed(text):
    assert parse_german_date(text) is None


# =========================================================
# FEED
# =========================================================


@pytest.fixture(scope="module")
def feed():
    return parse_feed((FIXTURES / "press-releases.json").read_text(encoding="utf-8"))


def test_a_url_listed_twice_is_kept_once_with_its_latest_date(feed):
    urls = [item.url for item in feed.items]

    assert len(urls) == len(set(urls)) == 14

    twice = f"{NEWS}/netzplanungsgrundsaetze-der-vier-deutschen-uebertragungsnetzbetreiber"

    kept = next(item for item in feed.items if item.url == twice)

    assert kept.date == date(2024, 11, 4)
    assert feed.duplicates == [{"url": twice, "dates": ["2024-11-04", "2022-07-01"]}]


def test_feed_titles_are_cleaned_of_entities(feed):
    titles = [item.title for item in feed.items]

    assert "Übertragungsnetzbetreiber veröffentlichen Ergebnisse der dritten Kapazitätsreserve-Ausschreibung" in titles
    assert not any("&" in title or "­" in title for title in titles)


def test_malformed_feed_items_are_reported_not_dropped_silently():
    raw = """[
      {"url": "https://www.transnetbw.de/de/newsroom/news/ok", "date": "2026-01-02", "title": "Gut", "type": ["Aktuelles"]},
      {"url": "", "date": "2026-01-02", "title": "Ohne URL", "type": []},
      {"url": "https://www.transnetbw.de/de/newsroom/news/kein-titel", "date": "2026-01-02", "title": "  ", "type": []},
      {"url": "https://www.transnetbw.de/de/newsroom/news/kaputtes-datum", "date": "02.01.2026x", "title": "Datum", "type": []}
    ]"""

    parsed = parse_feed(raw)

    assert [item.slug for item in parsed.items] == ["ok", "kaputtes-datum"]
    assert parsed.items[1].date is None
    assert [problem["reason"] for problem in parsed.malformed] == [
        "missing url",
        "missing title",
        "unreadable date '02.01.2026x'",
    ]


@pytest.mark.parametrize("raw", ["", "<html>Fehler</html>", '{"items": []}'])
def test_a_feed_that_is_not_a_json_list_is_a_parse_error(raw):
    with pytest.raises(ParseError):
        parse_feed(raw)


# =========================================================
# DATELINES
# =========================================================


@pytest.mark.parametrize(
    "paragraph, dateline, rest_start",
    [
        ("Stuttgart / Bayreuth. TransnetBW und TenneT Germany haben", "Stuttgart / Bayreuth", "TransnetBW und"),
        ("Oerlenbach. Stuttgart. Mit einem Festakt in Oerlenbach", "Oerlenbach. Stuttgart", "Mit einem Festakt"),
        ("Beuren an der Aach, Singen (Hohentwiel). Mit einem symbolischen Spatenstich", "Beuren an der Aach, Singen (Hohentwiel)", "Mit einem"),
        ("Stuttgart. Am 20. März 2024 erteilte das Regierungspräsidium", "Stuttgart", "Am 20. März 2024"),
    ],
)
def test_datelines_are_split_off(paragraph, dateline, rest_start):
    found, rest = strip_dateline(paragraph)

    assert found == dateline
    assert rest.startswith(rest_start)


@pytest.mark.parametrize(
    "paragraph",
    [
        "Am 20. März 2024 erteilte das Regierungspräsidium Stuttgart den Beschluss.",
        "Nach dreieinhalbjähriger Bauzeit konnte der Umbau abgeschlossen werden.",
        "Der beginnende Markthochlauf von Wärmepumpen stellt eine Herausforderung dar.",
        "Dr. Werner Götz erklärte im Rahmen der Veranstaltung.",
    ],
)
def test_ordinary_first_sentences_are_not_mistaken_for_datelines(paragraph):
    assert strip_dateline(paragraph) == (None, paragraph)


# =========================================================
# ARTICLES
# =========================================================


@pytest.fixture(scope="module")
def commissioning():
    return article("transnetbw-und-tennet-germany-feiern")


def test_the_article_date_title_and_subheads_are_read(commissioning):
    assert commissioning.date == date(2026, 10, 15)
    assert commissioning.title.startswith(
        "TransnetBW und TenneT Germany feiern symbolische Inbetriebnahme der Netzverstärkung"
    )
    assert len(commissioning.subheads) == 3
    assert commissioning.subheads[2] == "Bestehende Masten und Leitungsanlagen wurden soweit möglich genutzt"


def test_the_lead_starts_after_the_dateline(commissioning):
    assert commissioning.dateline == "Stuttgart / Bayreuth"
    assert commissioning.lead.startswith("TransnetBW und TenneT Germany haben die verstärkte Höchstspannungsleitung")


@pytest.mark.parametrize(
    "prefix, personal_detail",
    [
        ("transnetbw-und-tennet-germany-feiern", "m.scholz@transnetbw.de"),
        ("transnetbw-und-tennet-germany-feiern", "Pressesprecher"),
        ("kleinstflexibilitaeten", "joana.niggemann@amprion.net"),
        ("kleinstflexibilitaeten", "+49 151 16310889"),
    ],
)
def test_press_contacts_never_reach_the_extracted_text(prefix, personal_detail):
    """
    In the Kleinstflexibilitäten release the contacts share one content
    block with the text, so the cut happens per paragraph.
    """

    parsed = article(prefix)

    assert personal_detail not in parsed.text()


def test_content_before_the_contacts_is_kept():
    parsed = article("kleinstflexibilitaeten")

    assert parsed.lead.startswith("Der beginnende Markthochlauf von Wärmepumpen")
    assert "Redispatch" in parsed.text()


def test_an_article_without_a_date_line_has_no_date():
    path = next((FIXTURES / "pages").glob("press-feierlicher-baubeginn*.html"))
    html = path.read_text(encoding="utf-8").replace(
        '<p class="h1--preheadline header__overline">10. Juni 2024</p>', ""
    )

    parsed = parse_article(html, f"{NEWS}/feierlicher-baubeginn-des-netzboosters")

    assert parsed.date is None
    assert parsed.date_text is None


def test_an_article_without_a_title_is_a_parse_error():
    path = next((FIXTURES / "pages").glob("press-feierlicher-baubeginn*.html"))
    html = path.read_text(encoding="utf-8").replace(
        '<h1 class="header__headline">Feierlicher Baubeginn des Netzboosters</h1>', ""
    )

    with pytest.raises(ParseError, match="no page title"):
        parse_article(html, f"{NEWS}/feierlicher-baubeginn-des-netzboosters")
