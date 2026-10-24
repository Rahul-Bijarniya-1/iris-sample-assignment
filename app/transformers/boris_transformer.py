from __future__ import annotations

import geopandas as gpd
import shapefile

from shapely.geometry import shape

from app.config.paths import DataPaths


class BorisTransformer:
    """
    Transforms the static BORIS NRW land value shapefile
    into a standardized GeoJSON dataset.

    Input:

        data/raw/boris/BRW_2026.shp

    The complete BORIS shapefile dataset must remain together
    in the same directory:

        BRW_2026.shp
        BRW_2026.dbf
        BRW_2026.shx
        BRW_2026.prj
        BRW_2026.cpg

    Output:

        <run>/processed/boris/land_values.geojson

    BORIS is treated as a static reference dataset.

    The source files are NOT copied into every pipeline run.
    Only the transformed output is stored inside the run.

    The shapefile is read with pyshp instead of
    GeoPandas/Fiona/Pyogrio so the pipeline does not
    require GDAL DLLs on Windows.

    DataPaths controls the output workspace so each
    pipeline execution remains isolated.
    """

    CRS = "EPSG:25832"

    FILENAME = "BRW_2026.shp"

    FALLBACK_ENCODING = "cp1252"

    def __init__(
        self,
        paths: DataPaths | None = None,
    ):

        self.paths = paths or DataPaths()

        # -------------------------------------------------
        # Static BORIS source
        # -------------------------------------------------
        #
        # BORIS is a large static reference dataset.
        #
        # Keep the complete shapefile components in:
        #
        #     data/raw/boris/
        #
        # pyshp will automatically use the accompanying:
        #
        #     .dbf
        #     .shx
        #     .prj
        #     .cpg
        #
        # files when reading the .shp file.
        # -------------------------------------------------

        self.input_file = (
            DataPaths().boris_raw
            / self.FILENAME
        )

        # -------------------------------------------------
        # Run-specific output
        # -------------------------------------------------

        self.output_file = (
            self.paths.boris_processed
            / "land_values.geojson"
        )

    # =====================================================
    # ENCODING
    # =====================================================

    def _resolve_encoding(self) -> str:
        """
        Determine the .dbf text encoding.

        The NRW download ships a .cpg sidecar naming the real encoding, and
        the current export declares UTF-8. Reading it as cp1252 silently
        mangles every umlaut, so the sidecar wins when present.

        Older exports shipped without a .cpg and were cp1252, which is why
        that remains the fallback rather than UTF-8.
        """

        cpg_file = self.input_file.with_suffix(".cpg")

        if cpg_file.exists():

            declared = (
                cpg_file.read_text(
                    encoding="ascii",
                    errors="ignore",
                )
                .strip()
            )

            if declared:
                return declared

        return self.FALLBACK_ENCODING

    # =====================================================
    # TRANSFORM
    # =====================================================

    def transform(self) -> None:
        """
        Execute the BORIS transformation pipeline.
        """

        print(
            "\nLoading BORIS dataset..."
        )

        gdf = self._load_dataset()

        print(
            f"Loaded {len(gdf):,} "
            "land value polygons."
        )

        self._validate_crs(
            gdf
        )

        gdf = self._clean_land_values(
            gdf
        )

        gdf = self._select_columns(
            gdf
        )

        self._save(
            gdf
        )

        print(
            "BORIS transformation "
            "completed successfully."
        )

    # =====================================================
    # LOAD
    # =====================================================

    def _load_dataset(
        self,
    ) -> gpd.GeoDataFrame:
        """
        Load the BORIS shapefile using pyshp.

        The complete static BORIS dataset is expected
        in data/raw/boris/.

        Required files:

            BRW_2026.shp
            BRW_2026.dbf
            BRW_2026.shx
            BRW_2026.prj
            BRW_2026.cpg

        This avoids GeoPandas read_file(), which requires
        Fiona or Pyogrio/GDAL.
        """

        if not self.input_file.exists():

            raise FileNotFoundError(
                "BORIS shapefile not found:\n"
                f"{self.input_file}"
            )

        print(
            "Reading BORIS shapefile:"
        )

        print(
            self.input_file
        )

        reader = shapefile.Reader(
            str(self.input_file),
            encoding=self._resolve_encoding(),
        )

        fields = [
            field[0]
            for field in reader.fields[1:]
        ]

        rows = []

        for record, shp in zip(
            reader.iterRecords(),
            reader.iterShapes(),
        ):

            properties = dict(
                zip(
                    fields,
                    record,
                )
            )

            properties["geometry"] = shape(
                shp.__geo_interface__
            )

            rows.append(
                properties
            )

        reader.close()

        gdf = gpd.GeoDataFrame(
            rows,
            geometry="geometry",
            crs=self.CRS,
        )

        return gdf

    # =====================================================
    # CRS
    # =====================================================

    def _validate_crs(
        self,
        gdf: gpd.GeoDataFrame,
    ) -> None:
        """
        Ensure the dataset uses EPSG:25832.
        """

        expected = self.CRS

        if str(gdf.crs) != expected:

            raise ValueError(
                f"Unexpected CRS: {gdf.crs}. "
                f"Expected {expected}."
            )

    # =====================================================
    # CLEAN
    # =====================================================

    def _clean_land_values(
        self,
        gdf: gpd.GeoDataFrame,
    ) -> gpd.GeoDataFrame:
        """
        Convert German decimal notation to float.

        Examples:

            1,1 -> 1.1
            260 -> 260.0
        """

        if "BRW" not in gdf.columns:

            raise ValueError(
                "BORIS dataset does not contain "
                "the required BRW column."
            )

        gdf["BRW"] = (
            gdf["BRW"]
            .astype(str)
            .str.replace(
                ",",
                ".",
                regex=False,
            )
            .astype(float)
        )

        return gdf

    # =====================================================
    # SELECT COLUMNS
    # =====================================================

    def _select_columns(
        self,
        gdf: gpd.GeoDataFrame,
    ) -> gpd.GeoDataFrame:
        """
        Keep only required columns and rename them.
        """

        required_columns = [
            "BRW",
            "GENA",
            "ORTST",
            "PLZ",
            "geometry",
        ]

        missing = [
            column
            for column in required_columns
            if column not in gdf.columns
        ]

        if missing:

            raise ValueError(
                "BORIS dataset is missing required "
                f"columns: {missing}"
            )

        gdf = gdf[
            required_columns
        ].copy()

        gdf.rename(
            columns={
                "BRW": "land_value_eur_m2",
                "GENA": "municipality",
                "ORTST": "district",
                "PLZ": "postal_code",
            },
            inplace=True,
        )

        return gdf

    # =====================================================
    # SAVE
    # =====================================================

    def _save(
        self,
        gdf: gpd.GeoDataFrame,
    ) -> None:
        """
        Save GeoJSON without GeoPandas to_file().

        This avoids Fiona/Pyogrio/GDAL.
        """

        self.output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        geojson = gdf.to_json(
            ensure_ascii=False,
        )

        self.output_file.write_text(
            geojson,
            encoding="utf-8",
        )

        print(
            "\nSaved: "
            f"{self.output_file}"
        )