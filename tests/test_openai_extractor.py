"""
OpenAIExtractor: replaces MockExtractor's keyword matching (English
lists against a 100% German corpus — every expansion/power/renewable/
retrofit signal was False for all 40 real articles) with one structured
model call per article. Same output shape as MockExtractor so it is a
drop-in for EntityExtractor/EntityMatcher. Hermetic: the client is
injected and stubbed.
"""

import pytest

from app.extractors.openai_extractor import OpenAIExtractor


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


def test_extract_degrades_to_a_safe_default_on_malformed_response():
    fake_client = _FakeOpenAI("Sorry, I can't help with that.")
    extractor = OpenAIExtractor(client=fake_client, model="fake-model")

    result = extractor.extract(ARTICLE)

    assert result["article_id"] == "a1"
    assert result["company"] == ""
    assert result["expansion_signal"] is False
    assert result["power_signal"] is False
    assert result["confidence"] == 0.0


def test_extract_degrades_on_client_exception():
    class _ExplodingClient:
        class responses:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("network down")

    extractor = OpenAIExtractor(client=_ExplodingClient(), model="fake-model")

    result = extractor.extract(ARTICLE)

    assert result["article_id"] == "a1"
    assert result["expansion_signal"] is False


def test_construction_does_not_require_an_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    extractor = OpenAIExtractor()

    # extract() itself degrades gracefully (see
    # test_extract_degrades_on_client_exception) — this only guards
    # that __init__ doesn't raise before that path ever runs.
    result = extractor.extract(ARTICLE)

    assert result["article_id"] == "a1"
    assert result["expansion_signal"] is False


def test_extract_requests_deterministic_output():
    fake_client = _FakeOpenAI('{"company": ""}')
    extractor = OpenAIExtractor(client=fake_client, model="fake-model")

    extractor.extract(ARTICLE)

    assert fake_client.responses.calls[0]["temperature"] == 0
