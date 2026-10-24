"""
MaStR records must keep their country code through parsing.

iris_core.energy_assets.country_code is String(2), NOT NULL, and every record
in processed/mastr/power_generation.json carries a country_code. If the parser
drops it, the whole load aborts with a NotNullViolation and the table stays
empty.
"""

import json

from app.parsers.mastr_parser import MaStRParser


def _write_dataset(tmp_path, records):

    file_path = tmp_path / "power_generation.json"

    file_path.write_text(
        json.dumps(records),
        encoding="utf-8",
    )

    return file_path


def test_parsed_asset_carries_the_country_code(tmp_path):
    """
    The country_code in the source record must reach the EnergyAsset.
    """

    file_path = _write_dataset(
        tmp_path,
        [
            {
                "mastr_number": "SEE952502216062",
                "country_code": "DE",
                "name": "Balkonkraftwerk",
            }
        ],
    )

    assets = MaStRParser().parse(file_path)

    assert assets[0].country_code == "DE"
