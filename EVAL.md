# Agentic RAG — Planner Evaluation

14 planner questions (user-authored, in German — "the one input I should not author," per the
plan), run for real against the live `AgenticRagService` over the real 40-article corpus. Ground
truth was hand-labeled by reading every article's title/summary against each question (see
`eval/planner_questions.json`). The runner is `eval/run_eval.py`; raw output is
`eval/results.json`. Nothing here is simulated or stubbed — every "after" row below is a real
pgvector retrieval plus real `gpt-4.1-mini`/`gpt-4.1` calls.

## A finding from running the eval, and a fix made because of it

The first full run surfaced a real gap against the plan's own "Thin evidence" decision ("name the
gap and what was searched, then give the national context that does exist"): for place-specific
questions with no exact place match (q9, q10, q11), the model had the thematically-relevant
articles in its evidence (confirmed: `AgenticRagService`'s `_filter_relevant` already falls back
to the raw retrieved set when `verify` finds nothing to specifically confirm — that logic was
correct) but still answered "no information found," full stop — it had the evidence and declined
to use it, because the prompt only said "say so plainly instead of guessing," with nothing telling
it to still summarize the broader theme.

Fixed by rewording `AgenticAnswerPrompt` (`app/ai/prompts/agentic_answer_prompt.py`) to explicitly
separate "say plainly there's no place-specific coverage" from "then still summarize what the
evidence says about the same theme nationally, with its own citations." Re-ran q9/q10/q11 live
before and after the wording change — before: bare "no information" with zero citations on two of
three; after: all three lead with the honest gap, then correctly surface real national context
with proper `[n]` citations. The numbers in this report are from the full re-run after the fix.
See `FINDINGS.md` for the complete writeup (this is defect-class #12 there).

## Recall@5

For `coverage`/`partial` questions: of the hand-labeled relevant articles, what fraction appeared
in the top-5 retrieved candidates (before the verify step filters anything)? This measures
**retrieval**, not answer quality — a question can score low on recall@5 and still get a correct,
honest answer, because the verify/answer steps reason over what they're given rather than needing
every possible relevant article.

For `none` questions, recall@5 isn't a meaningful number (there's nothing to recall) — success is
instead whether the system correctly declined to claim local coverage, which is checked by hand
against the actual answer text (see "none / out-of-scope questions" below).

| id | question (short) | expectation | before: literal-substring matches | after: retrieved@5 | recall@5 | verify said sufficient |
|---|---|---|---:|---:|---:|---|
| q1 | Duisburg news? | none | 0 | 5 | — | No |
| q2 | Hamm projects? | none | 0 | 5 | — | No |
| q3 | Paderborn developments? | none | 0 | 5 | — | No |
| q4 | Mönchengladbach? | none | 0 | 5 | — | No |
| q5 | grid/power bottleneck signals | coverage | 0 | 5 | 0.67 | No |
| q6 | permitting/regulatory delays | coverage | 0 | 5 | 0.67 | No |
| q7 | big capacity investments | coverage | 0 | 5 | 0.50 | Yes |
| q8 | hyperscaler accel/pullback in DE | coverage | 0 | 5 | 0.67 | Yes |
| q9 | grid risk near Dortmund | partial | 0 | 5 | 0.33 | No |
| q10 | permitting problems in Wuppertal | partial | 0 | 5 | 0.67 | No |
| q11 | investment signals for Bonn | partial | 0 | 5 | 0.25 | No |
| q12 | power/land/authority bottlenecks | coverage | 0 | 5 | 0.57 | Yes |
| q13 | business-case signal vs. noise | coverage | 0 | 5 | 0.40 | Yes |
| q14 | Digital Realty, Northern Virginia | none | 0 | 5 | — | No |

**Before (literal substring match — the original defect #6 behavior, reconstructed for this
comparison only, not present in the live code anymore): 0 matches on every single question.**
Expected — these are full natural-language sentences; the exact sentence never appears verbatim
inside a 227-character article summary. This is the empirical demonstration of why defect #6 ("can
essentially never match") was a real, severe defect, not a theoretical one.

