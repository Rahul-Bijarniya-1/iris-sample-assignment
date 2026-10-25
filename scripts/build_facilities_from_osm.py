"""
Build a facilities dataset from OpenStreetMap.

WHY THIS EXISTS
---------------
The pipeline's facility source is datacentermap.com, which returned HTTP 429
to every request across a window of more than nine hours, so `main.py country`
cannot complete and `iris_core.facilities` stays empty. Everything downstream
of facilities is blocked by that: the spatial enrichers, the site score, the
news entity matcher and the news loader all read facilities.

OpenStreetMap tags data centers as `telecom=data_center` and is reachable, so
this script builds an equivalent dataset from Overpass and writes it in the
shape FacilityParser already expects.

THIS IS NOT DATACENTERMAP DATA. It is a clearly-marked substitute so the rest
of the pipeline can be exercised end to end. OSM carries far fewer attributes
than datacentermap: there is no power capacity, no floor space and no operator
detail beyond an `operator` tag. Once datacentermap is reachable again, run
the real Phase 1 — FacilityLoader upserts on source_id, and the id space used
here is deliberately disjoint from datacentermap's, so the two never collide.

Output:
    data/processed/datacentermap/facilities_clean.json

That path is dictated by LoadFacilitiesCommand, which resolves it through
DataPaths; it is not a claim about provenance.

Usage:
    uv run python -m scripts.build_facilities_from_osm
"""

from __future__ import annotations

import json

from app.config.data_sources import get_data_source
from app.config.paths import DataPaths
from app.scrapers.base.http_client import HttpClient

# OSM ids are only unique within their element type, and datacentermap uses
# small sequential ids. These offsets keep every generated source_id distinct
# from both, while staying far inside BigInteger.
TYPE_OFFSETS = {
    "node": 10_000_000_000_000,
    "way": 20_000_000_000_000,
    "relation": 30_000_000_000_000,
}

# OverpassScraper.build_telecom_point_query() also matches telecom=data_center,
# but bundles it with six other telecom types into one country-wide query. That
# combined query timed out four times against overpass-api.de and never produced
# de_telecom_points.json. Narrowing to the single tag is what makes this one
# complete, so the overlap is deliberate rather than an oversight.
QUERY = """
[out:json][timeout:180];
area["ISO3166-1"="DE"][admin_level=2]->.de;
(
  node["telecom"="data_center"](area.de);
  way["telecom"="data_center"](area.de);
  relation["telecom"="data_center"](area.de);
);
out center tags;
"""


def fetch_elements() -> list[dict]:
    """
    Query Overpass through the shared HttpClient, which supplies the project
    User-Agent, retries, 429 handling with Retry-After, and backoff. Overpass
    returned 502s and read timeouts throughout the run that motivated this
    script, so a bare unretried POST is not good enough.
    """

    source = get_data_source("overpass")

    response = HttpClient().post(
        source.urls[0],
        data={"data": QUERY},
        headers={"Accept": "application/json"},
    )

    return response.json().get("elements", [])


def coordinates(element: dict) -> tuple[float | None, float | None]:
    """
    Nodes carry lat/lon directly; ways and relations carry a center.
    """

    if element.get("lat") is not None:
        return element["lat"], element["lon"]

    center = element.get("center") or {}

    return center.get("lat"), center.get("lon")


def street_address(tags: dict) -> str | None:

    street = tags.get("addr:street")

    if not street:
        return None

    number = tags.get("addr:housenumber")

    return f"{street} {number}".strip() if number else street


def build_record(element: dict) -> dict | None:
    """
    Map one OSM element onto the shape FacilityParser reads.

    company and name are NOT NULL in iris_core.facilities, so an element that
    can supply neither is skipped rather than loaded under a placeholder.
    """

    tags = element.get("tags") or {}

    name = tags.get("name")
    operator = tags.get("operator") or tags.get("brand")

    if not name and not operator:
        return None

    latitude, longitude = coordinates(element)

    offset = TYPE_OFFSETS[element["type"]]

    return {
        "id": offset + element["id"],
        "company": operator or name,
        "name": name or operator,
        "address": street_address(tags),
        "city": tags.get("addr:city"),
        "postal_code": tags.get("addr:postcode"),
        "country": "Germany",
        "website": tags.get("website") or tags.get("contact:website"),
        "latitude": latitude,
        "longitude": longitude,
    }


def main() -> None:

    print("Querying Overpass for data centers in Germany...")

    elements = fetch_elements()

    print(f"Elements : {len(elements)}")

    records = [
        record
        for record in map(build_record, elements)
        if record is not None
    ]

    skipped = len(elements) - len(records)

    with_coordinates = sum(
        1
        for record in records
        if record["latitude"] is not None
    )

    output_file = (
        DataPaths().datacentermap_processed
        / "facilities_clean.json"
    )

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("--------------------------------")
    print(f"Facilities      : {len(records)}")
    print(f"With coordinates: {with_coordinates}")
    print(f"Skipped (unnamed): {skipped}")
    print(f"Saved           : {output_file}")


if __name__ == "__main__":
    main()
