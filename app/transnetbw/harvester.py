"""
The TransnetBW Project Radar harvest: one run, end to end.

    guards     advisory lock (exit 3 if another run holds it) · mode guard
               (fixture and live runs never share a database)
    discovery  sitemap (lastmod per URL) + project listing; the union of
               both is the project set, their difference is reported
    projects   overview + portrait page, fetched only when the sitemap
               says they may have changed since the last fetch
    press      feed for discovery; each candidate article fetched under
               the same rule; its date verified against the feed
    records    classify → stage → link → geocode → SignalRecord
    load       one transaction, one savepoint per record; derived
               cross-record facts refreshed
    gates      evaluated before commit; a breach rolls the run back, so a
               broken parse can never retire records
    retire     soft retirement of records the source no longer lists

Status: succeeded (exit 0) · partial (exit 2: a document or record failed,
or the press feed was missing or truncated) · failed (exit 1: discovery
failed, a gate was breached, or the run was refused) · refused (exit 3:
another run holds the lock).
"""

from __future__ import annotations

import hashlib
import subprocess
import traceback
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from app.transnetbw.classify import classify, press_stage, project_stage, title_is_candidate
from app.transnetbw.config import TransnetBWSettings
from app.transnetbw.discovery import (
    DEFAULT_DENYLIST,
    discovery_diff,
    parse_listing,
    parse_sitemap,
    project_slugs_from_sitemap,
)
from app.transnetbw.errors import ParseError
from app.transnetbw.fetch import FetchError, FetchResult, NotCapturedError
from app.transnetbw.geocode import Gazetteer, Geocoder, Location
from app.transnetbw.link import link_project, load_aliases
from app.transnetbw.normalize import SignalRecord, cap
from app.transnetbw.press_parser import parse_article, parse_feed, titles_agree
from app.transnetbw.project_parser import parse_project_page
from app.transnetbw.store import LedgerEntry, RunLog, SignalStore


SOURCE_SYSTEM = "transnetbw"

SUMMARY_LIMIT = 500

SNIPPET_LIMIT = 200

MEASURE_LIMIT = 25

# Issues that make a run "partial": a document or record could not be
# processed, or discovery was incomplete. Data-quality observations
# (unresolved locations, date mismatches, exclusions) do not.
DEGRADING_CODES = frozenset(
    {
        "fetch_failed",
        "parse_failed",
        "db_rejected",
        "sitemap_unavailable",
        "press_feed_unavailable",
        "press_feed_short",
    }
)

EXIT_CODES = {"succeeded": 0, "partial": 2, "failed": 1}


class _Fatal(Exception):
    """
    The run cannot continue; the reason has already been logged.
    """


def needs_fetch(entry: LedgerEntry | None, lastmod: datetime | None, full: bool) -> bool:
    """
    Fetch a document only when it may have changed since it was last
    fetched: never fetched, last attempt failed, or a newer sitemap lastmod.
    A document without a lastmod is fetched once and then only with --full.
    """

    if full or entry is None:
        return True

    if entry.last_outcome == "error":
        return True

    if lastmod is None:
        return False

    if entry.sitemap_lastmod is None:
        return True

    return lastmod > entry.sitemap_lastmod


def code_version() -> str | None:

    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip() or None

    except (OSError, subprocess.SubprocessError):
        return None


def _compact(values: dict) -> dict:
    return {key: value for key, value in values.items() if value not in (None, [], {}, "")}


@dataclass
class Discovery:

    cards: dict

    lastmods: dict

    slugs: list[str]

    sitemap_ok: bool

    listing_cards: int

    gap: int | None

    sitemap_slugs: frozenset = frozenset()


@dataclass
class HarvestResult:

    run_id: uuid.UUID | None

    status: str

    exit_code: int

    stats: dict

    gates: dict

    issues: list[dict] = field(default_factory=list)

    records: list[SignalRecord] = field(default_factory=list)

    mode: str = "live"

    dry_run: bool = False


