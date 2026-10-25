"""
AI Recommendation Service

Generates AI-powered recommendations
for Data Center Site Intelligence.

Model:
    GPT-5.5 Mini

Author:
    NRW BI Platform
"""

import os

from openai import OpenAI
from app.ai.prompts.site_analysis_prompt import SiteAnalysisPrompt


class AIRecommendationService:

    def __init__(
        self,
        client=None,
        model: str | None = None,
    ):

        self._client = client

        self.model = model or os.getenv(
            "OPENAI_MODEL",
            "gpt-4.1-mini",
        )

    # =====================================================
    # Public
    # =====================================================

    @property
    def client(self):

        if self._client is None:

            self._client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY")
            )

        return self._client

    def generate(
        self,
        prompt: str,
        model: str | None = None,
    ) -> str:

        response = self.client.responses.create(
            model=model or self.model,
            input=prompt,
        )

        return response.output_text.strip()
