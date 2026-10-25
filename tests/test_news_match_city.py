"""
A missing `city` on a matched facility must become None, not a literal
"NaN" string.

EntityMatcher.match_company() builds facility_matches by filtering a
GeoDataFrame. The `.fillna("")` on the `company` column covers only that
series — a facility with no `city` property still carries a pandas NaN
float there, which `facility.get("city")` returns verbatim. json.dump then
writes it as the bare token `NaN`, and loading that back into a VARCHAR
column stores the literal string "NaN".
"""

import math

import geopandas as gpd

from app.news.entity_matcher import EntityMatcher


def test_missing_city_becomes_none_not_nan():
    facilities = gpd.GeoDataFrame(
        [
            {
                "company": "SAP SE",
                "name": "SAP WDF51",
                # no "city" key for this row — pandas fills it with NaN
                # because the other row below does have the column.
            },
            {
                "company": "Other Co",
                "name": "Other Facility",
                "city": "Essen",
            },
        ]
    )

    matcher = EntityMatcher()
    matcher.facilities = facilities
    matcher.news = [
        {
            "article_id": "a1",
            "article_url": "https://news.invalid/a1/",
            "company": "SAP SE",
        }
    ]

    matches = matcher.match_company()

    assert len(matches) == 1
    city = matches[0]["city"]

    assert city is None, f"expected None, got {city!r}"
    assert not (isinstance(city, float) and math.isnan(city))


def test_missing_facility_name_becomes_none_not_nan():
    facilities = gpd.GeoDataFrame(
        [
            {
                "company": "SAP SE",
                # no "name" key; pandas fills it from the other row
                # with NaN.
                "city": "Walldorf",
            },
            {
                "company": "Other Co",
                "name": "Other Facility",
                "city": "Essen",
            },
        ]
    )

    matcher = EntityMatcher()
    matcher.facilities = facilities
    matcher.news = [
        {
            "article_id": "a1",
            "article_url": "https://news.invalid/a1/",
            "company": "SAP SE",
        }
    ]

    matches = matcher.match_company()

    assert len(matches) == 1
    facility_name = matches[0]["facility_name"]

    assert facility_name is None
    assert not (
        isinstance(facility_name, float) and math.isnan(facility_name)
    )


def test_missing_article_company_is_ignored_not_stringified():
    matcher = EntityMatcher()
    matcher.facilities = gpd.GeoDataFrame(
        [
            {
                "company": "SAP SE",
                "name": "SAP WDF51",
                "city": "Walldorf",
            }
        ]
    )
    matcher.news = [
        {
            "article_id": "a1",
            "article_url": "https://news.invalid/a1/",
            "company": float("nan"),
        }
    ]

    assert matcher.match_company() == []