class Harvester:

    def __init__(
        self,
        settings: TransnetBWSettings,
        fetcher,
        engine: Engine,
        mode: str,
        *,
        gazetteer: Gazetteer | None = None,
        aliases: dict | None = None,
        clock: Callable[[], datetime] | None = None,
        echo: Callable[[dict], None] | None = None,
        context: dict | None = None,
    ):
        self.settings = settings

        self.fetcher = fetcher

        self.engine = engine

        self.mode = mode

        self.geocoder = Geocoder(gazetteer or Gazetteer.load())

        self.aliases = aliases if aliases is not None else load_aliases()

        self.clock = clock or (lambda: datetime.now(timezone.utc))

        self.echo = echo

        # Recorded with the run, e.g. {"replay": "<snapshot dir>"}.
        self.context = context or {}

    def run(self, full: bool = False, dry_run: bool = False) -> HarvestResult:

        config = {**self.settings.public_dict(), **self.context, "full": full, "dry_run": dry_run}

        version = code_version()

        log = RunLog(self.engine, SOURCE_SYSTEM)

        try:

            if not log.acquire_lock():
                return self._refuse(log, config, version, 3, "lock_busy", "another harvest of this source is running")

            if log.other_mode_present(self.mode):
                other = "live" if self.mode == "offline" else "offline"
                return self._refuse(
                    log,
                    config,
                    version,
                    1,
                    "mode_mixing",
                    f"this database already holds {other} runs; point {self.mode} runs at a "
                    "separate database (TRANSNETBW_DATABASE_URL or --database-url)",
                )

            run_id = log.start(self.mode, config, version)

            return _Run(self, log, run_id, full, dry_run).execute()

        finally:
            log.close()

    def _refuse(self, log: RunLog, config, version, exit_code, code, message) -> HarvestResult:

        run_id = log.start(self.mode, config, version, status="refused")

        log.issue(run_id, "error", code, message)

        log.finish(run_id, "refused", exit_code, {}, {})

        return HarvestResult(
            run_id=run_id,
            status="refused",
            exit_code=exit_code,
            stats={},
            gates={},
            issues=[{"severity": "error", "code": code, "message": message}],
            mode=self.mode,
        )


