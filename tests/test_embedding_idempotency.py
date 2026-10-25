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

from contextlib import nullcontext

import pytest
from sqlalchemy.dialects import postgresql

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
    def __init__(self, model="fake-embedding-model-v1"):
        self.model = model
        self.embed_calls = 0

    def embed(self, text):
        self.embed_calls += 1
        return [0.1] * 1536

    content_hash = staticmethod(EmbeddingService.content_hash)


class _Rows:
    def __init__(self, articles):
        self.articles = articles

    def all(self):
        return self.articles


class _RecordingSession:
    """Small hermetic stand-in for batch-boundary tests."""

    def __init__(self, articles):
        self.articles = articles
        self.commits = 0

    def scalars(self, statement):
        return _Rows(self.articles)

    def begin_nested(self):
        return nullcontext()

    def commit(self):
        self.commits += 1


class _StatementCapturingSession:
    def __init__(self):
        self.statement = None

    def scalars(self, statement):
        self.statement = statement
        return _Rows([])

    def commit(self):
        pass


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


def test_embedding_is_deferred_but_explicitly_loaded_by_embed_command():
    assert NewsArticle.__mapper__.attrs.embedding.deferred is True

    session = _StatementCapturingSession()
    EmbedNewsCommand(
        session,
        _FakeTranslation(),
        _FakeEmbedding(),
    ).execute()

    sql = str(
        session.statement.compile(
            dialect=postgresql.dialect(),
        )
    )

    assert "iris_core.news_articles.embedding," in sql


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
def test_embedding_model_change_forces_re_embedding(db_session):
    """
    Changing OPENAI_EMBEDDING_MODEL (e.g. to a differently-dimensioned
    model) must not leave existing rows looking "unchanged" — the
    embedding model's name must be part of what decides re-work, the
    same way the translation model's name already is.
    """

    db_session.add(_make_article())
    db_session.commit()

    translation = _FakeTranslation()
    embedding = _FakeEmbedding()

    EmbedNewsCommand(db_session, translation, embedding).execute()
    assert embedding.embed_calls == 1

    embedding.model = "fake-embedding-model-v2"

    EmbedNewsCommand(db_session, translation, embedding).execute()
    assert embedding.embed_calls == 2, "an embedding model change was not caught"


@pytest.mark.integration
def test_partial_embedding_state_is_tolerated(db_session):
    """
    A row with a stored hash but no embedding (a run that died mid-batch)
    must still be embedded on the next run, not skipped as 'already done'.
    """

    translation = _FakeTranslation()
    embedding = _FakeEmbedding()

    article = _make_article()
    article.embedding_hash = EmbeddingService.content_hash(
        f"{article.title}\n{article.summary}\n"
        f"{translation.model}\n{embedding.model}"
    )
    article.embedding = None

    db_session.add(article)
    db_session.commit()

    result = EmbedNewsCommand(db_session, translation, embedding).execute()

    assert embedding.embed_calls == 1
    assert result["embedded"] == 1


def test_batch_commit_counts_work_not_skipped_loop_positions():
    translation = _FakeTranslation()
    embedding = _FakeEmbedding()

    skipped = _make_article(
        url="https://news.invalid/skipped/",
        id="e1a6b1f0-0000-0000-0000-000000000010",
        embedding=[0.1] * 1536,
    )
    skipped.embedding_hash = EmbeddingService.content_hash(
        f"{skipped.title}\n{skipped.summary}\n"
        f"{translation.model}\n{embedding.model}"
    )

    first = _make_article(
        url="https://news.invalid/first-work/",
        id="e1a6b1f0-0000-0000-0000-000000000011",
    )
    second = _make_article(
        url="https://news.invalid/second-work/",
        id="e1a6b1f0-0000-0000-0000-000000000012",
    )
    # Put the skipped row exactly on the old loop-index boundary. An
    # index-based implementation would miss the commit at position 2 and only
    # commit once at the end; work-based batching commits after ``second``.
    session = _RecordingSession([first, skipped, second])
    command = EmbedNewsCommand(session, translation, embedding)
    command.BATCH_SIZE = 2

    result = command.execute()

    assert result == {"embedded": 2, "skipped": 1, "failed": 0}
    assert session.commits == 2, "expected one batch commit plus the final commit"


def test_degraded_translation_is_retried_on_the_next_run():
    class _TranslationPayload(dict):
        def __init__(self, *args, succeeded, **kwargs):
            super().__init__(*args, **kwargs)
            self.succeeded = succeeded

    class _DegradesOnce:
        model = "fake-translation-model-v1"

        def __init__(self):
            self.calls = 0

        def translate(self, title, summary):
            self.calls += 1
            if self.calls == 1:
                return _TranslationPayload(
                    {"title_en": title, "summary_en": summary},
                    succeeded=False,
                )
            return _TranslationPayload(
                {"title_en": "Title EN", "summary_en": "Summary EN"},
                succeeded=True,
            )

    article = _make_article()
    session = _RecordingSession([article])
    translation = _DegradesOnce()
    embedding = _FakeEmbedding()
    command = EmbedNewsCommand(session, translation, embedding)

    first = command.execute()
    assert first["embedded"] == 1
    assert article.embedding_hash is None

    second = command.execute()

    assert second["embedded"] == 1
    assert translation.calls == 2
    assert article.embedding_hash is not None


def test_one_article_failure_does_not_abort_later_articles():
    class _FailsFirst:
        model = "fake-translation-model-v1"

        def __init__(self):
            self.calls = 0

        def translate(self, title, summary):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("rate limited")
            return {"title_en": "Title EN", "summary_en": "Summary EN"}

    articles = [
        _make_article(
            url="https://news.invalid/fails/",
            id="e1a6b1f0-0000-0000-0000-000000000020",
        ),
        _make_article(
            url="https://news.invalid/succeeds/",
            id="e1a6b1f0-0000-0000-0000-000000000021",
        ),
    ]
    session = _RecordingSession(articles)

    result = EmbedNewsCommand(
        session,
        _FailsFirst(),
        _FakeEmbedding(),
    ).execute()

    assert result == {"embedded": 1, "skipped": 0, "failed": 1}
    assert articles[1].embedding is not None
