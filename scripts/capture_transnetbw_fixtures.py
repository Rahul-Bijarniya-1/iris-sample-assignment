"""
Capture the TransnetBW fixtures used by tests and by `--offline` runs.

Fetches a fixed, small set of public pages through the harvester's own
LiveFetcher (robots.txt, request spacing, User-Agent, raw snapshots), then
trims each page to what the parsers read and writes fixtures/transnetbw/:

    index.json            URL → fixture file, status, content type
    robots.txt            as served
    sitemap.xml           project and selected newsroom entries only
    press-releases.json   a 15-item subset of /de/api/press-releases
    pages/*.html          trimmed listing, project and article pages

Trimming keeps <head> metadata and <main>, and drops scripts, styles, SVG
drawing data, images and site chrome. Each page gets an attribution header.
TransnetBW's text stays theirs; the fixtures exist to test parsers against
real markup.

Usage:
    uv run python -m scripts.capture_transnetbw_fixtures
    uv run python -m scripts.capture_transnetbw_fixtures --from-snapshot data/raw/transnetbw/capture-20261027

The second form rebuilds the fixtures from an earlier capture's raw
snapshots without any network access.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from bs4 import BeautifulSoup, Comment

from app.transnetbw.config import TransnetBWSettings
from app.transnetbw.fetch import FetchResult, LiveFetcher


SITE = "https://www.transnetbw.de"

PROJECTS = (
    "umspannwerk-pulverdingen",
    "netzverstaerkung-weinheim-karlsruhe",
    "netzbooster-kupferzell",
    "suedlink",
    "umspannwerk-uw-engstlatt",
    "umspannwerk-schwoerstadt",
    "grafenrheinfeld-kupferzell-grossgartach",
    "seiltausch-hoellental",
)

# Feed items whose article pages are captured: one per behaviour the
# harvester must get right (see tests/test_transnetbw_*.py). Entries are
# slug prefixes, resolved against the live feed, because some slugs are
# long enough to be truncated wherever they are copied.
ARTICLES = (
    "transnetbw-und-tennet-germany-feiern-symbolische-inbetriebnahme-der-netzverstaerkung-grafenrheinfeld-kupferzell-grossgartach",
    "nbr-teilbeschluss-abschnitt-B3-ortenaukreis",
    "freileitungsvorrang-staerkt-netzausbau-einschraenkungen-schaffen-unsicherheit",
    "spatenstich-am-umspannwerk-beuren",
    "kleinstflexibilitaeten-als-beitrag-fuer-das-netzengpassmanagement",
    "feierlicher-baubeginn-des-netzboosters",
    "transnetbw-erhaelt-planfeststellungsbeschluss-fuer-den-netzbooster-in-kupferzell",
    "baustart-fur-suedlink-in-bayern",
    "modernisierung-des-umspannwerkes-schwoerstadt-abgeschlossen",
)

# Feed items kept in the subset although no article is captured: each is
# dropped before any fetch (title pre-filter or date window), which is the
# behaviour under test.
FEED_ONLY = (
    "zentraler-kapazitaetsmarkt-mit-lokaler-komponente-fuer-sicherheit-und-netzverortete-investitionsanreize",
    "uebertragungsnetzbetreiber-veroeffentlichen-ergebnisse-der-dritten-kapazitaetsreserve-ausschreibung",
    "transnetbw-veroeffentlicht-nachhaltigkeitsbericht-2025",
    "netzplanungsgrundsaetze-der-vier-deutschen-uebertragungsnetzbetreiber",
    "bundesnetzagentur-bestaetigt-netzbooster-im-raum-kupferzell",
)

PORTRAIT_LINK = re.compile(r"projektport", re.IGNORECASE)


def project_url(slug: str) -> str:
    return f"{SITE}/de/netzentwicklung/projekte/{slug}"


def article_url(slug: str) -> str:
    return f"{SITE}/de/newsroom/news/{slug}"


# =========================================================
# TRIMMING
# =========================================================


def trim_html(html: str, source_url: str, retrieved: str) -> str:
    """
    Keep what the parsers read: head metadata and <main>.
    """

    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "noscript", "iframe", "picture", "img", "video", "source", "link"]):

        if tag.name == "script" and tag.get("type") == "application/ld+json":
            continue

        tag.decompose()

    for svg in soup.find_all("svg"):
        svg.clear()

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for tag in soup.find_all(True):

        for attribute in list(tag.attrs):

            if attribute in ("style", "srcset", "sizes") or attribute.startswith("data-neos"):
                del tag.attrs[attribute]

    head = soup.head

    kept_head = []

    if head is not None:

        for tag in head.find_all(["title", "meta", "script"]):

            if tag.name == "meta" and not (
                tag.get("property", "").startswith("og:")
                or tag.get("name") in ("description",)
                or tag.get("charset")
            ):
                continue

            kept_head.append(str(tag))

    main = soup.find("main")

    body = str(main) if main is not None else str(soup.body or "")

    header = (
        f"<!-- Source: {source_url} · retrieved {retrieved} · "
        "trimmed to parser-relevant fragments · © TransnetBW GmbH -->"
    )

    return (
        f"{header}\n<!DOCTYPE html>\n<html lang=\"de\">\n<head>\n"
        + "\n".join(kept_head)
        + "\n</head>\n<body>\n"
        + body
        + "\n</body>\n</html>\n"
    )


def trim_sitemap(xml: bytes, keep_articles: set[str]) -> bytes:
    """
    Keep every Netzentwicklung entry plus the selected newsroom articles.
    """

    namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"

    ElementTree.register_namespace("", namespace)

    root = ElementTree.fromstring(xml)

    for url in list(root):

        loc = url.findtext(f"{{{namespace}}}loc") or ""

        keep = (
            "/de/netzentwicklung/" in loc
            or loc.rsplit("/", 1)[-1] in keep_articles
        )

        if not keep:
            root.remove(url)

        else:
            # Image extensions are irrelevant to the harvester.
            for child in list(url):

                if not child.tag.startswith(f"{{{namespace}}}"):
                    url.remove(child)

    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def slug_of(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def resolve_slugs(items: list[dict], prefixes: tuple[str, ...]) -> list[str]:
    """
    Map each slug prefix to the one feed URL it starts. A prefix matching
    nothing or several URLs is a capture error, not something to guess.
    """

    slugs = sorted({slug_of(item["url"]) for item in items})

    resolved = []

    for prefix in prefixes:

        matches = [slug for slug in slugs if slug.startswith(prefix)]

        if len(matches) != 1:
            raise SystemExit(f"feed prefix {prefix!r} matched {matches}")

        resolved.append(matches[0])

    return resolved


def find_portrait_url(overview_html: str) -> str | None:
    """
    The portrait subpage's slug varies (projektportraet / projektportrait),
    so it is taken from the page's own chapter navigation.
    """

    soup = BeautifulSoup(overview_html, "lxml")

    for link in soup.find_all("a", href=True):

        if PORTRAIT_LINK.search(link["href"]) or PORTRAIT_LINK.search(link.get_text(" ", strip=True)):

            href = link["href"]

            return href if href.startswith("http") else SITE + href

    return None


# =========================================================
# CAPTURE
# =========================================================


class SnapshotSource:
    """
    Replays an earlier capture's raw snapshot directory.
    """

    def __init__(self, directory: Path):

        self.directory = directory

        self.entries = {}

        for line in (directory / "index.jsonl").read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            self.entries[entry["url"]] = entry

    def fetch(self, url: str, accept: str = "html") -> FetchResult:

        entry = self.entries[url]

        content = (self.directory / entry["file"]).read_bytes()

        return FetchResult(
            url=url,
            final_url=entry["final_url"],
            status=entry["status"],
            content=content,
            content_type=entry["content_type"],
            fetched_at=datetime.fromisoformat(entry["fetched_at"]),
            sha256=entry["sha256"],
        )


def capture(source, out_dir: Path, retrieved: str) -> dict:

    pages_dir = out_dir / "pages"

    pages_dir.mkdir(parents=True, exist_ok=True)

    documents = {}

    def record(result: FetchResult, file_name: str, body: bytes) -> None:

        (out_dir / file_name).write_bytes(body)

        documents[result.url] = {
            "file": file_name,
            "status": result.status,
            "content_type": result.content_type,
            "final_url": result.final_url,
        }

    robots = source.fetch(f"{SITE}/robots.txt", "text")

    record(robots, "robots.txt", robots.content)

    listing = source.fetch(project_url("alle-projekte"))

    record(
        listing,
        "pages/alle-projekte.html",
        trim_html(listing.text, listing.url, retrieved).encode(),
    )

    feed = source.fetch(f"{SITE}/de/api/press-releases", "json")

    items = json.loads(feed.text)

    article_slugs = resolve_slugs(items, ARTICLES)

    wanted = set(article_slugs) | set(resolve_slugs(items, FEED_ONLY))

    subset = [item for item in items if slug_of(item["url"]) in wanted]

    record(
        feed,
        "press-releases.json",
        json.dumps(subset, ensure_ascii=False, indent=1).encode(),
    )

    sitemap = source.fetch(f"{SITE}/de/sitemap.xml", "xml")

    record(sitemap, "sitemap.xml", trim_sitemap(sitemap.content, set(article_slugs)))

    for slug in PROJECTS:

        overview = source.fetch(project_url(slug))

        record(
            overview,
            f"pages/project-{slug}.html",
            trim_html(overview.text, overview.url, retrieved).encode(),
        )

        portrait_url = find_portrait_url(overview.text)

        if portrait_url is None:
            print(f"  no portrait link on {slug}")
            continue

        portrait = source.fetch(portrait_url)

        record(
            portrait,
            f"pages/project-{slug}--{portrait_url.rsplit('/', 1)[-1]}.html",
            trim_html(portrait.text, portrait.url, retrieved).encode(),
        )

    for slug in article_slugs:

        article = source.fetch(article_url(slug))

        record(
            article,
            f"pages/press-{slug[:80]}.html",
            trim_html(article.text, article.url, retrieved).encode(),
        )

    index = {
        "retrieved_at": retrieved,
        "source": SITE,
        "note": (
            "Trimmed captures of public TransnetBW pages, for tests and "
            "offline runs. © TransnetBW GmbH."
        ),
        "documents": documents,
    }

    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )

    return index


def main() -> None:

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])

    parser.add_argument("--from-snapshot", type=Path)

    parser.add_argument("--out", type=Path, default=Path("fixtures/transnetbw"))

    args = parser.parse_args()

    if args.from_snapshot:

        source = SnapshotSource(args.from_snapshot)

        retrieved = min(entry["fetched_at"] for entry in source.entries.values())

    else:

        settings = TransnetBWSettings()

        stamp = datetime.now(timezone.utc)

        source = LiveFetcher(
            settings=settings,
            snapshot_dir=settings.raw_dir / f"capture-{stamp:%Y%m%d}",
        )

        retrieved = stamp.replace(microsecond=0).isoformat()

    index = capture(source, args.out, retrieved)

    requests_made = getattr(source, "request_count", 0)

    print(f"Wrote {len(index['documents'])} fixtures to {args.out} ({requests_made} requests)")


if __name__ == "__main__":
    main()
