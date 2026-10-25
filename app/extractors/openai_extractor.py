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

import os

from openai import OpenAI

from app.ai.json_parsing import parse_json_object


class OpenAIExtractor:

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

    def extract(
        self,
        article: dict,
    ) -> dict:

        data = self._call_model(article)

        if data is None:

            data = {}

        return {
            "article_id": article.get("id"),
            "article_url": article.get("url"),
            "company": data.get("company") or "",
            "facility": data.get("facility") or "",
            "city": data.get("city") or "",
            "country": data.get("country") or "Germany",
            "investment_signal": bool(
                data.get("investment_signal", False)
            ),
            "expansion_signal": bool(
                data.get("expansion_signal", False)
            ),
            "retrofit_signal": bool(
                data.get("retrofit_signal", False)
            ),
            "renewable_signal": bool(
                data.get("renewable_signal", False)
            ),
            "power_signal": bool(
                data.get("power_signal", False)
            ),
            "capacity_mw": data.get("capacity_mw"),
            "confidence": data.get("confidence", 0.0) or 0.0,
        }

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

        except Exception:

            return None

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
