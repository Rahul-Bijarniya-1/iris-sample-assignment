"""
Retrieval Plan Prompt

Builds the prompt that asks the mini model to decide which tools to
call for a planner's question, and with what news search query.

Author:
NRW BI Platform
"""


class RetrievalPlanPrompt:

    AVAILABLE_TOOLS = (
        "news_search",
        "site_intelligence",
        "site_ranking",
    )

    @staticmethod
    def build(
        context: dict,
    ) -> str:

        question = context["question"]

        tools = ", ".join(
            RetrievalPlanPrompt.AVAILABLE_TOOLS
        )

        return f"""
You are the planning step of a data-center-siting research assistant.

Decide which tools are needed to answer the planner's question, and
rewrite the question into a short, keyword-rich search query for the
news tool (not the whole question — a search engine query).

Available tools: {tools}

- news_search: semantic search over German data-center news coverage.
- site_intelligence: grid/power/land signals for a facility or place.
- site_ranking: ranks facilities by a scoring dimension.

Respond with ONLY a JSON object, no other text:
{{"tools": ["news_search"], "query": "<search query>", "k": 10}}

"tools" must be a non-empty list drawn only from the names above.
"k" must be an integer between 1 and 10.

Question:
{question}
"""
