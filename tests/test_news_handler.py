"""
AIAdvisorService._news() must use the keyword search result, not discard it.

_news() computed `news` from search_news()/facility_news()/company_news()/
city_news()/latest_news() once, then immediately recomputed it from the
same cascade minus search_news() — so the keyword result was always
thrown away and replaced by whichever of facility/company/city/latest
matched first.
"""

import pytest

from app.services.ai_advisor_service import AIAdvisorService


class _EchoAI:
    """Stands in for AIRecommendationService: returns the prompt verbatim
    so the test can inspect what context actually reached it, without a
    real OpenAI call."""

    def generate(self, prompt: str) -> str:
        return prompt


def _article(title: str) -> dict:
    return {
        "title": title,
        "source": "Test Feed",
        "published": "2026-10-23",
        "summary": "irrelevant",
    }


@pytest.mark.integration
def test_news_uses_keyword_result_instead_of_discarding_it(db_session):
    advisor = AIAdvisorService(db_session)
    advisor.ai = _EchoAI()

    keyword_hit = [_article("KEYWORD_HIT")]
    cascade_hit = [_article("CASCADE_HIT")]

    advisor.news_service.search_news = lambda question: keyword_hit
    advisor.news_service.facility_news = lambda facility: cascade_hit
    advisor.news_service.company_news = lambda company: cascade_hit
    advisor.news_service.city_news = lambda city: cascade_hit
    advisor.news_service.latest_news = lambda limit: cascade_hit

    # A question that would also resolve to a facility, so the old
    # cascade's second pass had something to override the keyword result
    # with.
    advisor.parser.parse = lambda question: {
        "facility": "Some Facility",
        "company": None,
        "city": None,
    }

    result = advisor._news("what's happening with Some Facility")

    assert "KEYWORD_HIT" in result
    assert "CASCADE_HIT" not in result
