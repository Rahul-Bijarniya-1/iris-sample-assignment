from __future__ import annotations

import json

from app.config.paths import DataPaths
from app.extractors.mock_extractor import MockExtractor


class EntityExtractor:
    """
    Extract entities from normalized news.

    Current implementation:
        MockExtractor

    Future implementation:
        OpenAIExtractor

    DataPaths controls the workspace so each pipeline
    execution remains isolated.
    """

    def __init__(
        self,
        paths: DataPaths | None = None,
        extractor=None,
    ):

        self.paths = paths or DataPaths()

        # -------------------------------------------------
        # Input
        # -------------------------------------------------

        self.input_file = (
            self.paths.news_processed
            / "news.json"
        )

        # -------------------------------------------------
        # Output
        # -------------------------------------------------

        self.output_dir = (
            self.paths.news_processed
        )

        self.output_file = (
            self.output_dir
            / "news_entities.json"
        )

        # -------------------------------------------------
        # Entity extractor
        # -------------------------------------------------

        self.extractor = extractor or MockExtractor()

    # =====================================================
    # EXTRACT
    # =====================================================

    def extract(self):

        print("--------------------------------")
        print(
            "Extracting entities..."
        )

        if not self.input_file.exists():

            raise FileNotFoundError(
                "Normalized news file not found: "
                f"{self.input_file}"
            )

        with self.input_file.open(
            "r",
            encoding="utf-8",
        ) as file:

            articles = json.load(file)

        if not isinstance(
            articles,
            list,
        ):

            raise ValueError(
                "Expected normalized news "
                "data to contain a list."
            )

        entities = []

        for article in articles:

            entities.append(
                self.extractor.extract(
                    article
                )
            )

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.output_file.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                entities,
                file,
                indent=4,
                ensure_ascii=False,
            )

        print("--------------------------------")
        print(
            f"Entities Extracted : "
            f"{len(entities)}"
        )

        print(
            self.output_file
        )

        return entities
