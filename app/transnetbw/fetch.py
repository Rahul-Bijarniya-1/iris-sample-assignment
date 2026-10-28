"""
Fetch layer for the TransnetBW harvester.

Two implementations share one interface:

  - LiveFetcher talks to transnetbw.de through the project's HttpClient,
    adding what a polite, authorised harvester needs on top of retries:
    robots.txt (RFC 9309, failing closed when it cannot be read), request
    spacing, a stable User-Agent, a same-site restriction, and a raw
    snapshot of every document for traceability.

  - FixtureFetcher serves documents captured into fixtures/transnetbw/,
    so the whole pipeline runs with no network access (`--offline`). It
    never falls through to the network.

Both raise FetchError for every failure, so the harvester records an issue
for one document instead of aborting the run.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from app.scrapers.base.http_client import HttpClient
from app.transnetbw.config import TransnetBWSettings


ACCEPT_HEADERS = {
    "html": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "xml": "application/xml,text/xml;q=0.9,*/*;q=0.8",
    "json": "application/json,*/*;q=0.8",
    "text": "text/plain,*/*;q=0.8",
}

SNAPSHOT_EXTENSIONS = {
    "text/html": ".html",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "application/json": ".json",
    "text/plain": ".txt",
}


class FetchError(Exception):
    """
    One document could not be fetched. Carries the URL and, when the server
    answered, the HTTP status.
    """

    def __init__(
        self,
        url: str,
        message: str,
        status: int | None = None,
    ):
        super().__init__(f"{message}: {url}")

        self.url = url

        self.status = status


class NotCapturedError(FetchError):
    """
    Offline only: the fixture set does not contain this document. Not a
    network failure — the harvester reports it as information and does not
    count it against the fetch-failure gate.
    """


@dataclass(frozen=True)
class FetchResult:

    url: str

    final_url: str

    status: int

    content: bytes

    content_type: str | None

    fetched_at: datetime

    sha256: str

    @property
    def charset(self) -> str:

        if self.content_type and "charset=" in self.content_type.lower():

            declared = self.content_type.lower().split("charset=", 1)[1]

            return declared.split(";", 1)[0].strip() or "utf-8"

        return "utf-8"

    @property
    def text(self) -> str:
        """
        Decoded body. Undecodable bytes become U+FFFD rather than an
        exception; the parsers flag pages that end up unreadable.
        """

        return self.content.decode(self.charset, errors="replace")


class Fetcher(Protocol):

    def fetch(self, url: str, accept: str = "html") -> FetchResult:
        ...


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# =========================================================
# LIVE
# =========================================================


class LiveFetcher:
    """
    Polite fetcher for the configured source site.
    """

    def __init__(
        self,
        settings: TransnetBWSettings,
        client: HttpClient | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        snapshot_dir: Path | None = None,
    ):
        self.settings = settings

        self.client = client or HttpClient()

        self.monotonic = monotonic

        self.sleep = sleep

        self.snapshot_dir = snapshot_dir

        self.site = urlsplit(settings.base_url).netloc.lower()

        self.robots: RobotFileParser | None = None

        self.delay = settings.request_delay_s

        self._last_request_at: float | None = None

        self.request_count = 0

    # =====================================================
    # PUBLIC
    # =====================================================

    def fetch(
        self,
        url: str,
        accept: str = "html",
    ) -> FetchResult:

        if urlsplit(url).netloc.lower() != self.site:
            raise FetchError(
                url,
                f"refused: outside the configured source site {self.site}",
            )

        self._ensure_robots()

        if not self.robots.can_fetch(self.settings.user_agent, url):
            raise FetchError(url, "refused: disallowed by robots.txt")

        return self._get(url, accept)

    # =====================================================
    # ROBOTS
    # =====================================================

    def _ensure_robots(self) -> None:
        """
        Load robots.txt once per run.

        RFC 9309 §2.3.1: a 4xx answer means no restrictions; a server error
        or no answer means assume complete disallow. The second case raises,
        so a run cannot proceed without knowing the site's rules.
        """

        if self.robots is not None:
            return

        robots_url = self.settings.url("/robots.txt")

        parser = RobotFileParser(robots_url)

        try:
            result = self._get(robots_url, "text")

        except FetchError as exc:

            if exc.status is not None and 400 <= exc.status < 500:

                parser.allow_all = True

                self.robots = parser

                return

            raise FetchError(
                robots_url,
                "robots.txt unavailable, so crawling is not authorised",
                status=exc.status,
            ) from exc

        parser.parse(result.text.splitlines())

        crawl_delay = parser.crawl_delay(self.settings.user_agent)

        if crawl_delay:
            self.delay = max(self.delay, float(crawl_delay))

        self.robots = parser

    # =====================================================
    # REQUEST
    # =====================================================

    def _wait_for_slot(self) -> None:

        if self._last_request_at is None:
            return

        elapsed = self.monotonic() - self._last_request_at

        remaining = self.delay - elapsed

        if remaining > 0:
            self.sleep(remaining)

    def _get(
        self,
        url: str,
        accept: str,
    ) -> FetchResult:

        self._wait_for_slot()

        headers = {
            "User-Agent": self.settings.user_agent,
            "Accept": ACCEPT_HEADERS.get(accept, ACCEPT_HEADERS["html"]),
        }

        try:
            response = self.client.get(
                url,
                headers=headers,
                timeout=self.settings.timeout_s,
                max_retries=self.settings.max_retries,
            )

        except requests.HTTPError as exc:

            status = (
                exc.response.status_code
                if exc.response is not None
                else None
            )

            raise FetchError(url, f"HTTP {status}", status=status) from exc

        except (requests.RequestException, RuntimeError) as exc:

            raise FetchError(
                url,
                f"{type(exc).__name__}: {exc}",
            ) from exc

        finally:
            self._last_request_at = self.monotonic()

            self.request_count += 1

        result = FetchResult(
            url=url,
            final_url=response.url or url,
            status=response.status_code,
            content=response.content or b"",
            content_type=response.headers.get("Content-Type"),
            fetched_at=_now(),
            sha256=_sha256(response.content or b""),
        )

        self._snapshot(result)

        return result

    # =====================================================
    # SNAPSHOT
    # =====================================================

    def _snapshot(self, result: FetchResult) -> None:
        """
        Keep the raw bytes, named by content hash, plus an index line, so
        any staging record can be traced to exactly what was served.
        """

        if self.snapshot_dir is None:
            return

        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        media_type = (result.content_type or "").split(";", 1)[0].strip()

        name = result.sha256 + SNAPSHOT_EXTENSIONS.get(media_type, ".bin")

        target = self.snapshot_dir / name

        if not target.exists():
            target.write_bytes(result.content)

        entry = {
            "url": result.url,
            "final_url": result.final_url,
            "status": result.status,
            "content_type": result.content_type,
            "sha256": result.sha256,
            "file": name,
            "fetched_at": result.fetched_at.isoformat(),
        }

        with (self.snapshot_dir / "index.jsonl").open("a", encoding="utf-8") as index:
            index.write(json.dumps(entry, ensure_ascii=False) + "\n")


# =========================================================
# FIXTURES
# =========================================================


@dataclass(frozen=True)
class FixtureDocument:

    file: Path

    status: int

    content_type: str | None

    final_url: str

    fetched_at: datetime | None = None


@dataclass(frozen=True)
class FixtureIndex:

    retrieved_at: datetime

    documents: dict[str, FixtureDocument]


def load_fixture_index(path: str | Path) -> FixtureIndex:
    """
    Read fixtures/transnetbw/index.json. File paths in the index are
    relative to the index itself.
    """

    path = Path(path)

    data = json.loads(path.read_text(encoding="utf-8"))

    documents = {
        url: FixtureDocument(
            file=path.parent / entry["file"],
            status=int(entry.get("status", 200)),
            content_type=entry.get("content_type"),
            final_url=entry.get("final_url") or url,
        )
        for url, entry in data["documents"].items()
    }

    return FixtureIndex(
        retrieved_at=datetime.fromisoformat(data["retrieved_at"]),
        documents=documents,
    )


def load_snapshot_index(directory: str | Path) -> FixtureIndex:
    """
    Replay a LiveFetcher raw snapshot (index.jsonl + content files): the
    latest capture of each URL, with its own fetch time. Lets a run be
    re-processed without contacting the site again.
    """

    directory = Path(directory)

    latest: dict[str, dict] = {}

    for line in (directory / "index.jsonl").read_text(encoding="utf-8").splitlines():

        if not line.strip():
            continue

        entry = json.loads(line)

        held = latest.get(entry["url"])

        if held is None or entry["fetched_at"] >= held["fetched_at"]:
            latest[entry["url"]] = entry

    documents = {
        url: FixtureDocument(
            file=directory / entry["file"],
            status=int(entry["status"]),
            content_type=entry.get("content_type"),
            final_url=entry.get("final_url") or url,
            fetched_at=datetime.fromisoformat(entry["fetched_at"]),
        )
        for url, entry in latest.items()
    }

    times = [document.fetched_at for document in documents.values()]

    return FixtureIndex(
        retrieved_at=min(times) if times else datetime.now(timezone.utc),
        documents=documents,
    )


class FixtureFetcher:
    """
    Offline fetcher. Every document reports the capture time as its fetch
    time, so offline runs are deterministic.
    """

    def __init__(self, index: FixtureIndex):

        self.index = index

        self.request_count = 0

    def fetch(
        self,
        url: str,
        accept: str = "html",
    ) -> FetchResult:

        document = self.index.documents.get(url)

        if document is None:
            raise NotCapturedError(url, "not in the fixture index")

        self.request_count += 1

        if document.status >= 400:
            raise FetchError(
                url,
                f"HTTP {document.status} (captured)",
                status=document.status,
            )

        content = document.file.read_bytes()

        return FetchResult(
            url=url,
            final_url=document.final_url,
            status=document.status,
            content=content,
            content_type=document.content_type,
            fetched_at=document.fetched_at or self.index.retrieved_at,
            sha256=_sha256(content),
        )
