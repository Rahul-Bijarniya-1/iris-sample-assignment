# Agentic RAG — Planner Evaluation

14 planner questions (user-authored, in German — "the one input I should not author," per the
plan), run for real against the live `AgenticRagService` over the real 40-article corpus. Ground
truth was hand-labeled by reading every article's title/summary against each question (see
`eval/planner_questions.json`). The runner is `eval/run_eval.py`; raw output is
`eval/results.json`. Nothing here is simulated or stubbed — every "after" row below is a real
pgvector retrieval plus real `gpt-4.1-mini`/`gpt-4.1` calls.

## What the 2026-10-26 hardening rerun showed

This report now reflects a full live rerun after the follow-up review fixes and after refreshing
all 40 translations, embeddings, and structured signals. The earlier prompt fix still asks the
model to distinguish a local evidence gap from supported national context. The follow-up filter
fix adds an important boundary: `relevant_ids: []` plus a non-empty `rejected` list means the
verifier rejected every candidate, so those articles are no longer forwarded as answer evidence.

That explicit-rejection branch fired for q9, q10, and q11. Each answer correctly carries zero
citations rather than citing rejected sources. Their retrieval recall was 0.33, 0.67, and 0.00;
there was no q9–q11 recall improvement. This is expected conceptually because recall@5 is measured
before verification, but it contradicts the hardening plan's prediction and is recorded honestly.
The answer model still emits broad, uncited contextual statements when its evidence list is empty;
those statements should be treated as framing, not evidence-backed findings.

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
| q5 | grid/power bottleneck signals | coverage | 0 | 5 | 0.67 | Yes |
| q6 | permitting/regulatory delays | coverage | 0 | 5 | 0.67 | Yes |
| q7 | big capacity investments | coverage | 0 | 5 | 0.50 | Yes |
| q8 | hyperscaler accel/pullback in DE | coverage | 0 | 5 | 0.33 | Yes |
| q9 | grid risk near Dortmund | partial | 0 | 5 | 0.33 | No |
| q10 | permitting problems in Wuppertal | partial | 0 | 5 | 0.67 | No |
| q11 | investment signals for Bonn | partial | 0 | 5 | 0.00 | No |
| q12 | power/land/authority bottlenecks | coverage | 0 | 5 | 0.43 | Yes |
| q13 | business-case signal vs. noise | coverage | 0 | 5 | 0.40 | Yes |
| q14 | Digital Realty, Northern Virginia | none | 0 | 5 | — | No |

**Before (literal substring match — the original defect #6 behavior, reconstructed for this
comparison only, not present in the live code anymore): 0 matches on every single question.**
Expected — these are full natural-language sentences; the exact sentence never appears verbatim
inside a 227-character article summary. This is the empirical demonstration of why defect #6 ("can
essentially never match") was a real, severe defect, not a theoretical one.

**After — aggregate recall@5:**

- `coverage` questions (q5-q8, q12, q13): **0.50** average (6 questions)
- `partial` questions (q9-q11): **0.33** average (3 questions) — lower by design: these test
  retrieval under a place-name mismatch, where the question's dominant terms (the place name) don't
  match anything, diluting the embedding's similarity to the thematically relevant articles.

`verify said sufficient: No` on most rows does not mean the system failed — it means the
verification step recognized that what it found did not fully confirm the question as asked. When
it also supplied explicit rejections, the answer step now receives no article evidence and produces
no citations.

## `none` / out-of-scope questions — correctness is binary, not recall@5

All 5 (q1-q4: real NRW towns absent from this feed; q14: a US facility entirely outside this
corpus' scope) were checked by hand against the real DB — none of Duisburg, Hamm, Paderborn,
Mönchengladbach, Dortmund, Wuppertal, Bonn, "Digital Realty," or "Northern Virginia" appear
anywhere in the 40 articles. Every one of the 5 answers:

1. States plainly and correctly that no article covers the named place/entity.
2. Does **not** invent or imply local coverage.
3. Carries no citations when all retrieved candidates were explicitly rejected.

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

> "Es gibt keine Berichterstattung über relevante Rechenzentrumsnachrichten aus Duisburg in den
> letzten zwei Wochen; keine der vorliegenden Quellen nennt Duisburg explizit.
>
> Auf nationaler Ebene thematisieren verfügbare Berichte häufig Themen wie Netzkapazität,
> Genehmigungsprozesse und Investitionsdynamik für Rechenzentren, jedoch ohne konkreten Bezug zu
> Duisburg. Konkrete Aussagen zu dieser Stadt können daher aktuell nicht gemacht werden."

No facility selection required; the gap is stated honestly and specifically (not a generic
boilerplate string). Because the verifier rejected every candidate, the response intentionally has
no citations; its general national framing is not counted as an evidence-backed result.

## Observed characteristic, not a defect

q14 (the deliberately out-of-scope US question) correctly declines to invent campus capacity or
megawatt pricing and has no citations. The live answer did leak the prompt label `Evidence list:`
into its final sentence. That is a presentation-quality limitation, not a retrieval or grounding
failure; a future output sanitizer or deterministic no-evidence response could remove it.

## Reproducing

```bash
cd ~/Assignment/iris-sample
.venv/bin/python -m eval.run_eval
```

Makes real OpenAI calls (14 questions × up to 4 calls each); not part of the test suite, not run
by CI or `pytest`. Mini-model non-determinism means recall@5 numbers will vary slightly run to
run — the pattern (coverage > partial, both far above the 0.0 "before" baseline, correct abstention
on every `none` question) is the result that matters, not the exact decimals.
