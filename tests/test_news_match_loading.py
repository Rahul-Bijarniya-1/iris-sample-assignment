"""
News matches must load on the first run.

NewsLoader.execute() adds articles to the session and then resolves each
match's article by URL. SessionLocal is built with autoflush=False, so the
pending articles are invisible to that lookup: every match is skipped and
news_matches stays empty.

The articles commit at the end of the run, so a second run of the same step
does load the matches. That masks the bug in manual testing while leaving a
one-shot `main.py all` with zero matches.
"""

import json

import pytest

from app.config.paths import DataPaths
from app.database.models.facility import Facility
from app.loaders.news_loader import NewsLoader


ARTICLE = {
    "id": "b911a44b-2013-4af4-9ab2-5680414bcf87",
    "url": "https://news.invalid/sap-expands-data-center/",
    "source": "Test Feed",
    "language": "de",
    "title": "SAP erweitert Rechenzentrum",
    "summary": "SAP SE baut Kapazität aus.",
    "processed": True,
}


MATCH = {
    "article_id": ARTICLE["id"],
    "article_url": ARTICLE["url"],
    "company": "SAP SE",
    "facility_name": "SAP WDF51",
    "city": None,
    "match_type": "company",
    "match_score": 1.0,
}


@pytest.fixture
def staged_news(tmp_path):
    """
    A staged run holding one article and one match against it.
    """

    paths = DataPaths(tmp_path)
    paths.create_directories()

    (paths.news_processed / "news.json").write_text(
        json.dumps([ARTICLE], ensure_ascii=False),
        encoding="utf-8",
    )

    (paths.news_processed / "matched_news.json").write_text(
        json.dumps([MATCH], ensure_ascii=False),
        encoding="utf-8",
    )

    return paths


@pytest.mark.integration
def test_match_loads_on_the_first_run(db_session, staged_news):
    """
    The facility and article both exist, so the match must be created the
    first time the loader runs — not only on a repeat run.
    """

    db_session.add(
        Facility(
            source_id=1,
            country_code="DE",
            company=MATCH["company"],
            name=MATCH["facility_name"],
        )
    )

    db_session.commit()

    result = NewsLoader(
        db_session,
        paths=staged_news,
    ).execute()

    assert result["articles_inserted"] == 1

    assert result["matches_loaded"] == 1, (
        "the match was skipped even though its article and facility both "
        "resolve; the article was still pending in the session"
    )
