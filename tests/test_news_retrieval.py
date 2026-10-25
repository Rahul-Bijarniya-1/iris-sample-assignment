"""
NewsRetrievalService.search(): cosine ranking, filters, provenance, and
graceful degradation. The embedder is stubbed so these tests never touch
the network; ranking is exercised against a real pgvector column so the
cosine_distance() ordering itself is proven, not assumed.
"""

import pytest

from app.database.models.news_article import NewsArticle
from app.services.news_retrieval_service import NewsRetrievalService


DIM = 1536


def _vector(lead: float, index: int = 0) -> list[float]:
    """A unit-ish vector with `lead` in position `index`, zero elsewhere."""

    v = [0.0] * DIM
    v[index] = lead
    return v


class _FakeEmbedding:
    def __init__(self, vector):
        self._vector = vector

    def embed(self, text):
        return self._vector


class _FailingEmbedding:
    def embed(self, text):
        raise RuntimeError("no OPENAI_API_KEY")


def _article(id_, url, title, embedding, language="de", **extra):
    return NewsArticle(
        id=id_,
        source="Test Feed",
        language=language,
        title=title,
        summary="irrelevant",
        url=url,
        processed=True,
        embedding=embedding,
        **extra,
    )


@pytest.mark.integration
def test_search_ranks_the_closest_vector_first(db_session):
    db_session.add_all(
        [
            _article(
                "a0000000-0000-0000-0000-000000000001",
                "https://news.invalid/close/",
                "Close article",
                _vector(1.0, index=0),
                title_en="Close article",
            ),
            _article(
                "a0000000-0000-0000-0000-000000000002",
                "https://news.invalid/far/",
                "Far article",
                _vector(1.0, index=1),
                title_en="Far article",
            ),
        ]
    )
    db_session.commit()

    service = NewsRetrievalService(
        db_session,
        embedding_service=_FakeEmbedding(_vector(1.0, index=0)),
    )

    results = service.search("query text", k=10)

    assert [r["title"] for r in results] == [
        "Close article",
        "Far article",
    ]
    assert results[0]["score"] > results[1]["score"]


@pytest.mark.integration
def test_search_returns_provenance_fields(db_session):
    db_session.add(
        _article(
            "a0000000-0000-0000-0000-000000000003",
            "https://news.invalid/prov/",
            "Original Titel",
            _vector(1.0),
            title_en="Translated Title",
            summary_en="Translated summary",
        )
    )
    db_session.commit()

    service = NewsRetrievalService(
        db_session,
        embedding_service=_FakeEmbedding(_vector(1.0)),
    )

    results = service.search("query text", k=10)

    assert len(results) == 1
    result = results[0]

    assert result["title"] == "Translated Title"
    assert result["title_de"] == "Original Titel"
    assert result["summary_en"] == "Translated summary"
    assert result["url"] == "https://news.invalid/prov/"
    assert "published_at" in result
    assert "score" in result
    assert result["source"] == "Test Feed"


@pytest.mark.integration
def test_search_ignores_articles_without_an_embedding(db_session):
    db_session.add_all(
        [
            NewsArticle(
                id="a0000000-0000-0000-0000-000000000004",
                source="Test Feed",
                language="de",
                title="Not embedded yet",
                summary="irrelevant",
                url="https://news.invalid/none/",
                processed=True,
                embedding=None,
            ),
            _article(
                "a0000000-0000-0000-0000-000000000005",
                "https://news.invalid/embedded/",
                "Embedded article",
                _vector(1.0),
            ),
        ]
    )
    db_session.commit()

    service = NewsRetrievalService(
        db_session,
        embedding_service=_FakeEmbedding(_vector(1.0)),
    )

    results = service.search("query text", k=10)

    assert [r["title"] for r in results] == ["Embedded article"]


@pytest.mark.integration
def test_search_respects_a_language_filter(db_session):
    db_session.add_all(
        [
            _article(
                "a0000000-0000-0000-0000-000000000006",
                "https://news.invalid/de/",
                "German article",
                _vector(1.0),
                language="de",
            ),
            _article(
                "a0000000-0000-0000-0000-000000000007",
                "https://news.invalid/en/",
                "English article",
                _vector(1.0),
                language="en",
            ),
        ]
    )
    db_session.commit()

    service = NewsRetrievalService(
        db_session,
        embedding_service=_FakeEmbedding(_vector(1.0)),
    )

    results = service.search(
        "query text", k=10, filters={"language": "de"}
    )

    assert [r["title"] for r in results] == ["German article"]


@pytest.mark.integration
def test_search_degrades_to_empty_list_on_embedder_failure(db_session):
    """
    Missing OPENAI_API_KEY (or any embedder failure) must degrade to an
    empty result, never raise — the dashboard must never end up worse
    than the pre-RAG keyword path.
    """

    service = NewsRetrievalService(
        db_session,
        embedding_service=_FailingEmbedding(),
    )

    assert service.search("query text", k=10) == []


@pytest.mark.integration
def test_search_degrades_to_empty_list_with_no_api_key_at_all(
    db_session, monkeypatch
):
    """
    The claim this guards end-to-end, not via an injected stub: a real
    EmbeddingService(), with OPENAI_API_KEY genuinely unset, must still
    make search() degrade to [] rather than raise during construction
    (OpenAIExtractor() previously built its OpenAI() client eagerly,
    which raised before search()'s try/except ever ran).
    """

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    service = NewsRetrievalService(db_session)

    assert service.search("query text", k=10) == []
