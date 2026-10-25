"""
AI Recommendation Service

Generates AI-powered recommendations
for Data Center Site Intelligence.

Model:
    GPT-5.5 Mini

Author:
    NRW BI Platform
"""

from app.ai.prompts.site_analysis_prompt import SiteAnalysisPrompt
from app.config.openai import LazyOpenAIClient, get_chat_model


class AIRecommendationService(LazyOpenAIClient):

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
