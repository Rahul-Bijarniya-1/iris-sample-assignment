"""
News Retrieval Service

Semantic search over embedded news articles via pgvector cosine
distance. Degrades to an empty result on any failure — missing
OPENAI_API_KEY, no embeddings yet, or no pgvector extension — so the
dashboard is never worse than the pre-RAG keyword path.

Author:
NRW BI Platform
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.news_article import NewsArticle
from app.services.embedding_service import EmbeddingService


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

        except Exception:

            # Any failure here — a bad API key, an unreachable OpenAI
            # endpoint, the vector extension missing on this database —
            # must degrade to "nothing found", never raise.
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
