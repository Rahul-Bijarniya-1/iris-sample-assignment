"""
Agentic Answer Prompt

Builds the final grounded-answer prompt: cited news evidence, optional
site intelligence, and an explicit statement of what the question asked
that the evidence could not answer.

Author:
NRW BI Platform
"""


class AgenticAnswerPrompt:

    @staticmethod
    def build(
        context: dict,
    ) -> str:

        question = context["question"]
        articles = context["articles"]
        site = context.get("site")
        gaps = context.get("gaps") or ""

        citations = "\n".join(
            f"[{index + 1}] {article['title']} "
            f"({article.get('published_at')}, {article.get('source')}) "
            f"— {article.get('summary_en') or ''}"
            for index, article in enumerate(articles)
        )

        if not citations:

            citations = "(no relevant articles found)"

        site_block = ""

        if site:

            site_block = f"""

Site / location intelligence:
{site}
"""

        return f"""
You are a planner-facing data-center siting research assistant.

Answer the question using ONLY the evidence below. Cite articles
inline with [n] markers matching their number in the list. If the
evidence does not cover something the question asked, say so plainly
instead of guessing — do not invent local coverage that does not exist.

Question:
{question}

Evidence:
{citations}
{site_block}
Known gaps in this corpus: {gaps}
"""
