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
from app.services.site_ranking_service import RankingType, SiteRankingService


_TRUTHY_STRINGS = frozenset({"1", "on", "true", "y", "yes"})


class AgenticRagService:

    WHITELISTED_TOOLS = (
        "news_search",
        "site_intelligence",
        "site_ranking",
    )

    MAX_REFINEMENTS = 1
    MAX_QUERY_CHARS = 500

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

        issued_queries = {self._query_key(plan["query"])}

        while (
            not verify["sufficient"]
            and verify.get("refined_query")
            and len(rounds) <= self.MAX_REFINEMENTS
        ):

            refined_query = self._normalize_query(
                verify["refined_query"], ""
            )
            refined_query_key = self._query_key(refined_query)

            if not refined_query_key or refined_query_key in issued_queries:

                break

            issued_queries.add(refined_query_key)

            on_step("Refining")

            refined_results = self._retrieve_news(
                refined_query, plan["k"]
            )

            results = self._merge_results(results, refined_results)

            rounds.append(
                {
                    "query": refined_query,
                    "k": plan["k"],
                    "result_ids": [r["id"] for r in refined_results],
                }
            )

            verify = self._verify(question, results)

        relevant = self._filter_relevant(results, verify)

        if not any(round_["result_ids"] for round_ in rounds):

            # An all-empty retrieval trace is the infrastructure-degradation
            # signal consumed by AIAdvisor's keyword fallback. Return before
            # site/ranking work and the paid answer-model call.
            return {
                "answer": "",
                "citations": [],
                "trace": {
                    "plan": plan,
                    "rounds": rounds,
                    "verify": verify,
                    "site": None,
                    "ranking": None,
                },
            }

        site = None

        if "site_intelligence" in plan["tools"]:

            site = self._resolve_site(facility_id, place)

        ranking = None

        if "site_ranking" in plan["tools"]:

            ranking = self._safe_call(
                lambda: self.ranking_service.rank_sites(
                    ranking_type=plan["ranking_type"],
                    limit=plan["ranking_limit"],
                )
            )

        on_step("Answering")

        answer_text = self._answer(
            question,
            relevant,
            site,
            ranking,
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

        raw_tools = data.get("tools") or []

        if not isinstance(raw_tools, (list, tuple, set)):

            raw_tools = []

        tools = [
            tool
            for tool in raw_tools
            if isinstance(tool, str)
            and tool in self.WHITELISTED_TOOLS
        ]

        if not tools:

            tools = ["news_search"]

        try:

            k = int(data.get("k", 10))

        except (TypeError, ValueError):

            k = 10

        k = max(1, min(10, k))

        ranking_type = self._as_ranking_type(data.get("ranking_type"))

        try:

            ranking_limit = int(data.get("ranking_limit", 10))

        except (TypeError, ValueError):

            ranking_limit = 10

        ranking_limit = max(1, min(10, ranking_limit))

        query = self._normalize_query(data.get("query"), question)

        return {
            "tools": tools,
            "query": query,
            "k": k,
            "ranking_type": ranking_type,
            "ranking_limit": ranking_limit,
        }

    @classmethod
    def _default_plan(
        cls,
        question: str,
    ) -> dict:

        return {
            "tools": ["news_search"],
            "query": cls._normalize_query(question, ""),
            "k": 10,
            "ranking_type": RankingType.OVERALL,
            "ranking_limit": 10,
        }

    @classmethod
    def _normalize_query(
        cls,
        value,
        fallback: str,
    ) -> str:

        query = value if isinstance(value, str) else fallback

        if not isinstance(query, str):

            query = ""

        query = query.strip()

        if not query and isinstance(fallback, str):

            query = fallback.strip()

        return query[: cls.MAX_QUERY_CHARS]

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
            "sufficient": self._as_bool(data.get("sufficient", True)),
            "relevant_ids": self._as_id_list(data.get("relevant_ids")),
            "rejected": self._as_rejected_list(data.get("rejected")),
            "missing": data.get("missing") or "",
            "refined_query": self._normalize_query(
                data.get("refined_query"), ""
            ),
        }

    @staticmethod
    def _as_bool(
        value,
    ) -> bool:
        """
        A mini model occasionally returns the string "false" for a
        boolean field; bool("false") is True in Python, so that must be
        handled explicitly rather than trusted to truthiness.
        """

        if isinstance(value, str):

            return value.strip().lower() in _TRUTHY_STRINGS

        return bool(value)

    @staticmethod
    def _as_id_list(
        value,
    ) -> list:
        """
        SufficiencyPrompt shows "relevant_ids": ["..."] directly above
        "rejected": [{"id": "...", "reason": "..."}] — a model
        conflating the two shapes and returning objects (or a bare
        scalar) here must not crash the rest of the pipeline, which
        treats these as hashable ids.
        """

        if not isinstance(value, list):

            return []

        return [
            item
            for item in value
            if isinstance(item, (str, int))
        ]

    @staticmethod
    def _as_rejected_list(
        value,
    ) -> list[dict[str, str]]:

        if value is None:

            return []

        if not isinstance(value, list):

            value = [value]

        rejected = []

        for item in value:

            if isinstance(item, dict):

                id_ = item.get("id")
                reason = item.get("reason")

            elif isinstance(item, (str, int)):

                id_ = item
                reason = ""

            else:

                continue

            if id_ is None:

                continue

            rejected.append(
                {
                    "id": str(id_),
                    "reason": "" if reason is None else str(reason),
                }
            )

        return rejected

    @staticmethod
    def _as_ranking_type(value) -> RankingType:

        try:

            return RankingType(str(value or RankingType.OVERALL.value).lower())

        except ValueError:

            return RankingType.OVERALL

    @staticmethod
    def _query_key(value) -> str:

        return str(value or "").strip().casefold()

    @staticmethod
    def _filter_relevant(
        results: list[dict],
        verify: dict,
    ) -> list[dict]:

        relevant_ids = set(verify.get("relevant_ids") or [])

        if not relevant_ids:

            return [] if verify.get("rejected") else results

        by_id = {item["id"]: item for item in results}

        relevant = [
            by_id[id_] for id_ in verify["relevant_ids"] if id_ in by_id
        ]

        if not relevant:

            verify["relevance"] = "id_mismatch"
            return results

        return relevant

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
        ranking: list[dict] | None,
        gaps: str,
    ) -> str:

        text = self._safe_call(
            lambda: self.ai.generate(
                AgenticAnswerPrompt.build(
                    {
                        "question": question,
                        "articles": relevant,
                        "site": site,
                        "ranking": ranking,
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
