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
