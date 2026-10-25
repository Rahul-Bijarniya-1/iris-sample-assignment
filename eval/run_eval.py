"""
Runs the planner eval set (eval/planner_questions.json) against the real,
live AgenticRagService — real OpenAI calls, real pgvector retrieval — and
reports recall@5 against hand-labeled ground truth, plus a "before"
baseline reconstructing the original defect #6 behavior (match the whole
question as one literal substring) for comparison.

Not part of the test suite (makes real paid API calls on every run,
deliberately). Run by hand:

    .venv/bin/python -m eval.run_eval

Writes eval/results.json (raw data) and prints a recall@5 table + the
literal acceptance-test before/after text to stdout.
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.database.session import SessionLocal  # noqa: E402
from app.database.models.news_article import NewsArticle  # noqa: E402
from app.services.agentic_rag_service import AgenticRagService  # noqa: E402
from sqlalchemy import select  # noqa: E402


EVAL_DIR = Path(__file__).resolve().parent
QUESTIONS_FILE = EVAL_DIR / "planner_questions.json"
RESULTS_FILE = EVAL_DIR / "results.json"


def _before_baseline(session, question: str) -> list[str]:
    """
    Reconstructs the ORIGINAL defect #6 behavior: the whole question,
    lower-cased, checked as one literal substring of title+summary.
    This is what search_news() did before this session's fix — kept
    here only for the eval's before/after comparison, not used by the
    live code anymore.
    """

    keyword = question.lower()

    matches = []

    for article in session.scalars(select(NewsArticle)):

        text = (
            (article.title or "") + " " + (article.summary or "")
        ).lower()

        if keyword in text:

            matches.append(article.id)

    return matches


def recall_at_5(retrieved_top5: list[str], relevant: list[str]) -> float | None:

    if not relevant:

        return None  # not applicable — "none" expectation questions

    hit = len(set(retrieved_top5) & set(relevant))

    return round(hit / len(relevant), 2)


def main():

    questions = json.loads(QUESTIONS_FILE.read_text())

    session = SessionLocal()

    results = []

    try:

        service = AgenticRagService(session)

        for item in questions:

            print(f"Running {item['id']}: {item['question'][:60]}...")

            before_matches = _before_baseline(session, item["question"])

            after = service.answer(item["question"])

            round1 = (
                after["trace"]["rounds"][0]["result_ids"]
                if after["trace"]["rounds"]
                else []
            )

            top5 = round1[:5]

            citation_ids = [c["id"] for c in after["citations"]]

            results.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "expectation": item["expectation"],
                    "relevant_article_ids": item["relevant_article_ids"],
                    "before_matches": before_matches,
                    "after_round1_top5": top5,
                    "after_citation_ids": citation_ids,
                    "after_verify_sufficient": after["trace"]["verify"].get(
                        "sufficient"
                    ),
                    "after_answer": after["answer"],
                    "recall_at_5": recall_at_5(
                        top5, item["relevant_article_ids"]
                    ),
                }
            )

    finally:

        session.close()

    RESULTS_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    print(f"\nWrote {RESULTS_FILE}\n")

    print(
        f"{'id':<5} {'expect':<9} {'before':<7} {'after@5':<8} "
        f"{'recall@5':<9} verify_sufficient"
    )

    for r in results:

        print(
            f"{r['id']:<5} {r['expectation']:<9} "
            f"{len(r['before_matches']):<7} "
            f"{len(r['after_round1_top5']):<8} "
            f"{str(r['recall_at_5']):<9} {r['after_verify_sufficient']}"
        )


if __name__ == "__main__":
    main()
