"""
Extract News Signals Command

Runs an extractor (normally OpenAIExtractor) over every news article
and loads the result into news_signals — idempotently: each run
replaces a given article's row rather than duplicating it, so this is
safe to re-run after an extraction-prompt change.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database.models.news_article import NewsArticle
from app.database.models.news_signal import NewsSignal
from app.extractors.openai_extractor import OpenAIExtractor


class ExtractNewsSignalsCommand:

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

        for article in articles:

            result = self.extractor.extract(
                {
                    "id": article.id,
                    "title": article.title,
                    "summary": article.summary,
                    "url": article.url,
                }
            )

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
                    city=result["city"] or None,
                    company=result["company"] or None,
                )
            )

            loaded += 1

        self.session.commit()

        return {"loaded": loaded}
