"""
AI Infrastructure Advisor Service

Central AI Orchestrator for the
NRW Data Center Business Intelligence Platform.

Responsibilities

- Detect user intent
- Route requests to business services
- Build AI context
- Generate AI responses

Author:
NRW BI Platform
"""

from __future__ import annotations

import re

from enum import Enum
from enum import auto

from sqlalchemy.orm import Session

from app.services.dashboard_service import DashboardService
from app.services.ai_recommendation_service import (
    AIRecommendationService,
)
from app.services.context_builder_service import ContextBuilderService
from app.ai.prompts.site_analysis_prompt import SiteAnalysisPrompt
from app.ai.prompts.city_search_prompt import CitySearchPrompt
from app.ai.prompts.news_prompt import NewsPrompt
from app.services.agentic_rag_service import AgenticRagService

from app.services.intelligence_search_service import (
    IntelligenceSearchService,
)

from app.ai.prompts.city_search_prompt import (
    CitySearchPrompt,
)
from app.ai.prompts.company_search_prompt import (
    CompanySearchPrompt,
)
from app.services.site_intelligence_service import (
    SiteIntelligenceService,
)

from app.ai.prompts.comparison_prompt import (
    ComparisonPrompt,
)

from app.services.site_ranking_service import (
    SiteRankingService,
    RankingType,
)
from app.services.query_parser_service import (
    QueryParserService,
)
from app.ai.prompts.nearby_search_prompt import (
    NearbySearchPrompt,
)
from app.services.news_intelligence_service import (
    NewsIntelligenceService,
)

from app.ai.prompts.ranking_prompt import RankingPrompt
from app.ai.ai_keywords import (
    HELP_TERMS,
    CITY_TERMS,
    FACILITY_TERMS,
    COMPANY_TERMS,
    COMPARE_TERMS,
    RANKING_TERMS,
    POWER_TERMS,
    LAND_TERMS,
    RENEWABLE_TERMS,
    EXPANSION_TERMS,
    NEARBY_TERMS,
    NEWS_TERMS,
)
# ==========================================================
# AI Intent
# ==========================================================

class AIIntent(Enum):

    SITE_ANALYSIS = auto()

    SEARCH_CITY = auto()

    SEARCH_NEARBY = auto()

    SEARCH_COMPANY = auto()

    SEARCH_POWER = auto()

    SEARCH_RENEWABLE = auto()

    SEARCH_LAND = auto()

    SEARCH_EXPANSION = auto()

    COMPARE_SITES = auto()

    RANK_SITES = auto()

    NEWS = auto()

    HELP = auto()

    UNKNOWN = auto()

class AITopic(Enum):

    OVERALL = auto()

    POWER = auto()

    GRID = auto()

    TRANSMISSION = auto()

    TRANSFORMER = auto()

    LAND = auto()

    RENEWABLE = auto()

    EXPANSION = auto()

    NEWS = auto()

    INVESTMENT = auto()

    ACQUISITION = auto()

    CAPACITY = auto()

    RISK = auto()

    OPPORTUNITY = auto()

# ==========================================================
# AI Advisor
# ==========================================================

