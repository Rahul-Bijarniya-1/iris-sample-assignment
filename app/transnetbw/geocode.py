"""
Place names → EPSG:25832 points, or an explicit reason why not.

Places come from structure, never from scanning free text for any known
name (Baden-Württemberg has municipalities called Au, Berg, Lauf and Wald):

  - project titles are split on their separators — "Weinheim – Karlsruhe",
    "Hochrhein | Herbertingen – Waldshut-Tiengen", "Stalldorf / Main-Tauber"
    — after stripping type words ("Umspannwerk", "Netzknoten", "Punkt");
  - press releases contribute explicit station mentions ("Umspannwerk
    Beuren") from title, subheads and lead; failing that, the linked
    project's location.

A name resolves substation first (OSM; a TransnetBW-operated station wins a
tie), then settlement (OSM place), then municipality (BKG). A tie that
cannot be broken is reported as ambiguous, never guessed. Every point is
validated and tested against the BKG boundary of Baden-Württemberg.

Outcomes: resolved · ambiguous (lines, regions, ties; endpoints kept) ·
unresolved · invalid_coordinates · outside_bw (the record is excluded).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from shapely import wkt
from shapely.geometry import Point
from shapely.prepared import prep

from app.transnetbw.normalize import clean_text


DATA_DIR = Path(__file__).parent / "data"

# Plausible EPSG:25832 range for southern Germany and its neighbours; a
# gazetteer point outside it is corrupt, not merely far away.
EASTING_RANGE = (100_000, 900_000)

NORTHING_RANGE = (5_000_000, 6_200_000)


@dataclass(frozen=True)
class GazetteerEntry:

    name: str

    kind: str

    x: float

    y: float

    source: str

    operator: str | None = None

    names: tuple[str, ...] = ()

    @property
    def all_names(self) -> tuple[str, ...]:
        return self.names or (self.name,)

    @property
    def precision(self) -> str:
        return "substation" if self.kind == "substation" else "municipality"


@dataclass(frozen=True)
class Resolution:

    entry: GazetteerEntry | None

    candidates: int

    note: str | None


@dataclass
class Location:

    status: str

    text: str | None = None

    precision: str | None = None

    method: str | None = None

    x: float | None = None

    y: float | None = None

    source: str | None = None

    endpoints: list[dict] = field(default_factory=list)

    regions: list[str] = field(default_factory=list)

    flags: list[str] = field(default_factory=list)

    note: str | None = None

    @property
    def excluded(self) -> bool:
        return self.status == "outside_bw"


@dataclass(frozen=True)
class TitlePlaces:

    places: list[str]

    regions: list[str]

    outside: list[str]


# =========================================================
# GAZETTEER
# =========================================================


def _lower(text: str) -> str:
    # lower(), not casefold(): casefold() turns ß into ss.
    return (clean_text(text) or "").lower()


def _mentions(name: str, place: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(_lower(place))}(?!\w)", _lower(name)) is not None


def _is_transnetbw(operator: str | None) -> bool:
    return bool(operator) and "transnet" in operator.lower().replace(" ", "")


def valid_point(x: float | None, y: float | None) -> bool:

    if x is None or y is None:
        return False

    if not (math.isfinite(x) and math.isfinite(y)):
        return False

    return (
        EASTING_RANGE[0] <= x <= EASTING_RANGE[1]
        and NORTHING_RANGE[0] <= y <= NORTHING_RANGE[1]
    )


class Gazetteer:

    def __init__(
        self,
        substations: list[GazetteerEntry],
        settlements: list[GazetteerEntry],
        municipalities: list[GazetteerEntry],
        regions: list[str],
        outside: dict[str, str],
        not_places: list[str],
        boundary,
    ):
        self.substations = substations

        self.settlements = settlements

        self.municipalities = municipalities

        self.regions = regions

        self.outside = outside

        self.not_places = not_places

        self.boundary = boundary

        self._prepared = prep(boundary)

    @classmethod
    def load(cls, data_dir: Path = DATA_DIR) -> "Gazetteer":

        osm = json.loads((data_dir / "osm_gazetteer.json").read_text(encoding="utf-8"))

        bkg = json.loads((data_dir / "bw_municipalities.json").read_text(encoding="utf-8"))

        vocabulary = json.loads((data_dir / "place_aliases.json").read_text(encoding="utf-8"))

        boundary = wkt.loads((data_dir / "de_bw_boundary_25832.wkt").read_text(encoding="utf-8"))

        substations = [
            GazetteerEntry(
                name=entry["names"][0],
                kind="substation",
                x=entry["x"],
                y=entry["y"],
                source=f"osm:{entry['osm']}",
                operator=entry.get("operator"),
                names=tuple(entry["names"]),
            )
            for entry in osm["substations"]
            if entry["names"]
        ]

        settlements = [
            GazetteerEntry(
                name=entry["names"][0],
                kind="settlement",
                x=entry["x"],
                y=entry["y"],
                source=f"osm:{entry['osm']}",
            )
            for entry in osm["places"]
            if entry["names"]
        ]

        municipalities = [
            GazetteerEntry(
                name=entry["name"],
                kind="municipality",
                x=entry["x"],
                y=entry["y"],
                source=f"bkg:{entry['ags']}",
            )
            for entry in bkg["municipalities"]
        ]

        return cls(
            substations=substations,
            settlements=settlements,
            municipalities=municipalities,
            regions=vocabulary["regions"],
            outside=vocabulary["outside"],
            not_places=vocabulary["not_places"],
            boundary=boundary,
        )

    def contains(self, x: float, y: float) -> bool:
        return self._prepared.contains(Point(x, y))

    def resolve(self, place: str, substations_only: bool = False) -> Resolution:

        stations = [
            entry
            for entry in self.substations
            if any(_mentions(name, place) for name in entry.all_names)
        ]

        if len(stations) > 1:

            operated = [entry for entry in stations if _is_transnetbw(entry.operator)]

            if len(operated) == 1:
                stations = operated

        if len(stations) == 1:
            return Resolution(stations[0], 1, None)

        station_note = f"{len(stations)} substations named {place}" if stations else None

        if substations_only:
            return Resolution(None, len(stations), station_note or f"no substation named {place}")

        for kind, entries in (("settlements", self.settlements), ("municipalities", self.municipalities)):

            named = [entry for entry in entries if _lower(entry.name) == _lower(place)]

            if len(named) == 1:
                return Resolution(named[0], 1, station_note)

            if len(named) > 1:
                return Resolution(None, len(named), f"{len(named)} {kind} named {place}")

        return Resolution(None, 0, station_note or f"no gazetteer entry for {place}")


# =========================================================
# TITLE PLACES
# =========================================================


PARENTHESES = re.compile(r"\s*\([^)]*\)")

CHUNK_SPLIT = re.compile(r"\s*\|\s*")

SEGMENT_SPLIT = re.compile(r"\s*[–—]\s*|\s+-\s+|\s*/\s*")

TYPE_PREFIX = re.compile(
    r"^(?:(?:380|220)-kv-)?(?:netzverstärkung|netzausbau|erweiterung|umbau|neubau|"
    r"umspannwerk(?:s|es)?|uw|netzknoten|schaltanlage|netzbooster|projekte am standort|"
    r"standort|punkt|seiltausch|projekt)\s+",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _default_vocabulary():
    data = json.loads((DATA_DIR / "place_aliases.json").read_text(encoding="utf-8"))
    return TitleVocabulary(data["regions"], data["outside"], data["not_places"])


@dataclass(frozen=True)
class TitleVocabulary:

    regions: list[str]

    outside: dict[str, str]

    not_places: list[str]


def extract_title_places(title: str, vocabulary=None) -> TitlePlaces:

    vocabulary = vocabulary or _default_vocabulary()

    regions = {_lower(name): name for name in vocabulary.regions}

    outside = {_lower(name): name for name in vocabulary.outside}

    not_places = {_lower(name) for name in vocabulary.not_places}

    found = TitlePlaces(places=[], regions=[], outside=[])

    text = PARENTHESES.sub("", clean_text(title) or "")

    for chunk in CHUNK_SPLIT.split(text):

        for segment in SEGMENT_SPLIT.split(chunk):

            segment = segment.strip(" ,.;:")

            while True:

                prefix = TYPE_PREFIX.match(segment)

                if not prefix:
                    break

                segment = segment[prefix.end():]

            key = _lower(segment)

            if not segment or key in not_places:
                continue

            if key in regions:
                found.regions.append(regions[key])

            elif key in outside:
                found.outside.append(outside[key])

            elif segment[0].isupper():
                found.places.append(segment)

    return found


# =========================================================
# GEOCODER
# =========================================================


SUBSTATION_MENTION = re.compile(
    r"(?:Umspannwerk(?:s|es)?|UW|Netzknoten(?:s)?|Schaltanlage|Konverter(?:s)?(?:\s+in)?)"
    r"\s+([A-ZÄÖÜ][\wäöüß]+(?:-[A-ZÄÖÜ][\wäöüß]+)?)"
)


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


class Geocoder:

    def __init__(self, gazetteer: Gazetteer):

        self.gazetteer = gazetteer

        alternatives = "|".join(
            sorted((re.escape(name) for name in gazetteer.outside), key=len, reverse=True)
        )

        self._outside_phrase = re.compile(
            rf"\b(?:in|nach|aus)\s+(?:der\s+|dem\s+)?(?:{alternatives})\b"
        )

    # =====================================================
    # SINGLE POINTS
    # =====================================================

    def _point(self, place: str, resolution: Resolution, text: str | None, note: str | None = None) -> Location:

        entry = resolution.entry

        if entry is None:
            return Location(
                status="ambiguous" if resolution.candidates > 1 else "unresolved",
                text=text,
                note=resolution.note,
            )

        if not valid_point(entry.x, entry.y):
            return Location(
                status="invalid_coordinates",
                text=text,
                source=entry.source,
                note=f"gazetteer point for {place} is not a valid EPSG:25832 coordinate ({entry.x}, {entry.y})",
            )

        if not self.gazetteer.contains(entry.x, entry.y):
            return Location(
                status="outside_bw",
                text=text,
                source=entry.source,
                note=f"{place} ({entry.name}) lies outside Baden-Württemberg",
            )

        return Location(
            status="resolved",
            text=text,
            precision=entry.precision,
            method="gazetteer",
            x=_round(entry.x),
            y=_round(entry.y),
            source=entry.source,
            note=note or resolution.note,
        )

    def _endpoint(self, place: str, substations_only: bool = False) -> dict:

        resolution = self.gazetteer.resolve(place, substations_only=substations_only)

        entry = resolution.entry

        if entry is None or not valid_point(entry.x, entry.y):
            return {
                "name": place,
                "x": None,
                "y": None,
                "in_bw": None,
                "precision": None,
                "source": entry.source if entry else None,
                "status": "invalid_coordinates" if entry else ("ambiguous" if resolution.candidates > 1 else "unresolved"),
                "note": resolution.note,
            }

        return {
            "name": place,
            "x": _round(entry.x),
            "y": _round(entry.y),
            "in_bw": self.gazetteer.contains(entry.x, entry.y),
            "precision": entry.precision,
            "source": entry.source,
            "status": "resolved",
            "note": resolution.note,
        }

    def _outside_endpoint(self, name: str) -> dict:
        return {
            "name": name,
            "x": None,
            "y": None,
            "in_bw": False,
            "precision": None,
            "source": f"curated:{self.gazetteer.outside.get(name, 'outside')}",
            "status": "outside",
            "note": None,
        }

    def _multi(self, endpoints: list[dict], regions: list[str], text: str | None, note: str) -> Location:

        known = [endpoint["in_bw"] for endpoint in endpoints if endpoint["in_bw"] is not None]

        if not regions and known and not any(known):
            return Location(
                status="outside_bw",
                text=text,
                endpoints=endpoints,
                note="every named place lies outside Baden-Württemberg",
            )

        flags = []

        if any(flag is False for flag in known) and (any(known) or regions):
            flags.append("cross_border")

        return Location(
            status="ambiguous",
            text=text,
            endpoints=endpoints,
            regions=list(regions),
            flags=flags,
            note=note,
        )

    # =====================================================
    # PROJECTS
    # =====================================================

    def locate_project(self, title: str) -> Location:

        found = extract_title_places(title, self.gazetteer)

        text = ", ".join(found.places + found.regions + found.outside) or None

        if not (found.places or found.regions or found.outside):
            return Location(status="unresolved", note="no place named in the title")

        if len(found.places) == 1 and not found.regions and not found.outside:
            place = found.places[0]
            return self._point(place, self.gazetteer.resolve(place), text)

        endpoints = [self._endpoint(place) for place in found.places]

        endpoints += [self._outside_endpoint(name) for name in found.outside]

        return self._multi(
            endpoints,
            found.regions,
            text,
            "line or area project: no single representative point",
        )

    # =====================================================
    # PRESS RELEASES
    # =====================================================

    def locate_press(
        self,
        title: str,
        subheads: list[str],
        lead: str | None,
        project_location: Location | None = None,
    ) -> Location:

        mentions = []

        for text in (title, *subheads, lead):

            for match in SUBSTATION_MENTION.finditer(clean_text(text) or ""):

                if match.group(1) not in mentions:
                    mentions.append(match.group(1))

        endpoints = [self._endpoint(name, substations_only=True) for name in mentions]

        resolved = [endpoint for endpoint in endpoints if endpoint["status"] == "resolved"]

        if self._outside_phrase.search(clean_text(title) or "") and not any(
            endpoint["in_bw"] for endpoint in resolved
        ):
            return Location(
                status="outside_bw",
                text=", ".join(mentions) or None,
                endpoints=endpoints,
                note="the title places the release outside Baden-Württemberg",
            )

        if len(resolved) == 1:
            place = resolved[0]["name"]
            return self._point(place, self.gazetteer.resolve(place, substations_only=True), place)

        if len(resolved) > 1:
            return self._multi(
                resolved,
                [],
                ", ".join(endpoint["name"] for endpoint in resolved),
                "several stations named: no single representative point",
            )

        if project_location is not None and project_location.status == "resolved":
            return Location(
                status="resolved",
                text=project_location.text,
                precision=project_location.precision,
                method="via_project",
                x=project_location.x,
                y=project_location.y,
                source=project_location.source,
                note="location of the linked project",
            )

        if project_location is not None and project_location.status == "ambiguous":
            return Location(
                status="ambiguous",
                text=project_location.text,
                endpoints=list(project_location.endpoints),
                regions=list(project_location.regions),
                flags=list(project_location.flags),
                note="linked project has no single representative point",
            )

        return Location(status="unresolved", note="no station named in title, subheads or lead, and no linked project")
