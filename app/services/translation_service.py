"""
Translation Service

Translates a news article's German title and summary to English with
one model call per article. The English text doubles as what the
planner reads in citations.

Author:
NRW BI Platform
"""

from __future__ import annotations

from app.ai.json_parsing import parse_json_object
from app.config.openai import LazyOpenAIClient, get_chat_model


class TranslationResult(dict):
    """Translation payload with out-of-band fallback provenance."""

    def __init__(self, *args, succeeded: bool, **kwargs):

        super().__init__(*args, **kwargs)
        self.succeeded = succeeded


class TranslationService(LazyOpenAIClient):

    def __init__(
        self,
        client=None,
        model: str | None = None,
    ):

        super().__init__(client)

        self.model = model or get_chat_model()

    # =====================================================
    # Public
    # =====================================================

    def translate(
        self,
        title: str,
        summary: str | None,
    ) -> TranslationResult:
        """
        Translate title/summary to English.

        Falls back to the source text on anything that is not the
        expected JSON shape, rather than raising — a model returning
        prose must degrade the translation, not break the pipeline.
        """

        prompt = self._prompt(title, summary)

        response = self.client.responses.create(
            model=self.model,
            input=prompt,
            temperature=0,
        )

        return self._parse(
            response.output_text,
            fallback_title=title,
            fallback_summary=summary,
        )

    # =====================================================
    # Internal
    # =====================================================

    @staticmethod
    def _prompt(
        title: str,
        summary: str | None,
    ) -> str:

        return f"""
Translate the following German data-center news title and summary into
English. Respond with ONLY a JSON object: {{"title_en": "...", "summary_en": "..."}}

Title:
{title}

Summary:
{summary or ""}
"""

    @staticmethod
    def _parse(
        output_text: str,
        fallback_title: str,
        fallback_summary: str | None,
    ) -> TranslationResult:

        data = parse_json_object(output_text)

        if data is None:

            return TranslationResult(
                {
                    "title_en": fallback_title,
                    "summary_en": fallback_summary,
                },
                succeeded=False,
            )

        title_en = data.get("title_en")
        summary_en = data.get("summary_en")

        title_succeeded = isinstance(title_en, str) and bool(
            title_en.strip()
        )
        summary_succeeded = (
            not fallback_summary
            or (
                isinstance(summary_en, str)
                and bool(summary_en.strip())
            )
        )

        return TranslationResult(
            {
                "title_en": title_en or fallback_title,
                "summary_en": summary_en or fallback_summary,
            },
            succeeded=title_succeeded and summary_succeeded,
        )
