"""
What a run tells people: the one-screen CLI summary, and the committed
artifacts (quality report, sample exports).
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa

from app.transnetbw.harvester import HarvestResult


def _n(section: dict, key: str) -> int:
    return int(section.get(key, 0) or 0)


def render_summary(result: HarvestResult, report_path=None) -> str:
    """
    One screen, one line per stage, ending in the status and exit code.
    """

    stats = result.stats

    run = str(result.run_id)[:8] if result.run_id else "—"

    lines = [f"TransnetBW Project Radar   run {run}  mode={result.mode}" + ("  (dry run)" if result.dry_run else "")]

    if result.status == "refused":
        reason = result.issues[0]["message"] if result.issues else "refused"
        lines += [f"refused   {reason}", f"status    REFUSED  (exit {result.exit_code})"]
        return "\n".join(lines)

    discovery = stats.get("discovery", {})
    fetch = stats.get("fetch", {})
    projects = stats.get("projects", {})
    press = stats.get("press", {})
    classify = stats.get("classify", {})
    geocode = stats.get("geocode", {})
    load = stats.get("load", {})
    issues = stats.get("issues", {})

    excluded = sum(value for key, value in classify.items() if key.startswith("excluded_"))

    lines += [
        f"discovery sitemap {discovery.get('sitemap_urls', 0)} urls · listing {discovery.get('listing_cards', 0)} cards"
        f" · {discovery.get('projects', 0)} projects (gap {discovery.get('gap')})",
        f"projects  seen {_n(projects, 'seen')}  fetched {_n(projects, 'fetched')}"
        f"  unchanged-lastmod {_n(projects, 'skipped_unchanged')}",
        f"press     feed {_n(press, 'feed_items')} → candidates {_n(press, 'candidates')}"
        f" → fetched {_n(press, 'fetched')}  unchanged-lastmod {_n(press, 'skipped_unchanged')}",
        f"fetch     requests {_n(fetch, 'http_requests') or _n(fetch, 'attempted')}  failed {_n(fetch, 'failed')}"
        + (f"  not-captured {_n(fetch, 'not_captured')}" if _n(fetch, 'not_captured') else ""),
        f"classify  in {_n(classify, 'included')}  needs_review {_n(classify, 'needs_review')}  excluded {excluded}",
        f"geocode   resolved {_n(geocode, 'resolved')} (substation {_n(geocode, 'substation')},"
        f" municipality {_n(geocode, 'municipality')})",
        f"          ambiguous {_n(geocode, 'ambiguous')}  unresolved {_n(geocode, 'unresolved')}"
        f"  invalid {_n(geocode, 'invalid_coordinates')}",
        f"load      inserted {_n(load, 'inserted')}  updated {_n(load, 'updated')}  unchanged {_n(load, 'unchanged')}"
        f"  reverted {_n(load, 'reverted')}  rejected {_n(load, 'rejected')}  retired {_n(load, 'retired')}",
        f"issues    error {_n(issues, 'error')}  warning {_n(issues, 'warning')}  info {_n(issues, 'info')}",
    ]

    failed_gates = [name for name, gate in result.gates.items() if not gate.get("passed", True)]

    if failed_gates:
        lines.append("gates     FAILED: " + ", ".join(failed_gates))

    if report_path:
        lines.append(f"report    {report_path}")

    lines.append(f"status    {result.status.upper()}  (exit {result.exit_code})")

    return "\n".join(lines)


# =========================================================
# ARTIFACTS
# =========================================================


SOURCE_SYSTEM = "transnetbw"

# Verified by hand on 2026-10-27 while confirming the source's current
# format (see TRANSNETBW.md). Run-time numbers are reported next to them.
SOURCE_FINDINGS = [
    "The brief's URL https://www.transnetbw.de/de/netzentwicklung answers HTTP 303 and lands on "
    "/de/netzentwicklung/planung/netzentwicklungsplan, an overview without project data.",
    "The project catalogue is /de/netzentwicklung/projekte/alle-projekte: server-rendered HTML, "
    "one page, no pagination; its map is a schematic SVG without coordinates.",
    "robots.txt disallows only /neos/.",
    "/de/sitemap.xml gives a lastmod for every URL; listing and sitemap disagree on three projects.",
    "Project pages carry no publication date and no coordinates.",
    "The newsroom list is rendered by JavaScript from /de/api/press-releases (JSON, 564 entries "
    "from 2009-10-15 to 2026-10-15, one URL listed twice); article pages state their date as text "
    "(\"15. Oktober 2026\").",
    "The newsroom CMS reuses URL slugs for unrelated articles (e.g. …-umspannwerkes-wendlingen-1 is a "
    "release on the underground-cable priority); the URL is a stable identifier, the page title is "
    "authoritative.",
]

CSV_COLUMNS = (
    "source_record_id",
    "record_kind",
    "signal_type",
    "secondary_signal_types",
    "project_stage",
    "review_status",
    "title",
    "published_at",
    "published_at_verified",
    "source_last_modified",
    "source_url",
    "location_status",
    "location_precision",
    "location_method",
    "location_text",
    "x_25832",
    "y_25832",
    "wkt_25832",
    "related_project",
    "quality_flags",
    "first_seen_at",
    "last_seen_at",
    "retired_at",
)

GEOJSON_PROPERTIES = (
    "source_record_id",
    "record_kind",
    "signal_type",
    "project_stage",
    "review_status",
    "title",
    "published_at",
    "source_url",
    "location_status",
    "location_precision",
    "location_text",
    "related_project",
    "quality_flags",
)


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def collect(engine, run_id=None, source_system: str = SOURCE_SYSTEM) -> dict:
    """
    Everything the artifacts show, read from the database: current rows,
    and the issues of the run shown (the given one, else the latest).
    """

    with engine.connect() as conn:

        def query(sql, **params):
            return conn.execute(sa.text(sql), {"source": source_system, **params}).mappings().all()

        if run_id is None:
            latest = query(
                """
                select run_id from iris_staging.ingest_run
                where source_system = :source and status <> 'refused'
                order by started_at desc limit 1
                """
            )
            run_id = latest[0]["run_id"] if latest else None

        run = query("select * from iris_staging.ingest_run where run_id = :run_id", run_id=run_id) if run_id else []

        rows = query(
            """
            select s.*,
                   ST_X(s.geom) as x, ST_Y(s.geom) as y, ST_AsText(s.geom) as wkt,
                   ST_X(ST_Transform(s.geom, 4326)) as lon, ST_Y(ST_Transform(s.geom, 4326)) as lat
            from iris_staging.signal_ingest s
            where s.source_system = :source
            order by s.source_record_id
            """
        )

        issues = query(
            "select * from iris_staging.ingest_issue where run_id = :run_id order by id",
            run_id=run_id,
        ) if run_id else []

        # Exclusions are logged only when a document is fetched, so take the
        # latest exclusion of every record not currently staged, across runs.
        exclusions = query(
            """
            select distinct on (i.source_record_id)
                   i.code, i.source_record_id, i.source_url, i.message, i.context ->> 'evidence' as evidence
            from iris_staging.ingest_issue i
            join iris_staging.ingest_run r on r.run_id = i.run_id
            where r.source_system = :source and i.code like 'excluded_%'
              and not exists (
                  select 1 from iris_staging.signal_ingest s
                  where s.source_system = :source and s.source_record_id = i.source_record_id
                    and s.retired_at is null
              )
            order by i.source_record_id, i.created_at desc
            """
        )

    live = [row for row in rows if row["retired_at"] is None]

    def count(field):
        return dict(sorted(Counter(row[field] for row in live).items()))

    run_row = run[0] if run else {}

    press = [row for row in live if row["record_kind"] == "press_release"]

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_system": source_system,
        "run": {
            "run_id": str(run_row.get("run_id")) if run_row else None,
            "mode": run_row.get("mode"),
            "status": run_row.get("status"),
            "exit_code": run_row.get("exit_code"),
            "started_at": _iso(run_row.get("started_at")),
            "finished_at": _iso(run_row.get("finished_at")),
            "code_version": run_row.get("code_version"),
            "stats": run_row.get("stats") or {},
            "gates": run_row.get("gates") or {},
        },
        "source_findings": SOURCE_FINDINGS,
        "records": {
            "total": len(live),
            "retired": len(rows) - len(live),
            "by_kind": count("record_kind"),
            "by_signal_type": count("signal_type"),
            "by_stage": count("project_stage"),
            "needs_review": sum(1 for row in live if row["review_status"] == "needs_review"),
        },
        "locations": {
            "by_status": count("location_status"),
            "by_precision": dict(sorted(Counter(row["location_precision"] for row in live if row["location_precision"]).items())),
            "not_resolved": [
                {
                    "source_record_id": row["source_record_id"],
                    "title": row["title"],
                    "location_status": row["location_status"],
                    "location_text": row["location_text"],
                    "note": row["attributes"].get("location_note") or "no location note",
                    "endpoints": [endpoint["name"] for endpoint in row["attributes"].get("endpoints", [])],
                    "flags": row["quality_flags"],
                }
                for row in live
                if row["location_status"] != "resolved"
            ],
        },
        "dates": {
            "press_releases": len(press),
            "verified": sum(1 for row in press if row["published_at_verified"]),
            "not_verified": [
                {
                    "source_record_id": row["source_record_id"],
                    "published_at": _iso(row["published_at"]),
                    "article_date": row["attributes"].get("article_date"),
                    "feed_date": row["attributes"].get("feed_date"),
                    "flags": row["quality_flags"],
                }
                for row in press
                if not row["published_at_verified"]
            ],
        },
        "exclusions": [dict(row) for row in exclusions],
        "discovery": [
            {"code": issue["code"], "source_record_id": issue["source_record_id"]}
            for issue in issues
            if issue["code"].startswith("discovery_")
        ],
        "issues": {
            "by_code": [
                {"severity": severity, "code": code, "count": total}
                for (severity, code), total in sorted(
                    Counter((issue["severity"], issue["code"]) for issue in issues).items()
                )
            ],
            "errors": [
                {
                    "code": issue["code"],
                    "source_record_id": issue["source_record_id"],
                    "source_url": issue["source_url"],
                    "message": issue["message"],
                }
                for issue in issues
                if issue["severity"] == "error"
            ],
        },
        "review_queue": [
            {
                "source_record_id": row["source_record_id"],
                "title": row["title"],
                "reasons": row["attributes"].get("review_reasons", []),
            }
            for row in live
            if row["review_status"] == "needs_review"
        ],
        "rows": rows,
    }


def _csv_row(row) -> dict:

    attributes = row["attributes"] or {}

    return {
        "source_record_id": row["source_record_id"],
        "record_kind": row["record_kind"],
        "signal_type": row["signal_type"],
        "secondary_signal_types": ";".join(attributes.get("secondary_signal_types", [])),
        "project_stage": row["project_stage"],
        "review_status": row["review_status"],
        "title": row["title"],
        "published_at": _iso(row["published_at"]) or "",
        "published_at_verified": row["published_at_verified"],
        "source_last_modified": _iso(row["source_last_modified"]) or "",
        "source_url": row["source_url"],
        "location_status": row["location_status"],
        "location_precision": row["location_precision"] or "",
        "location_method": row["location_method"] or "",
        "location_text": row["location_text"] or "",
        "x_25832": "" if row["x"] is None else round(row["x"], 1),
        "y_25832": "" if row["y"] is None else round(row["y"], 1),
        "wkt_25832": row["wkt"] or "",
        "related_project": attributes.get("related_project", ""),
        "quality_flags": ";".join(row["quality_flags"] or []),
        "first_seen_at": _iso(row["first_seen_at"]),
        "last_seen_at": _iso(row["last_seen_at"]),
        "retired_at": _iso(row["retired_at"]) or "",
    }


def _feature(row) -> dict:

    attributes = row["attributes"] or {}

    properties = {name: _iso(row[name]) if name in row else None for name in GEOJSON_PROPERTIES}

    properties["related_project"] = attributes.get("related_project")

    properties["quality_flags"] = row["quality_flags"] or []

    geometry = None

    if row["lon"] is not None:
        geometry = {"type": "Point", "coordinates": [round(row["lon"], 6), round(row["lat"], 6)]}

    return {"type": "Feature", "geometry": geometry, "properties": properties}


def render_markdown(data: dict) -> str:

    run = data["run"]

    records = data["records"]

    locations = data["locations"]

    dates = data["dates"]

    def table(header: list[str], body: list[list]) -> list[str]:
        lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
        lines += ["| " + " | ".join(str(cell).replace("|", "\\|") for cell in row) + " |" for row in body]
        return lines

    out = [
        "# TransnetBW Project Radar — quality report",
        "",
        f"Generated {data['generated_at']} from `iris_staging` · run `{run['run_id']}` · mode **{run['mode']}** · "
        f"status **{run['status']}** (exit {run['exit_code']}) · code `{run['code_version']}`",
        "",
        "## Source verification",
        "",
        "Facts checked by hand on 2026-10-27 — this run: "
        f"listing {run['stats'].get('discovery', {}).get('listing_cards', '?')} cards, "
        f"sitemap {run['stats'].get('discovery', {}).get('sitemap_urls', '?')} URLs, "
        f"press feed {run['stats'].get('press', {}).get('feed_items', '?')} items.",
        "",
        *[f"- {finding}" for finding in data["source_findings"]],
        "",
        "## Records",
        "",
        f"{records['total']} staged records ({records['retired']} retired), "
        f"{records['needs_review']} held for review.",
        "",
        *table(["by kind", "records"], [[key, value] for key, value in records["by_kind"].items()]),
        "",
        *table(["by signal type", "records"], [[key, value] for key, value in records["by_signal_type"].items()]),
        "",
        *table(["by stage", "records"], [[key, value] for key, value in records["by_stage"].items()]),
        "",
        "## Quality gates",
        "",
        *table(
            ["gate", "value", "required", "passed"],
            [[name, gate.get("value"), gate.get("limit"), "yes" if gate.get("passed") else "**no**"] for name, gate in run["gates"].items()],
        ),
        "",
        "## Unresolved and ambiguous locations",
        "",
        "Points are EPSG:25832. " + ", ".join(f"{key}: {value}" for key, value in locations["by_status"].items())
        + (" · precision " + ", ".join(f"{key}: {value}" for key, value in locations["by_precision"].items()) if locations["by_precision"] else ""),
        "",
        *table(
            ["record", "status", "named", "reason"],
            [
                [row["source_record_id"], row["location_status"], ", ".join(row["endpoints"]) or (row["location_text"] or "—"), row["note"]]
                for row in locations["not_resolved"]
            ],
        ),
        "",
        "## Publication dates",
        "",
        f"{dates['verified']} of {dates['press_releases']} press-release dates confirmed by both the article page and the feed.",
        "",
    ]

    if dates["not_verified"]:
        out += table(
            ["record", "published_at", "article", "feed", "flags"],
            [[row["source_record_id"], row["published_at"], row["article_date"], row["feed_date"], ", ".join(row["flags"])] for row in dates["not_verified"]],
        ) + [""]

    out += [
        "Project pages state no publication date: `published_at` is NULL for projects by design; "
        "`source_last_modified` carries the sitemap lastmod.",
        "",
        "## Exclusions",
        "",
        *table(
            ["reason", "record", "evidence"],
            [[row["code"].removeprefix("excluded_"), row["source_record_id"], row["evidence"] or row["message"]] for row in data["exclusions"]],
        ),
        "",
        "## Listing and sitemap differences",
        "",
        *table(["difference", "project"], [[row["code"].removeprefix("discovery_"), row["source_record_id"]] for row in data["discovery"]]),
        "",
        "## Review queue",
        "",
        *table(["record", "title", "reasons"], [[row["source_record_id"], row["title"], ", ".join(row["reasons"])] for row in data["review_queue"]]),
        "",
        "## Issues of this run",
        "",
        *table(["severity", "code", "count"], [[row["severity"], row["code"], row["count"]] for row in data["issues"]["by_code"]]),
        "",
    ]

    if data["issues"]["errors"]:
        out += ["### Errors", "", *table(
            ["code", "record", "message"],
            [[row["code"], row["source_record_id"] or row["source_url"] or "—", row["message"]] for row in data["issues"]["errors"]],
        ), ""]

    return "\n".join(out)


def write_artifacts(engine, settings, result=None, run_id=None) -> Path:
    """
    Write the sample exports and the quality report; returns the report path.
    The report covers `result`'s run, else `run_id`, else the latest run.
    """

    data = collect(engine, run_id=result.run_id if result else run_id)

    directory = Path(settings.artifacts_dir)

    directory.mkdir(parents=True, exist_ok=True)

    rows = data.pop("rows")

    with (directory / "sample_signal_ingest.csv").open("w", encoding="utf-8", newline="") as handle:

        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)

        writer.writeheader()

        for row in rows:
            writer.writerow(_csv_row(row))

    (directory / "sample_signal_ingest.geojson").write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": [_feature(row) for row in rows]},
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )

    (directory / "quality_report.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1, default=_iso) + "\n",
        encoding="utf-8",
    )

    report = directory / "quality_report.md"

    report.write_text(render_markdown(data) + "\n", encoding="utf-8")

    return report
