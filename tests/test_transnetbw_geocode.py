"""
Geocoding turns place names into EPSG:25832 points — or says plainly why
it cannot. The brief requires that ambiguous and unresolved locations be
documented and that invalid coordinates are never accepted silently.

These tests use the committed reference data (OSM substations and
settlements, BKG municipalities and the BKG boundary of Baden-Württemberg),
so they also guard that data. Reference coordinates were computed
independently with PostGIS ST_Transform.
"""

import math

import pytest

from app.transnetbw.geocode import Gazetteer, GazetteerEntry, Geocoder, extract_title_places


@pytest.fixture(scope="module")
def geocoder():
    return Geocoder(Gazetteer.load())


# =========================================================
# TITLE PLACES
# =========================================================


@pytest.mark.parametrize(
    "title, places, regions, outside",
    [
        ("Umspannwerk Pulverdingen", ["Pulverdingen"], [], []),
        ("Projekte am Standort Neckarwestheim", ["Neckarwestheim"], [], []),
        ("Birkenfeld – Punkt Ötisheim", ["Birkenfeld", "Ötisheim"], [], []),
        ("Reicheneck–Rommelsbach", ["Reicheneck", "Rommelsbach"], [], []),
        ("Hochrhein | Herbertingen – Waldshut-Tiengen", ["Herbertingen", "Waldshut-Tiengen"], ["Hochrhein"], []),
        ("Eichstetten – Bundesgrenze Frankreich", ["Eichstetten"], [], ["Bundesgrenze Frankreich"]),
        ("Stalldorf / Main-Tauber", ["Stalldorf"], ["Main-Tauber"], []),
        ("Netzverstärkung Badische Rheinschiene", [], ["Badische Rheinschiene"], []),
        ("Seiltausch Höllental (LA5120)", ["Höllental"], [], []),
        ("SuedLink", [], [], []),
    ],
)
def test_places_are_read_from_the_title_structure(title, places, regions, outside):
    found = extract_title_places(title)

    assert found.places == places
    assert found.regions == regions
    assert found.outside == outside


# =========================================================
# PROJECTS
# =========================================================


def test_a_substation_project_resolves_to_the_substation_point(geocoder):
    location = geocoder.locate_project("Umspannwerk Pulverdingen")

    assert location.status == "resolved"
    assert location.precision == "substation"
    assert location.method == "gazetteer"
    # PostGIS ST_Transform of the OSM point (9.045515, 48.902937).
    assert math.dist((location.x, location.y), (503_335.5, 5_416_666.8)) < 1.0
    assert location.source.startswith("osm:way/")


def test_the_transnetbw_station_wins_among_same_named_substations(geocoder):
    """
    Neckarwestheim has four transmission-level stations in OSM (two of DB
    Energie, one of the power plant, one of TransnetBW).
    """

    location = geocoder.locate_project("Projekte am Standort Neckarwestheim")

    assert location.status == "resolved"
    assert location.precision == "substation"
    assert location.source == "osm:way/41334805"


def test_substations_near_the_swiss_border_are_inside_bw(geocoder):
    for title in ("Umspannwerk Schwörstadt", "Netzknoten Kühmoos"):
        location = geocoder.locate_project(title)

        assert location.status == "resolved", title


def test_a_project_whose_only_place_is_outside_bw_is_excluded(geocoder):
    """
    Umspannwerk Stalldorf is a TransnetBW project, but the substation lies
    in Bavaria (Riedenheim, Landkreis Würzburg).
    """

    location = geocoder.locate_project("Umspannwerk Stalldorf")

    assert location.status == "outside_bw"
    assert location.excluded


def test_a_line_project_is_ambiguous_and_keeps_its_endpoints(geocoder):
    location = geocoder.locate_project("Weinheim – Karlsruhe")

    assert location.status == "ambiguous"
    assert location.x is None and location.y is None

    endpoints = {endpoint["name"]: endpoint for endpoint in location.endpoints}

    assert endpoints["Weinheim"]["precision"] == "substation"
    assert endpoints["Weinheim"]["in_bw"] is True
    # Two TransnetBW substations carry "Karlsruhe" (Daxlanden, Ost); the
    # endpoint falls back to the municipality instead of guessing one.
    assert endpoints["Karlsruhe"]["precision"] == "municipality"
    assert endpoints["Karlsruhe"]["in_bw"] is True


def test_a_cross_border_line_is_kept_and_flagged(geocoder):
    location = geocoder.locate_project("Grafenrheinfeld – Kupferzell – Großgartach")

    assert location.status == "ambiguous"
    assert "cross_border" in location.flags

    in_bw = {endpoint["name"]: endpoint["in_bw"] for endpoint in location.endpoints}

    assert in_bw == {"Grafenrheinfeld": False, "Kupferzell": True, "Großgartach": True}


