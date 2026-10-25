"""The paid news-signals step must have observable readers."""

from types import SimpleNamespace

import pytest

import conftest
from app.ai.prompts.agentic_answer_prompt import AgenticAnswerPrompt
from app.ai.prompts.sufficiency_prompt import SufficiencyPrompt
from app.config.paths import DataPaths
from app.news.entity_extractor import EntityExtractor
from app.services.context_builder_service import ContextBuilderService
from app.services.news_intelligence_service import NewsIntelligenceService
from app.services.news_retrieval_service import NewsRetrievalService


def _article():
    return SimpleNamespace(
        id="a1",
        title="German title",
        title_en="English title",
        summary="German summary",
        summary_en="English summary",
        url="https://news.invalid/a1/",
        published_at="2026-10-25",
        source="Test Feed",
    )


def _signal():
    return SimpleNamespace(
        expansion=True,
        power=True,
        renewable=False,
        retrofit=False,
        investment=True,
        capacity_mw=50.0,
        confidence=0.9,
        city="Essen",
        company="Example GmbH",
    )


def test_retrieval_result_exposes_structured_news_signals():
    result = NewsRetrievalService._to_result(_article(), 0.1, _signal())

    assert result["signals"] == {
        "expansion": True,
        "power": True,
        "renewable": False,
        "retrofit": False,
        "investment": True,
        "capacity_mw": 50.0,
        "confidence": 0.9,
        "city": "Essen",
        "company": "Example GmbH",
    }


def test_verify_and_answer_prompts_receive_news_signals():
    article = {
        "id": "a1",
        "title": "English title",
        "summary_en": "English summary",
        "published_at": "2026-10-25",
        "source": "Test Feed",
        "signals": {
            "power": True,
            "investment": True,
            "capacity_mw": 50.0,
        },
    }

    verify_prompt = SufficiencyPrompt.build(
        {"question": "Any power signals?", "results": [article]}
    )
    answer_prompt = AgenticAnswerPrompt.build(
        {"question": "Any power signals?", "articles": [article]}
    )

    for prompt in (verify_prompt, answer_prompt):
        assert '"power": true' in prompt
        assert '"capacity_mw": 50.0' in prompt


def test_news_signal_kpi_counts_signal_rows_not_facility_matches():
    service = NewsIntelligenceService.__new__(NewsIntelligenceService)
    service.repository = SimpleNamespace(
        get_signal_count=lambda: 7,
        get_matches=lambda: [object()] * 99,
    )

    assert service.get_signal_count() == 7


def test_generic_context_dispatcher_rejects_string_news_builder():
    with pytest.raises(ValueError, match="Unknown context type: news"):
        ContextBuilderService().build(
            "news",
            news=[],
            question="question",
        )


def test_free_entity_extractor_remains_default_but_is_injectable(tmp_path):
    injected = object()

    extractor = EntityExtractor(
        paths=DataPaths(tmp_path),
        extractor=injected,
    )

    assert extractor.extractor is injected


def test_not_live_marker_expression_never_opts_into_paid_tests():
    requested = getattr(conftest, "_live_tests_requested", None)

    assert callable(requested)
    assert requested("live") is True
    assert requested("not live") is False
    assert requested("") is False
