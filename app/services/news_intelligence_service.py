"""
News Intelligence Service

Provides Business Intelligence over
processed news and matched facilities.

Author:
NRW BI Platform
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.database.repositories.news_repository import (
    NewsRepository,
)


class NewsIntelligenceService:

    # Short function words in the two languages the advisor sees
    # questions in (English and German, since the corpus is German).
    # Excluding them keeps a one-word match from firing on "what"/"die".
    _STOPWORDS = {
        "what", "whats", "about", "near", "with", "from", "that", "this",
        "there", "should", "know", "happening", "recent", "activity",
        "the", "and", "for", "are", "was", "were", "have", "has",
        "die", "der", "das", "und", "ist", "sind", "mit", "fuer",
    }

    def __init__(
        self,
        session: Session,
    ):

        self.repository = NewsRepository(
            session,
        )

    # =====================================================
    # Latest News
    # =====================================================

    def latest_news(
        self,
        limit: int = 10,
    ):

        return (
            self.repository
            .get_recent_articles_with_matches(
                limit,
            )
        )

    # =====================================================
    # Signal Count
    # =====================================================

    def get_signal_count(
        self,
    ) -> int:
        """
        Return the total number of news intelligence
        signals stored in PostgreSQL.

        Each NewsMatch represents a detected
        relationship between a news article and
        a known facility.
        """

        matches = (
            self.repository.get_matches()
        )

        return len(matches)

    # =====================================================
    # Company
    # =====================================================

    def company_news(
        self,
        company: str,
    ) -> list[dict]:

        matches = (
            self.repository.get_company_matches(
                company,
            )
        )

        return self._merge_matches(
            matches,
        )

    # =====================================================
    # Facility
    # =====================================================

    def facility_news(
        self,
        facility_name: str,
    ) -> list[dict]:

        matches = (
            self.repository.get_facility_matches(
                facility_name,
            )
        )

        return self._merge_matches(
            matches,
        )

    # =====================================================
    # City
    # =====================================================

    def city_news(
        self,
        city: str,
    ) -> list[dict]:

        matches = (
            self.repository.get_city_matches(
                city,
            )
        )

        return self._merge_matches(
            matches,
        )

    # =====================================================
    # Search
    # =====================================================

    def search_news(
        self,
        keyword: str,
    ) -> list[dict]:
        """
        Search news articles by title and summary.

        `keyword` is normally a full natural-language question. Matching
        it as one literal substring essentially never hits a real
        article, so it is split into individual significant words first
        and an article matches if any one of them appears.
        """

        tokens = self._keywords(keyword)

        if not tokens:

            return []

        articles = []

        for article in (
            self.repository.get_articles()
        ):

            text = (
                (article.title or "")
                + " "
                + (article.summary or "")
            ).lower()

            if any(token in text for token in tokens):

                articles.append(
                    article,
                )

        return self._merge(
            articles,
        )

    @classmethod
    def _keywords(
        cls,
        question: str,
    ) -> list[str]:
        """
        Significant words from a question: lower-cased, split on
        non-alphanumerics, short function words and anything under 4
        characters dropped.
        """

        words = re.findall(
            r"[\wäöüß]+",
            question.lower(),
        )

        return [
            word
            for word in words
            if len(word) >= 4 and word not in cls._STOPWORDS
        ]

    # =====================================================
    # Merge Articles
    # =====================================================

    def _merge(
        self,
        articles: list,
    ) -> list[dict]:
        """
        Merge articles with their news matches.

        Returns plain dictionaries suitable for
        Streamlit/UI consumption.
        """

        matches = {
            match.article_id: match
            for match in (
                self.repository.get_matches()
            )
        }

        news = []

        for article in articles:

            match = matches.get(
                article.id,
            )

            news.append(
                {
                    "id": article.id,

                    "title": article.title,

                    "summary": article.summary,

                    "source": article.source,

                    "published": article.published_at,

                    "url": article.url,

                    "company": (
                        match.company
                        if match
                        else None
                    ),

                    "facility_name": (
                        match.facility_name
                        if match
                        else None
                    ),

                    "city": (
                        match.city
                        if match
                        else None
                    ),

                    "match_type": (
                        match.match_type
                        if match
                        else None
                    ),

                    "match_score": (
                        match.match_score
                        if match
                        else None
                    ),
                }
            )

        return news

    # =====================================================
    # Merge Matches
    # =====================================================

    def _merge_matches(
        self,
        matches,
    ) -> list[dict]:
        """
        Convert NewsMatch records into article
        dictionaries enriched with article data.
        """

        articles = []

        for match in matches:

            article = (
                self.repository.get_article(
                    str(match.article_id),
                )
            )

            if article:

                articles.append(
                    article,
                )

        return self._merge(
            articles,
        )