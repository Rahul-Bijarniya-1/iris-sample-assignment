"""
Build the substation gazetteer for the TransnetBW harvester from OpenStreetMap.

Two Overpass queries:

  1. every named substation and converter station in Baden-Württemberg;
     the transmission-level ones (≥ 220 kV, operated by TransnetBW, or
     tagged substation=transmission / power=converter) are kept with a
     representative point inside each station's outline;
  2. settlement points (villages, hamlets, districts) and substations for
     the specific place names TransnetBW's project and press titles use
     that are not municipalities or have no OSM substation — searched in a
     box around BW, because some endpoints (Grafenrheinfeld, possibly
     Stalldorf) lie outside it. Whether a point is in BW is decided later
     by the BKG boundary, never by this list.

Writes app/transnetbw/data/osm_gazetteer.json. Data © OpenStreetMap
contributors, ODbL 1.0 — kept in its own file, apart from the BKG-derived
municipalities (scripts/build_bw_boundary.py), so each licence stays with
its data.

Usage:
    uv run python -m scripts.build_transnetbw_gazetteer
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from app.config.data_sources import get_data_source
from app.scrapers.base.http_client import HttpClient
from app.transnetbw.config import TransnetBWSettings


OUT_FILE = Path("app/transnetbw/data/osm_gazetteer.json")

RAW_FILE = Path("data/raw/osm/bw_substations_overpass.json")

RAW_PLACES_FILE = Path("data/raw/osm/transnetbw_places_overpass.json")

# Names used in TransnetBW titles that query 1 cannot resolve: districts of
# a municipality (Großgartach, Kork, Daxlanden…) and line endpoints without
# a substation of that name. Extend this list when a run reports
# location_unresolved for a real place name, then rebuild.
PLACE_NAMES = (
    "Beuren",
    "Daxlanden",
    "Engstlatt",
    "Grafenrheinfeld",
    "Großgartach",
    "Gurtweil",
    "Istein",
    "Kork",
    "Kühmoos",
    "Leingarten",
    "Merdingen",
    "Obermooweiler",
    "Ötisheim",
    "Pulverdingen",
    "Reicheneck",
    "Rippolingen",
    "Rommelsbach",
    "Stalldorf",
)

# south, west, north, east — BW plus a margin into the neighbouring states.
SEARCH_BOX = "47.2,7.2,50.4,10.8"

QUERY = """
[out:json][timeout:180];
area["ISO3166-2"="DE-BW"]["admin_level"="4"]->.bw;
(
  nwr["power"="substation"]["name"](area.bw);
  nwr["power"="converter"](area.bw);
);
out tags geom;
"""

NAME_TAGS = ("name", "alt_name", "short_name", "old_name", "official_name")


def max_voltage(tags: dict) -> int:

    best = 0

    for part in (tags.get("voltage") or "").replace(",", ";").split(";"):

        part = part.strip()

        if part.isdigit():
            best = max(best, int(part))

    return best


def is_transmission_level(tags: dict) -> bool:

    return (
        max_voltage(tags) >= 220_000
        or "transnetbw" in (tags.get("operator") or "").lower()
        or tags.get("substation") == "transmission"
        or tags.get("power") == "converter"
    )


def representative_point(element: dict) -> tuple[Point, str]:
    """
    A point guaranteed to lie inside the station's outline when the outline
    can be built; otherwise the bounding-box centre, labelled as such.
    """

    if element["type"] == "node":
        return Point(element["lon"], element["lat"]), "node"

    if element["type"] == "way":

        coords = [(node["lon"], node["lat"]) for node in element.get("geometry", [])]

        if len(coords) >= 4 and coords[0] == coords[-1]:
            return Polygon(coords).representative_point(), "outline"

    if element["type"] == "relation":

        lines = [
            LineString([(node["lon"], node["lat"]) for node in member["geometry"]])
            for member in element.get("members", [])
            if member.get("role") in ("outer", "") and len(member.get("geometry", [])) >= 2
        ]

        polygons = list(polygonize(unary_union(lines))) if lines else []

        if polygons:
            return unary_union(polygons).representative_point(), "outline"

    bounds = element.get("bounds")

    if bounds:
        return (
            Point(
                (bounds["minlon"] + bounds["maxlon"]) / 2,
                (bounds["minlat"] + bounds["maxlat"]) / 2,
            ),
            "bbox_centre",
        )

    raise ValueError(f"no geometry for {element['type']}/{element['id']}")


def place_query() -> str:

    names = "|".join(PLACE_NAMES)

    return f"""
[out:json][timeout:120];
(
  node["place"~"^(city|town|village|hamlet|suburb|quarter|locality|isolated_dwelling)$"]["name"~"^({names})$"]({SEARCH_BOX});
  nwr["power"="substation"]["name"~"({names})"]({SEARCH_BOX});
);
out tags geom;
"""


def fetch(settings: TransnetBWSettings, query: str, cache: Path) -> dict:

    if cache.exists():
        print(f"Using cached {cache}")
        return json.loads(cache.read_text(encoding="utf-8"))

    client = HttpClient()

    response = client.post(
        get_data_source("overpass").urls[0],
        data={"data": query},
        headers={"User-Agent": settings.user_agent},
        timeout=240,
    )

    cache.parent.mkdir(parents=True, exist_ok=True)

    cache.write_bytes(response.content)

    return response.json()


def entry_for(element: dict, to_utm: Transformer) -> dict:

    tags = element.get("tags", {})

    point, method = representative_point(element)

    x, y = to_utm.transform(point.x, point.y)

    return {
        "osm": f"{element['type']}/{element['id']}",
        "names": [tags[tag] for tag in NAME_TAGS if tags.get(tag)],
        "power": tags.get("power"),
        "place": tags.get("place"),
        "operator": tags.get("operator"),
        "max_voltage_kv": max_voltage(tags) // 1000 or None,
        "point_method": method,
        "lon": round(point.x, 6),
        "lat": round(point.y, 6),
        "x": round(x, 1),
        "y": round(y, 1),
    }


def main() -> None:

    settings = TransnetBWSettings()

    to_utm = Transformer.from_crs(4326, 25832, always_xy=True)

    substations = {}

    for element in fetch(settings, QUERY, RAW_FILE)["elements"]:

        if is_transmission_level(element.get("tags", {})):
            entry = entry_for(element, to_utm)
            substations[entry["osm"]] = entry

    places = []

    for element in fetch(settings, place_query(), RAW_PLACES_FILE)["elements"]:

        tags = element.get("tags", {})

        if tags.get("power") in ("substation", "converter"):

            if is_transmission_level(tags):
                entry = entry_for(element, to_utm)
                substations.setdefault(entry["osm"], entry)

        elif tags.get("place"):
            places.append(entry_for(element, to_utm))

    def order(entry: dict) -> tuple:
        return (entry["names"][0] if entry["names"] else "", entry["osm"])

    entries = sorted(substations.values(), key=order)

    places.sort(key=order)

    OUT_FILE.write_text(
        json.dumps(
            {
                "source": "OpenStreetMap via Overpass API",
                "queries": [QUERY.strip(), place_query().strip()],
                "licence": "ODbL 1.0",
                "attribution": "© OpenStreetMap contributors",
                "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "srid": 25832,
                "substations": entries,
                "places": places,
            },
            ensure_ascii=False,
            indent=0,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"Transmission-level substations: {len(entries)} · places: {len(places)}")


if __name__ == "__main__":
    main()