class _Run:
    """
    State of one run. Not reused.
    """

    def __init__(self, harvester: Harvester, log: RunLog, run_id: uuid.UUID, full: bool, dry_run: bool):

        self.h = harvester

        self.settings = harvester.settings

        self.log = log

        self.run_id = run_id

        self.full = full

        self.dry_run = dry_run

        self.now = harvester.clock()

        self.issues: list[dict] = []

        self.records: list[SignalRecord] = []

        self.stats = {
            "discovery": {},
            "fetch": Counter(),
            "projects": Counter(),
            "press": Counter(),
            "classify": Counter(),
            "geocode": Counter(),
            "load": Counter(),
        }

        self.gates: dict = {}

        self.press_retire_ok = False

        self.seen_press: set[str] = set()

    # =====================================================
    # BOOKKEEPING
    # =====================================================

    def issue(self, severity, code, message, *, record=None, url=None, context=None) -> None:

        self.log.issue(
            self.run_id,
            severity,
            code,
            message,
            source_record_id=record,
            source_url=url,
            context=context,
        )

        self.issues.append(
            {"severity": severity, "code": code, "message": message, "source_record_id": record, "source_url": url}
        )

        self._emit({"event": "issue", "severity": severity, "code": code, "record": record, "message": message})

    def _emit(self, event: dict) -> None:

        if self.h.echo is not None:
            self.h.echo(event)

    def _document(self, store, url, kind, lastmod, result: FetchResult | None, outcome, status=None) -> None:

        store.record_document(
            url=url,
            doc_kind=kind,
            sitemap_lastmod=lastmod,
            http_status=result.status if result else status,
            raw_sha256=result.sha256 if result else None,
            outcome=outcome,
            run_id=self.run_id,
            fetched_at=result.fetched_at if result else None,
        )

    def fetch(self, store, url, kind, accept="html", lastmod=None, record=None) -> FetchResult | None:

        try:
            result = self.h.fetcher.fetch(url, accept)

        except NotCapturedError:
            self.stats["fetch"]["not_captured"] += 1
            self.issue("info", "not_captured", "not part of the offline fixture set", record=record, url=url)
            return None

        except FetchError as exc:
            self.stats["fetch"]["attempted"] += 1
            self.stats["fetch"]["failed"] += 1
            self.issue("error", "fetch_failed", str(exc), record=record, url=url, context={"status": exc.status})
            self._document(store, url, kind, lastmod, None, "error", status=exc.status)
            return None

        self.stats["fetch"]["attempted"] += 1

        self._emit({"event": "fetch", "url": url, "status": result.status})

        return result

    # =====================================================
    # RUN
    # =====================================================

    def execute(self) -> HarvestResult:

        status = "failed"

        with self.h.engine.connect() as conn:

            transaction = conn.begin()

            store = SignalStore(conn, SOURCE_SYSTEM)

            try:
                ledger = store.ledger()

                discovery = self.discover(store)

                self.projects(store, ledger, discovery)

                self.press(store, ledger, discovery)

                self.stats["load"]["derived_refreshed"] = store.refresh_derived()

                self.evaluate_gates(store, discovery)

                if not all(gate["passed"] for gate in self.gates.values()):

                    for name, gate in self.gates.items():

                        if not gate["passed"]:
                            self.issue("error", "gate_failed", f"{name}: {gate['value']} (required {gate['limit']})")

                    raise _Fatal("quality gate breached")

                self.retire(store, discovery)

                if self.dry_run:
                    transaction.rollback()
                else:
                    transaction.commit()

                degrading = any(issue["code"] in DEGRADING_CODES for issue in self.issues)

                status = "partial" if degrading else "succeeded"

            except _Fatal:
                transaction.rollback()

            except Exception as exc:  # noqa: BLE001 — every failure must end in a recorded run
                transaction.rollback()
                last = traceback.format_exception_only(type(exc), exc)[-1].strip()
                self.issue("error", "unexpected_error", last)

        exit_code = EXIT_CODES[status]

        stats = self.export_stats()

        self.log.finish(self.run_id, status, exit_code, stats, self.gates)

        return HarvestResult(
            run_id=self.run_id,
            status=status,
            exit_code=exit_code,
            stats=stats,
            gates=self.gates,
            issues=self.issues,
            records=self.records,
            mode=self.h.mode,
            dry_run=self.dry_run,
        )

    def export_stats(self) -> dict:

        stats = {
            name: (dict(value) if isinstance(value, Counter) else value)
            for name, value in self.stats.items()
        }

        for key in ("inserted", "updated", "unchanged", "reverted", "page_changed", "rejected", "missed", "retired"):
            stats["load"].setdefault(key, 0)

        for key in ("attempted", "failed", "not_captured", "skipped_unchanged"):
            stats["fetch"].setdefault(key, 0)

        severities = Counter(issue["severity"] for issue in self.issues)

        stats["issues"] = {
            "error": severities.get("error", 0),
            "warning": severities.get("warning", 0),
            "info": severities.get("info", 0),
            "by_code": dict(Counter(issue["code"] for issue in self.issues)),
        }

        return stats

    # =====================================================
    # DISCOVERY
    # =====================================================

    def discover(self, store) -> Discovery:

        settings = self.settings

        sitemap_url = settings.url(settings.sitemap_path)

        listing_url = settings.url(settings.listing_path)

        lastmods: dict = {}

        sitemap_ok = False

        sitemap = self.fetch(store, sitemap_url, "sitemap", "xml")

        if sitemap is not None:

            try:
                lastmods = parse_sitemap(sitemap.content, sitemap_url)
                sitemap_ok = True
                self._document(store, sitemap_url, "sitemap", None, sitemap, "parsed")

            except ParseError as exc:
                self._document(store, sitemap_url, "sitemap", None, sitemap, "error")
                self.issue("error", "sitemap_unavailable", str(exc), url=sitemap_url)

        else:
            self.issue("error", "sitemap_unavailable", "sitemap could not be fetched", url=sitemap_url)

        listing = self.fetch(store, listing_url, "listing")

        if listing is None:
            self.issue("error", "listing_unavailable", "project listing could not be fetched", url=listing_url)
            raise _Fatal("listing unavailable")

        cards = {card.slug: card for card in parse_listing(listing.text, settings.base_url)}

        if not cards:
            self._document(store, listing_url, "listing", None, listing, "error")
            self.issue(
                "error",
                "empty_response",
                "the project listing contains no project cards (redesign or error page?)",
                url=listing_url,
            )
            raise _Fatal("empty listing")

        self._document(store, listing_url, "listing", None, listing, "parsed")

        sitemap_slugs = project_slugs_from_sitemap(lastmods, settings.base_url, DEFAULT_DENYLIST) if sitemap_ok else {}

        gap = None

        if sitemap_ok:

            listing_only, sitemap_only = discovery_diff(set(cards), set(sitemap_slugs))

            gap = len(listing_only) + len(sitemap_only)

            for slug in sorted(listing_only):
                self.issue("warning", "discovery_listing_only", "on the project listing but not in the sitemap", record=f"project:{slug}")

            for slug in sorted(sitemap_only):
                self.issue("warning", "discovery_sitemap_only", "in the sitemap but not on the project listing", record=f"project:{slug}")

        slugs = sorted(set(cards) | set(sitemap_slugs))

        self.stats["discovery"] = {
            "listing_cards": len(cards),
            "sitemap_projects": len(sitemap_slugs),
            "projects": len(slugs),
            "sitemap_urls": len(lastmods),
            "gap": gap,
        }

        return Discovery(cards, lastmods, slugs, sitemap_ok, len(cards), gap, frozenset(sitemap_slugs))

    # =====================================================
    # PROJECTS
    # =====================================================

    def projects(self, store, ledger, discovery: Discovery) -> None:

        base = self.settings.base_url.rstrip("/")

        for slug in discovery.slugs:

            key = f"project:{slug}"

            overview_url = f"{base}/de/netzentwicklung/projekte/{slug}"

            page_lastmods = [
                lastmod
                for url, lastmod in discovery.lastmods.items()
                if lastmod is not None and (url == overview_url or url.startswith(overview_url + "/projektport"))
            ]

            lastmod = max(page_lastmods) if page_lastmods else None

            self.stats["projects"]["seen"] += 1

            if not needs_fetch(ledger.get(overview_url), lastmod, self.full):
                self.stats["fetch"]["skipped_unchanged"] += 1
                self.stats["projects"]["skipped_unchanged"] += 1
                continue

            overview_result = self.fetch(store, overview_url, "project_overview", lastmod=lastmod, record=key)

            if overview_result is None:
                continue

            try:
                overview = parse_project_page(overview_result.text, overview_url, base)

            except ParseError as exc:
                self.issue("error", "parse_failed", str(exc), record=key, url=overview_url)
                self._document(store, overview_url, "project_overview", lastmod, overview_result, "error")
                continue

            self.stats["projects"]["fetched"] += 1

            portrait, portrait_result = None, None

            portrait_url = overview.portrait_url()

            if portrait_url and portrait_url != overview_url:

                portrait_result = self.fetch(
                    store,
                    portrait_url,
                    "project_portrait",
                    lastmod=discovery.lastmods.get(portrait_url),
                    record=key,
                )

                if portrait_result is not None:

                    try:
                        portrait = parse_project_page(portrait_result.text, portrait_url, base)

                    except ParseError as exc:
                        self.issue("error", "parse_failed", str(exc), record=key, url=portrait_url)

            record = self.project_record(slug, discovery, overview, portrait, overview_result, portrait_result, lastmod)

            outcome = "excluded" if record is None else self.load(store, record)

            self._document(store, overview_url, "project_overview", lastmod, overview_result, outcome)

            if portrait_result is not None:
                self._document(
                    store,
                    portrait_url,
                    "project_portrait",
                    discovery.lastmods.get(portrait_url),
                    portrait_result,
                    outcome,
                )

    def project_record(self, slug, discovery, overview, portrait, overview_result, portrait_result, lastmod):

        key = f"project:{slug}"

        card = discovery.cards.get(slug)

        title = card.title if card else overview.title

        subject = " ".join(part for part in (title, card.category_label if card else None, overview.overline) if part)

        body = " ".join(part for part in (overview.text(), portrait.text() if portrait else None) if part)

        classification = classify(subject, body)

        if not classification.included:
            return self.exclude(key, overview.url, classification.exclusion, classification.evidence)

        stage, stage_evidence = project_stage(overview, portrait, card.completed if card else False)

        location = self.h.geocoder.locate_project(title)

        if location.excluded:
            return self.exclude(key, overview.url, "outside_bw", location.note)

        self.location_issues(key, overview.url, location)

        measures = []

        for measure in overview.measures() + (portrait.measures() if portrait else []):

            if measure["text"] not in {seen["text"] for seen in measures}:
                measures.append(measure)

        pages = [page for page in (overview, portrait) if page is not None]

        flags = list(location.flags)

        if portrait is None:
            flags.append("portrait_missing")

        if card is None:
            flags.append("not_in_listing")

        review_reasons = ["low_confidence_classification"] if classification.confidence == "low" else []

        raw = hashlib.sha256(
            (overview_result.sha256 + (portrait_result.sha256 if portrait_result else "")).encode()
        ).hexdigest()

        discovered_via = [
            source
            for source, present in (("listing", card is not None), ("sitemap", slug in discovery.sitemap_slugs))
            if present
        ]

        record = SignalRecord(
            source_system=SOURCE_SYSTEM,
            source_record_id=key,
            record_kind="project",
            signal_type=classification.signal_type,
            title=title,
            source_url=overview.url,
            project_stage=stage,
            review_status="needs_review" if review_reasons else "auto",
            summary=cap(overview.lead or (card.teaser if card else None) or (portrait.lead if portrait else None), SUMMARY_LIMIT),
            source_last_modified=lastmod,
            location_text=location.text,
            location_status=location.status,
            location_precision=location.precision,
            location_method=location.method,
            x=location.x,
            y=location.y,
            attributes=_compact(
                {
                    "category_label": card.category_label if card else None,
                    "listing_section": card.section if card else None,
                    "discovered_via": discovered_via,
                    "secondary_signal_types": list(classification.secondary_types),
                    "classification": _compact(
                        {
                            "rule": classification.rule,
                            "confidence": classification.confidence,
                            "evidence": classification.evidence,
                        }
                    ),
                    "stage_evidence": stage_evidence,
                    "measures": measures[:MEASURE_LIMIT],
                    "voltages_kv": sorted({value for page in pages for value in page.voltages_kv}),
                    "line_ids": sorted({value for page in pages for value in page.line_ids}),
                    "endpoints": location.endpoints,
                    "regions": location.regions,
                    "location_note": location.note,
                    "location_source": location.source,
                    "portrait_url": portrait.url if portrait else None,
                    "review_reasons": review_reasons,
                }
            ),
            quality_flags=flags,
            raw_sha256=raw,
        )

        self.count(record, classification)

        return record

    # =====================================================
    # PRESS
    # =====================================================

    def press(self, store, ledger, discovery: Discovery) -> None:

        settings = self.settings

        feed_url = settings.url(settings.press_feed_path)

        feed_result = self.fetch(store, feed_url, "feed", "json")

        if feed_result is None:
            self.issue("error", "press_feed_unavailable", "press feed could not be fetched", url=feed_url)
            return

        try:
            feed = parse_feed(feed_result.text, feed_url)

        except ParseError as exc:
            self._document(store, feed_url, "feed", None, feed_result, "error")
            self.issue("error", "press_feed_unavailable", str(exc), url=feed_url)
            return

        self._document(store, feed_url, "feed", None, feed_result, "parsed")

        for duplicate in feed.duplicates:
            self.issue(
                "info",
                "duplicate_in_feed",
                f"listed {len(duplicate['dates'])} times with dates {', '.join(duplicate['dates'])}; kept the latest",
                url=duplicate["url"],
            )

        for problem in feed.malformed:
            self.issue("warning", "malformed_feed_item", f"feed item {problem['index']}: {problem['reason']}", url=problem["url"])

        self.stats["press"]["feed_items"] = len(feed.items)

        self.stats["press"]["duplicates"] = len(feed.duplicates)

        self.stats["press"]["malformed"] = len(feed.malformed)

        self.seen_press = {f"press:{item.slug}" for item in feed.items}

        if len(feed.items) < settings.gate_min_feed_items:
            self.issue(
                "warning",
                "press_feed_short",
                f"press feed has {len(feed.items)} items (expected at least {settings.gate_min_feed_items}); "
                "processed, but nothing is retired on its strength",
                url=feed_url,
            )

        else:
            self.press_retire_ok = True

        project_locations = {
            key: self.stored_location(row) for key, row in store.project_locations().items()
        }

        for item in feed.items:

            key = f"press:{item.slug}"

            if item.date is not None and item.date < settings.since:
                self.stats["press"]["before_since"] += 1
                continue

            if not title_is_candidate(item.title):
                self.stats["press"]["prefiltered_out"] += 1
                continue

            self.stats["press"]["candidates"] += 1

            lastmod = discovery.lastmods.get(item.url)

            if not needs_fetch(ledger.get(item.url), lastmod, self.full):
                self.stats["fetch"]["skipped_unchanged"] += 1
                self.stats["press"]["skipped_unchanged"] += 1
                continue

            result = self.fetch(store, item.url, "press_article", lastmod=lastmod, record=key)

            if result is None:
                continue

            try:
                article = parse_article(result.text, item.url)

            except ParseError as exc:
                self.issue("error", "parse_failed", str(exc), record=key, url=item.url)
                self._document(store, item.url, "press_article", lastmod, result, "error")
                continue

            self.stats["press"]["fetched"] += 1

            record = self.press_record(item, article, result, lastmod, project_locations)

            outcome = "excluded" if record is None else self.load(store, record)

            self._document(store, item.url, "press_article", lastmod, result, outcome)

    @staticmethod
    def stored_location(row: dict) -> Location:

        return Location(
            status=row["location_status"],
            text=row["location_text"],
            precision=row["location_precision"],
            method="gazetteer" if row["x"] is not None else None,
            x=row["x"],
            y=row["y"],
            source=row["source"],
            endpoints=row["endpoints"] or [],
            regions=row["regions"] or [],
            flags=[flag for flag in (row["quality_flags"] or []) if flag == "cross_border"],
        )

    def press_record(self, item, article, result, lastmod, project_locations):

        key = f"press:{item.slug}"

        title = article.title or item.title

        flags: list[str] = []

        if not titles_agree(item.title, article.title):
            flags.append("feed_title_mismatch")
            self.issue(
                "warning",
                "feed_title_mismatch",
                f"feed title {item.title!r} differs from the page title {article.title!r}; the page title is kept",
                record=key,
                url=item.url,
            )

        published, verified = None, False

        if article.date and item.date:

            published, verified = article.date, article.date == item.date

            if not verified:
                flags.append("date_mismatch")
                self.issue(
                    "warning",
                    "date_mismatch",
                    f"article says {article.date.isoformat()}, feed says {item.date.isoformat()}; the article's date is kept",
                    record=key,
                    url=item.url,
                )

        elif article.date:
            published = article.date

        elif item.date:
            published = item.date
            flags.append("date_unverified")
            self.issue(
                "warning",
                "date_unverified",
                f"no readable date on the article page ({article.date_text!r}); the feed date is used",
                record=key,
                url=item.url,
            )

        else:
            flags.append("date_missing")
            self.issue("error", "date_missing", "neither the article nor the feed gives a readable date", record=key, url=item.url)

        classification = classify(title, " ".join([*article.subheads, *article.paragraphs]))

        if not classification.included:
            return self.exclude(key, item.url, classification.exclusion, classification.evidence)

        link = link_project(" ".join(part for part in (title, *article.subheads, article.lead) if part), self.h.aliases)

        related = f"project:{link.slug}" if link.slug else None

        stage, stage_evidence = press_stage(title, article.subheads, article.lead)

        location = self.h.geocoder.locate_press(
            title,
            article.subheads,
            article.lead,
            project_location=project_locations.get(related) if related else None,
        )

        if location.excluded:
            return self.exclude(key, item.url, "outside_bw", location.note)

        self.location_issues(key, item.url, location)

        review_reasons = []

        if classification.confidence == "low":
            review_reasons.append("low_confidence_classification")

        if link.ambiguous:
            review_reasons.append("several_projects_named")

        if related is None and location.status not in ("resolved", "ambiguous"):
            review_reasons.append("no_project_and_no_location")

        record = SignalRecord(
            source_system=SOURCE_SYSTEM,
            source_record_id=key,
            record_kind="press_release",
            signal_type=classification.signal_type,
            title=title,
            source_url=item.url,
            project_stage=stage,
            review_status="needs_review" if review_reasons else "auto",
            summary=cap(article.lead, SUMMARY_LIMIT),
            published_at=published,
            published_at_verified=verified,
            source_last_modified=lastmod,
            location_text=location.text,
            location_status=location.status,
            location_precision=location.precision,
            location_method=location.method,
            x=location.x,
            y=location.y,
            attributes=_compact(
                {
                    "feed_type": list(item.types),
                    "feed_date": item.date.isoformat() if item.date else item.raw_date,
                    "article_date": article.date.isoformat() if article.date else article.date_text,
                    "dateline": article.dateline,
                    "subheads": [cap(subhead, SNIPPET_LIMIT) for subhead in article.subheads[:5]],
                    "related_project": related,
                    "link_evidence": link.evidence,
                    "link_candidates": list(link.candidates) if link.ambiguous else None,
                    "secondary_signal_types": list(classification.secondary_types),
                    "classification": _compact(
                        {
                            "rule": classification.rule,
                            "confidence": classification.confidence,
                            "evidence": classification.evidence,
                        }
                    ),
                    "stage_evidence": stage_evidence,
                    "endpoints": location.endpoints,
                    "regions": location.regions,
                    "location_note": location.note,
                    "location_source": location.source,
                    "review_reasons": review_reasons,
                }
            ),
            quality_flags=flags + list(location.flags),
            raw_sha256=result.sha256,
        )

        self.count(record, classification)

        return record

    # =====================================================
    # SHARED
    # =====================================================

    def exclude(self, key, url, reason, evidence) -> None:

        self.stats["classify"][f"excluded_{reason}"] += 1

        self.issue(
            "info",
            f"excluded_{reason}",
            f"not loaded: {reason.replace('_', ' ')}",
            record=key,
            url=url,
            context={"evidence": evidence} if evidence else None,
        )

        return None

    def location_issues(self, key, url, location: Location) -> None:

        if location.status == "unresolved":
            self.issue("warning", "location_unresolved", location.note or "no location", record=key, url=url)

        elif location.status == "ambiguous":
            self.issue("info", "location_ambiguous", location.note or "no single point", record=key, url=url)

        elif location.status == "invalid_coordinates":
            self.issue("error", "invalid_coordinates", location.note or "invalid coordinates", record=key, url=url)

    def count(self, record: SignalRecord, classification) -> None:

        self.stats["classify"]["included"] += 1

        self.stats["classify"][record.signal_type] += 1

        if record.review_status == "needs_review":
            self.stats["classify"]["needs_review"] += 1

        self.stats["geocode"][record.location_status] += 1

        if record.location_precision:
            self.stats["geocode"][record.location_precision] += 1

    def load(self, store, record: SignalRecord) -> str:

        try:

            with store.savepoint():
                outcome = store.upsert(record, self.run_id, self.now)

        except DBAPIError as exc:
            message = str(exc.orig).splitlines()[0] if exc.orig else str(exc)
            self.stats["load"]["rejected"] += 1
            self.issue("error", "db_rejected", message, record=record.source_record_id, url=record.source_url)
            return "error"

        self.records.append(record)

        self.stats["load"][outcome.action] += 1

        if outcome.page_changed:
            self.stats["load"]["page_changed"] += 1

        self._emit(
            {
                "event": "record",
                "record": record.source_record_id,
                "action": outcome.action,
                "signal_type": record.signal_type,
                "stage": record.project_stage,
                "location": record.location_status,
                "review": record.review_status,
            }
        )

        return "parsed"

    # =====================================================
    # GATES AND RETIREMENT
    # =====================================================

    def evaluate_gates(self, store, discovery: Discovery) -> None:

        settings = self.settings

        attempted = self.stats["fetch"]["attempted"]

        ratio = round(self.stats["fetch"]["failed"] / attempted, 3) if attempted else 0.0

        resolved = store.resolved_count()

        self.gates = {
            "listing_cards": {
                "value": discovery.listing_cards,
                "limit": f">= {settings.gate_min_listing_cards}",
                "passed": discovery.listing_cards >= settings.gate_min_listing_cards,
            },
            "fetch_failure_ratio": {
                "value": ratio,
                "limit": f"<= {settings.gate_max_fetch_failure_ratio}",
                "passed": ratio <= settings.gate_max_fetch_failure_ratio,
            },
            "resolved_rows": {
                "value": resolved,
                "limit": f">= {settings.gate_min_resolved}",
                "passed": resolved >= settings.gate_min_resolved,
            },
            "discovery_gap": {
                "value": discovery.gap,
                "limit": f"<= {settings.gate_max_discovery_gap}",
                "passed": discovery.gap is None or discovery.gap <= settings.gate_max_discovery_gap,
            },
        }

    def retire(self, store, discovery: Discovery) -> None:

        retire_after = self.settings.retire_after_misses

        if discovery.sitemap_ok:

            keys = {f"project:{slug}" for slug in discovery.slugs}

            store.mark_seen("project", keys, self.run_id, self.now)

            missed, retired = store.mark_missing("project", keys, retire_after)

            self.stats["load"]["missed"] += missed

            self.stats["load"]["retired"] += retired

        if self.press_retire_ok:

            store.mark_seen("press_release", self.seen_press, self.run_id, self.now)

            missed, retired = store.mark_missing("press_release", self.seen_press, retire_after)

            self.stats["load"]["missed"] += missed

            self.stats["load"]["retired"] += retired
