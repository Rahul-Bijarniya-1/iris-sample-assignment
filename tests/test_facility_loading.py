"""
End-to-end facility loading against a real migrated database.

The wiring tests prove the step is reachable. These prove that running it
actually populates iris_core.facilities, which is what the dashboard reads.
"""

import json

import pytest
from sqlalchemy import text

from app.commands.load_facilities_command import LoadFacilitiesCommand
from app.config.paths import DataPaths


FACILITIES = [
    {
        "id": 101,
        "company": "Example Operator",
        "name": "Düsseldorf DC1",
        "address": "Beispielweg 1",
        "city": "Düsseldorf",
        "postal_code": "40210",
        "country": "Germany",
        "latitude": 51.2217,
        "longitude": 6.7762,
        "url": "https://example.com/dc1",
    },
    {
        # No coordinates: the parser is documented to preserve these.
        "id": 102,
        "company": "Example Operator",
        "name": "Köln DC2",
        "address": "Beispielweg 2",
        "city": "Köln",
        "postal_code": "50667",
        "country": "Germany",
        "latitude": None,
        "longitude": None,
        "url": "https://example.com/dc2",
    },
]


@pytest.fixture
def staged_run(tmp_path):
    """
    A DataPaths workspace holding the clean JSON the load step consumes.
    """

    paths = DataPaths(tmp_path)
    paths.create_directories()

    target = paths.datacentermap_processed / "facilities_clean.json"

    target.write_text(
        json.dumps(FACILITIES, ensure_ascii=False),
        encoding="utf-8",
    )

    return paths


def facility_count(session) -> int:
    return session.execute(
        text("select count(*) from iris_core.facilities")
    ).scalar()


@pytest.mark.integration
def test_load_inserts_facilities_into_iris_core(db_session, staged_run):
    """
    Running the load step puts rows in the table the dashboard queries.
    """

    result = LoadFacilitiesCommand(
        db_session,
        paths=staged_run,
    ).execute()

    assert result["inserted"] == 2
    assert facility_count(db_session) == 2


@pytest.mark.integration
def test_load_is_idempotent(db_session, staged_run):
    """
    The loader upserts on source_id, so re-running must not duplicate rows.
    """

    LoadFacilitiesCommand(db_session, paths=staged_run).execute()

    second = LoadFacilitiesCommand(
        db_session,
        paths=staged_run,
    ).execute()

    assert second["inserted"] == 0
    assert second["updated"] == 2
    assert facility_count(db_session) == 2


@pytest.mark.integration
def test_load_writes_postgis_geometry_only_where_coordinates_exist(
    db_session,
    staged_run,
):
    """
    Facilities with coordinates get a POINT geometry; those without are
    still loaded, with a null geometry.
    """

    LoadFacilitiesCommand(db_session, paths=staged_run).execute()

    rows = dict(
        db_session.execute(
            text(
                """
                select source_id, ST_AsText(geometry)
                from iris_core.facilities
                order by source_id
                """
            )
        ).all()
    )

    assert rows[101] == "POINT(6.7762 51.2217)"
    assert rows[102] is None
