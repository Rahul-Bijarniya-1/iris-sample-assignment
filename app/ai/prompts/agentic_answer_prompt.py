"""
Agentic Answer Prompt

Builds the final grounded-answer prompt: cited news evidence, optional
site intelligence and facility ranking, and an explicit statement of
what the question asked that the evidence could not answer.

Author:
NRW BI Platform
"""

from __future__ import annotations

import json


class AgenticAnswerPrompt:

    @staticmethod
    def build(
        context: dict,
    ) -> str:

        question = context["question"]
        articles = context["articles"]
        site = context.get("site")
        ranking = context.get("ranking")
        gaps = context.get("gaps") or ""

        citations = "\n".join(
            f"[{index + 1}] {article['title']} "
            f"({article.get('published_at')}, {article.get('source')}) "
            f"— {article.get('summary_en') or ''} — signals: "
            f"{json.dumps(article.get('signals') or {}, default=str, ensure_ascii=False, sort_keys=True)}"
            for index, article in enumerate(articles)
        )

        if not citations:

            citations = "(no relevant articles found)"

        site_block = ""

        if site:

            site_block = f"""

Site / location intelligence:
{AgenticAnswerPrompt._to_json(site)}
"""

        ranking_block = ""

        if ranking:

            ranking_block = f"""

Facility ranking (top {len(ranking)}):
{AgenticAnswerPrompt._to_json(ranking)}
"""

        return f"""
You are a planner-facing data-center siting research assistant.

Answer the question using ONLY the evidence below. Cite articles
inline with [n] markers matching their number in the list. Do not
invent local coverage that does not exist.

Place-specific vs. thematic evidence: if the question names a specific
place and none of the evidence mentions that place by name, say so
plainly first — do not imply local coverage exists. Then, separately,
still summarize what the evidence DOES say about the same theme (grid
capacity, permitting, investment, etc.) at a national or regional
level, with its own [n] citations, clearly framed as national context
rather than local coverage. An evidence list that is non-empty means
there is something worth summarizing even when none of it is local —
only write "no information available" when the evidence list is
genuinely empty.

Question:
{question}

Evidence:
{citations}
{site_block}{ranking_block}
Known gaps in this corpus: {gaps}
"""

    @staticmethod
    def _to_json(
        value,
    ) -> str:
        """
        json.dumps with default=str rather than an f-string
        interpolation of the raw dict — site/ranking payloads carry
        datetime and Decimal values whose repr() is noise a model
        should not have to parse.
        """

        return json.dumps(
            value,
            indent=2,
            default=str,
            ensure_ascii=False,
        )
