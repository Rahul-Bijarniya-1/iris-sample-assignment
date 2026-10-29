"""
The fetch layer is the harvester's only contact with transnetbw.de.

It must honour robots.txt (and fail closed when robots.txt cannot be read),
space its requests, identify itself, keep a raw copy of everything it
fetched, and turn every transport failure into one FetchError the harvester
can record instead of crash on.

Only the network is faked: the real HttpClient retry logic runs underneath,
fed real requests.Response objects.
"""

import json

import pytest
import requests

from app.scrapers.base.http_client import HttpClient
from app.transnetbw.config import TransnetBWSettings
from app.transnetbw.fetch import (
    FetchError,
    FixtureFetcher,
    LiveFetcher,
    load_fixture_index,
)


BASE = "https://www.transnetbw.de"
ROBOTS = f"{BASE}/robots.txt"
LISTING = f"{BASE}/de/netzentwicklung/projekte/alle-projekte"


def make_response(url, status=200, body=b"<html></html>", content_type="text/html; charset=UTF-8"):
    response = requests.Response()
    response.status_code = status
    response._content = body
    response.headers["Content-Type"] = content_type
    response.url = url
    response.encoding = "utf-8"
    return response


class FakeSession:
    """
    Stands in for requests.Session: answers from a URL → [responses or
    exceptions] script and records every call it receives.
    """

    def __init__(self, script):
        self.script = {url: list(items) for url, items in script.items()}
        self.calls = []
        self.headers = {}

    def request(self, method, url, timeout=None, **kwargs):
        self.calls.append({"method": method, "url": url, "timeout": timeout, **kwargs})

        items = self.script.get(url)

        if not items:
            raise AssertionError(f"unexpected request: {url}")

        item = items.pop(0) if len(items) > 1 else items[0]

        if isinstance(item, Exception):
            raise item

        return item


class Clock:
    """
    Monotonic clock that only moves when the fetcher sleeps.
    """

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def no_backoff(monkeypatch):
    """
    HttpClient sleeps 5 s and more between retries; tests must not.
    """

    monkeypatch.setattr("app.scrapers.base.http_client.time.sleep", lambda _: None)


def make_fetcher(script, tmp_path=None, **settings_overrides):
    settings = TransnetBWSettings(
        _env_file=None,
        request_delay_s=settings_overrides.pop("request_delay_s", 1.5),
        max_retries=settings_overrides.pop("max_retries", 1),
        **settings_overrides,
    )

    client = HttpClient()
    session = FakeSession(script)
    client.session = session
    clock = Clock()

    fetcher = LiveFetcher(
        settings=settings,
        client=client,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        snapshot_dir=tmp_path,
    )

    return fetcher, session, clock


ALLOW_ALL = make_response(ROBOTS, body=b"User-agent: *\nDisallow: /neos/\n", content_type="text/plain")


def test_a_path_disallowed_by_robots_is_never_requested(no_backoff):
    fetcher, session, _ = make_fetcher({ROBOTS: [ALLOW_ALL]})

    with pytest.raises(FetchError, match="robots.txt"):
        fetcher.fetch(f"{BASE}/neos/login")

    assert [call["url"] for call in session.calls] == [ROBOTS]


def test_urls_outside_the_source_site_are_refused(no_backoff):
    """
    Links found in TransnetBW pages point to partner sites (TenneT,
    Amprion, YouTube). The harvester is authorised for one site only.
    """

    fetcher, session, _ = make_fetcher({ROBOTS: [ALLOW_ALL]})

    with pytest.raises(FetchError, match="outside"):
        fetcher.fetch("https://www.tennet.eu/de/projekte/suedlink")

    assert session.calls == []


def test_robots_txt_missing_means_everything_is_allowed(no_backoff):
    """
    RFC 9309: an unavailable (4xx) robots.txt places no restrictions.
    """

    fetcher, _, _ = make_fetcher(
        {
            ROBOTS: [make_response(ROBOTS, status=404, body=b"")],
            LISTING: [make_response(LISTING, body=b"<main>ok</main>")],
        }
    )

    assert fetcher.fetch(LISTING).text == "<main>ok</main>"


def test_unreachable_robots_txt_fails_closed(no_backoff):
    """
    RFC 9309: a server error on robots.txt means assume complete disallow.
    """

    fetcher, session, _ = make_fetcher(
        {ROBOTS: [make_response(ROBOTS, status=503, body=b"")]}
    )

    with pytest.raises(FetchError, match="robots.txt"):
        fetcher.fetch(LISTING)

    assert LISTING not in [call["url"] for call in session.calls]


def test_requests_are_spaced_by_the_configured_delay(no_backoff):
    project = f"{BASE}/de/netzentwicklung/projekte/suedlink"

    fetcher, _, clock = make_fetcher(
        {
            ROBOTS: [ALLOW_ALL],
            LISTING: [make_response(LISTING)],
            project: [make_response(project)],
        },
        request_delay_s=2.0,
    )

    fetcher.fetch(LISTING)
    fetcher.fetch(project)

    # robots.txt → listing → project: two gaps, each a full delay.
    assert clock.sleeps == [2.0, 2.0]


def test_a_longer_robots_crawl_delay_is_honoured(no_backoff):
    robots = make_response(
        ROBOTS,
        body=b"User-agent: *\nCrawl-delay: 5\nDisallow: /neos/\n",
        content_type="text/plain",
    )

    fetcher, _, clock = make_fetcher(
        {ROBOTS: [robots], LISTING: [make_response(LISTING)]},
        request_delay_s=1.5,
    )

    fetcher.fetch(LISTING)

    assert clock.sleeps == [5.0]


