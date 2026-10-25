"""
AIIntent.NEWS must route through AgenticRagService (Decision: "Route
AIIntent.NEWS through the new service... no 14th intent"), with the
parsed city as the optional place name and the selected facility as the
optional facility_id — but fall back to the old keyword/match path
(_news()) when the new retrieval degraded entirely (missing API key, no
embeddings, no pgvector all surface as an all-empty retrieval trace), so
the dashboard is never worse than before.
"""

import pytest

from app.services.ai_advisor_service import AIAdvisorService, AIIntent


def _trace(round_ids):
    return {
        "plan": {"tools": ["news_search"], "query": "q", "k": 10},
        "rounds": [{"query": "q", "k": 10, "result_ids": round_ids}],
        "verify": {"sufficient": True},
        "site": None,
        "ranking": None,
    }


@pytest.mark.integration
def test_agentic_news_passes_the_parsed_city_as_place(db_session):
    advisor = AIAdvisorService(db_session)

    captured = {}

    def fake_answer(question, facility_id=None, place=None, on_step=None):
        captured["question"] = question
        captured["facility_id"] = facility_id
        captured["place"] = place
        return {
            "answer": "Grid pressure is rising [1].",
            "citations": [{"id": "a1"}],
            "trace": _trace(["a1"]),
        }

    advisor.agentic_rag.answer = fake_answer
    advisor.parser.parse = lambda question: {
        "facility": None,
        "company": None,
        "city": "Bottrop",
    }

    result = advisor._agentic_news(
        "What grid pressure exists near Bottrop?",
        facility_id=None,
    )

    assert result == "Grid pressure is rising [1]."
    assert captured["place"] == "Bottrop"
    assert captured["facility_id"] is None
    assert advisor.last_citations == [{"id": "a1"}]


@pytest.mark.integration
def test_news_intent_dispatches_to_agentic_news(db_session):
    advisor = AIAdvisorService(db_session)

    advisor.agentic_rag.answer = lambda question, **kwargs: {
        "answer": "Grid pressure is rising [1].",
        "citations": [{"id": "a1"}],
        "trace": _trace(["a1"]),
    }

    result = advisor.ask(
        "What is the latest news signal here?",
        selected_facility_id=None,
    )

    assert result == "Grid pressure is rising [1]."


@pytest.mark.integration
def test_agentic_news_passes_through_the_selected_facility(db_session):
    advisor = AIAdvisorService(db_session)

    captured = {}

    def fake_answer(question, facility_id=None, place=None, on_step=None):
        captured["facility_id"] = facility_id
        return {
            "answer": "Answer [1].",
            "citations": [{"id": "a1"}],
            "trace": _trace(["a1"]),
        }

    advisor.agentic_rag.answer = fake_answer
    advisor.parser.parse = lambda question: {
        "facility": None,
        "company": None,
        "city": None,
    }

    advisor._agentic_news("Any news on this site?", facility_id=42)

    assert captured["facility_id"] == 42


@pytest.mark.integration
def test_falls_back_to_keyword_path_when_retrieval_degrades_entirely(
    db_session,
):
    """
    An empty first retrieval round means NewsRetrievalService itself
    degraded (no API key / no embeddings / no pgvector), not that the
    corpus legitimately lacks coverage — that case must fall back to
    the pre-RAG keyword/match path instead of a bare "nothing found".
    """

    advisor = AIAdvisorService(db_session)

    advisor.agentic_rag.answer = lambda question, **kwargs: {
        "answer": "No coverage found anywhere.",
        "citations": [],
        "trace": _trace([]),
    }

    advisor.parser.parse = lambda question: {
        "facility": None,
        "company": None,
        "city": None,
    }

    advisor.news_service.search_news = lambda question: []
    advisor.news_service.latest_news = lambda limit: [
        {
            "title": "Fallback article",
            "source": "s",
            "published": "p",
            "summary": "sum",
        }
    ]
    advisor.ai = type(
        "_Echo", (), {"generate": staticmethod(lambda prompt: prompt)}
    )()

    result = advisor._agentic_news("Any news?", facility_id=None)

    assert "Fallback article" in result


def test_keyword_fallback_does_not_publish_an_agentic_trace():
    advisor = AIAdvisorService.__new__(AIAdvisorService)
    advisor.last_trace = None
    advisor.last_citations = None
    advisor.parser = type(
        "_Parser",
        (),
        {
            "parse": staticmethod(
                lambda question: {
                    "facility": None,
                    "company": None,
                    "city": None,
                }
            )
        },
    )()
    advisor.agentic_rag = type(
        "_AgenticRag",
        (),
        {
            "answer": staticmethod(
                lambda question, **kwargs: {
                    "answer": "Agentic no-results answer.",
                    "citations": [],
                    "trace": _trace([]),
                }
            )
        },
    )()
    advisor._news = lambda question: "Keyword fallback answer."

    result = advisor._agentic_news("Any news?", facility_id=None)

    assert result == "Keyword fallback answer."
    assert advisor.last_trace is None
    assert advisor.last_citations is None


def test_second_retrieval_round_prevents_keyword_fallback():
    advisor = AIAdvisorService.__new__(AIAdvisorService)
    advisor.last_trace = None
    advisor.last_citations = None
    advisor.parser = type(
        "_Parser",
        (),
        {
            "parse": staticmethod(
                lambda question: {
                    "facility": None,
                    "company": None,
                    "city": None,
                }
            )
        },
    )()

    trace = _trace([])
    trace["rounds"].append(
        {"query": "refined q", "k": 10, "result_ids": ["a1"]}
    )
    advisor.agentic_rag = type(
        "_AgenticRag",
        (),
        {
            "answer": staticmethod(
                lambda question, **kwargs: {
                    "answer": "Refined answer [1].",
                    "citations": [{"id": "a1"}],
                    "trace": trace,
                }
            )
        },
    )()
    advisor._news = lambda question: pytest.fail(
        "A successful refinement must not use the keyword fallback"
    )

    result = advisor._agentic_news("Any news?", facility_id=None)

    assert result == "Refined answer [1]."
    assert advisor.last_trace is trace
    assert advisor.last_citations == [{"id": "a1"}]


def test_ask_clears_trace_and_citations_between_turns():
    advisor = AIAdvisorService.__new__(AIAdvisorService)
    advisor.last_trace = None
    advisor.last_citations = None
    advisor.detect_intent = lambda question: (
        AIIntent.NEWS if question == "news" else AIIntent.HELP
    )

    trace = _trace(["a1"])

    def answer_news(question, facility_id, on_step=None):
        advisor.last_trace = trace
        advisor.last_citations = [{"id": "a1"}]
        return "News answer [1]."

    advisor._agentic_news = answer_news

    assert advisor.ask("news", selected_facility_id=None) == "News answer [1]."
    assert advisor.last_trace is trace
    assert advisor.last_citations == [{"id": "a1"}]

    result = advisor.ask("help", selected_facility_id=None)

    assert "AI Infrastructure Advisor" in result
    assert advisor.last_trace is None
    assert advisor.last_citations is None
