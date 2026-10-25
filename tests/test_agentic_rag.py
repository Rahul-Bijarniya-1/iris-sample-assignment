"""
AgenticRagService: plan -> retrieve -> verify -> refine -> answer, fully
hermetic (every collaborator is a scripted/fake stand-in, no network).

Guards: bounded rounds (max 2 retrieval, max 1 refinement), citations
present for relevant articles, a malformed plan falls back to a default
plan instead of raising, and a tool failure or empty retrieval degrades
the answer instead of raising.
"""

import json

import pytest

from app.services.agentic_rag_service import AgenticRagService
from app.services.site_ranking_service import RankingType


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


def test_plan_rejects_non_string_tools_and_query(service_factory):
    service, ai, retrieval = service_factory(
        ai_responses=[
            json.dumps(
                {
                    "tools": [{"name": "news_search"}, "news_search"],
                    "query": ["grid", "capacity"],
                    "k": 5,
                }
            ),
            SUFFICIENT_VERIFY,
            "Answer.",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
    )

    result = service.answer("raw planner question")

    assert retrieval.calls[0]["query"] == "raw planner question"
    assert result["trace"]["plan"]["tools"] == ["news_search"]


def test_plan_bounds_an_oversized_model_query(service_factory):
    service, ai, retrieval = service_factory(
        ai_responses=[
            json.dumps(
                {
                    "tools": ["news_search"],
                    "query": "q" * 2_000,
                    "k": 5,
                }
            ),
            SUFFICIENT_VERIFY,
            "Answer.",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
    )

    service.answer("raw planner question")

    assert retrieval.calls[0]["query"] == "q" * 500


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


def test_verify_tolerates_relevant_ids_as_objects_instead_of_strings(
    service_factory,
):
    """
    SufficiencyPrompt shows "relevant_ids": ["..."] directly above
    "rejected": [{"id": "...", "reason": "..."}] — a model conflating
    the two shapes and returning relevant_ids as objects must not crash
    answer(); found by code review, reproduced against the real
    _filter_relevant/_verify path.
    """

    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "q", "k": 10}',
            (
                '{"sufficient": true, '
                '"relevant_ids": [{"id": "a1", "reason": "on topic"}], '
                '"rejected": [], "missing": "", "refined_query": ""}'
            ),
            "Answer [1].",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
    )

    result = service.answer("question")

    assert result["answer"] == "Answer [1]."


def test_verify_tolerates_relevant_ids_as_a_non_list_scalar(
    service_factory,
):
    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "q", "k": 10}',
            (
                '{"sufficient": true, "relevant_ids": 5, '
                '"rejected": [], "missing": "", "refined_query": ""}'
            ),
            "Answer.",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
    )

    result = service.answer("question")

    assert result["answer"] == "Answer."


def test_verify_treats_the_string_false_as_false(service_factory):
    """
    bool("false") is True in Python — a model returning the literal
    string "false" for the sufficient field must not be treated as
    truthy and suppress the refinement round.
    """

    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "q1", "k": 10}',
            (
                '{"sufficient": "false", "relevant_ids": [], '
                '"rejected": [], "missing": "x", "refined_query": "q2"}'
            ),
            SUFFICIENT_VERIFY,
            "Refined answer.",
        ],
        retrieval_responses=[
            [_result("old", "Old article")],
            [_result("a1", "New article")],
        ],
    )

    service.answer("question")

    assert [c["query"] for c in retrieval.calls] == ["q1", "q2"]


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


