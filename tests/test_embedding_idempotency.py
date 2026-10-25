"""
EmbedNewsCommand must not re-translate or re-embed unchanged text, must
reprocess changed text, and must tolerate a partially-embedded table
(a row with a stored hash but no embedding, e.g. from a run that died
mid-batch).

The hash gates on the *source* (German title + summary + the
translation model's name) rather than the translated English output.
Verified against the live API: even at temperature=0, gpt-4.1-mini does
not reproduce byte-identical English text run to run (measured 35-36 of
40 unchanged articles "changed" under a hash of the translated text) —
hashing the source is what actually makes a re-run a no-op, and a
translation-model bump is still caught by naming the model in the hash
input.
"""

import pytest

from app.commands.embed_news_command import EmbedNewsCommand
from app.database.models.news_article import NewsArticle
from app.services.embedding_service import EmbeddingService


class _FakeTranslation:
    model = "fake-translation-model-v1"

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


def _make_article(url="https://news.invalid/embed-test/", **kwargs):
    defaults = dict(
        id="e1a6b1f0-0000-0000-0000-000000000001",
        source="Test Feed",
        language="de",
        title="Titel",
        summary="Zusammenfassung.",
        url=url,
        processed=True,
    )
    defaults.update(kwargs)
    return NewsArticle(**defaults)


@pytest.mark.integration
def test_unchanged_text_is_not_re_embedded(db_session):
    db_session.add(_make_article())
    db_session.commit()

    translation = _FakeTranslation()
    embedding = _FakeEmbedding()

    EmbedNewsCommand(db_session, translation, embedding).execute()
    assert embedding.embed_calls == 1
    assert translation.calls == 1

    # Second run: same source, same translation model — must be a
    # complete no-op, not just skip the embed call.
    EmbedNewsCommand(db_session, translation, embedding).execute()
    assert embedding.embed_calls == 1, "unchanged text was re-embedded"
    assert translation.calls == 1, "unchanged text was re-translated"


@pytest.mark.integration
def test_edited_summary_is_re_embedded(db_session):
    article = _make_article()
    db_session.add(article)
    db_session.commit()

    translation = _FakeTranslation()
    embedding = _FakeEmbedding()

    EmbedNewsCommand(db_session, translation, embedding).execute()
    assert embedding.embed_calls == 1

    article.summary = "Eine bearbeitete Zusammenfassung."
    db_session.commit()

    EmbedNewsCommand(db_session, translation, embedding).execute()
    assert embedding.embed_calls == 2, "an edited summary was not re-embedded"


@pytest.mark.integration
def test_translation_model_change_forces_re_embedding(db_session):
    """
    A deliberate translation-model/prompt upgrade must still be caught
    even though the German source did not change, since the English
    text the planner reads would differ.
    """

    db_session.add(_make_article())
    db_session.commit()

    translation = _FakeTranslation()
    embedding = _FakeEmbedding()

    EmbedNewsCommand(db_session, translation, embedding).execute()
    assert embedding.embed_calls == 1

    translation.model = "fake-translation-model-v2"

    EmbedNewsCommand(db_session, translation, embedding).execute()
    assert embedding.embed_calls == 2, "a translation model change was not caught"


@pytest.mark.integration
def test_partial_embedding_state_is_tolerated(db_session):
    """
    A row with a stored hash but no embedding (a run that died mid-batch)
    must still be embedded on the next run, not skipped as 'already done'.
    """

    translation = _FakeTranslation()

    article = _make_article()
    article.embedding_hash = EmbeddingService.content_hash(
        f"{article.title}\n{article.summary}\n{translation.model}"
    )
    article.embedding = None

    db_session.add(article)
    db_session.commit()

    embedding = _FakeEmbedding()

    result = EmbedNewsCommand(db_session, translation, embedding).execute()

    assert embedding.embed_calls == 1
    assert result["embedded"] == 1
