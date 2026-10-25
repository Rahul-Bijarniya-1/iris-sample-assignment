"""
AIRecommendationService.generate() must accept a per-call model override,
so AgenticRagService can use the configured mini model for plan/verify
steps and a separate, more capable model for the final answer — without
constructing a second service instance per call. The client is
injectable so this never touches the network.
"""

import pytest

from app.services.ai_recommendation_service import AIRecommendationService


class _FakeResponsesClient:
    def __init__(self):
        self.calls = []

    def create(self, model, input):
        self.calls.append((model, input))

        class _Response:
            output_text = "ok"

        return _Response()


class _FakeOpenAI:
    def __init__(self):
        self.responses = _FakeResponsesClient()


def test_generate_uses_the_default_model_when_none_given():
    fake_client = _FakeOpenAI()
    service = AIRecommendationService(
        client=fake_client, model="default-model"
    )

    service.generate("prompt")

    assert fake_client.responses.calls == [("default-model", "prompt")]


def test_generate_uses_an_override_model_when_given():
    fake_client = _FakeOpenAI()
    service = AIRecommendationService(
        client=fake_client, model="default-model"
    )

    service.generate("prompt", model="override-model")

    assert fake_client.responses.calls == [("override-model", "prompt")]


def test_construction_does_not_require_an_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    service = AIRecommendationService()

    with pytest.raises(Exception):
        service.generate("prompt")
