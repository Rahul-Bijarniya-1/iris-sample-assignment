"""Regression guards for retrieval transactions and keyless fallback."""

import pytest
from openai import OpenAIError

from app.services.ai_advisor_service import AIAdvisorService
from app.services.agentic_rag_service import AgenticRagService
from app.services.embedding_service import EmbeddingDimensionMismatch
from app.services.news_retrieval_service import NewsRetrievalService


class _Embedding:
    def embed(self, text):
        return [0.0] * 1536


class _DimensionMismatchEmbedding:
    def embed(self, text):
        raise EmbeddingDimensionMismatch("expected 1536 dimensions")


class _PoisonedSession:
    """Mimic a database transaction that stays aborted until rollback."""

    def __init__(self):
        self.failed = False
        self.rollback_calls = 0
        self.execute_calls = 0

    def execute(self, statement):
        self.execute_calls += 1

        if self.execute_calls == 1:
            self.failed = True
            raise RuntimeError("database statement failed")

        if self.failed:
            raise RuntimeError("transaction is still aborted")

        return "fallback query succeeded"

    def rollback(self):
        self.failed = False
        self.rollback_calls += 1


class _RecordingSession:
    def __init__(self):
        self.execute_calls = 0

    def execute(self, statement):
        self.execute_calls += 1
        raise AssertionError("dimension failures happen before SQL execution")

    def rollback(self):
        raise AssertionError("there is no failed transaction to roll back")


def test_failed_retrieval_rolls_back_before_a_fallback_query():
    session = _PoisonedSession()
    service = NewsRetrievalService(
        session,
        embedding_service=_Embedding(),
    )

    assert service.search("query") == []
    assert session.rollback_calls == 1
    assert session.execute(object()) == "fallback query succeeded"


def test_embedding_dimension_mismatch_propagates():
    session = _RecordingSession()
    service = NewsRetrievalService(
        session,
        embedding_service=_DimensionMismatchEmbedding(),
    )

    with pytest.raises(EmbeddingDimensionMismatch, match="1536"):
        service.search("query")

    assert session.execute_calls == 0


def test_agentic_safe_call_does_not_hide_dimension_mismatch():
    def dimension_mismatch():
        raise EmbeddingDimensionMismatch("expected 1536 dimensions")

    with pytest.raises(EmbeddingDimensionMismatch, match="1536"):
        AgenticRagService._safe_call(dimension_mismatch)


def test_agentic_safe_call_degrades_an_unrelated_value_error():
    def invalid_tool_value():
        raise ValueError("ordinary tool validation failure")

    assert AgenticRagService._safe_call(invalid_tool_value) is None


def test_keyless_keyword_fallback_returns_plain_unavailable_answer():
    advisor = AIAdvisorService.__new__(AIAdvisorService)
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
    advisor.news_service = type(
        "_NewsService",
        (),
        {
            "search_news": staticmethod(lambda question: [{"title": "News"}]),
        },
    )()
    advisor.context_builder = type(
        "_ContextBuilder",
        (),
        {
            "build_news_context": staticmethod(
                lambda news, question: "news context"
            ),
        },
    )()

    def unavailable(prompt):
        raise OpenAIError("The api_key client option must be set")

    advisor.ai = type("_UnavailableAI", (), {"generate": staticmethod(unavailable)})()

    result = advisor._news("Any news?")

    assert result == "AI unavailable right now. Please try again later."
