"""
OpenAIExtractor: replaces MockExtractor's keyword matching (English
lists against a 100% German corpus — every expansion/power/renewable/
retrofit signal was False for all 40 real articles) with one structured
model call per article. Same output shape as MockExtractor so it is a
drop-in for EntityExtractor/EntityMatcher. Hermetic: the client is
injected and stubbed.
"""

import json

import pytest

from app.extractors.openai_extractor import (
    ExtractionFailed,
    OpenAIExtractor,
)


class _FakeResponsesClient:
    def __init__(self, output_text):
        self._output_text = output_text
        self.calls = []

    def create(self, model, input, **kwargs):
        self.calls.append({"model": model, "input": input, **kwargs})

        class _Response:
            pass

        response = _Response()
        response.output_text = self._output_text
        return response


class _FakeOpenAI:
    def __init__(self, output_text):
        self.responses = _FakeResponsesClient(output_text)


ARTICLE = {
    "id": "a1",
    "url": "https://news.invalid/a1/",
    "title": "KI-Boom trifft auf Stromengpaesse und Nachhaltigkeitspflicht",
    "summary": (
        "Eine aktuelle Studie zeigt, dass Microsoft seine "
        "Rechenzentren um 50 MW erweitert."
    ),
}


def test_extract_parses_structured_signals():
    fake_client = _FakeOpenAI(
        '{"company": "Microsoft", "facility": "", "city": "", '
        '"country": "Germany", "investment_signal": true, '
        '"expansion_signal": true, "retrofit_signal": false, '
        '"renewable_signal": false, "power_signal": true, '
        '"capacity_mw": 50, "confidence": 0.9}'
    )
    extractor = OpenAIExtractor(client=fake_client, model="fake-model")

    result = extractor.extract(ARTICLE)

    assert result["article_id"] == "a1"
    assert result["article_url"] == "https://news.invalid/a1/"
    assert result["company"] == "Microsoft"
    assert result["expansion_signal"] is True
    assert result["power_signal"] is True
    assert result["retrofit_signal"] is False
    assert result["capacity_mw"] == 50
    assert result["confidence"] == 0.9


def test_extract_strips_markdown_code_fences():
    fake_client = _FakeOpenAI(
        '```json\n{"company": "", "investment_signal": false, '
        '"expansion_signal": false, "retrofit_signal": false, '
        '"renewable_signal": false, "power_signal": false}\n```'
    )
    extractor = OpenAIExtractor(client=fake_client, model="fake-model")

    result = extractor.extract(ARTICLE)

    assert result["expansion_signal"] is False


def test_extract_raises_on_malformed_response():
    fake_client = _FakeOpenAI("Sorry, I can't help with that.")
    extractor = OpenAIExtractor(client=fake_client, model="fake-model")

    with pytest.raises(ExtractionFailed):
        extractor.extract(ARTICLE)


def test_extract_raises_on_client_exception():
    class _ExplodingClient:
        class responses:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("network down")

    extractor = OpenAIExtractor(client=_ExplodingClient(), model="fake-model")

    with pytest.raises(ExtractionFailed):
        extractor.extract(ARTICLE)


def test_extract_coerces_a_non_numeric_capacity_mw_to_none():
    """
    A model answering "capacity_mw": "50 MW" (prose instead of a bare
    number) must not reach the caller as a string — NewsSignal.capacity_mw
    is a Float column, and ExtractNewsSignalsCommand commits once at the
    end of a 40-article run, so one bad value there would lose every
    extraction in that run.
    """

    fake_client = _FakeOpenAI(
        '{"company": "", "capacity_mw": "50 MW", "confidence": "high"}'
    )
    extractor = OpenAIExtractor(client=fake_client, model="fake-model")

    result = extractor.extract(ARTICLE)

    assert result["capacity_mw"] is None
    assert result["confidence"] == 0.0


def test_extract_coerces_a_numeric_string_capacity_mw():
    fake_client = _FakeOpenAI(
        '{"company": "", "capacity_mw": "50", "confidence": "0.8"}'
    )
    extractor = OpenAIExtractor(client=fake_client, model="fake-model")

    result = extractor.extract(ARTICLE)

    assert result["capacity_mw"] == 50.0
    assert result["confidence"] == 0.8


def test_extract_does_not_treat_the_string_false_as_a_true_signal():
    fake_client = _FakeOpenAI(
        '{"investment_signal": "false", "expansion_signal": "false", '
        '"retrofit_signal": "false", "renewable_signal": "false", '
        '"power_signal": "false"}'
    )
    extractor = OpenAIExtractor(client=fake_client, model="fake-model")

    result = extractor.extract(ARTICLE)

    assert result["investment_signal"] is False
    assert result["expansion_signal"] is False
    assert result["retrofit_signal"] is False
    assert result["renewable_signal"] is False
    assert result["power_signal"] is False


@pytest.mark.parametrize(
    ("capacity", "confidence", "expected_capacity"),
    [
        ("NaN", "Infinity", None),
        ("-5", "1.5", None),
    ],
)
def test_extract_rejects_non_finite_or_out_of_range_numbers(
    capacity,
    confidence,
    expected_capacity,
):
    fake_client = _FakeOpenAI(
        json.dumps(
            {"capacity_mw": capacity, "confidence": confidence}
        )
    )
    extractor = OpenAIExtractor(client=fake_client, model="fake-model")

    result = extractor.extract(ARTICLE)

    assert result["capacity_mw"] is expected_capacity
    assert result["confidence"] == 0.0


def test_construction_does_not_require_an_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    extractor = OpenAIExtractor()

    # Construction remains lazy; the first paid call reports failure
    # explicitly instead of fabricating an all-False extraction.
    with pytest.raises(ExtractionFailed):
        extractor.extract(ARTICLE)


def test_extract_requests_deterministic_output():
    fake_client = _FakeOpenAI('{"company": ""}')
    extractor = OpenAIExtractor(client=fake_client, model="fake-model")

    extractor.extract(ARTICLE)

    assert fake_client.responses.calls[0]["temperature"] == 0