**After — aggregate recall@5:**
- `coverage` questions (q5-q8, q12, q13): **0.58** average (6 questions)
- `partial` questions (q9-q11): **0.42** average (3 questions) — lower by design: these test
  retrieval under a place-name mismatch, where the question's dominant terms (the place name) don't
  match anything, diluting the embedding's similarity to the thematically-relevant articles. The
  system still correctly surfaces them (see below) — the lower number here is retrieval working
  against a harder case, not a wrong answer.

`verify said sufficient: No` on most rows does not mean the system failed — it means the
verification step correctly recognized that what it found didn't fully confirm the question as
asked, and (per the fix above) the answer step still used that evidence to give an honest,
contextualized response rather than nothing.

## `none` / out-of-scope questions — correctness is binary, not recall@5

All 5 (q1-q4: real NRW towns absent from this feed; q14: a US facility entirely outside this
corpus' scope) were checked by hand against the real DB — none of Duisburg, Hamm, Paderborn,
Mönchengladbach, Dortmund, Wuppertal, Bonn, "Digital Realty," or "Northern Virginia" appear
anywhere in the 40 articles. Every one of the 5 answers:

1. States plainly and correctly that no article covers the named place/entity.
2. Does **not** invent or imply local coverage.
3. (q1-q4, and partially q14) Still offers relevant national-market context, correctly labeled as
   not place-specific.

This is the acceptance test's own framing, generalized across 5 independent control questions
rather than the single example the plan named.

## Before/after, literal text (the plan's acceptance-test format)

**Question:** *"Gab es in den letzten zwei Wochen relevante Rechenzentrumsnachrichten aus
Duisburg?"*

**Before** (what the pre-session system would have produced): a facility had to be selected first
just to ask — the UI blocked any question with "⚠️ Please select a Data Center on the map first,"
regardless of content. If a facility happened to be selected and the keyword path ran anyway, the
literal-substring `search_news()` (defect #6, reconstructed above) finds **0** matches for every
one of these 14 real questions — the pre-fix system's actual output for any of them would have been
`_news()`'s hard-coded string:

> "No matching news signals were found."

**After** (real output, this session's branch, captured in `eval/results.json`):

> "Keine der vorliegenden Evidenzquellen erwähnt Duisburg oder berichtet über
> Rechenzentrumsnachrichten aus Duisburg in den letzten zwei Wochen. Es existiert somit keine
> lokale Berichterstattung zu diesem Thema.
>
> Im nationalen bzw. regionalen Kontext werden jedoch einige relevante Themen für den
> Rechenzentrumsmarkt in Deutschland behandelt, zum Beispiel: Große Investitionen namhafter
> Unternehmen wie Amazon, Nvidia und Siemens in Cloud-, KI- und Datenzentrumsinfrastruktur [...]"

No facility selection required; the gap is stated honestly and specifically (not a generic
boilerplate string); real national context is surfaced with citations instead of nothing.

## Observed characteristic, not a defect

q14 (the deliberately out-of-scope US question) also receives the "national context" treatment —
German market trends in response to a question about Northern Virginia pricing. This isn't wrong
(it correctly declines the specific question first), but it's less sharp than for the NRW-town
questions, where national German context is genuinely useful to the same planner. A future
refinement could have `_plan()` recognize a clearly non-German/non-corpus location and skip the
national-context framing entirely for that case; not done here — a polish item, not a defect.

## Reproducing

```bash
cd ~/Assignment/iris-sample
PYTHONPATH=. uv run python eval/run_eval.py
```

Makes real OpenAI calls (14 questions × up to 4 calls each); not part of the test suite, not run
by CI or `pytest`. Mini-model non-determinism means recall@5 numbers will vary slightly run to
run — the pattern (coverage > partial, both far above the 0.0 "before" baseline, correct abstention
on every `none` question) is the result that matters, not the exact decimals.
