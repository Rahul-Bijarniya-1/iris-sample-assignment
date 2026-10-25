"""
Opt-in live tests against the real OpenAI API.

Never run by default — see conftest.py's pytest_collection_modifyitems,
which skips every `live`-marked test unless invoked with
`pytest -m live`. These exist to catch response-shape drift (a new SDK
version, a changed field name) that a stubbed client can never surface
— the exact class of defect that two of this feature's real bugs
(FINDINGS.md #9, #10) turned out to be, both found only by running
against the live API.

Skips (rather than fails) with no OPENAI_API_KEY, so CI without a key
configured doesn't need to special-case this file.
"""

import os

import pytest

from app.services.ai_recommendation_service import AIRecommendationService
from app.services.embedding_service import EmbeddingService


pytestmark = pytest.mark.live


def _require_api_key():
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is not set")


def test_generate_returns_a_non_empty_string():
    _require_api_key()

    service = AIRecommendationService()

    result = service.generate("Reply with exactly the word: OK")

    assert isinstance(result, str)
    assert len(result) > 0


def test_embed_returns_a_1536_dimension_vector():
    _require_api_key()

    service = EmbeddingService()

    vector = service.embed("Rechenzentrum in Nordrhein-Westfalen")

    assert isinstance(vector, list)
    assert len(vector) == 1536
    assert all(isinstance(value, float) for value in vector)
