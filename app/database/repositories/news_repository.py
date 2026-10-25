"""
News Repository

Loads and queries News Intelligence from PostgreSQL.

Author:
NRW BI Platform
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models.facility import Facility
from app.database.models.news_article import NewsArticle
from app.database.models.news_match import NewsMatch
from app.database.models.news_signal import NewsSignal


class NewsRepository:

    def __init__(
        self,
        session: Session,
    ):
        self.session = session

    # =====================================================
    # Articles
    # =====================================================

    def get_articles(
        self,
    ) -> list[NewsArticle]:

        return list(
            self.session.scalars(
                select(NewsArticle)
                .order_by(
                    NewsArticle.published_at.desc()
                )
            )
        )

    def get_signal_count(self) -> int:

        return self.session.scalar(
            select(func.count()).select_from(NewsSignal)
        ) or 0

    # -----------------------------------------------------

    def get_article(
        self,
        article_id: str,
    ) -> NewsArticle | None:

        return self.session.get(
            NewsArticle,
            article_id,
        )

    # -----------------------------------------------------

    def get_recent_articles(
        self,
        limit: int = 20,
    ):

        rows = self.session.execute(

            select(
                NewsArticle,
                NewsMatch.company,
                NewsMatch.facility_name,
                NewsMatch.city,
                NewsMatch.match_type,
                NewsMatch.match_score,
            )

            .join(
                NewsMatch,
                NewsArticle.id == NewsMatch.article_id,
            )

            .order_by(
                NewsArticle.published_at.desc()
            )

            .limit(limit)

        ).all()

        result = []

        for (
            article,
            company,
            facility,
            city,
            match_type,
            match_score,
        ) in rows:

            result.append(
                {
                    "id": article.id,
                    "title": article.title,
                    "summary": article.summary,
                    "source": article.source,
                    "published": article.published_at,
                    "url": article.url,
                    "company": company,
                    "facility_name": facility,
                    "city": city,
                    "match_type": match_type,
                    "match_score": match_score,
                }
            )

        return result

    # -----------------------------------------------------

    def get_recent_articles_with_matches(
        self,
        limit: int = 5,
    ):

        rows = self.session.execute(

            select(
                NewsArticle,
                NewsMatch.company,
                NewsMatch.facility_name,
                NewsMatch.city,
                NewsMatch.match_type,
                NewsMatch.match_score,
            )

            .join(
                NewsMatch,
                NewsArticle.id == NewsMatch.article_id,
            )

            .order_by(
                NewsArticle.published_at.desc()
            )

            .limit(limit)

        ).all()

        result = []

        for (
            article,
            company,
            facility,
            city,
            match_type,
            match_score,
        ) in rows:

            result.append(
                {
                    "id": article.id,
                    "title": article.title,
                    "summary": article.summary,
                    "source": article.source,
                    "published": article.published_at,
                    "url": article.url,
                    "company": company,
                    "facility_name": facility,
                    "city": city,
                    "match_type": match_type,
                    "match_score": match_score,
                }
            )

        return result

    # -----------------------------------------------------

    def get_latest_news(
        self,
        limit: int = 5,
    ):

        rows = self.session.execute(

            select(
                NewsArticle,
                NewsMatch,
            )

            .outerjoin(
                NewsMatch,
                NewsMatch.article_id == NewsArticle.id,
            )

            .order_by(
                NewsArticle.published_at.desc(),
            )

            .limit(limit)

        ).all()

        return rows

    # =====================================================
    # Facility Resolution
    # =====================================================

    def find_facility(
        self,
        company: str,
        facility_name: str,
        city: str | None = None,
    ) -> Facility | None:
        """
        Find a facility for a news match.

        Matching priority:

        1. Company + exact facility name
        2. Company + facility name containing the value
        3. Company + facility name + city

        The method returns the first matching facility.
        """

        if not company or not facility_name:
            return None

        # -------------------------------------------------
        # Exact company + exact facility name
        # -------------------------------------------------

        query = (
            select(Facility)
            .where(
                Facility.company.ilike(company),
                Facility.name.ilike(facility_name),
            )
        )

        if city:
            query = query.where(
                Facility.city.ilike(city)
            )

        facility = self.session.scalars(
            query
        ).first()

        if facility:
            return facility

        # -------------------------------------------------
        # Company + facility name contains value
        # -------------------------------------------------

        query = (
            select(Facility)
            .where(
                Facility.company.ilike(company),
                Facility.name.ilike(
                    f"%{facility_name}%"
                ),
            )
        )

        if city:
            query = query.where(
                Facility.city.ilike(city)
            )

        facility = self.session.scalars(
            query
        ).first()

        if facility:
            return facility

        # -------------------------------------------------
        # Final fallback:
        # company + facility name without city
        # -------------------------------------------------

        query = (
            select(Facility)
            .where(
                Facility.company.ilike(company),
                Facility.name.ilike(
                    f"%{facility_name}%"
                ),
            )
        )

        return self.session.scalars(
            query
        ).first()

    # =====================================================
    # Matches
    # =====================================================

    def get_matches(
        self,
    ) -> list[NewsMatch]:

        return list(
            self.session.scalars(
                select(NewsMatch)
            )
        )

    # -----------------------------------------------------

    def get_company_matches(
        self,
        company: str,
    ) -> list[NewsMatch]:

        return list(
            self.session.scalars(
                select(NewsMatch)
                .where(
                    NewsMatch.company.ilike(
                        f"%{company}%"
                    )
                )
            )
        )

    # -----------------------------------------------------

    def get_city_matches(
        self,
        city: str,
    ) -> list[NewsMatch]:

        return list(
            self.session.scalars(
                select(NewsMatch)
                .where(
                    NewsMatch.city.ilike(
                        f"%{city}%"
                    )
                )
            )
        )

    # -----------------------------------------------------

    def get_facility_matches(
        self,
        facility_name: str,
    ) -> list[NewsMatch]:

        return list(
            self.session.scalars(
                select(NewsMatch)
                .where(
                    NewsMatch.facility_name.ilike(
                        f"%{facility_name}%"
                    )
                )
            )
        )
