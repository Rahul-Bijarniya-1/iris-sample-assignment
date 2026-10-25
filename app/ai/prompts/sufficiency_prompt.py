"""
Sufficiency Prompt

Builds the prompt that asks the mini model to verify whether retrieved
news evidence is enough to answer the planner's question, and which
articles are actually relevant.

Author:
NRW BI Platform
"""

import json


class SufficiencyPrompt:

    @staticmethod
    def build(
        context: dict,
    ) -> str:

        question = context["question"]
        results = context["results"]

        listing = "\n".join(
            f"[{item['id']}] {item['title']} "
            f"({item.get('published_at')}) — "
            f"{(item.get('summary_en') or '')[:300]} — signals: "
            f"{json.dumps(item.get('signals') or {}, default=str, ensure_ascii=False, sort_keys=True)}"
            for item in results
        )

        if not listing:

            listing = "(no articles retrieved)"

        return f"""
You are verifying retrieved news evidence for a data-center-siting
research assistant.

Question:
{question}

Retrieved articles:
{listing}

For each article, decide if it is actually relevant to the question.
Decide whether the relevant articles, together, are sufficient to
answer the question. If not, say what is missing and suggest a better
search query.

Respond with ONLY a JSON object, no other text:
{{
  "sufficient": true,
  "relevant_ids": ["..."],
  "rejected": [{{"id": "...", "reason": "..."}}],
  "missing": "",
  "refined_query": ""
}}
"""
