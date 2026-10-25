from __future__ import annotations

import json

import geopandas as gpd
import pandas as pd

from app.config.paths import DataPaths


class EntityMatcher:
    """
    Matches news entities against known data center
    facilities.

    Input:

        <run>/processed/enriched/facilities_site.geojson
        <run>/processed/news/news_entities.json

    Output:

        <run>/processed/news/matched_news.json

    DataPaths controls the workspace so each pipeline
    execution remains isolated.
    """

    def __init__(
        self,
        paths: DataPaths | None = None,
    ):

        self.paths = paths or DataPaths()

        # -------------------------------------------------
        # Input
        # -------------------------------------------------

        self.facilities_file = (
            self.paths.enriched
            / "facilities_site.geojson"
        )

        self.news_file = (
            self.paths.news_processed
            / "news_entities.json"
        )

        # -------------------------------------------------
        # Output
        # -------------------------------------------------

        self.output_dir = (
            self.paths.news_processed
        )

        self.output_file = (
            self.output_dir
            / "matched_news.json"
        )

        # -------------------------------------------------
        # Data
        # -------------------------------------------------

        self.facilities: (
            gpd.GeoDataFrame | None
        ) = None

        self.news: list[dict] = []

    # =====================================================
    # MAIN
    # =====================================================

    def match(self):

        self.load()

        matches = self.match_company()

        self.save(matches)

        return matches

    # =====================================================
    # LOAD
    # =====================================================

    def load(self):

        print("--------------------------------")
        print(
            "Loading facilities..."
        )

        self.facilities = (
            self._read_geojson(
                self.facilities_file
            )
        )

        print(
            f"Facilities : "
            f"{len(self.facilities)}"
        )

        print("--------------------------------")
        print(
            "Loading news entities..."
        )

        if not self.news_file.exists():

            raise FileNotFoundError(
                "News entities file not found: "
                f"{self.news_file}"
            )

        with self.news_file.open(
            "r",
            encoding="utf-8",
        ) as file:

            self.news = json.load(file)

        if not isinstance(
            self.news,
            list,
        ):

            raise ValueError(
                "Expected news_entities.json "
                "to contain a list."
            )

        print(
            f"News Articles : "
            f"{len(self.news)}"
        )

    # =====================================================
    # GEOJSON READER
    # =====================================================

    def _read_geojson(
        self,
        file_path,
    ) -> gpd.GeoDataFrame:

        if not file_path.exists():

            raise FileNotFoundError(
                "GeoJSON file not found: "
                f"{file_path}"
            )

        with file_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        if data.get(
            "type"
        ) != "FeatureCollection":

            raise ValueError(
                "Expected GeoJSON "
                "FeatureCollection: "
                f"{file_path}"
            )

        features = data.get(
            "features",
            [],
        )

        return (
            gpd.GeoDataFrame.from_features(
                features,
                crs="EPSG:25832",
            )
        )

    # =====================================================
    # COMPANY MATCHING
    # =====================================================

    def match_company(self):

        if self.facilities is None:

            raise RuntimeError(
                "Facilities have not "
                "been loaded."
            )

        print("--------------------------------")
        print(
            "Matching companies..."
        )

        matches = []

        # -------------------------------------------------
        # Prepare company names once.
        # -------------------------------------------------

        facility_companies = (
            self.facilities[
                "company"
            ]
            .fillna("")
            .astype(str)
            .str.lower()
        )

        for article in self.news:

            company = (
                article.get(
                    "company"
                )
                or ""
            ).strip().lower()

            if not company:
                continue

            facility_matches = (
                self.facilities[
                    facility_companies.str.contains(
                        company,
                        regex=False,
                    )
                ]
            )

            for _, facility in (
                facility_matches.iterrows()
            ):

                matches.append(
                    {
                        "article_id": (
                            article.get(
                                "article_id"
                            )
                        ),

                        "article_url": (
                            article.get(
                                "article_url"
                            )
                        ),

                        "company": (
                            facility[
                                "company"
                            ]
                        ),

                        "facility_name": (
                            facility[
                                "name"
                            ]
                        ),

                        "city": self._clean_city(
                            facility.get(
                                "city"
                            )
                        ),

                        "match_type": (
                            "company"
                        ),

                        "match_score": 1.0,
                    }
                )

        print(
            f"Matches Found : "
            f"{len(matches)}"
        )

        return matches

    # =====================================================
    # CITY
    # =====================================================

    @staticmethod
    def _clean_city(
        city,
    ):
        """
        A facility row with no `city` property carries a pandas NaN float
        there instead of a missing key. json.dump writes that as the bare
        token `NaN`, which loads back as a float and lands in the VARCHAR
        `city` column as the literal string "NaN".
        """

        if pd.isna(city):

            return None

        return city

    # =====================================================
    # SAVE
    # =====================================================

    def save(
        self,
        matches: list[dict],
    ):

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.output_file.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                matches,
                file,
                indent=4,
                ensure_ascii=False,
            )

        print("--------------------------------")
        print(
            "Matched news saved"
        )

        print(
            self.output_file
        )