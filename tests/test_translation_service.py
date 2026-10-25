"""
TranslationService: one mini call per article, translating German title
+ summary to English. Doubles as what the planner reads. Defensive JSON
parsing — a model returning prose instead of JSON falls back to the
original text rather than raising.
"""

from app.services.translation_service import TranslationService


class _FakeResponsesClient:
    def __init__(self, output_text):
        self._output_text = output_text
        self.calls = []

    def create(self, model, input):
        self.calls.append((model, input))

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


def test_translate_falls_back_to_source_on_malformed_json():
    fake_client = _FakeOpenAI("Sorry, I cannot help with that.")
    service = TranslationService(client=fake_client, model="fake-model")

    result = service.translate("Titel auf Deutsch", "Zusammenfassung.")

    assert result == {
        "title_en": "Titel auf Deutsch",
        "summary_en": "Zusammenfassung.",
    }


def test_translate_handles_missing_summary():
    fake_client = _FakeOpenAI(
        '{"title_en": "Title", "summary_en": null}'
    )
    service = TranslationService(client=fake_client, model="fake-model")

    result = service.translate("Titel", None)

    assert result["title_en"] == "Title"
    assert result["summary_en"] is None
