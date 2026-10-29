"""
Build the Baden-Württemberg reference geometry from BKG VG250.

VG250 (Verwaltungsgebiete 1:250 000) is the federal administrative-boundary
dataset of the Bundesamt für Kartographie und Geodäsie, published under the
Datenlizenz Deutschland – Namensnennung – 2.0 (dl-de/by-2-0). Attribution:
"© GeoBasis-DE / BKG (2026)". It is distributed in EPSG:25832 already.

Writes, under app/transnetbw/data/:

    de_bw_boundary_25832.wkt     BW state polygon, generalized (≤ 25 m)
    de_bw_boundary.json          provenance: source URL, licence, tolerance
    bw_municipalities.json       every BW municipality: name, AGS, kind and
                                 a representative point inside its area

The boundary seeds iris_staging.ref_region (and the harvester's point-in-BW
check); the municipalities are the gazetteer's fallback level.

Usage:
    uv run python -m scripts.build_bw_boundary
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import requests
from pyproj import Transformer
from shapely import wkt
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union

from app.transnetbw.config import TransnetBWSettings


VG250_URL = (
    "https://daten.gdz.bkg.bund.de/produkte/vg/vg250_ebenen_0101/"
    "aktuell/vg250_01-01.utm32s.shape.ebenen.zip"
)

RAW_DIR = Path("data/raw/bkg")

OUT_DIR = Path("app/transnetbw/data")

BW_STATE_KEY = "08"

# Generalisation tolerance. Small enough that the substations closest to the
# border (Schwörstadt and Kühmoos on the Rhine) stay on the right side;
# tests/test_transnetbw_geocode.py checks exactly those points.
TOLERANCE_M = 25

LICENCE = "Datenlizenz Deutschland – Namensnennung – 2.0 (dl-de/by-2-0)"

ATTRIBUTION = "© GeoBasis-DE / BKG (2026)"


def download(url: str, target: Path, user_agent: str) -> Path:

    if target.exists():
        print(f"Using cached {target}")
        return target

    target.parent.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {url}")

    with requests.get(url, headers={"User-Agent": user_agent}, stream=True, timeout=120) as response:

        response.raise_for_status()

        partial = target.with_suffix(".part")

        with partial.open("wb") as handle:

            for chunk in response.iter_content(chunk_size=1 << 20):
                handle.write(chunk)

        partial.rename(target)

    return target


def layer_path(archive: Path, layer: str) -> str:
    """
    The shapefile's path inside the archive, for a zip:// read.
    """

    with zipfile.ZipFile(archive) as handle:

        for name in handle.namelist():

            if name.upper().endswith(f"/{layer}.SHP") or name.upper() == f"{layer}.SHP":
                return f"zip://{archive.resolve()}!{name}"

    raise SystemExit(f"{layer}.shp not found in {archive}")


def main() -> None:

    settings = TransnetBWSettings()

    archive = download(VG250_URL, RAW_DIR / "vg250_01-01.utm32s.shape.ebenen.zip", settings.user_agent)

    states = gpd.read_file(layer_path(archive, "VG250_LAN"))

    if states.crs is None or states.crs.to_epsg() != 25832:
        states = states.to_crs(25832)

    bw = states[states["SN_L"] == BW_STATE_KEY]

    print(f"BW features: {len(bw)}  GF values: {sorted(bw['GF'].unique().tolist())}")

    # GF 4 = land area (Landfläche mit Struktur); GF 2 = water. Lake
    # Constance belongs to no state in VG250, so the land area is BW.
    land = bw[bw["GF"] == 4] if (bw["GF"] == 4).any() else bw

    boundary = unary_union(list(land.geometry))

    generalized = boundary.simplify(TOLERANCE_M, preserve_topology=True)

    if generalized.geom_type == "Polygon":
        generalized = MultiPolygon([generalized])

    text = wkt.dumps(generalized, rounding_precision=1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    (OUT_DIR / "de_bw_boundary_25832.wkt").write_text(text + "\n", encoding="utf-8")

    vertex_count = sum(len(polygon.exterior.coords) for polygon in generalized.geoms)

    (OUT_DIR / "de_bw_boundary.json").write_text(
        json.dumps(
            {
                "region_code": "DE-BW",
                "name": "Baden-Württemberg",
                "srid": 25832,
                "source": VG250_URL,
                "layer": "VG250_LAN (SN_L=08, GF=4)",
                "licence": LICENCE,
                "attribution": ATTRIBUTION,
                "generalization_tolerance_m": TOLERANCE_M,
                "area_km2": round(generalized.area / 1e6, 1),
                "exterior_vertices": vertex_count,
                "built_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )

    municipalities = gpd.read_file(layer_path(archive, "VG250_GEM"))

    if municipalities.crs is None or municipalities.crs.to_epsg() != 25832:
        municipalities = municipalities.to_crs(25832)

    municipalities = municipalities[
        (municipalities["SN_L"] == BW_STATE_KEY)
        & (municipalities["GF"] == 4)
    ]

    to_wgs84 = Transformer.from_crs(25832, 4326, always_xy=True)

    entries = []

    for row in municipalities.itertuples():

        point = row.geometry.representative_point()

        lon, lat = to_wgs84.transform(point.x, point.y)

        entries.append(
            {
                "name": row.GEN,
                "kind": row.BEZ,
                "ags": row.AGS,
                "x": round(point.x, 1),
                "y": round(point.y, 1),
                "lon": round(lon, 6),
                "lat": round(lat, 6),
            }
        )

    entries.sort(key=lambda entry: (entry["name"], entry["ags"]))

    (OUT_DIR / "bw_municipalities.json").write_text(
        json.dumps(
            {
                "source": VG250_URL,
                "layer": "VG250_GEM (SN_L=08, GF=4), representative point inside each area",
                "licence": LICENCE,
                "attribution": ATTRIBUTION,
                "srid": 25832,
                "municipalities": entries,
            },
            ensure_ascii=False,
            indent=0,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        f"Boundary: {round(generalized.area / 1e6, 1)} km², {vertex_count} vertices, "
        f"{len(text) // 1024} KB · municipalities: {len(entries)}"
    )


if __name__ == "__main__":
    main()
