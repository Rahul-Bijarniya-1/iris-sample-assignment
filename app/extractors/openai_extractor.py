"""
OpenAI Extractor

Replaces MockExtractor's English keyword matching — which scored every
expansion/power/renewable/retrofit signal False against the real,
100% German corpus — with one structured, German-aware model call per
article. Same output shape as MockExtractor, so it is a drop-in for
anything that calls .extract(article).

Author:
NRW BI Platform
"""

from __future__ import annotations

import math

from app.ai.json_parsing import parse_json_object
from app.config.openai import LazyOpenAIClient, get_chat_model


class ExtractionFailed(RuntimeError):
    """The model call did not produce a trustworthy extraction."""


class OpenAIExtractor(LazyOpenAIClient):

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

    def extract(
        self,
        article: dict,
    ) -> dict:

        data = self._call_model(article)

        if data is None:

            raise ExtractionFailed("model returned malformed extraction JSON")

        confidence = self._as_float(
            data.get("confidence"),
            minimum=0.0,
            maximum=1.0,
        )

        return {
            "article_id": article.get("id"),
            "article_url": article.get("url"),
            "company": data.get("company") or "",
            "facility": data.get("facility") or "",
            "city": data.get("city") or "",
            "country": data.get("country") or "Germany",
            "investment_signal": self._as_bool(
                data.get("investment_signal", False)
            ),
            "expansion_signal": self._as_bool(
                data.get("expansion_signal", False)
            ),
            "retrofit_signal": self._as_bool(
                data.get("retrofit_signal", False)
            ),
            "renewable_signal": self._as_bool(
                data.get("renewable_signal", False)
            ),
            "power_signal": self._as_bool(
                data.get("power_signal", False)
            ),
            "capacity_mw": self._as_float(
                data.get("capacity_mw"), minimum=0.0
            ),
            "confidence": confidence if confidence is not None else 0.0,
        }

    @staticmethod
    def _as_bool(
        value,
    ) -> bool:

        if isinstance(value, bool):

            return value

        if isinstance(value, str):

            return value.strip().lower() in {
                "1",
                "on",
                "true",
                "yes",
            }

        return False

    @staticmethod
    def _as_float(
        value,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float | None:
        """
        NewsSignal.capacity_mw/confidence are Float columns, and
        ExtractNewsSignalsCommand commits once at the end of a 40-article
        run — a model answering "50 MW" or "high" instead of a bare
        number must not reach the insert and lose the whole batch.
        """

        if value is None or isinstance(value, bool):

            return None

        try:

            number = float(value)

        except (TypeError, ValueError):

            return None

        if not math.isfinite(number):

            return None

        if minimum is not None and number < minimum:

            return None

        if maximum is not None and number > maximum:

            return None

        return number

    # =====================================================
    # Internal
    # =====================================================

    def _call_model(
        self,
        article: dict,
    ) -> dict | None:

        try:

            response = self.client.responses.create(
                model=self.model,
                input=self._prompt(article),
                temperature=0,
            )

            return parse_json_object(response.output_text)

        except Exception as exc:

            raise ExtractionFailed("news-signal extraction failed") from exc

    @staticmethod
    def _prompt(
        article: dict,
    ) -> str:

        title = article.get("title") or ""
        summary = article.get("summary") or ""

        return f"""
You are extracting structured business signals from a German
data-center industry news article. The article is in German.

Respond with ONLY a JSON object, no other text:
{{
  "company": "",
  "facility": "",
  "city": "",
  "country": "Germany",
  "investment_signal": false,
  "expansion_signal": false,
  "retrofit_signal": false,
  "renewable_signal": false,
  "power_signal": false,
  "capacity_mw": null,
  "confidence": 0.0
}}

- "company": the primary company named, or "" if none.
- "facility": a named facility/site, or "" if none.
- "city": a German city named, or "" if none.
- "investment_signal": true if the article discusses investment,
  funding, or acquisition.
- "expansion_signal": true if it discusses expansion, new capacity,
  or a new campus.
- "retrofit_signal": true if it discusses retrofitting, modernizing,
  or upgrading existing infrastructure.
- "renewable_signal": true if it discusses renewable energy, solar,
  wind, or sustainability commitments.
- "power_signal": true if it discusses grid capacity, substations,
  power supply, or electricity constraints.
- "capacity_mw": a numeric MW figure if explicitly stated, else null.
- "confidence": your confidence in this extraction, 0.0 to 1.0.

Title:
{title}

Summary:
{summary}
"""
