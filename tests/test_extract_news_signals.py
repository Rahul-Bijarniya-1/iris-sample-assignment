"""
ExtractNewsSignalsCommand: runs an extractor over every news article
and loads the result into news_signals, idempotently (a second run
replaces rather than duplicates each article's row).
"""

import pytest

from app.commands.extract_news_signals_command import (
    ExtractNewsSignalsCommand,
)
from app.database.models.news_article import NewsArticle
from app.database.models.news_signal import NewsSignal
from app.extractors.openai_extractor import ExtractionFailed


class _FakeExtractor:
    def __init__(self, result_by_id=None):
        self.result_by_id = result_by_id or {}
        self.calls = []

    def extract(self, article):
        self.calls.append(article["id"])

        return self.result_by_id.get(
            article["id"],
            {
                "article_id": article["id"],
                "article_url": article.get("url"),
                "company": "",
                "facility": "",
                "city": "",
                "country": "Germany",
                "investment_signal": False,
                "expansion_signal": False,
                "retrofit_signal": False,
                "renewable_signal": False,
                "power_signal": False,
                "capacity_mw": None,
                "confidence": 0.0,
            },
        )


def _article(id_="a1"):
    return NewsArticle(
        id=id_,
        source="Test Feed",
        language="de",
        title="Titel",
        summary="Zusammenfassung",
        url=f"https://news.invalid/{id_}/",
        processed=True,
    )


def test_failed_extraction_does_not_delete_or_replace_existing_signal():
    class _ScalarResult:
        def all(self):
            return [_article()]

    class _Session:
        def __init__(self):
            self.executed = []
            self.added = []
            self.commits = 0

        def scalars(self, statement):
            return _ScalarResult()

        def execute(self, statement):
            self.executed.append(statement)

        def add(self, signal):
            self.added.append(signal)

        def commit(self):
            self.commits += 1

    class _FailedExtractor:
        def extract(self, article):
            raise ExtractionFailed("model unavailable")

    session = _Session()

    result = ExtractNewsSignalsCommand(
        session,
        _FailedExtractor(),
    ).execute()

    assert result == {"loaded": 0, "failed": 1}
    assert session.executed == []
    assert session.added == []
    assert session.commits == 1


@pytest.mark.integration
def test_loads_signals_for_every_article(db_session):
    db_session.add_all([_article("a1"), _article("a2")])
    db_session.commit()

    extractor = _FakeExtractor(
        {
            "a1": {
                "article_id": "a1",
                "article_url": "https://news.invalid/a1/",
                "company": "Microsoft",
                "facility": "",
                "city": "Essen",
                "country": "Germany",
                "investment_signal": True,
                "expansion_signal": True,
                "retrofit_signal": False,
                "renewable_signal": False,
                "power_signal": True,
                "capacity_mw": 50.0,
                "confidence": 0.9,
            }
        }
    )

    result = ExtractNewsSignalsCommand(db_session, extractor).execute()

    assert result["loaded"] == 2
    assert sorted(extractor.calls) == ["a1", "a2"]

    signal = (
        db_session.query(NewsSignal)
        .filter_by(article_id="a1")
        .one()
    )

    assert signal.company == "Microsoft"
    assert signal.expansion is True
    assert signal.power is True
    assert signal.retrofit is False
    assert signal.capacity_mw == 50.0
    assert signal.confidence == 0.9


@pytest.mark.integration
def test_a_failure_partway_through_does_not_lose_earlier_progress(
    db_session,
):
    """
    ExtractNewsSignalsCommand previously committed once at the very
    end: one bad extraction on article 40 of 40 would lose all 39 paid
    calls that came before it. Batching commits (same pattern as
    EmbedNewsCommand) means earlier rows survive a later failure.
    """

    db_session.add_all(
        [_article("a1"), _article("a2"), _article("a3")]
    )
    db_session.commit()

    class _FailsOnThird:
        calls = 0

        def extract(self, article):
            self.calls += 1

            if article["id"] == "a3":
                raise RuntimeError("rate limited")

            return {
                "article_id": article["id"],
                "article_url": article.get("url"),
                "company": "",
                "facility": "",
                "city": "",
                "country": "Germany",
                "investment_signal": False,
                "expansion_signal": False,
                "retrofit_signal": False,
                "renewable_signal": False,
                "power_signal": False,
                "capacity_mw": None,
                "confidence": 0.0,
            }

    command = ExtractNewsSignalsCommand(
        db_session, _FailsOnThird()
    )
    command.BATCH_SIZE = 2

    with pytest.raises(RuntimeError):
        command.execute()

    # a1 landed in the first batch commit; a3's failure must not have
    # rolled it back.
    assert (
        db_session.query(NewsSignal)
        .filter_by(article_id="a1")
        .count()
        == 1
    )


@pytest.mark.integration
def test_a_second_run_replaces_rather_than_duplicates(db_session):
    db_session.add(_article("a1"))
    db_session.commit()

    extractor = _FakeExtractor()

    ExtractNewsSignalsCommand(db_session, extractor).execute()
    ExtractNewsSignalsCommand(db_session, extractor).execute()

    count = (
        db_session.query(NewsSignal)
        .filter_by(article_id="a1")
        .count()
    )

    assert count == 1


@pytest.mark.integration
def test_failed_extraction_preserves_existing_signal_and_is_reported(
    db_session,
):
    db_session.add(_article("a1"))
    db_session.add(
        NewsSignal(
            article_id="a1",
            expansion=True,
            power=False,
            renewable=False,
            retrofit=False,
            investment=True,
            capacity_mw=25.0,
            confidence=0.8,
            city="Essen",
            company="Existing Company",
        )
    )
    db_session.commit()

    class _FailedExtractor:
        def extract(self, article):
            raise ExtractionFailed("model unavailable")

    result = ExtractNewsSignalsCommand(
        db_session,
        _FailedExtractor(),
    ).execute()

    signal = db_session.query(NewsSignal).filter_by(article_id="a1").one()

    assert result == {"loaded": 0, "failed": 1}
    assert signal.company == "Existing Company"
    assert signal.expansion is True
    assert signal.capacity_mw == 25.0


@pytest.mark.integration
def test_overlong_company_and_city_are_truncated(db_session):
    db_session.add(_article("a1"))
    db_session.commit()

    extractor = _FakeExtractor(
        {
            "a1": {
                "article_id": "a1",
                "article_url": "https://news.invalid/a1/",
                "company": "C" * 300,
                "facility": "",
                "city": "X" * 150,
                "country": "Germany",
                "investment_signal": False,
                "expansion_signal": False,
                "retrofit_signal": False,
                "renewable_signal": False,
                "power_signal": False,
                "capacity_mw": None,
                "confidence": 0.5,
            }
        }
    )

    result = ExtractNewsSignalsCommand(db_session, extractor).execute()
    signal = db_session.query(NewsSignal).filter_by(article_id="a1").one()

    assert result == {"loaded": 1, "failed": 0}
    assert signal.company == "C" * 255
    assert signal.city == "X" * 100
