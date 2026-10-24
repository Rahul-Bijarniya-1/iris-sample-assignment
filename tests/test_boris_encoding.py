"""
BORIS place names must survive reading.

The NRW BORIS shapefile ships a .cpg sidecar declaring UTF-8, but the reader
hardcoded cp1252. Every German umlaut was mangled on the way in: "Koeln"
spelled with an umlaut came back as mojibake, affecting roughly a quarter of
the 61,916 land value polygons.

pyshp warns about the mismatch rather than failing, so the corruption only
shows up once the rows are in the database.
"""

import shapefile

from app.transformers.boris_transformer import BorisTransformer


MUNICIPALITY = "Köln"
DISTRICT = "Lützowstraße"


def _write_utf8_shapefile(directory):
    """
    A minimal BORIS-shaped dataset written as UTF-8, with the .cpg sidecar
    the real NRW download ships.
    """

    path = directory / "BRW_2026.shp"

    writer = shapefile.Writer(
        str(directory / "BRW_2026"),
        shapeType=shapefile.POLYGON,
        encoding="utf-8",
    )

    writer.field("BRW", "C")
    writer.field("GENA", "C")
    writer.field("ORTST", "C")
    writer.field("PLZ", "C")

    writer.record("250", MUNICIPALITY, DISTRICT, "50667")

    writer.poly(
        [
            [
                [0.0, 0.0],
                [0.0, 1.0],
                [1.0, 1.0],
                [1.0, 0.0],
                [0.0, 0.0],
            ]
        ]
    )

    writer.close()

    (directory / "BRW_2026.cpg").write_text(
        "UTF-8",
        encoding="ascii",
    )

    return path


def test_umlauts_survive_reading_the_shapefile(tmp_path):
    """
    A municipality written as UTF-8 must read back unchanged.
    """

    shapefile_path = _write_utf8_shapefile(tmp_path)

    transformer = BorisTransformer()
    transformer.input_file = shapefile_path

    gdf = transformer._load_dataset()

    assert gdf.iloc[0]["GENA"] == MUNICIPALITY
    assert gdf.iloc[0]["ORTST"] == DISTRICT
