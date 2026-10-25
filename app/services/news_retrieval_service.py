"""
News Retrieval Service

Semantic search over embedded news articles via pgvector cosine
distance. Recoverable failures — a missing API key or unavailable
pgvector database — degrade to an empty result, while an embedding
dimension mismatch remains visible as a configuration defect.

Author:
NRW BI Platform
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.news_article import NewsArticle
from app.database.models.news_signal import NewsSignal
from app.services.embedding_service import (
    EmbeddingDimensionMismatch,
    EmbeddingService,
)


class NewsRetrievalService:

    def __init__(
        self,
        session: Session,
        embedding_service: EmbeddingService | None = None,
    ):

        self.session = session
        self.embedding_service = embedding_service or EmbeddingService()

    # =====================================================
    # Public
    # =====================================================

    def search(
        self,
        query: str,
        k: int = 10,
        filters: dict | None = None,
    ) -> list[dict]:

        try:

            query_vector = self.embedding_service.embed(query)

            distance = NewsArticle.embedding.cosine_distance(
                query_vector
            ).label("distance")

            stmt = (
                select(NewsArticle, distance)
                .where(NewsArticle.embedding.is_not(None))
                .order_by(distance)
                .limit(k)
            )

            if filters and filters.get("language"):

                stmt = stmt.where(
                    NewsArticle.language == filters["language"]
                )

            rows = self.session.execute(stmt).all()

        except EmbeddingDimensionMismatch:

            # A model/column dimension mismatch is a configuration defect,
            # not a temporary retrieval outage, and must remain visible to
            # operators.
            raise

        except Exception:

            # Any failure here — a bad API key, an unreachable OpenAI
            # endpoint, the vector extension missing on this database —
            # must degrade to "nothing found", never raise. A failed SQL
            # statement poisons the transaction until it is rolled back;
            # the keyword fallback reuses this same session.
            self.session.rollback()

            return []

        return [
            self._to_result(article, dist)
            for article, dist in rows
        ]

    # =====================================================
    # Internal
    # =====================================================

    @staticmethod
    def _to_result(
        article: NewsArticle,
        distance: float,
    ) -> dict:

        return {
            "id": article.id,
            "title": article.title_en or article.title,
            "title_de": article.title,
            "summary_en": article.summary_en,
            "summary_de": article.summary,
            "url": article.url,
            "published_at": article.published_at,
            "source": article.source,
            "score": 1.0 - distance,
        }
