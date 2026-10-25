"""
AgenticRagService: plan -> retrieve -> verify -> refine -> answer, fully
hermetic (every collaborator is a scripted/fake stand-in, no network).

Guards: bounded rounds (max 2 retrieval, max 1 refinement), citations
present for relevant articles, a malformed plan falls back to a default
plan instead of raising, and a tool failure or empty retrieval degrades
the answer instead of raising.
"""

import pytest

from app.services.agentic_rag_service import AgenticRagService


def _result(id_, title, score=0.9):
    return {
        "id": id_,
        "title": title,
        "title_de": title,
        "summary_en": f"Summary of {title}",
        "summary_de": f"Summary of {title}",
        "url": f"https://news.invalid/{id_}/",
        "published_at": "2026-10-23",
        "source": "Test Feed",
        "score": score,
    }


class _ScriptedAI:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, prompt, model=None):
        self.calls.append({"prompt": prompt, "model": model})
        return self.responses.pop(0)


class _ScriptedRetrieval:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def search(self, query, k=10, filters=None):
        self.calls.append({"query": query, "k": k, "filters": filters})
        return self._responses.pop(0) if self._responses else []


SUFFICIENT_VERIFY = (
    '{"sufficient": true, "relevant_ids": ["a1"], '
    '"rejected": [], "missing": "", "refined_query": ""}'
)


@pytest.fixture
def service_factory():
    def _make(ai_responses, retrieval_responses, **kwargs):
        ai = _ScriptedAI(ai_responses)
        retrieval = _ScriptedRetrieval(retrieval_responses)
        service = AgenticRagService(
            session=object(),
            ai=ai,
            news_retrieval=retrieval,
            answer_model="answer-model",
            **kwargs,
        )
        return service, ai, retrieval

    return _make


def test_happy_path_returns_citations_and_a_grounded_answer(
    service_factory,
):
    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "Stromengpaesse", "k": 10}',
            SUFFICIENT_VERIFY,
            "Grid pressure is rising near your site [1].",
        ],
        retrieval_responses=[[_result("a1", "Grid article")]],
    )

    result = service.answer("What grid pressure exists near Bottrop?")

    assert result["answer"] == "Grid pressure is rising near your site [1]."
    assert [c["id"] for c in result["citations"]] == ["a1"]
    assert retrieval.calls[0]["query"] == "Stromengpaesse"
    assert ai.calls[0]["model"] is None  # mini default, for the plan
    assert ai.calls[-1]["model"] == "answer-model"


def test_malformed_plan_falls_back_to_news_search_with_raw_question(
    service_factory,
):
    service, ai, retrieval = service_factory(
        ai_responses=[
            "Sorry, I can't help with that.",  # plan: prose, not JSON
            SUFFICIENT_VERIFY,
            "Fallback answer [1].",
        ],
        retrieval_responses=[[_result("a1", "Some article")]],
    )

    result = service.answer("What is happening near Bottrop?")

    assert retrieval.calls[0]["query"] == "What is happening near Bottrop?"
    assert retrieval.calls[0]["k"] == 10
    assert result["trace"]["plan"]["tools"] == ["news_search"]


def test_unknown_tool_names_are_filtered_out(service_factory):
    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search", "delete_database"], '
            '"query": "q", "k": 5}',
            SUFFICIENT_VERIFY,
            "Answer.",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
    )

    result = service.answer("question")

    assert result["trace"]["plan"]["tools"] == ["news_search"]


def test_k_is_clamped_to_the_one_to_ten_range(service_factory):
    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "q", "k": 999}',
            SUFFICIENT_VERIFY,
            "Answer.",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
    )

    service.answer("question")

    assert retrieval.calls[0]["k"] == 10


def test_refines_once_when_insufficient_then_answers(service_factory):
    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "q1", "k": 10}',
            (
                '{"sufficient": false, "relevant_ids": [], "rejected": [], '
                '"missing": "grid data", "refined_query": "q2"}'
            ),
            SUFFICIENT_VERIFY,
            "Refined answer [1].",
        ],
        retrieval_responses=[
            [_result("old", "Old article")],
            [_result("a1", "New article")],
        ],
    )

    result = service.answer("question")

    assert [c["query"] for c in retrieval.calls] == ["q1", "q2"]
    assert len(result["trace"]["rounds"]) == 2
    assert result["answer"] == "Refined answer [1]."


def test_never_refines_more_than_once(service_factory):
    """
    Even if the second verify is still insufficient, there must be no
    third retrieval round — max 2 retrieval rounds, max 1 refinement.
    """

    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "q1", "k": 10}',
            (
                '{"sufficient": false, "relevant_ids": [], "rejected": [], '
                '"missing": "grid data", "refined_query": "q2"}'
            ),
            (
                '{"sufficient": false, "relevant_ids": [], "rejected": [], '
                '"missing": "still missing", "refined_query": "q3"}'
            ),
            "Best-effort answer.",
        ],
        retrieval_responses=[
            [_result("a1", "Article one")],
            [_result("a2", "Article two")],
        ],
    )

    service.answer("question")

    assert len(retrieval.calls) == 2, (
        "a third retrieval round happened; max is 2"
    )
    assert len(ai.calls) == 4, "expected exactly plan+verify+verify+answer"


def test_degrades_gracefully_on_empty_retrieval(service_factory):
    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "q1", "k": 10}',
            (
                '{"sufficient": false, "relevant_ids": [], "rejected": [], '
                '"missing": "nothing retrieved", "refined_query": "q2"}'
            ),
            (
                '{"sufficient": false, "relevant_ids": [], "rejected": [], '
                '"missing": "still nothing", "refined_query": ""}'
            ),
            "No coverage found for this area.",
        ],
        retrieval_responses=[[], []],
    )

    result = service.answer("question")

    assert result["citations"] == []
    assert result["answer"] == "No coverage found for this area."


def test_on_step_reports_each_stage_for_a_live_status_display(
    service_factory,
):
    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "q", "k": 10}',
            SUFFICIENT_VERIFY,
            "Answer [1].",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
    )

    stages = []

    service.answer("question", on_step=stages.append)

    assert stages == ["Planning", "Retrieving", "Verifying", "Answering"]


def test_a_failing_tool_does_not_raise(service_factory):
    class _ExplodingSiteService:
        def analyze_facility(self, facility_id):
            raise RuntimeError("database exploded")

        def analyze_location(self, latitude, longitude, facility=None):
            raise RuntimeError("database exploded")

    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search", "site_intelligence"], '
            '"query": "q1", "k": 10}',
            SUFFICIENT_VERIFY,
            "Answer despite the tool failure [1].",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
        site_service=_ExplodingSiteService(),
    )

    result = service.answer("question", facility_id=42)

    assert result["answer"] == "Answer despite the tool failure [1]."
    assert result["trace"]["site"] is None
