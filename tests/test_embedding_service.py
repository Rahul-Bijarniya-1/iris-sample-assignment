"""
EmbeddingService: a thin, env-driven wrapper over the OpenAI embeddings
API, mirroring AIRecommendationService's shape. The OpenAI client is
injected so these tests never touch the network.
"""

import hashlib

import pytest

from app.services.embedding_service import EmbeddingService


class _FakeEmbeddingsClient:
    def __init__(self, vector):
        self._vector = vector
        self.calls = []

    def create(self, model, input):
        self.calls.append((model, input))

        class _Data:
            def __init__(self, embedding):
                self.embedding = embedding

        class _Response:
            def __init__(self, embedding):
                self.data = [_Data(embedding)]

        return _Response(self._vector)


class _FakeOpenAI:
    def __init__(self, vector):
        self.embeddings = _FakeEmbeddingsClient(vector)


def test_embed_returns_the_vector_from_the_api():
    fake_client = _FakeOpenAI([0.1, 0.2, 0.3])
    service = EmbeddingService(client=fake_client, model="fake-model")

    vector = service.embed("hello world")

    assert vector == [0.1, 0.2, 0.3]
    assert fake_client.embeddings.calls == [("fake-model", "hello world")]


def test_content_hash_is_deterministic_sha256():
    text = "Stromengpaesse treffen Rechenzentren"

    expected = hashlib.sha256(text.encode("utf-8")).hexdigest()

    assert EmbeddingService.content_hash(text) == expected


def test_content_hash_differs_for_different_text():
    assert EmbeddingService.content_hash("a") != EmbeddingService.content_hash("b")


def test_construction_does_not_require_an_api_key(monkeypatch):
    """
    NewsRetrievalService.search() is documented to degrade to [] when
    OPENAI_API_KEY is missing — but EmbeddingService() previously built
    the real OpenAI() client in __init__, which raises before search()
    ever gets a chance to catch anything. The client must be built
    lazily so a missing key surfaces inside the try/except that is
    actually meant to catch it.
    """

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    service = EmbeddingService()

    with pytest.raises(Exception):
        service.embed("text")
