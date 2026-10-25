"""
Extract News Signals Command

Runs an extractor (normally OpenAIExtractor) over every news article
and loads the result into news_signals — idempotently: each run
replaces a given article's row rather than duplicating it, so this is
safe to re-run after an extraction-prompt change.

Commits every BATCH_SIZE rows, same pattern as EmbedNewsCommand, so a
failure partway through (one bad model value, a rate limit) does not
discard the paid extractions that already succeeded in that run.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database.models.news_article import NewsArticle
from app.database.models.news_signal import NewsSignal
from app.extractors.openai_extractor import ExtractionFailed, OpenAIExtractor


class ExtractNewsSignalsCommand:

    BATCH_SIZE = 10

    def __init__(
        self,
        session: Session,
        extractor=None,
    ):

        self.session = session
        self.extractor = extractor or OpenAIExtractor()

    def execute(self) -> dict:

        articles = self.session.scalars(
            select(NewsArticle)
        ).all()

        loaded = 0
        failed = 0

        for article in articles:

            try:

                result = self.extractor.extract(
                    {
                        "id": article.id,
                        "title": article.title,
                        "summary": article.summary,
                        "url": article.url,
                    }
                )

            except ExtractionFailed:

                failed += 1
                continue

            self.session.execute(
                delete(NewsSignal).where(
                    NewsSignal.article_id == article.id
                )
            )

            self.session.add(
                NewsSignal(
                    article_id=article.id,
                    expansion=result["expansion_signal"],
                    power=result["power_signal"],
                    renewable=result["renewable_signal"],
                    retrofit=result["retrofit_signal"],
                    investment=result["investment_signal"],
                    capacity_mw=result["capacity_mw"],
                    confidence=result["confidence"],
                    city=self._bounded_text(result.get("city"), 100),
                    company=self._bounded_text(result.get("company"), 255),
                )
            )

            loaded += 1

            if loaded % self.BATCH_SIZE == 0:

                self.session.commit()

        self.session.commit()

        return {"loaded": loaded, "failed": failed}

    @staticmethod
    def _bounded_text(value, limit: int) -> str | None:

        if value is None:

            return None

        text = str(value).strip()

        return text[:limit] or None