def test_site_ranking_result_actually_reaches_the_answer_prompt(
    service_factory,
):
    """
    Found by code review: rank_sites() was computed whenever the plan
    picked the site_ranking tool, but the result only ever landed in
    trace["ranking"] — never passed to _answer(), so the (expensive,
    all-223-facilities) computation was thrown away. It must now reach
    the prompt the final answer is generated from.
    """

    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search", "site_ranking"], '
            '"query": "q", "k": 10}',
            SUFFICIENT_VERIFY,
            "Answer [1].",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
        ranking_service=type(
            "_FakeRanking",
            (),
            {
                "rank_sites": lambda self, ranking_type=None, limit=10: [
                    {"facility": "DISTINCTIVE_RANKED_FACILITY"}
                ]
            },
        )(),
    )

    service.answer("question")

    answer_prompt = ai.calls[-1]["prompt"]
    assert "DISTINCTIVE_RANKED_FACILITY" in answer_prompt


def test_filter_relevant_drops_articles_the_verifier_rejected(
    service_factory,
):
    """
    An explicit rejected list is a model judgement that none of the
    retrieved articles is usable. Those articles must not be cited as
    though the verifier accepted them.
    """

    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "Dortmund grid risk", '
            '"k": 10}',
            (
                '{"sufficient": false, "relevant_ids": [], '
                '"rejected": [{"id": "a1", "reason": "no Dortmund mention"}], '
                '"missing": "nothing specific to Dortmund", '
                '"refined_query": ""}'
            ),
            "Answer using the national context [1].",
        ],
        retrieval_responses=[
            [_result("a1", "National grid shortage article")]
        ],
    )

    result = service.answer("question about Dortmund")

    assert result["citations"] == []
    assert result["answer"] == "Answer using the national context [1]."


def test_filter_relevant_keeps_results_when_verifier_cannot_classify_them(
    service_factory,
):
    service, _, _ = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "q", "k": 10}',
            (
                '{"sufficient": true, "relevant_ids": [], '
                '"rejected": [], "missing": "", "refined_query": ""}'
            ),
            "Best-effort answer [1].",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
    )

    result = service.answer("question")

    assert [citation["id"] for citation in result["citations"]] == ["a1"]


def test_verify_treats_the_string_no_as_false(service_factory):
    """
    _as_bool's deny-list covered "false"/"0"/"" but not the equally
    common "no"/"none"/"null", so `"sufficient": "no"` read as True and
    silently suppressed the refinement round the model had asked for by
    supplying a refined_query.
    """

    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "q1", "k": 10}',
            (
                '{"sufficient": "no", "relevant_ids": [], '
                '"rejected": [], "missing": "x", "refined_query": "q2"}'
            ),
            SUFFICIENT_VERIFY,
            "Refined answer.",
        ],
        retrieval_responses=[
            [_result("old", "Old article")],
            [_result("a1", "New article")],
        ],
    )

    service.answer("question")

    assert [c["query"] for c in retrieval.calls] == ["q1", "q2"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("true", True),
        ("YES", True),
        ("on", True),
        ("1", True),
        ("false", False),
        ("no", False),
        ("none", False),
        ("null", False),
        ("off", False),
        ("n", False),
        ("", False),
        ("unexpected", False),
    ],
)
def test_as_bool_uses_an_explicit_truthy_allow_list(value, expected):
    assert AgenticRagService._as_bool(value) is expected


def test_plan_tolerates_tools_as_an_explicit_null(service_factory):
    """
    data.get("tools", []) does not protect against an explicit JSON
    null, and the comprehension sits outside _safe_call, so a model
    answering `"tools": null` raised TypeError straight out of answer().
    """

    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": null, "query": "q", "k": 10}',
            SUFFICIENT_VERIFY,
            "Answer [1].",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
    )

    result = service.answer("question")

    assert result["trace"]["plan"]["tools"] == ["news_search"]
    assert result["answer"] == "Answer [1]."


