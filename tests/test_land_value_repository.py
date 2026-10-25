"""
LandValueRepository.find_municipality_location(): resolve a place name
against land_values.municipality into a representative point (the
parcel centroid, transformed to 4326) plus an average land value — what
AgenticRagService needs to answer "near <place>" without a selected
facility.
"""

import pytest
from geoalchemy2.elements import WKTElement

from app.database.models.land_value import LandValue
from app.database.repositories.land_value_repository import (
    LandValueRepository,
)


def _polygon(min_e: float, min_n: float, size: float = 100.0) -> WKTElement:
    max_e = min_e + size
    max_n = min_n + size

    return WKTElement(
        f"MULTIPOLYGON((("
        f"{min_e} {min_n}, {max_e} {min_n}, "
        f"{max_e} {max_n}, {min_e} {max_n}, {min_e} {min_n}"
        f")))",
        srid=25832,
    )


@pytest.mark.integration
def test_resolves_a_municipality_to_a_centroid_and_average_value(
    db_session,
):
    db_session.add_all(
        [
            LandValue(
                country_code="DE",
                municipality="Bottrop",
                district="Bottrop",
                postal_code="46236",
                land_value_eur_m2=100.0,
                geometry=_polygon(341000, 5706000),
            ),
            LandValue(
                country_code="DE",
                municipality="Bottrop",
                district="Bottrop",
                postal_code="46236",
                land_value_eur_m2=200.0,
                geometry=_polygon(341200, 5706200),
            ),
            LandValue(
                country_code="DE",
                municipality="Essen",
                district="Essen",
                postal_code="45127",
                land_value_eur_m2=500.0,
                geometry=_polygon(355000, 5700000),
            ),
        ]
    )
    db_session.commit()

    repository = LandValueRepository(db_session)

    result = repository.find_municipality_location("Bottrop")

    assert result is not None
    assert result["municipality"] == "Bottrop"
    assert result["parcel_count"] == 2
    assert result["avg_land_value_eur_m2"] == 150.0
    # Bottrop is roughly 51.5N, 6.9E — a loose sanity bound, not an exact
    # fixture value, since the centroid math itself is what's tested.
    assert 51.0 < result["latitude"] < 52.0
    assert 6.0 < result["longitude"] < 7.5


@pytest.mark.integration
def test_matches_case_insensitively(db_session):
    db_session.add(
        LandValue(
            country_code="DE",
            municipality="Bottrop",
            land_value_eur_m2=100.0,
            geometry=_polygon(341000, 5706000),
        )
    )
    db_session.commit()

    repository = LandValueRepository(db_session)

    assert repository.find_municipality_location("bottrop") is not None
    assert repository.find_municipality_location("BOTTROP") is not None


@pytest.mark.integration
def test_returns_none_for_an_unknown_municipality(db_session):
    repository = LandValueRepository(db_session)

    assert repository.find_municipality_location("Nowhereville") is None
