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

    def __init__(
        self,
        client=None,
        model: str | None = None,
    ):

        self.client = client or OpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )

        self.model = model or os.getenv(
            "OPENAI_EMBEDDING_MODEL",
            "text-embedding-3-small",
        )

    # =====================================================
    # Public
    # =====================================================

    def embed(
        self,
        text: str,
    ) -> list[float]:

        response = self.client.embeddings.create(
            model=self.model,
            input=text,
        )

        return response.data[0].embedding

    @staticmethod
    def content_hash(
        text: str,
    ) -> str:

        return hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()