def test_relevant_ids_matching_no_retrieved_article_fall_back(
    service_factory,
):
    """
    The empty-relevant_ids fallback only fires on an empty list. Ids are
    String(36) UUIDs but _as_id_list admits ints, so a model answering
    with 1-based indices — plausible, since the citation convention is
    [n] markers — produced a non-empty list matching nothing, and the
    comprehension silently returned no evidence at all.

    Falling back is the same choice as the empty case; the mismatch is
    recorded in the trace so it is visible rather than silent.
    """

    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "q", "k": 10}',
            (
                '{"sufficient": true, "relevant_ids": [1, 2], '
                '"rejected": [], "missing": "", "refined_query": ""}'
            ),
            "Answer [1].",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
    )

    result = service.answer("question")

    assert [c["id"] for c in result["citations"]] == ["a1"]
    assert result["trace"]["verify"]["relevance"] == "id_mismatch"


def test_rejected_entries_are_coerced_to_id_reason_dicts(service_factory):
    """
    _verify passed `rejected` through uncoerced while relevant_ids was
    sanitized. A model returning the common simplification
    `"rejected": ["a1", "a2"]` then reached the trace renderer, which
    calls .get() on each entry — crashing the AI panel, and crashing it
    again on every rerun because the bad trace was already persisted
    into session state.
    """

    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "q", "k": 10}',
            (
                '{"sufficient": true, "relevant_ids": ["a1"], '
                '"rejected": ["a2", "a3"], "missing": "", '
                '"refined_query": ""}'
            ),
            "Answer [1].",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
    )

    result = service.answer("question")

    rejected = result["trace"]["verify"]["rejected"]

    assert [entry["id"] for entry in rejected] == ["a2", "a3"]
    assert all(
        isinstance(entry.get("reason"), str) for entry in rejected
    )


def test_a_refined_query_identical_to_the_first_skips_the_round(
    service_factory,
):
    """
    A mini model echoing the original query back as refined_query cost a
    second embedding, a second search returning the same rows, and a
    second verify call — three round trips for zero new evidence.
    """

    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search"], "query": "q1", "k": 10}',
            (
                '{"sufficient": false, "relevant_ids": [], '
                '"rejected": [], "missing": "x", "refined_query": "q1"}'
            ),
            "Best-effort answer.",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
    )

    service.answer("question")

    assert len(retrieval.calls) == 1, (
        "the refined query repeated the original; no round should be spent"
    )
    assert len(ai.calls) == 3, "expected plan+verify+answer only"


def test_the_plans_ranking_dimension_reaches_rank_sites(service_factory):
    """
    rank_sites() was called bare, so RankingType.OVERALL was always used
    and a question explicitly about renewable readiness got an overall
    ranking presented as its answer.
    """

    class _RecordingRanking:
        def __init__(self):
            self.calls = []

        def rank_sites(self, ranking_type=None, limit=10):
            self.calls.append(
                {"ranking_type": ranking_type, "limit": limit}
            )
            return [{"facility": "ranked"}]

    ranking = _RecordingRanking()

    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search", "site_ranking"], "query": "q", '
            '"k": 10, "ranking_type": "renewable", '
            '"ranking_limit": 3}',
            SUFFICIENT_VERIFY,
            "Answer [1].",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
        ranking_service=ranking,
    )

    service.answer("question")

    assert ranking.calls[0]["ranking_type"] == RankingType.RENEWABLE
    assert ranking.calls[0]["limit"] == 3


def test_an_unknown_ranking_dimension_falls_back_to_overall(
    service_factory,
):
    class _RecordingRanking:
        def __init__(self):
            self.calls = []

        def rank_sites(self, ranking_type=None, limit=10):
            self.calls.append({"ranking_type": ranking_type})
            return []

    ranking = _RecordingRanking()

    service, ai, retrieval = service_factory(
        ai_responses=[
            '{"tools": ["news_search", "site_ranking"], "query": "q", '
            '"k": 10, "ranking_type": "vibes"}',
            SUFFICIENT_VERIFY,
            "Answer [1].",
        ],
        retrieval_responses=[[_result("a1", "Article")]],
        ranking_service=ranking,
    )

    service.answer("question")

    assert ranking.calls[0]["ranking_type"] == RankingType.OVERALL


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
