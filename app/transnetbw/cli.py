"""
Command line for the TransnetBW Project Radar harvester (IRIS-SIG-30).

    uv run python -m app.transnetbw.cli harvest [--offline] [--full] [--since YYYY-MM-DD]
                                                [--dry-run] [-v | --log-json]
                                                [--database-url URL] [--fixtures DIR] [--no-report]
    uv run python -m app.transnetbw.cli report [--database-url URL]

Exit codes: 0 succeeded · 2 partial · 1 failed or refused · 3 another run
holds the lock.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine

from app.transnetbw import report
from app.transnetbw.config import TransnetBWSettings
from app.transnetbw.fetch import FixtureFetcher, LiveFetcher, load_fixture_index, load_snapshot_index
from app.transnetbw.harvester import Harvester


# The committed fixture feed is a 15-item subset of the live feed, so the
# truncated-feed threshold is lowered for offline runs only.
OFFLINE_MIN_FEED_ITEMS = 10

SYMBOLS = {"error": "✖", "warning": "⚠", "info": "·"}


def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        prog="python -m app.transnetbw.cli",
        description="TransnetBW Project Radar harvester (IRIS-SIG-30).",
    )

    commands = parser.add_subparsers(dest="command", required=True)

    harvest = commands.add_parser("harvest", help="harvest projects and press releases into iris_staging")

    harvest.add_argument("--offline", action="store_true", help="read the committed fixtures instead of transnetbw.de")
    harvest.add_argument("--fixtures", type=Path, help="fixture directory for --offline (default: fixtures/transnetbw)")
    harvest.add_argument(
        "--replay",
        type=Path,
        metavar="SNAPSHOT_DIR",
        help="re-process a live run's raw snapshot (data/raw/transnetbw/run-*) without contacting the site",
    )
    harvest.add_argument("--full", action="store_true", help="refetch every document, ignoring the sitemap lastmod")
    harvest.add_argument("--since", type=date.fromisoformat, help="earliest press release date to fetch (default: 2020-01-01)")
    harvest.add_argument("--dry-run", action="store_true", help="do everything, then roll the data back")
    harvest.add_argument("-v", "--verbose", action="store_true", help="print a line per fetch, record and issue")
    harvest.add_argument("--log-json", action="store_true", help="emit JSON lines instead of the summary")
    harvest.add_argument("--database-url", help="override TRANSNETBW_DATABASE_URL / DATABASE_URL")
    harvest.add_argument("--no-report", action="store_true", help="do not regenerate artifacts/transnetbw")

    regenerate = commands.add_parser("report", help="regenerate artifacts/transnetbw from the database")

    regenerate.add_argument("--database-url", help="override TRANSNETBW_DATABASE_URL / DATABASE_URL")
    regenerate.add_argument("--run-id", type=uuid.UUID, help="report on this run (default: the latest)")

    return parser


def _database_url(args, settings: TransnetBWSettings) -> str | None:

    url = args.database_url or settings.database_url

    if not url:
        print(
            "No database configured: set TRANSNETBW_DATABASE_URL (or DATABASE_URL) in .env, "
            "or pass --database-url.",
            file=sys.stderr,
        )

    return url


def _verbose(event: dict) -> None:

    kind = event["event"]

    if kind == "fetch":
        print(f"  GET {event['url']} {event['status']}")

    elif kind == "record":
        print(
            f"  ✔ {event['record']}  {event['signal_type']} · {event['location']} · "
            f"{event['stage']} · {event['review']} · {event['action']}"
        )

    elif kind == "issue":
        target = f" {event['record']}" if event.get("record") else ""
        print(f"  {SYMBOLS.get(event['severity'], '?')} {event['code']}{target}: {event['message']}")


def _json(event: dict) -> None:
    print(json.dumps(event, ensure_ascii=False, default=str))


def harvest(args, settings: TransnetBWSettings) -> int:

    overrides = {}

    if args.since:
        overrides["since"] = args.since

    if args.offline:
        overrides["gate_min_feed_items"] = min(settings.gate_min_feed_items, OFFLINE_MIN_FEED_ITEMS)

    settings = settings.model_copy(update=overrides)

    url = _database_url(args, settings)

    if not url:
        return 1

    context = {}

    if args.offline:

        fixtures = Path(args.fixtures or settings.fixtures_dir)

        fetcher = FixtureFetcher(load_fixture_index(fixtures / "index.json"))

        mode = "offline"

    elif args.replay:

        # The snapshot holds documents as the live site served them, so a
        # replay is a live run; the source is recorded with it.
        fetcher = FixtureFetcher(load_snapshot_index(args.replay))

        mode = "live"

        context = {"replay": str(args.replay)}

    else:

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        fetcher = LiveFetcher(settings, snapshot_dir=settings.raw_dir / f"run-{stamp}")

        mode = "live"

    echo = _json if args.log_json else (_verbose if args.verbose else None)

    engine = create_engine(url)

    try:

        result = Harvester(settings, fetcher, engine, mode, echo=echo, context=context).run(
            full=args.full,
            dry_run=args.dry_run,
        )

        report_path = None

        if not (args.no_report or args.dry_run or result.status == "refused"):
            report_path = report.write_artifacts(engine, settings, result)

    finally:
        engine.dispose()

    if args.log_json:
        _json(
            {
                "event": "run_finished",
                "run_id": str(result.run_id),
                "status": result.status,
                "exit_code": result.exit_code,
                "stats": result.stats,
                "gates": result.gates,
                "report": str(report_path) if report_path else None,
            }
        )

    else:
        print(report.render_summary(result, report_path))

    return result.exit_code


def regenerate(args, settings: TransnetBWSettings) -> int:

    url = _database_url(args, settings)

    if not url:
        return 1

    engine = create_engine(url)

    try:
        path = report.write_artifacts(engine, settings, run_id=args.run_id)

    finally:
        engine.dispose()

    print(f"report    {path}")

    return 0


def main(argv: list[str] | None = None) -> int:

    args = build_parser().parse_args(argv)

    settings = TransnetBWSettings()

    if args.command == "harvest":
        return harvest(args, settings)

    return regenerate(args, settings)


if __name__ == "__main__":
    sys.exit(main())
