"""
Embedding Service

Thin, env-driven wrapper over the OpenAI embeddings API, mirroring
AIRecommendationService's shape.

Author:
NRW BI Platform
"""

from __future__ import annotations

import hashlib
import os

from openai import OpenAI


class EmbeddingService:

    EXPECTED_DIMENSIONS = 1536

    def __init__(
        self,
        client=None,
        model: str | None = None,
    ):

        self._client = client

        self.model = model or os.getenv(
            "OPENAI_EMBEDDING_MODEL",
            "text-embedding-3-small",
        )

    # =====================================================
    # Public
    # =====================================================

    @property
    def client(self):
        """
        Built lazily: constructing OpenAI() with no API key raises
        immediately, and callers like NewsRetrievalService.search()
        rely on that failure happening inside their own try/except
        (missing key -> degrade to []), not at service-construction
        time, before there is anything to catch it.
        """

        if self._client is None:

            self._client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY")
            )

        return self._client

    def embed(
        self,
        text: str,
    ) -> list[float]:

        response = self.client.embeddings.create(
            model=self.model,
            input=text,
        )

        vector = response.data[0].embedding

        if len(vector) != self.EXPECTED_DIMENSIONS:

            # A silent mismatch here would otherwise surface as
            # NewsRetrievalService's blanket except swallowing a
            # cosine_distance() dimension error and returning [] —
            # indistinguishable from "no results", forever.
            raise ValueError(
                f"{self.model} returned a {len(vector)}-dimension "
                f"vector; news_articles.embedding is "
                f"vector({self.EXPECTED_DIMENSIONS})"
            )

        return vector

    @staticmethod
    def content_hash(
        text: str,
    ) -> str:

        return hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()
