"""
Embed News Command

Translates and embeds every news article, resumably: a content hash of
the source (German title + summary + the translation model's name +
the embedding model's name) decides whether a row needs re-work at
all, so an unchanged article makes no API call of either kind, an
edited summary or a deliberate translation/embedding-model change
triggers a fresh translate-and-embed, and a row left partially
embedded by a prior failed run is picked back up rather than treated
as done.

Hashing the source rather than the translated output is deliberate:
measured against the live API, gpt-4.1-mini does not reproduce
byte-identical English text run to run even at temperature=0, which
would make "unchanged input" look like "changed output" on almost
every re-run.

Commits every BATCH_SIZE rows so a later failure does not lose earlier
progress in the same run.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, undefer

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
            select(NewsArticle).options(
                undefer(NewsArticle.embedding)
            )
        ).all()

        embedded = 0
        skipped = 0
        failed = 0
        work_since_commit = 0

        for article in articles:

            source_signature = (
                f"{article.title}\n"
                f"{article.summary or ''}\n"
                f"{getattr(self.translation, 'model', '')}\n"
                f"{getattr(self.embedding, 'model', '')}"
            )

            content_hash = self.embedding.content_hash(
                source_signature
            )

            already_done = (
                article.embedding_hash == content_hash
                and article.embedding is not None
            )

            if already_done:

                skipped += 1

                continue

            try:

                # A savepoint contains partial per-article mutations without
                # rolling back successful paid work since the last batch.
                with self.session.begin_nested():

                    translated = self.translation.translate(
                        article.title,
                        article.summary,
                    )

                    article.title_en = translated["title_en"]
                    article.summary_en = translated["summary_en"]

                    embed_text = (
                        f"{translated['title_en']}\n"
                        f"{translated['summary_en'] or ''}"
                    )

                    article.embedding = self.embedding.embed(
                        embed_text
                    )

                    article.embedding_model = getattr(
                        self.embedding, "model", None
                    )

                    translation_succeeded = getattr(
                        translated,
                        "succeeded",
                        True,
                    )
                    article.embedding_hash = (
                        content_hash if translation_succeeded else None
                    )

                    article.embedded_at = datetime.now(
                        timezone.utc
                    )

            except Exception:

                failed += 1
                continue

            embedded += 1
            work_since_commit += 1

            if work_since_commit >= self.BATCH_SIZE:

                self.session.commit()
                work_since_commit = 0

        self.session.commit()

        return {
            "embedded": embedded,
            "skipped": skipped,
            "failed": failed,
        }
