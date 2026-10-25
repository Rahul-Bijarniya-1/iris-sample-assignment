"""
search_news(question) must find articles on their keywords, not require
the whole question as a literal substring.

NewsIntelligenceService.search_news() lower-cased the *entire* question
and checked whether it appeared verbatim inside each article's title +
summary. A natural-language question essentially never matches that way,
even when the article is squarely about what was asked.
"""

import pytest

from app.database.models.news_article import NewsArticle
from app.services.news_intelligence_service import NewsIntelligenceService


@pytest.mark.integration
def test_search_news_matches_on_a_keyword_from_the_question(db_session):
    db_session.add(
        NewsArticle(
            id="d2a6b1f0-0000-0000-0000-000000000001",
            source="DataCenter-Insider",
            language="de",
            title=(
                "KI-Boom trifft auf Stromengpaesse und "
                "Nachhaltigkeitspflicht"
            ),
            summary="Rechenzentren spueren den Strommangel.",
            url="https://news.invalid/stromengpaesse/",
            processed=True,
        )
    )

    db_session.commit()

    service = NewsIntelligenceService(db_session)

    results = service.search_news(
        "What should I know about Stromengpaesse near Bottrop?"
    )

    assert len(results) == 1
    assert results[0]["title"].startswith("KI-Boom")
