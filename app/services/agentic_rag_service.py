"""
Agentic RAG Service

Orchestrates the planner-facing news intelligence loop:

    question -> PLAN -> RETRIEVE -> VERIFY -> (REFINE once) -> ANSWER

Hard bounds: at most 2 retrieval rounds, at most 1 refinement, roughly
4 model calls per question. Every external call (model or tool) is
wrapped so a failure degrades the answer rather than raising — the
dashboard must never end up worse than the pre-RAG keyword path.

Author:
NRW BI Platform
"""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.ai.json_parsing import parse_json_object
from app.ai.prompts.agentic_answer_prompt import AgenticAnswerPrompt
from app.ai.prompts.retrieval_plan_prompt import RetrievalPlanPrompt
from app.ai.prompts.sufficiency_prompt import SufficiencyPrompt
from app.database.repositories.land_value_repository import (
    LandValueRepository,
)
from app.services.ai_recommendation_service import AIRecommendationService
from app.services.news_retrieval_service import NewsRetrievalService
from app.services.site_intelligence_service import SiteIntelligenceService
from app.services.site_ranking_service import SiteRankingService


class AgenticRagService:

    WHITELISTED_TOOLS = (
        "news_search",
        "site_intelligence",
        "site_ranking",
    )

    MAX_REFINEMENTS = 1

    def __init__(
        self,
        session: Session,
        ai=None,
        news_retrieval=None,
        site_service=None,
        ranking_service=None,
        land_repository=None,
        answer_model: str | None = None,
    ):

        self.session = session
        self.ai = ai or AIRecommendationService()
        self.news_retrieval = news_retrieval or NewsRetrievalService(
            session
        )
        self.site_service = site_service or SiteIntelligenceService(
            session
        )
        self.ranking_service = ranking_service or SiteRankingService(
            session
        )
        self.land_repository = land_repository or LandValueRepository(
            session
        )

        self.answer_model = answer_model or os.getenv(
            "OPENAI_ANSWER_MODEL",
            "gpt-4.1",
        )

    # =====================================================
    # Public
    # =====================================================

    def answer(
        self,
        question: str,
        facility_id: int | None = None,
        place: str | None = None,
        on_step=None,
    ) -> dict:

        on_step = on_step or (lambda stage: None)

        on_step("Planning")

        plan = self._plan(question)

        on_step("Retrieving")

        results = self._retrieve_news(plan["query"], plan["k"])

        rounds = [
            {
                "query": plan["query"],
                "k": plan["k"],
                "result_ids": [r["id"] for r in results],
            }
        ]

        on_step("Verifying")

        verify = self._verify(question, results)

        if (
            not verify["sufficient"]
            and verify.get("refined_query")
            and len(rounds) <= self.MAX_REFINEMENTS
        ):

            on_step("Refining")

            refined_results = self._retrieve_news(
                verify["refined_query"], plan["k"]
            )

            results = self._merge_results(results, refined_results)

            rounds.append(
                {
                    "query": verify["refined_query"],
                    "k": plan["k"],
                    "result_ids": [r["id"] for r in refined_results],
                }
            )

            verify = self._verify(question, results)

        relevant = self._filter_relevant(results, verify)

        site = None

        if "site_intelligence" in plan["tools"]:

            site = self._resolve_site(facility_id, place)

        ranking = None

        if "site_ranking" in plan["tools"]:

            ranking = self._safe_call(
                self.ranking_service.rank_sites
            )

        on_step("Answering")

        answer_text = self._answer(
            question,
            relevant,
            site,
            verify.get("missing", ""),
        )

        citations = [
            self._citation(index + 1, article)
            for index, article in enumerate(relevant)
        ]

        return {
            "answer": answer_text,
            "citations": citations,
            "trace": {
                "plan": plan,
                "rounds": rounds,
                "verify": verify,
                "site": site,
                "ranking": ranking,
            },
        }

    # =====================================================
    # PLAN
    # =====================================================

    def _plan(
        self,
        question: str,
    ) -> dict:

        data = self._safe_call(
            lambda: parse_json_object(
                self.ai.generate(
                    RetrievalPlanPrompt.build(
                        {"question": question}
                    )
                )
            )
        )

        if not isinstance(data, dict):

            return self._default_plan(question)

        tools = [
            tool
            for tool in data.get("tools", [])
            if tool in self.WHITELISTED_TOOLS
        ]

        if not tools:

            tools = ["news_search"]

        try:

            k = int(data.get("k", 10))

        except (TypeError, ValueError):

            k = 10

        k = max(1, min(10, k))

        query = data.get("query") or question

        return {
            "tools": tools,
            "query": query,
            "k": k,
        }

    @staticmethod
    def _default_plan(
        question: str,
    ) -> dict:

        return {
            "tools": ["news_search"],
            "query": question,
            "k": 10,
        }

    # =====================================================
    # RETRIEVE
    # =====================================================

    def _retrieve_news(
        self,
        query: str,
        k: int,
    ) -> list[dict]:

        return (
            self._safe_call(
                lambda: self.news_retrieval.search(query, k=k)
            )
            or []
        )

    @staticmethod
    def _merge_results(
        first: list[dict],
        second: list[dict],
    ) -> list[dict]:

        merged = list(first)
        seen_ids = {item["id"] for item in first}

        for item in second:

            if item["id"] not in seen_ids:

                merged.append(item)

                seen_ids.add(item["id"])

        return merged

    # =====================================================
    # VERIFY
    # =====================================================

    def _verify(
        self,
        question: str,
        results: list[dict],
    ) -> dict:

        data = self._safe_call(
            lambda: parse_json_object(
                self.ai.generate(
                    SufficiencyPrompt.build(
                        {"question": question, "results": results}
                    )
                )
            )
        )

        if not isinstance(data, dict):

            # Can't verify — assume whatever was retrieved is usable
            # rather than discarding it and answering with nothing.
            return {
                "sufficient": True,
                "relevant_ids": [item["id"] for item in results],
                "rejected": [],
                "missing": "",
                "refined_query": "",
            }

        return {
            "sufficient": bool(data.get("sufficient", True)),
            "relevant_ids": data.get("relevant_ids") or [],
            "rejected": data.get("rejected") or [],
            "missing": data.get("missing") or "",
            "refined_query": data.get("refined_query") or "",
        }

    @staticmethod
    def _filter_relevant(
        results: list[dict],
        verify: dict,
    ) -> list[dict]:

        relevant_ids = set(verify.get("relevant_ids") or [])

        if not relevant_ids:

            return results

        by_id = {item["id"]: item for item in results}

        return [
            by_id[id_] for id_ in verify["relevant_ids"] if id_ in by_id
        ]

    # =====================================================
    # Site / place resolution
    # =====================================================

    def _resolve_site(
        self,
        facility_id: int | None,
        place: str | None,
    ) -> dict | None:

        if facility_id is not None:

            return self._safe_call(
                lambda: self.site_service.analyze_facility(facility_id)
            )

        if place:

            location = self._safe_call(
                lambda: self.land_repository.find_municipality_location(
                    place
                )
            )

            if location is None:

                return None

            return self._safe_call(
                lambda: self.site_service.analyze_location(
                    latitude=location["latitude"],
                    longitude=location["longitude"],
                )
            )

        return None

    # =====================================================
    # ANSWER
    # =====================================================

    def _answer(
        self,
        question: str,
        relevant: list[dict],
        site: dict | None,
        gaps: str,
    ) -> str:

        text = self._safe_call(
            lambda: self.ai.generate(
                AgenticAnswerPrompt.build(
                    {
                        "question": question,
                        "articles": relevant,
                        "site": site,
                        "gaps": gaps,
                    }
                ),
                model=self.answer_model,
            )
        )

        if not text:

            return (
                "Unable to generate an answer right now. "
                f"{len(relevant)} article(s) were retrieved; "
                "please try again."
            )

        return text

    @staticmethod
    def _citation(
        index: int,
        article: dict,
    ) -> dict:

        return {
            "index": index,
            "id": article["id"],
            "title": article["title"],
            "title_de": article.get("title_de"),
            "url": article.get("url"),
            "published_at": article.get("published_at"),
            "source": article.get("source"),
        }

    # =====================================================
    # Internal
    # =====================================================

    @staticmethod
    def _safe_call(fn):

        try:

            return fn()

        except Exception:

            return None
