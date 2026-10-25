"""Shared OpenAI configuration keeps model and client setup consistent."""

import pytest

from app.config.openai import (
    LazyOpenAIClient,
    get_answer_model,
    get_chat_model,
    get_embedding_model,
)
from app.extractors.openai_extractor import OpenAIExtractor
from app.services.agentic_rag_service import AgenticRagService
from app.services.ai_recommendation_service import AIRecommendationService
from app.services.embedding_service import EmbeddingService
from app.services.translation_service import TranslationService


def _agentic_service(answer_model=None):
    dependency = object()

    return AgenticRagService(
        session=None,
        ai=dependency,
        news_retrieval=dependency,
        site_service=dependency,
        ranking_service=dependency,
        land_repository=dependency,
        answer_model=answer_model,
    )


def test_model_settings_are_read_at_runtime(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "chat-v1")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "embedding-v1")
    monkeypatch.setenv("OPENAI_ANSWER_MODEL", "answer-v1")

    assert get_chat_model() == "chat-v1"
    assert get_embedding_model() == "embedding-v1"
    assert get_answer_model() == "answer-v1"

    monkeypatch.setenv("OPENAI_MODEL", "chat-v2")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "embedding-v2")
    monkeypatch.setenv("OPENAI_ANSWER_MODEL", "answer-v2")

    assert get_chat_model() == "chat-v2"
    assert get_embedding_model() == "embedding-v2"
    assert get_answer_model() == "answer-v2"


def test_services_use_runtime_model_settings(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "configured-chat")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "configured-embedding")
    monkeypatch.setenv("OPENAI_ANSWER_MODEL", "configured-answer")

    assert AIRecommendationService().model == "configured-chat"
    assert TranslationService().model == "configured-chat"
    assert OpenAIExtractor().model == "configured-chat"
    assert EmbeddingService().model == "configured-embedding"
    assert _agentic_service().answer_model == "configured-answer"


@pytest.mark.parametrize(
    ("factory", "attribute"),
    [
        (lambda: AIRecommendationService(model="explicit"), "model"),
        (lambda: TranslationService(model="explicit"), "model"),
        (lambda: OpenAIExtractor(model="explicit"), "model"),
        (lambda: EmbeddingService(model="explicit"), "model"),
        (lambda: _agentic_service(answer_model="explicit"), "answer_model"),
    ],
)
def test_explicit_model_overrides_still_win(monkeypatch, factory, attribute):
    monkeypatch.setenv("OPENAI_MODEL", "configured")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "configured")
    monkeypatch.setenv("OPENAI_ANSWER_MODEL", "configured")

    assert getattr(factory(), attribute) == "explicit"


def test_shared_client_is_lazy_injected_and_cached(monkeypatch):
    created = []
    expected = object()

    def _build_client(**kwargs):
        created.append(kwargs)
        return expected

    monkeypatch.setattr("app.config.openai.OpenAI", _build_client)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    lazy = LazyOpenAIClient()

    assert created == []

    monkeypatch.setenv("OPENAI_API_KEY", "runtime-key")

    assert lazy.client is expected
    assert lazy.client is expected
    assert created == [{"api_key": "runtime-key"}]

    injected = object()
    assert LazyOpenAIClient(injected).client is injected
    assert created == [{"api_key": "runtime-key"}]
