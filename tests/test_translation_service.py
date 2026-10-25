"""
TranslationService: one mini call per article, translating German title
+ summary to English. Doubles as what the planner reads. Defensive JSON
parsing — a model returning prose instead of JSON falls back to the
original text rather than raising.
"""

import pytest

from app.services.translation_service import TranslationService


class _FakeResponsesClient:
    def __init__(self, output_text):
        self._output_text = output_text
        self.calls = []

    def create(self, model, input, **kwargs):
        self.calls.append((model, input, kwargs))

        class _Response:
            def __init__(self, text):
                self.output_text = text

        return _Response(self._output_text)


class _FakeOpenAI:
    def __init__(self, output_text):
        self.responses = _FakeResponsesClient(output_text)


def test_translate_parses_json_response():
    fake_client = _FakeOpenAI(
        '{"title_en": "AI boom meets power shortage", '
        '"summary_en": "Data centers feel the power shortage."}'
    )
    service = TranslationService(client=fake_client, model="fake-model")

    result = service.translate(
        "KI-Boom trifft auf Stromengpaesse",
        "Rechenzentren spueren den Strommangel.",
    )

    assert result == {
        "title_en": "AI boom meets power shortage",
        "summary_en": "Data centers feel the power shortage.",
    }


def test_translate_strips_markdown_code_fences():
    """
    The real gpt-4.1-mini response wraps JSON in a ```json ... ``` fence
    even when explicitly told to return only JSON. That must still parse,
    not fall back to the untranslated source text.
    """

    fake_client = _FakeOpenAI(
        '```json\n{\n  "title_en": "AI Boom Meets Power Shortages",\n'
        '  "summary_en": "Data centers under pressure."\n}\n```'
    )
    service = TranslationService(client=fake_client, model="fake-model")

    result = service.translate(
        "KI-Boom trifft auf Stromengpaesse", "Rechenzentren unter Druck."
    )

    assert result == {
        "title_en": "AI Boom Meets Power Shortages",
        "summary_en": "Data centers under pressure.",
    }


def test_translate_falls_back_to_source_on_malformed_json():
    fake_client = _FakeOpenAI("Sorry, I cannot help with that.")
    service = TranslationService(client=fake_client, model="fake-model")

    result = service.translate("Titel auf Deutsch", "Zusammenfassung.")

    assert result == {
        "title_en": "Titel auf Deutsch",
        "summary_en": "Zusammenfassung.",
    }


def test_translate_requests_deterministic_output():
    """
    Against the real API, sampling noise at the default temperature made
    the English text for an *unchanged* German article differ run to
    run, which defeated the embedding content-hash idempotency check
    (36/40 articles spuriously "changed" on a second run with no source
    edit). temperature=0 makes repeated translations of the same input
    stable, which is what idempotency actually depends on.
    """

    fake_client = _FakeOpenAI('{"title_en": "T", "summary_en": "S"}')
    service = TranslationService(client=fake_client, model="fake-model")

    service.translate("Titel", "Zusammenfassung.")

    _, _, kwargs = fake_client.responses.calls[0]
    assert kwargs.get("temperature") == 0


def test_translate_handles_missing_summary():
    fake_client = _FakeOpenAI(
        '{"title_en": "Title", "summary_en": null}'
    )
    service = TranslationService(client=fake_client, model="fake-model")

    result = service.translate("Titel", None)

    assert result["title_en"] == "Title"
    assert result["summary_en"] is None


def test_construction_does_not_require_an_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    service = TranslationService()

    with pytest.raises(Exception):
        service.translate("Titel", "Zusammenfassung")
