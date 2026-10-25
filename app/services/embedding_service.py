"""
Embedding Service

Thin, env-driven wrapper over the OpenAI embeddings API, mirroring
AIRecommendationService's shape.

Author:
NRW BI Platform
"""

from __future__ import annotations

import hashlib

from app.config.openai import LazyOpenAIClient, get_embedding_model


class EmbeddingDimensionMismatch(ValueError):
    """The API vector cannot fit the configured database column."""


class EmbeddingService(LazyOpenAIClient):

    EXPECTED_DIMENSIONS = 1536

    def __init__(
        self,
        client=None,
        model: str | None = None,
    ):

        super().__init__(client)

        self.model = model or get_embedding_model()

    # =====================================================
    # Public
    # =====================================================

    def embed(
        self,
        text: str,
    ) -> list[float]:

        if not isinstance(text, str) or not text.strip():

            raise ValueError("embedding input must be a non-empty string")

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
            raise EmbeddingDimensionMismatch(
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
