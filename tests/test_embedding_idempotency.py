"""
EmbedNewsCommand must not re-embed unchanged text, must re-embed changed
text, and must tolerate a partially-embedded table (a row with a stored
hash but no embedding, e.g. from a run that died mid-batch).

Re-embed policy is a content hash of the exact embedded text (the English
translation), not a NULL-check — that catches a re-translated or edited
summary that a NULL-check would miss.
"""

import pytest

from app.commands.embed_news_command import EmbedNewsCommand
from app.database.models.news_article import NewsArticle
from app.services.embedding_service import EmbeddingService


class _FakeTranslation:
    """Returns a fixed English text unless told to return something
    else, so hash stability is fully controlled by the test."""

    def __init__(self, title_en="Title EN", summary_en="Summary EN"):
        self.title_en = title_en
        self.summary_en = summary_en
        self.calls = 0

    def translate(self, title, summary):
        self.calls += 1
        return {"title_en": self.title_en, "summary_en": self.summary_en}


class _FakeEmbedding:
    def __init__(self):
        self.embed_calls = 0

    def embed(self, text):
        self.embed_calls += 1
        return [0.1] * 1536

    content_hash = staticmethod(EmbeddingService.content_hash)


def _make_article(url="https://news.invalid/embed-test/"):
    return NewsArticle(
        id="e1a6b1f0-0000-0000-0000-000000000001",
        source="Test Feed",
        language="de",
        title="Titel",
        summary="Zusammenfassung.",
        url=url,
        processed=True,
    )


@pytest.mark.integration
def test_unchanged_text_is_not_re_embedded(db_session):
    db_session.add(_make_article())
    db_session.commit()

    translation = _FakeTranslation()
    embedding = _FakeEmbedding()

    EmbedNewsCommand(db_session, translation, embedding).execute()
    assert embedding.embed_calls == 1

    # Second run: translation returns the identical English text, so the
    # hash matches and the embedding call must be skipped.
    EmbedNewsCommand(db_session, translation, embedding).execute()
    assert embedding.embed_calls == 1, "unchanged text was re-embedded"


@pytest.mark.integration
def test_changed_translation_is_re_embedded(db_session):
    db_session.add(_make_article())
    db_session.commit()

    translation = _FakeTranslation()
    embedding = _FakeEmbedding()

    EmbedNewsCommand(db_session, translation, embedding).execute()
    assert embedding.embed_calls == 1

    translation.summary_en = "A different English summary now"

    EmbedNewsCommand(db_session, translation, embedding).execute()
    assert embedding.embed_calls == 2, "changed text was not re-embedded"


@pytest.mark.integration
def test_partial_embedding_state_is_tolerated(db_session):
    """
    A row with a stored hash but no embedding (a run that died mid-batch)
    must still be embedded on the next run, not skipped as 'already done'.
    """

    article = _make_article()
    article.embedding_hash = EmbeddingService.content_hash(
        "Title EN\nSummary EN"
    )
    article.embedding = None

    db_session.add(article)
    db_session.commit()

    translation = _FakeTranslation()
    embedding = _FakeEmbedding()

    result = EmbedNewsCommand(db_session, translation, embedding).execute()

    assert embedding.embed_calls == 1
    assert result["embedded"] == 1
