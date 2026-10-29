"""
Project pages (overview and portrait) → structured content.

Everything comes from the page's own markup: the header (h1 title,
overline, lead), the chapter navigation (which names the portrait subpage,
whose slug varies between projects), and the content sections. Blocks
repeated on every page — contact form, hotline card, event teasers,
cross-links — are skipped so they never reach a record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.transnetbw.errors import ParseError
from app.transnetbw.htmltext import element_text as _text
from app.transnetbw.htmltext import is_boilerplate as _is_boilerplate
from app.transnetbw.normalize import cap

PORTRAIT = re.compile(r"projektport", re.IGNORECASE)

LINE_ID = re.compile(r"\bLA\s?(\d{3,4})\b")

VOLTAGE = re.compile(r"(?<!\d)(\d{2,3})\s?(?:-|–)?\s?kV\b")

PLAUSIBLE_VOLTAGES = range(60, 1000)

MEASURE_TEXT_LIMIT = 200

# German equipment terms → controlled vocabulary. Order matters only for
# reading; each term is tested independently. The transformer pattern
# refuses a preceding letter so "Phasenschiebertransformator" does not also
# count as a plain transformer.
EQUIPMENT = (
    ("phase_shifting_transformer", re.compile(r"phasenschieber", re.IGNORECASE)),
    ("transformer", re.compile(r"(?<![a-zäöüß])(?:transformator|trafo)", re.IGNORECASE)),
    ("switchgear", re.compile(r"schaltanlage|schaltfeld", re.IGNORECASE)),
    ("shunt_reactor", re.compile(r"drosselspule", re.IGNORECASE)),
    ("capacitor_bank", re.compile(r"kondensator", re.IGNORECASE)),
    ("statcom", re.compile(r"statcom", re.IGNORECASE)),
    ("battery_storage", re.compile(r"batteriespeicher|batterie", re.IGNORECASE)),
    ("converter_station", re.compile(r"konverter", re.IGNORECASE)),
    ("overhead_line", re.compile(r"freileitung|leiterseil|stromkreis", re.IGNORECASE)),
    ("cable", re.compile(r"kabel", re.IGNORECASE)),
    ("tower", re.compile(r"(?<![a-zäöüß])mast", re.IGNORECASE)),
)


@dataclass
class ContentSection:

    heading: str | None

    preheadline: str | None = None

    anchor: str | None = None

    paragraphs: list[str] = field(default_factory=list)

    items: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(
            part
            for part in (self.preheadline, self.heading, *self.paragraphs, *self.items)
            if part
        )


@dataclass
class ProjectPage:

    url: str

    title: str

    overline: str | None

    lead: str | None

    chapter_links: dict[str, str]

    sections: list[ContentSection]

    line_ids: list[str]

    voltages_kv: list[int]

    def portrait_url(self) -> str | None:

        for label, url in self.chapter_links.items():

            if PORTRAIT.search(label) or PORTRAIT.search(url.rsplit("/", 1)[-1]):
                return url

        return None

    def text(self) -> str:
        """
        All extracted content: header lead plus every section.
        """

        return " ".join(
            part
            for part in (self.title, self.overline, self.lead, *(section.text for section in self.sections))
            if part
        )

    def items(self) -> list[str]:
        return [item for section in self.sections for item in section.items]

    def measures(self) -> list[dict]:
        """
        List items naming equipment, with the voltages they mention.
        """

        measures = []

        for item in self.items():

            equipment = [name for name, pattern in EQUIPMENT if pattern.search(item)]

            if not equipment:
                continue

            measures.append(
                {
                    "text": cap(item, MEASURE_TEXT_LIMIT),
                    "equipment": equipment,
                    "voltages_kv": voltages_in(item),
                }
            )

        return measures


def voltages_in(text: str) -> list[int]:

    found = {int(value) for value in VOLTAGE.findall(text)}

    return sorted(value for value in found if value in PLAUSIBLE_VOLTAGES)


def line_ids_in(text: str) -> list[str]:
    return sorted({f"LA{number}" for number in LINE_ID.findall(text)})


def _anchor_of(tag: Tag) -> str | None:

    for node in tag.parents:

        if isinstance(node, Tag) and node.get("id") and "section" in (node.get("class") or []):
            return node["id"]

    return None


def _sections(main: Tag) -> list[ContentSection]:
    """
    Walk content elements in document order, starting a new section at
    every h2. Preheadlines attach to the heading that follows them.
    """

    sections: list[ContentSection] = []

    current: ContentSection | None = None

    pending_preheadline: str | None = None

    for element in main.find_all(["h2", "h3", "h4", "p", "li"]):

        if element.find_parent(class_="header") is not None:
            continue

        if _is_boilerplate(element):
            continue

        text = _text(element)

        if not text:
            continue

        classes = element.get("class") or []

        if element.name == "p" and "h2--preheadline" in classes:
            pending_preheadline = text
            continue

        if element.name == "h2":

            current = ContentSection(
                heading=text,
                preheadline=pending_preheadline,
                anchor=_anchor_of(element),
            )

            sections.append(current)

            pending_preheadline = None

            continue

        if current is None:
            current = ContentSection(heading=None, anchor=_anchor_of(element))
            sections.append(current)

        if element.name == "li":
            current.items.append(text)

        elif element.name == "p" and element.find_parent("li") is None:
            current.paragraphs.append(text)

        elif element.name in ("h3", "h4"):
            current.paragraphs.append(text)

    return sections


def parse_project_page(html: str, url: str, base_url: str) -> ProjectPage:

    soup = BeautifulSoup(html, "lxml")

    main = soup.find("main") or soup.body

    if main is None:
        raise ParseError(url, "no page body")

    title = _text(main.select_one("h1"))

    if not title:
        raise ParseError(url, "no page title")

    chapter_links = {}

    for link in main.select("a.header-nav__link[href]"):

        label = _text(link)

        if label:
            chapter_links[label] = urljoin(base_url, link["href"])

    sections = _sections(main)

    page = ProjectPage(
        url=url,
        title=title,
        overline=_text(main.select_one("p.header__overline")),
        lead=_text(main.select_one(".header__copy")),
        chapter_links=chapter_links,
        sections=sections,
        line_ids=[],
        voltages_kv=[],
    )

    full_text = page.text()

    page.line_ids = line_ids_in(full_text)

    page.voltages_kv = voltages_in(full_text)

    return page
