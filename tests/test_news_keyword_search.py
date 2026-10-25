"""
search_news(question) must find articles on their keywords, not require
the whole question as a literal substring.

NewsIntelligenceService.search_news() lower-cased the *entire* question
and checked whether it appeared verbatim inside each article's title +
summary. A natural-language question essentially never matches that way,
even when the article is squarely about what was asked.
"""

from types import SimpleNamespace

import pytest

from app.database.models.news_article import NewsArticle
from app.services.news_intelligence_service import NewsIntelligenceService


class _Repository:
    def __init__(self, articles):
        self._articles = articles

    def get_articles(self):
        return self._articles

    def get_matches(self):
        return []


def _article(id_, title, summary=""):
    return SimpleNamespace(
        id=id_,
        title=title,
        summary=summary,
        source="Test Feed",
        published_at=None,
        url=f"https://news.invalid/{id_}/",
    )


def _service(*articles):
    service = object.__new__(NewsIntelligenceService)
    service.repository = _Repository(list(articles))
    return service


def test_search_news_matches_whole_words_only():
    service = _service(
        _article("a1", "Deutschland baut neue Rechenzentren"),
    )

    assert service.search_news("land") == []


def test_search_news_keeps_short_uppercase_entities():
    service = _service(
        _article("a1", "RWE plant neue Stromkapazitaet"),
    )

    results = service.search_news("What is RWE planning?")

    assert [result["id"] for result in results] == ["a1"]


def test_search_news_keeps_short_dotted_entities():
    service = _service(
        _article("a1", "E.ON erweitert das Stromnetz"),
    )

    results = service.search_news("What is E.ON planning?")

    assert [result["id"] for result in results] == ["a1"]


def test_search_news_drops_uppercase_function_words_before_ranking():
    service = _service(
        _article("generic", "Was ist mit dem Ausbau"),
        _article("rwe", "RWE plant neue Stromkapazitaet"),
    )

    results = service.search_news("WAS IST MIT RWE")

    assert [result["id"] for result in results] == ["rwe"]


def test_search_news_ranks_distinct_hits_and_caps_results():
    articles = [
        _article("three", "Grid power expansion"),
        _article("two", "Grid power"),
        _article("one", "Grid"),
        *[
            _article(f"extra-{index}", "Grid update")
            for index in range(10)
        ],
    ]
    service = _service(*articles)

    results = service.search_news("grid power expansion")

    assert len(results) == 10
    assert [result["id"] for result in results[:3]] == [
        "three",
        "two",
        "one",
    ]


def test_search_news_generic_question_does_not_return_the_corpus():
    service = _service(
        *[
            _article(f"a{index}", "Daily news update")
            for index in range(12)
        ]
    )

    results = service.search_news("What is happening?")

    assert results == []


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