def test_every_request_carries_the_configured_user_agent(no_backoff):
    fetcher, session, _ = make_fetcher(
        {ROBOTS: [ALLOW_ALL], LISTING: [make_response(LISTING)]},
        user_agent="IRIS-ProjectRadar/test (+https://example.org)",
    )

    fetcher.fetch(LISTING)

    agents = {call["headers"]["User-Agent"] for call in session.calls}

    assert agents == {"IRIS-ProjectRadar/test (+https://example.org)"}


def test_a_connection_failure_becomes_a_fetch_error_after_retrying(no_backoff):
    fetcher, session, _ = make_fetcher(
        {
            ROBOTS: [ALLOW_ALL],
            LISTING: [requests.ConnectionError("connection reset")],
        },
        max_retries=1,
    )

    with pytest.raises(FetchError) as caught:
        fetcher.fetch(LISTING)

    assert caught.value.url == LISTING
    assert [call["url"] for call in session.calls].count(LISTING) == 2


def test_an_http_error_status_becomes_a_fetch_error_with_the_status(no_backoff):
    fetcher, _, _ = make_fetcher(
        {ROBOTS: [ALLOW_ALL], LISTING: [make_response(LISTING, status=404, body=b"")]}
    )

    with pytest.raises(FetchError) as caught:
        fetcher.fetch(LISTING)

    assert caught.value.status == 404


def test_the_redirect_target_is_reported(no_backoff):
    """
    The brief's own URL answers 303 → the Netzentwicklungsplan page; the
    harvester must be able to see and record where it actually landed.
    """

    brief_url = f"{BASE}/de/netzentwicklung"
    landed = f"{BASE}/de/netzentwicklung/planung/netzentwicklungsplan"

    fetcher, _, _ = make_fetcher(
        {ROBOTS: [ALLOW_ALL], brief_url: [make_response(landed)]}
    )

    result = fetcher.fetch(brief_url)

    assert result.url == brief_url
    assert result.final_url == landed


def test_every_fetched_document_is_kept_as_a_raw_snapshot(no_backoff, tmp_path):
    body = "<main>Umspannwerk Pulverdingen</main>".encode()

    fetcher, _, _ = make_fetcher(
        {ROBOTS: [ALLOW_ALL], LISTING: [make_response(LISTING, body=body)]},
        tmp_path=tmp_path,
    )

    result = fetcher.fetch(LISTING)

    index = [json.loads(line) for line in (tmp_path / "index.jsonl").read_text().splitlines()]
    entry = next(item for item in index if item["url"] == LISTING)

    assert (tmp_path / entry["file"]).read_bytes() == body
    assert entry["sha256"] == result.sha256


# =========================================================
# FIXTURE FETCHER (offline mode)
# =========================================================


def write_index(tmp_path, documents):
    (tmp_path / "pages").mkdir()

    entries = {}

    for url, (name, body) in documents.items():
        (tmp_path / "pages" / name).write_bytes(body)
        entries[url] = {
            "file": f"pages/{name}",
            "status": 200,
            "content_type": "text/html; charset=UTF-8",
            "final_url": url,
        }

    index = tmp_path / "index.json"
    index.write_text(
        json.dumps({"retrieved_at": "2026-10-27T12:00:00+00:00", "documents": entries})
    )

    return index


def test_offline_mode_serves_the_captured_document(tmp_path):
    index = write_index(tmp_path, {LISTING: ("listing.html", b"<main>captured</main>")})

    fetcher = FixtureFetcher(load_fixture_index(index))

    result = fetcher.fetch(LISTING)

    assert result.text == "<main>captured</main>"
    assert result.status == 200
    assert result.fetched_at.isoformat() == "2026-10-27T12:00:00+00:00"


def test_offline_mode_never_falls_through_to_the_network(tmp_path):
    index = write_index(tmp_path, {LISTING: ("listing.html", b"<main/>")})

    fetcher = FixtureFetcher(load_fixture_index(index))

    with pytest.raises(FetchError, match="not in the fixture index"):
        fetcher.fetch(f"{BASE}/de/netzentwicklung/projekte/suedlink")


# =========================================================
# SNAPSHOT REPLAY
# =========================================================


from app.transnetbw.fetch import load_snapshot_index  # noqa: E402


def test_a_raw_snapshot_replays_the_latest_capture_of_each_url(tmp_path):
    (tmp_path / "old.html").write_bytes(b"<main>old</main>")
    (tmp_path / "new.html").write_bytes(b"<main>new</main>")

    entries = [
        {"url": LISTING, "final_url": LISTING, "status": 200, "content_type": "text/html", "sha256": "1", "file": "old.html", "fetched_at": "2026-10-28T16:20:00+00:00"},
        {"url": LISTING, "final_url": LISTING, "status": 200, "content_type": "text/html", "sha256": "2", "file": "new.html", "fetched_at": "2026-10-28T16:25:00+00:00"},
    ]

    (tmp_path / "index.jsonl").write_text("\n".join(json.dumps(entry) for entry in entries) + "\n")

    fetcher = FixtureFetcher(load_snapshot_index(tmp_path))

    result = fetcher.fetch(LISTING)

    assert result.text == "<main>new</main>"
    assert result.fetched_at.isoformat() == "2026-10-28T16:25:00+00:00"
