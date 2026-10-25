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

from app.ai.ai_keywords import NEWS_SEARCH_STOPWORDS
from app.database.repositories.news_repository import (
    NewsRepository,
)


class NewsIntelligenceService:

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
        Return the total number of structured news-signal rows.
        """

        return self.repository.get_signal_count()

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

        ranked_articles = []

        for source_index, article in enumerate(
            self.repository.get_articles()
        ):

            text = (
                (article.title or "")
                + " "
                + (article.summary or "")
            ).lower()

            hit_count = sum(
                bool(
                    re.search(
                        rf"\b{re.escape(token)}\b",
                        text,
                        flags=re.IGNORECASE,
                    )
                )
                for token in tokens
            )

            if hit_count:

                ranked_articles.append(
                    (hit_count, source_index, article)
                )

        ranked_articles.sort(
            key=lambda item: (-item[0], item[1])
        )

        return self._merge(
            [item[2] for item in ranked_articles[:10]],
        )

    @classmethod
    def _keywords(
        cls,
        question: str,
    ) -> list[str]:
        """
        Significant words from a question. Short all-caps and dotted
        names (RWE, E.ON) are retained while ordinary short words drop.
        """

        words = re.findall(
            r"[\wäöüß]+(?:\.[\wäöüß]+)*",
            question,
            flags=re.IGNORECASE,
        )

        keywords = []

        for word in words:

            normalized = word.lower()
            looks_like_name = word.isupper() or "." in word

            if normalized in NEWS_SEARCH_STOPWORDS:

                continue

            if len(normalized) < 4 and not looks_like_name:

                continue

            if normalized not in keywords:

                keywords.append(normalized)

        return keywords

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
