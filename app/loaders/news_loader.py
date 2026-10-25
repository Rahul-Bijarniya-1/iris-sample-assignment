from __future__ import annotations

import json
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.paths import DataPaths
from app.database.models.news_article import NewsArticle
from app.database.models.news_match import NewsMatch
from app.database.models.facility import Facility


class NewsLoader:
    """
    Loads processed news and entity matches into PostgreSQL.

    The loader is idempotent:

    - Existing articles are identified by URL.
    - Existing articles are updated instead of inserted again.
    - Existing NewsMatch records are not duplicated.
    - New articles and matches are inserted normally.

    Article URLs are the stable identity for news articles.
    Article UUIDs generated during parsing may differ between
    pipeline runs.

    DataPaths controls the input workspace so each
    pipeline execution can load its own isolated data.
    """

    def __init__(
        self,
        session: Session,
        paths: DataPaths | None = None,
    ):

        self.session = session

        self.paths = paths or DataPaths()

        # --------------------------------------------------
        # Input files
        # --------------------------------------------------

        self.news_file = (
            self.paths.news_processed
            / "news.json"
        )

        self.matches_file = (
            self.paths.news_processed
            / "matched_news.json"
        )

    # ======================================================
    # MAIN
    # ======================================================

    def execute(self):

        print("--------------------------------")
        print(
            "Loading News Intelligence"
        )

        articles = self._load_json(
            self.news_file
        )

        matches = self._load_json(
            self.matches_file
        )

        print(
            f"News Articles : "
            f"{len(articles)}"
        )

        print(
            f"News Matches   : "
            f"{len(matches)}"
        )

        try:

            inserted_articles, updated_articles = (
                self._load_articles(
                    articles
                )
            )

            # _load_matches resolves articles by URL, and SessionLocal sets
            # autoflush=False, so flush the pending articles first or every
            # match is skipped. Inside the transaction, so rollback still
            # covers the whole load.
            self.session.flush()

            loaded_matches = (
                self._load_matches(
                    matches
                )
            )

            self.session.commit()

        except Exception:

            self.session.rollback()

            raise

        print("--------------------------------")

        print(
            f"Articles Inserted : "
            f"{inserted_articles}"
        )

        print(
            f"Articles Updated  : "
            f"{updated_articles}"
        )

        print(
            f"Matches Loaded    : "
            f"{loaded_matches}"
        )

        print("--------------------------------")

        print(
            "News Intelligence "
            "Loaded Successfully"
        )

        return {
            "articles_inserted": inserted_articles,
            "articles_updated": updated_articles,
            "matches_loaded": loaded_matches,
        }

    # ======================================================
    # JSON
    # ======================================================

    @staticmethod
    def _load_json(
        file: Path,
    ) -> list:

        if not file.exists():

            raise FileNotFoundError(
                f"News file not found:\n{file}"
            )

        with file.open(
            "r",
            encoding="utf-8",
        ) as handle:

            data = json.load(handle)

        if not isinstance(
            data,
            list,
        ):

            raise ValueError(
                f"Expected a JSON list in {file}"
            )

        return data

    # ======================================================
    # DATES
    # ======================================================

    @staticmethod
    def _parse_published(
        published: str | None,
    ):
        """
        Parse an RFC-822 date string (e.g. feedparser/email format) into a
        timezone-aware datetime, or None when missing/unparseable.
        """

        if not published:

            return None

        try:

            parsed = parsedate_to_datetime(published)

            if parsed.tzinfo is None:

                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed

        except (TypeError, ValueError):

            return None

    # ======================================================
    # ARTICLES
    # ======================================================

    def _load_articles(
        self,
        articles: list,
    ) -> tuple[int, int]:

        inserted = 0
        updated = 0

        for data in articles:

            article_id = data.get(
                "id"
            )

            url = data.get(
                "url"
            )

            if not article_id or not url:

                continue

            # --------------------------------------------------
            # Find by URL first.
            #
            # URL is the stable database identity for an article.
            #
            # The UUID generated by ArticleParser may change
            # between pipeline runs.
            # --------------------------------------------------

            existing = self.session.scalar(
                select(NewsArticle)
                .where(
                    NewsArticle.url == url
                )
            )

            # --------------------------------------------------
            # Existing article
            # --------------------------------------------------

            if existing:

                existing.source = data.get(
                    "source"
                )

                existing.language = data.get(
                    "language",
                    "en",
                )

                existing.title = data.get(
                    "title"
                )

                existing.summary = data.get(
                    "summary"
                )

                published_at = self._parse_published(
                    data.get("published")
                )

                if published_at is not None:

                    existing.published_at = published_at

                existing.processed = data.get(
                    "processed",
                    False,
                )

                updated += 1

                continue

            # --------------------------------------------------
            # New article
            # --------------------------------------------------

            article = NewsArticle(

                id=article_id,

                source=data.get(
                    "source"
                ),

                language=data.get(
                    "language",
                    "en",
                ),

                title=data.get(
                    "title"
                ),

                summary=data.get(
                    "summary"
                ),

                url=url,

                published_at=self._parse_published(
                    data.get("published")
                ),

                processed=data.get(
                    "processed",
                    False,
                ),
            )

            self.session.add(
                article
            )

            inserted += 1

        return inserted, updated

    # ======================================================
    # MATCHES
    # ======================================================

    def _load_matches(
        self,
        matches: list,
    ) -> int:

        loaded = 0

        for data in matches:

            # --------------------------------------------------
            # Extract match data
            # --------------------------------------------------

            article_url = data.get(
                "article_url"
            )

            company = data.get(
                "company"
            )

            facility_name = data.get(
                "facility_name"
            )

            if not article_url:

                continue

            if not company or not facility_name:

                continue

            # --------------------------------------------------
            # Resolve article by URL.
            #
            # IMPORTANT:
            #
            # article_id from matched_news.json cannot be used
            # as the database identity because ArticleParser
            # generates a new UUID for every parsing run.
            #
            # article_url is unique and stable, so use it to
            # resolve the actual database article.
            # --------------------------------------------------

            article = self.session.scalar(
                select(NewsArticle)
                .where(
                    NewsArticle.url == article_url
                )
            )

            if not article:

                continue

            # --------------------------------------------------
            # Resolve facility.
            # --------------------------------------------------

            facility = self.session.scalar(
                select(Facility)
                .where(
                    Facility.company == company,
                    Facility.name == facility_name,
                )
            )

            if not facility:

                continue

            # --------------------------------------------------
            # Prevent duplicate match.
            #
            # One article can match multiple facilities.
            # Therefore the combination of article + facility
            # identifies an existing match.
            # --------------------------------------------------

            existing = self.session.scalar(
                select(NewsMatch)
                .where(
                    NewsMatch.article_id == article.id,
                    NewsMatch.facility_id == facility.id,
                )
            )

            if existing:

                continue

            # --------------------------------------------------
            # Create match.
            # --------------------------------------------------

            match = NewsMatch(

                article_id=article.id,

                facility_id=facility.id,

                company=company,

                facility_name=facility_name,

                city=data.get(
                    "city"
                ),

                match_type=data.get(
                    "match_type"
                ),

                match_score=data.get(
                    "match_score",
                    0.0,
                ),
            )

            self.session.add(
                match
            )

            loaded += 1

        return loaded
