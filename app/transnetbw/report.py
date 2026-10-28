"""
What a run tells people: the one-screen CLI summary, and the committed
artifacts (quality report, sample exports).
"""

from __future__ import annotations

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
        f"fetch     requests {_n(fetch, 'attempted')}  failed {_n(fetch, 'failed')}"
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
