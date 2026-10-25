# Updates — Agentic RAG & Pipeline Hardening

Summary of the work on branch `feat/agentic-rag`. For full detail, see `FINDINGS.md` (every
defect: root cause, live evidence, fix, test) and `EVAL.md` (the planner evaluation).

## What changed

The README listed "Retrieval-Augmented Generation (RAG)" as complete, but no retrieval
machinery existed — matching was keyword/substring only, and fired once across 40 articles
and 223 facilities. That's now built for real:

- A planner can ask a natural-language question — naming a place instead of picking a
  facility — and gets a grounded, cited answer over the news corpus.
- Retrieval is semantic (pgvector), via a plan → retrieve → verify → refine → answer loop,
  bounded to a small number of model calls per question.
- Citations are bilingual: English for reading, German original for provenance, with dates
  and sources.
- A "how I got this" trace shows the retrieval plan, rounds, and verification verdict.
- Structured signal extraction (expansion, power, renewable, retrofit, investment) replaces
  the English-keyword mock that scored everything `False` against the German corpus.

## Defects found and fixed

Eleven defects from the initial investigation and a code review (stale `published_at`, a
mock extractor with English keywords against a German corpus, a duplicated selection cascade
discarding its own result, a `'NaN'` string leaking into the database, among others), plus a
follow-up 25-finding hardening pass covering model-output robustness, session/transaction
safety, signal extraction and consumption, and translation/embedding resumability.

Full writeup, file:line references, live evidence, and guarding tests: `FINDINGS.md`.

## Verification

- 190 tests passing (plus 2 opt-in tests against the real OpenAI API).
- A 14-question planner evaluation, authored independently and run for real against the live
  system with hand-labeled ground truth. Methodology and results: `EVAL.md`.
- Walked through the dashboard in a real browser to confirm end-to-end behavior, not just
  the test suite.

## Running it

```bash
uv run pytest                        # 190 passed, 2 skipped
uv run pytest -m live                # opt-in, real API calls
uv run streamlit run ui/app.py
uv run python eval/run_eval.py       # re-run the planner eval (real API calls)
```