def test_a_border_marker_counts_as_an_endpoint_outside_bw(geocoder):
    location = geocoder.locate_project("Eichstetten – Bundesgrenze Frankreich")

    assert location.status == "ambiguous"
    assert "cross_border" in location.flags
    assert {"name": "Bundesgrenze Frankreich", "in_bw": False} in [
        {key: endpoint[key] for key in ("name", "in_bw")} for endpoint in location.endpoints
    ]


def test_a_region_is_ambiguous(geocoder):
    location = geocoder.locate_project("Mittlerer Neckarraum")

    assert location.status == "ambiguous"
    assert location.regions == ["Mittlerer Neckarraum"]


def test_a_project_named_without_a_place_is_unresolved(geocoder):
    location = geocoder.locate_project("SuedLink")

    assert location.status == "unresolved"
    assert location.note


def test_an_unknown_place_is_unresolved_not_guessed(geocoder):
    location = geocoder.locate_project("Umspannwerk Nirgendwohausen")

    assert location.status == "unresolved"
    assert "Nirgendwohausen" in location.note


def test_a_municipality_name_that_exists_twice_is_ambiguous(geocoder):
    """
    Baden-Württemberg has two municipalities called Altdorf.
    """

    location = geocoder.locate_project("Umspannwerk Altdorf")

    assert location.status == "ambiguous"
    assert "2" in location.note


def test_a_settlement_without_a_substation_resolves_at_settlement_level(geocoder):
    location = geocoder.locate_project("Umspannwerk Ötisheim")

    assert location.status == "resolved"
    assert location.precision == "municipality"


# =========================================================
# INVALID AND OUT-OF-AREA COORDINATES
# =========================================================


def tiny_gazetteer(entry: GazetteerEntry) -> Gazetteer:
    real = Gazetteer.load()
    return Gazetteer(
        substations=[entry],
        settlements=[],
        municipalities=[],
        regions=real.regions,
        outside=real.outside,
        not_places=real.not_places,
        boundary=real.boundary,
    )


@pytest.mark.parametrize(
    "x, y",
    [(0.0, 0.0), (float("nan"), 5_400_000.0), (503_335.5, float("inf"))],
    ids=["null-island", "nan", "infinite"],
)
def test_invalid_coordinates_are_rejected_with_a_reason(x, y):
    entry = GazetteerEntry(name="Umspannwerk Kaputt", kind="substation", x=x, y=y, source="test", operator="TransnetBW")

    location = Geocoder(tiny_gazetteer(entry)).locate_project("Umspannwerk Kaputt")

    assert location.status == "invalid_coordinates"
    assert location.x is None and location.y is None
    assert location.note


def test_a_point_outside_the_boundary_but_inside_its_box_is_outside_bw():
    """
    Strasbourg lies inside BW's bounding box; only the polygon catches it.
    """

    # Strasbourg Cathedral (7.7509, 48.5818), via PostGIS ST_Transform.
    entry = GazetteerEntry(
        name="Umspannwerk Strasbourg",
        kind="substation",
        x=407_876.1,
        y=5_381_721.3,
        source="test",
        operator="TransnetBW",
    )

    location = Geocoder(tiny_gazetteer(entry)).locate_project("Umspannwerk Strasbourg")

    assert location.status == "outside_bw"


# =========================================================
# PRESS RELEASES
# =========================================================


def test_a_substation_named_in_a_press_title_resolves(geocoder):
    location = geocoder.locate_press(
        "Spatenstich am Umspannwerk Beuren: TransnetBW startet Bauarbeiten für das Projekt Hochrhein",
        [],
        "Mit einem symbolischen Spatenstich setzt die Übertragungsnetzbetreiberin TransnetBW den Startpunkt.",
    )

    # 13 settlements are called Beuren, but one transmission substation is.
    assert location.status == "resolved"
    assert location.precision == "substation"
    assert location.source == "osm:way/102743264"


def test_a_press_release_about_another_state_is_excluded(geocoder):
    location = geocoder.locate_press("Baustart für SuedLink in Bayern – Netzausbau schreitet voran", [], None)

    assert location.status == "outside_bw"


def test_a_press_release_without_places_inherits_its_project_point(geocoder):
    project = geocoder.locate_project("Netzbooster Kupferzell")

    location = geocoder.locate_press("Feierlicher Baubeginn des Netzboosters", [], None, project_location=project)

    assert location.status == "resolved"
    assert location.method == "via_project"
    assert (location.x, location.y) == (project.x, project.y)


def test_a_dateline_place_is_not_a_project_location(geocoder):
    """
    The lead passed in has its dateline removed already; the HQ city of the
    issuing office must not appear as a location.
    """

    location = geocoder.locate_press(
        "Kleinstflexibilitäten als Beitrag für das Netzengpassmanagement",
        ["Flexibilitätspotenziale von Kleinverbrauchern und Speichern nutzen"],
        "Der beginnende Markthochlauf von Wärmepumpen und Elektromobilität stellt eine Herausforderung dar.",
    )

    assert location.status == "unresolved"