class AIAdvisorService:

    """
    Central AI Orchestrator.

    The UI communicates ONLY with this class.

    It decides:

        • What the user wants.
        • Which business service to call.
        • What data should be sent to GPT.
    """

    # ------------------------------------------------------
    # Constructor
    # ------------------------------------------------------

    def __init__(
        self,
        session: Session,
    ):

        self.dashboard = DashboardService(session)
        self.search = IntelligenceSearchService(session)

        self.context_builder = ContextBuilderService()
        self.site_service = SiteIntelligenceService(session)
        self.ai = AIRecommendationService()

        
        self.parser = QueryParserService(
            session
        )

        self.ranking_service = SiteRankingService(
            session
        )
        self.news_service = NewsIntelligenceService(
            session,
        )

        self.agentic_rag = AgenticRagService(
            session,
        )

        self.last_trace: dict | None = None
        self.last_citations: list | None = None

    # ======================================================
    # Intent Detection
    # ======================================================

    def detect_intent(
        self,
        question: str,
    ) -> AIIntent:
        """
        Intelligent intent detection using
        keyword scoring + entity recognition.
        """

        question = question.lower().strip()

        parsed = self.parser.parse(question)

        scores = {

            AIIntent.HELP:
                self._score(question, HELP_TERMS),

            AIIntent.NEWS:
                self._score(question, NEWS_TERMS),

            AIIntent.COMPARE_SITES:
                self._score(question, COMPARE_TERMS),

            AIIntent.RANK_SITES:
                self._score(question, RANKING_TERMS),

            AIIntent.SEARCH_NEARBY:
                self._score(question, NEARBY_TERMS),

            AIIntent.SEARCH_POWER:
                self._score(question, POWER_TERMS),

            AIIntent.SEARCH_LAND:
                self._score(question, LAND_TERMS),

            AIIntent.SEARCH_RENEWABLE:
                self._score(question, RENEWABLE_TERMS),

            AIIntent.SEARCH_EXPANSION:
                self._score(question, EXPANSION_TERMS),

            AIIntent.SEARCH_COMPANY: 0,

            AIIntent.SEARCH_CITY: 0,

            AIIntent.SITE_ANALYSIS: 0,

        }

        # ---------------------------------------------
        # News boost
        # ---------------------------------------------

        news_words = [

            "news",
            "signal",
            "signals",
            "announcement",
            "announcements",
            "press",
            "media",
            "headline",
            "headlines",
            "latest",
            "recent",
            "activity",
            "activities",
            "investment",
            "investments",
            "invested",
            "funding",
            "capital",
            "expansion",
            "expand",
            "expanded",
            "retrofit",
            "market",
            "opening",
            "launch",
            "capacity",
            "growth",
            "acquisition",
            "acquired",

        ]

        for word in news_words:

            if word in question:

                scores[AIIntent.NEWS] += 3

        # ---------------------------------------------
        # Company
        # ---------------------------------------------

        if parsed["company"]:

            scores[AIIntent.SEARCH_COMPANY] += 4

            scores[AIIntent.NEWS] += 2

        # ---------------------------------------------
        # Facility
        # ---------------------------------------------

        if parsed.get("facility"):

            scores[AIIntent.SITE_ANALYSIS] += 3

            scores[AIIntent.NEWS] += 3

        # ---------------------------------------------
        # City
        # ---------------------------------------------

        if parsed["city"]:

            scores[AIIntent.SEARCH_CITY] += 4

            scores[AIIntent.NEWS] += 1

        # ---------------------------------------------
        # Comparison
        # ---------------------------------------------

        try:

            left, right = self.parser.extract_companies(question)

            if left and right:

                scores[AIIntent.COMPARE_SITES] += 6

        except Exception:

            pass

        # ---------------------------------------------
        # Ranking
        # ---------------------------------------------

        if any(

            word in question

            for word in [

                "top",

                "highest",

                "best",

                "rank",

                "ranking",

            ]

        ):

            scores[AIIntent.RANK_SITES] += 5

        # ---------------------------------------------
        # Nearby
        # ---------------------------------------------

        if "near" in question or "nearby" in question:

            scores[AIIntent.SEARCH_NEARBY] += 5

        # ---------------------------------------------
        # Site Analysis
        # ---------------------------------------------

        if any(

            word in question

            for word in [

                "site",

                "facility",

                "analyze",

                "analysis",

                "risk",

                "opportunity",

                "score",

                "recommendation",

            ]

        ):

            scores[AIIntent.SITE_ANALYSIS] += 3

        # ---------------------------------------------
        # Winner
        # ---------------------------------------------

        intent = max(

            scores,

            key=scores.get,

        )

        return intent

        # ======================================================
    # Public API
    # ======================================================

    def ask(
        self,
        question: str,
        selected_facility_id: int | None,
        on_step=None,
    ) -> str:
        """
        Main entry point for the AI Advisor.

        Every question from the UI comes here first.
        """

        intent = self.detect_intent(question)

        # ----------------------------------------------
        # Help
        # ----------------------------------------------

        if intent == AIIntent.HELP:
            return self._help()

        # ----------------------------------------------
        # Site Intelligence
        # ----------------------------------------------

        if intent == AIIntent.SITE_ANALYSIS:
            return self._site_analysis(
                selected_facility_id,
                question,
            )

        # ----------------------------------------------
        # Power
        # ----------------------------------------------

        if intent == AIIntent.SEARCH_POWER:
            return self._site_analysis(
                selected_facility_id,
                question,
            )

        # ----------------------------------------------
        # Land
        # ----------------------------------------------

        if intent == AIIntent.SEARCH_LAND:
            return self._site_analysis(
                selected_facility_id,
                question,
            )

        # ----------------------------------------------
        # Renewable
        # ----------------------------------------------

        if intent == AIIntent.SEARCH_RENEWABLE:
            return self._site_analysis(
                selected_facility_id,
                question,
            )

        # ----------------------------------------------
        # Expansion
        # ----------------------------------------------

        if intent == AIIntent.SEARCH_EXPANSION:
            return self._site_analysis(
                selected_facility_id,
                question,
            )

        # ----------------------------------------------
        # City Search
        # ----------------------------------------------

        if intent == AIIntent.SEARCH_CITY:
            return self._search_city(
                question,
            )

        # ----------------------------------------------
        # Nearby Search
        # ----------------------------------------------

        if intent == AIIntent.SEARCH_NEARBY:
            return self._search_nearby(
                question,
            )

        # ----------------------------------------------
        # Company Search
        # ----------------------------------------------

        if intent == AIIntent.SEARCH_COMPANY:
            return self._search_company(
                question,
            )

        # ----------------------------------------------
        # Compare
        # ----------------------------------------------

        if intent == AIIntent.COMPARE_SITES:
            return self._compare_sites(
                question,
            )

        # ----------------------------------------------
        # Ranking
        # ----------------------------------------------

        if intent == AIIntent.RANK_SITES:
            return self._rank_sites(
                question,
            )

        # ----------------------------------------------
        # News
        # ----------------------------------------------

        if intent == AIIntent.NEWS:
            return self._agentic_news(
                question,
                selected_facility_id,
                on_step,
            )

        return self._unknown()

    # ======================================================
    # Site Intelligence
    # ======================================================

    def _site_analysis(
        self,
        facility_id: int | None,
        question: str,
    ) -> str:

        if not facility_id:

            return (
                "Please select a Data Center on the map first "
                "before requesting Site Intelligence."
            )

        site = self.dashboard.get_site_intelligence(
            facility_id
        )

        context = self.context_builder.build_site_context(
        site=site,
            question=question,
        )

        prompt = SiteAnalysisPrompt.build(context)

        return self.ai.generate(prompt)

    # ======================================================
    # Help
    # ======================================================

    def _help(self) -> str:

       return """
    # 🧠 AI Infrastructure Advisor

    Welcome to the NRW Data Center Business Intelligence Platform.

    I can help you analyze Data Center Site Intelligence and answer questions using the available Business Intelligence.

    ## Current Capabilities

    ### 📊 Site Intelligence

    • Analyze the selected facility

    • Explain the Site Score

    • Explain Grid Infrastructure

    • Explain Transmission Network

    • Explain Transformer Accessibility

    • Explain Renewable Energy Readiness

    • Explain Land Intelligence

    • Explain Expansion Potential

    • Explain Investment Recommendation

    ---

    ### 🔍 Search

    • Search facilities by city

    • Search facilities by company

    • Search facilities by country

    ---

    ### 📈 Analysis

    • Identify strengths

    • Identify weaknesses

    • Explain risks

    • Explain opportunities

    • Recommend improvements

    ---

    ### 🚧 Coming Soon

    • Compare facilities

    • Nearby facility search

    • Facility rankings

    • Investment ranking

    • News Intelligence

    • Document Intelligence (RAG)

    • Voice AI Assistant

    ---

    ### Example Questions

    • Analyze this site

    • Explain the Grid Score

    • Why is the score 77?

    • What are the biggest risks?

    • What opportunities exist?

    • Show facilities in Aachen

    • Show Equinix facilities

    • Which facilities are in Germany?
    """
    # ======================================================
    # Unknown
    # ======================================================

    def _unknown(self) -> str:

        return (
            "I am the AI Infrastructure Advisor for the NRW "
            "Data Center Business Intelligence Platform.\n\n"
            "I can answer questions related to Site Intelligence, "
            "power infrastructure, renewable energy, land, "
            "expansion potential and investment assessment."
        )

    # ======================================================
    # Search by City
    # ======================================================

    def _search_city(
        self,
        question: str,
    ) -> str:
        """
        Search facilities by city using the
        Query Parser Service.
        """

        parsed = self.parser.parse(question)

        city = parsed["city"]

        if city is None:

            return (
                "I couldn't identify a city in your question.\n\n"
                "Examples:\n"
                "• Show data centers in Berlin\n"
                "• Find facilities in Cologne\n"
                "• Which operators are in Düsseldorf?"
            )

        facilities = self.search.search_by_city(city)

        if not facilities:

            return (
                f"No Data Center facilities were found "
                f"in '{city}'."
            )

        context = self.context_builder.build_city_context(
            question=question,
            city=city,
            facilities=facilities,
        )

        prompt = CitySearchPrompt.build(
            context
        )

        return self.ai.generate(
            prompt
        )

    # ======================================================
    # Nearby Search
    # ======================================================

    def _search_nearby(
        self,
        question: str,
    ) -> str:
        """
        Search nearby facilities around a city.
        """

        parsed = self.parser.parse(
            question,
        )

        city = parsed["city"]

        radius = parsed["radius_km"] or 25

        if city is None:

            return (
                "Please specify a city.\n\n"
                "Examples:\n"
                "• Find facilities within 20 km of Berlin\n"
                "• Show nearby data centers around Cologne\n"
                "• Find facilities near Düsseldorf"
            )

        city_facilities = self.search.search_by_city(
            city,
        )

        if not city_facilities:

            return (
                f"No facilities were found in '{city}'."
            )

        origin = city_facilities[0]

        facilities = self.search.search_nearby(
            latitude=origin["latitude"],
            longitude=origin["longitude"],
            radius_km=radius,
        )

        if not facilities:

            return (
                f"No facilities were found within "
                f"{radius} km of {city}."
            )

        context = self.context_builder.build_nearby_context(
            facilities=facilities,
            latitude=origin["latitude"],
            longitude=origin["longitude"],
            radius_km=radius,
            question=question,
        )

        prompt = NearbySearchPrompt.build(
            context,
        )

        return self.ai.generate(
            prompt,
        )
    # ======================================================
    # Company Search
    # ======================================================

    def _search_company(
        self,
        question: str,
    ) -> str:
        """
        Search facilities by company using the
        Query Parser Service.
        """

        parsed = self.parser.parse(question)

        company = parsed["company"]

        if company is None:

            return (
                "I couldn't identify a company in your question.\n\n"
                "Examples:\n"
                "• Show Microsoft facilities\n"
                "• Find Equinix data centers\n"
                "• Show euNetworks facilities\n"
                "• Show Penta Infra sites"
            )

        facilities = self.search.search_by_company(
            company
        )

        if not facilities:

            return (
                f"No Data Center facilities were found "
                f"for '{company}'."
            )

        context = self.context_builder.build_company_context(
            question=question,
            company=company,
            facilities=facilities,
        )

        prompt = CompanySearchPrompt.build(
            context
        )

        return self.ai.generate(
            prompt
        )


    # ======================================================
    # Compare Sites
    # ======================================================

    def _compare_sites(
        self,
        question: str,
    ) -> str:

        left_company, right_company = (
            self.parser.extract_companies(
                question
            )
        )

        if left_company is None or right_company is None:

            return (
                "Please specify two companies to compare.\n\n"
                "Examples:\n"
                "• Compare Microsoft vs Equinix\n"
                "• Compare euNetworks vs Penta Infra\n"
                "• Compare AtlasEdge against NorthC"
            )

        if left_company == right_company:

            return (
                "You selected the same company twice.\n\n"
                "Please choose two different companies to compare."
            )

        comparison = self.site_service.compare_companies(
            left_company,
            right_company,
        )

        left = comparison["left"]
        right = comparison["right"]

        if not left:

            return (
                f"No facilities were found for '{left_company}'."
            )

        if not right:

            return (
                f"No facilities were found for '{right_company}'."
            )

        context = self.context_builder.build_comparison_context(
            left=left,
            right=right,
            question=question,
        )

        prompt = ComparisonPrompt.build(
            context
        )

        return self.ai.generate(
            prompt
        )


    # ======================================================
    # Ranking
    # ======================================================

    def _rank_sites(
        self,
        question: str,
    ) -> str:
        """
        Rank facilities using the Site Ranking Service.
        """

        parsed = self.parser.parse(question)

        question_lower = question.lower()

        limit = parsed["limit"] or 10

        # --------------------------------------------------
        # Ranking Type
        # --------------------------------------------------

        ranking_type = RankingType.OVERALL

        if "grid" in question_lower:
            ranking_type = RankingType.GRID

        elif "transmission" in question_lower:
            ranking_type = RankingType.TRANSMISSION

        elif "transformer" in question_lower:
            ranking_type = RankingType.TRANSFORMER

        elif "renewable" in question_lower:
            ranking_type = RankingType.RENEWABLE

        elif "land" in question_lower:
            ranking_type = RankingType.LAND

        elif "expansion" in question_lower:
            ranking_type = RankingType.EXPANSION

        facilities = self.ranking_service.rank_sites(
            ranking_type=ranking_type,
            limit=limit,
        )

        if not facilities:

            return (
                "No facilities were found."
            )

        context = self.context_builder.build_ranking_context(
            facilities=facilities,
            ranking_type=ranking_type.value,
            question=question,
        )

        prompt = RankingPrompt.build(
            context
        )

        return self.ai.generate(
            prompt
        )

    # ======================================================
    # Agentic News
    # ======================================================

    def _agentic_news(
        self,
        question: str,
        facility_id: int | None,
        on_step=None,
    ) -> str:
        """
        Route AIIntent.NEWS through the agentic retrieval loop, letting
        the planner name a place instead of selecting a facility.

        Degradation path: an empty first retrieval round means
        NewsRetrievalService itself degraded (missing OPENAI_API_KEY,
        no embeddings yet, or no pgvector extension) — not that the
        corpus legitimately lacks coverage for a real question, which
        the agentic answer already states explicitly. Only the former
        falls back to the pre-RAG keyword/match path, so the dashboard
        is never worse than before.
        """

        parsed = self.parser.parse(question)

        result = self.agentic_rag.answer(
            question,
            facility_id=facility_id,
            place=parsed["city"],
            on_step=on_step,
        )

        self.last_trace = result["trace"]
        self.last_citations = result["citations"]

        first_round = (
            result["trace"]["rounds"][0]["result_ids"]
            if result["trace"]["rounds"]
            else []
        )

        if not first_round:

            return self._news(question)

        return result["answer"]

    # ======================================================
    # News Signals
    # ======================================================

    def _news(
        self,
        question: str,
    ) -> str:
        """
        Handle News Intelligence queries.
        """

        parsed = self.parser.parse(question)
        keyword_news = self.news_service.search_news(
            question,
        )

        if keyword_news:

            news = keyword_news

        elif parsed["facility"]:

            news = self.news_service.facility_news(
                parsed["facility"]
            )

        elif parsed["company"]:

            news = self.news_service.company_news(
                parsed["company"]
            )

        elif parsed["city"]:

            news = self.news_service.city_news(
                parsed["city"]
            )

        else:

            news = self.news_service.latest_news(10)

        if not news:

            return (
                "No matching news signals were found."
            )

        context = self.context_builder.build_news_context(
            news=news,
            question=question,
        )

        prompt = NewsPrompt.build(
            context,
        )

        return self.ai.generate(
            prompt,
        )
        
    def _extract_companies(
        self,
        question: str,
    ) -> tuple[str, str]:

        text = (
            question
            .replace("Compare", "")
            .replace("compare", "")
            .replace("Difference between", "")
            .replace("difference between", "")
            .replace("versus", "|")
            .replace("vs", "|")
            .replace("and", "|")
        )

        companies = [
            value.strip()
            for value in text.split("|")
            if value.strip()
        ]

        if len(companies) < 2:
            raise ValueError(
                "Please provide two companies to compare."
            )

        return (
            companies[0],
            companies[1],
        )

    def _score(
        self,
        question: str,
        terms: list[str],
    ) -> int:
        """
        Calculate how strongly a question matches an intent.
        """

        score = 0

        for term in terms:

            if term in question:
                score += 1

        return score