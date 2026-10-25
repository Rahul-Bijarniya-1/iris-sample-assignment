"""
Translation Service

Translates a news article's German title and summary to English with
one model call per article. The English text doubles as what the
planner reads in citations.

Author:
NRW BI Platform
"""

from __future__ import annotations

import json
import os

from openai import OpenAI


class TranslationService:

    def __init__(
        self,
        client=None,
        model: str | None = None,
    ):

        self.client = client or OpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )

        self.model = model or os.getenv(
            "OPENAI_MODEL",
            "gpt-4.1-mini",
        )

    # =====================================================
    # Public
    # =====================================================

    def translate(
        self,
        title: str,
        summary: str | None,
    ) -> dict:
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
    ) -> dict:

        try:

            data = json.loads(output_text.strip())

        except (json.JSONDecodeError, AttributeError):

            return {
                "title_en": fallback_title,
                "summary_en": fallback_summary,
            }

        if not isinstance(data, dict):

            return {
                "title_en": fallback_title,
                "summary_en": fallback_summary,
            }

        return {
            "title_en": data.get("title_en") or fallback_title,
            "summary_en": data.get("summary_en", fallback_summary),
        }
