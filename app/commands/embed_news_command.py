"""
Embed News Command

Translates and embeds every news article, resumably: a content hash of
the exact embedded (English) text decides whether a row needs re-work,
so an unchanged article is skipped, an edited or re-translated one is
re-embedded, and a row left partially embedded by a prior failed run is
picked back up rather than treated as done.

Commits every BATCH_SIZE rows so a later failure does not lose earlier
progress in the same run.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models.news_article import NewsArticle
from app.services.embedding_service import EmbeddingService
from app.services.translation_service import TranslationService


class EmbedNewsCommand:

    BATCH_SIZE = 10

    def __init__(
        self,
        session: Session,
        translation_service: TranslationService | None = None,
        embedding_service: EmbeddingService | None = None,
    ):

        self.session = session
        self.translation = translation_service or TranslationService()
        self.embedding = embedding_service or EmbeddingService()

    # =====================================================
    # Public
    # =====================================================

    def execute(self) -> dict:

        articles = self.session.scalars(
            select(NewsArticle)
        ).all()

        embedded = 0
        skipped = 0

        for index, article in enumerate(articles, start=1):

            translated = self.translation.translate(
                article.title,
                article.summary,
            )

            embed_text = (
                f"{translated['title_en']}\n"
                f"{translated['summary_en'] or ''}"
            )

            content_hash = self.embedding.content_hash(
                embed_text
            )

            already_done = (
                article.embedding_hash == content_hash
                and article.embedding is not None
            )

            article.title_en = translated["title_en"]
            article.summary_en = translated["summary_en"]

            if already_done:

                skipped += 1

                continue

            article.embedding = self.embedding.embed(
                embed_text
            )

            article.embedding_model = getattr(
                self.embedding, "model", None
            )

            article.embedding_hash = content_hash

            article.embedded_at = datetime.now(
                timezone.utc
            )

            embedded += 1

            if index % self.BATCH_SIZE == 0:

                self.session.commit()

        self.session.commit()

        return {
            "embedded": embedded,
            "skipped": skipped,
        }
