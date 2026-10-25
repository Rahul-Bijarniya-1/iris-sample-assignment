"""
`published_at` must survive the load.

news.json carries an RFC-822 date string under "published" (e.g.
'Fri, 23 Oct 2026 14:21:00 +0200'), but NewsLoader._load_articles sets it in
neither the insert nor the update path, so every article lands with
published_at NULL. Same class of defect as Issue 10 (MaStRParser dropping
country_code): upstream data carries a field, the loader drops it.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.config.paths import DataPaths
from app.database.models.news_article import NewsArticle
from app.loaders.news_loader import NewsLoader


ARTICLE = {
    "id": "b911a44b-2013-4af4-9ab2-5680414bcf87",
    "url": "https://news.invalid/published-at-test/",
    "source": "Test Feed",
    "language": "de",
    "title": "Testartikel",
    "summary": "Ein Testartikel.",
    "published": "Fri, 23 Oct 2026 14:21:00 +0200",
    "processed": True,
}


@pytest.fixture
def staged_article(tmp_path):
    paths = DataPaths(tmp_path)
    paths.create_directories()

    (paths.news_processed / "news.json").write_text(
        json.dumps([ARTICLE], ensure_ascii=False),
        encoding="utf-8",
    )

    (paths.news_processed / "matched_news.json").write_text(
        json.dumps([], ensure_ascii=False),
        encoding="utf-8",
    )

    return paths


@pytest.mark.integration
def test_published_at_set_on_insert(db_session, staged_article):
    NewsLoader(db_session, paths=staged_article).execute()

    article = db_session.query(NewsArticle).filter_by(
        url=ARTICLE["url"]
    ).one()

    assert article.published_at == datetime(
        2026, 10, 23, 14, 21, 0, tzinfo=timezone(timedelta(hours=2)),
    )


@pytest.mark.integration
def test_published_at_set_on_update(db_session, staged_article):
    # First run inserts; second run takes the update path.
    NewsLoader(db_session, paths=staged_article).execute()
    db_session.commit()

    NewsLoader(db_session, paths=staged_article).execute()

    article = db_session.query(NewsArticle).filter_by(
        url=ARTICLE["url"]
    ).one()

    assert article.published_at is not None


@pytest.mark.integration
def test_missing_date_on_reload_preserves_existing_value(
    db_session,
    staged_article,
):
    NewsLoader(db_session, paths=staged_article).execute()

    article_without_date = {key: value for key, value in ARTICLE.items()}
    article_without_date.pop("published")
    (staged_article.news_processed / "news.json").write_text(
        json.dumps([article_without_date], ensure_ascii=False),
        encoding="utf-8",
    )

    NewsLoader(db_session, paths=staged_article).execute()

    article = db_session.query(NewsArticle).filter_by(
        url=ARTICLE["url"]
    ).one()

    assert article.published_at == datetime(
        2026, 10, 23, 14, 21, 0, tzinfo=timezone(timedelta(hours=2)),
    )


def test_unknown_rfc822_timezone_is_treated_as_utc():
    parsed = NewsLoader._parse_published(
        "Fri, 23 Oct 2026 14:21:00 -0000"
    )

    assert parsed == datetime(2026, 10, 23, 14, 21, tzinfo=timezone.utc)
    assert parsed.tzinfo is not None
