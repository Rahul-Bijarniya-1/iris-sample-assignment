# Findings — Agentic RAG for News Intelligence

Written for the reviewer. Each entry: symptom, root cause with `file:line`, the live
evidence that confirmed it, the fix, and the test that guards it. All defects below were
verified against the live project database and code before being fixed — none are
speculative.

**Starting symptom.** A planner asks about a candidate location and gets *"No matching
news signals were found."* for 222 of 223 facilities. Investigating turned up eight defects
in the existing code, plus three more discovered only by running the new code against the
live OpenAI API (stubbed tests cannot catch these — see "New defects found during
implementation" below).

---

## Pre-existing defects (all eight from the original investigation)

### 1. Matching is exact company-name containment only

`app/news/entity_matcher.py` matched facilities to articles only by checking whether a
facility's company name appeared as a substring of the article's `company` field. Live
evidence: 1 `news_match` from 40 articles, 223 facilities. This is a structural limitation
of keyword/substring matching, not a one-line bug — it's exactly what semantic retrieval
(Agentic RAG) replaces. No standalone fix; superseded by `NewsRetrievalService`.

### 2. `published_at` NULL for all 40 articles — FIXED

`app/loaders/news_loader.py` (`_load_articles`, both the insert and update paths) never
read the `published` field from `news.json`, despite every article carrying an RFC-822 date
string there (`'Fri, 23 Oct 2026 14:21:00 +0200'`). Same class of defect as the
already-fixed Issue 10 (`MaStRParser` dropping `country_code`): upstream data carries a
field, the loader drops it.

Live evidence before the fix: `select count(*), count(published_at) from
iris_core.news_articles` → `40, 0`.

**Fix:** `NewsLoader._parse_published()` parses the field with
`email.utils.parsedate_to_datetime`, set in both the insert and update paths.
**Test:** `tests/test_news_published_at.py`.
**Verified after fix:** `40, 40`.

### 3. Extraction is an explicit mock — FIXED

`app/extractors/mock_extractor.py`'s own docstring: *"Simulates an LLM… Later this will be
replaced by OpenAIExtractor."*

**Fix:** `app/extractors/openai_extractor.py` — one structured, German-aware model call per
article, same output shape as `MockExtractor` so it's a drop-in. See "Where OpenAIExtractor
is actually wired" below for why it isn't `EntityExtractor`'s unconditional default.
**Test:** `tests/test_openai_extractor.py`.

### 4. Mock keyword lists are English, corpus is 100% German — FIXED

`MockExtractor.COMPANIES`/signal keyword lists (`"investment"`, `"expand"`, `"renewable"`,
etc.) are English; every article is German. Live evidence before the fix:
`expansion`/`power`/`renewable`/`retrofit` signals `False` for all 40 articles;
`investment` fired on 4 (coincidentally matching the English word "million"
appearing inside German sentences); `capacity_mw` hardcoded `None`; `confidence` hardcoded
`0.50`.

**Fix:** same as #3 — `OpenAIExtractor` reads German text directly, no keyword list.
**Live evidence after fix** (`uv run python main.py news-signals` against the real 40-article
corpus): 5 expansion, 10 power, 2 renewable, 7 retrofit, 8 investment signals — a real,
non-degenerate distribution instead of all-zero.
**Test:** `tests/test_openai_extractor.py`, `tests/test_extract_news_signals.py`.

### 5. `_news()` duplicates its selection cascade — FIXED

`app/services/ai_advisor_service.py:1006-1035` computed `news` from
`search_news()`/`facility_news()`/`company_news()`/`city_news()`/`latest_news()`, then
immediately recomputed the identical cascade minus `search_news()` at `:1037-1075` and
overwrote the first result unconditionally. The keyword-search result was therefore always
thrown away.

**Fix:** removed the duplicate cascade (the second block), keeping only the first.
**Test:** `tests/test_news_handler.py` — stubs `search_news` to return a distinctive result
and the rest of the cascade to return a different one; asserts the keyword result survives.

### 6. `search_news(question)` passes the whole question as a substring keyword — FIXED

`app/services/news_intelligence_service.py` lower-cased the *entire* question and checked
whether it appeared verbatim inside an article's `title + summary`. A natural-language
question essentially never matches that way.

**Fix:** tokenize the question into significant words (≥4 characters, small EN/DE stopword
list) and match on any one token appearing in the text.
**Test:** `tests/test_news_keyword_search.py`.

*Note: this fix stands on its own, but in production `_news()`'s keyword path is now a
fallback — real news questions route through `AgenticRagService` instead (see Phase D
below). Both are tested because the keyword path is still the degradation target when
retrieval infrastructure fails (see "Degradation path" below).*

### 7. `'NaN'` leaks into the database as a string — FIXED

`app/news/entity_matcher.py:271` read a missing `city` property off a `GeoDataFrame` row as
a pandas `NaN` float (the existing `.fillna("")` at `:215` covered only the `company`
series). `json.dump` serialized that as the bare token `NaN`; loading it back produced a
Python float that landed in the `VARCHAR` `city` column as the literal string `"NaN"`.

Live evidence before the fix: `select city from iris_core.news_matches` → `NaN` (confirmed
`pg_typeof(city) = character varying`, not an actual null).

**Fix:** `EntityMatcher._clean_city()` converts a pandas-NaN city to `None` before it enters
the match dict.
**Test:** `tests/test_news_match_city.py`.
**Data cleanup:** the one pre-existing row (predating this fix) was updated directly —
`update news_matches set city = NULL where city = 'NaN'` — since the loader only inserts
new matches, it never would have self-healed.

### 8. `build_news_context` defined twice — FIXED

`app/services/context_builder_service.py` defined `build_news_context` twice: once at
line 252 (dict-returning, matching the generic `build()` dispatcher's convention used by
every other context builder) and again at line 294 (string-returning). Python method
resolution makes the second definition win, silently shadowing the first with an
incompatible signature (`articles=` vs. the live one's `news=`). The first definition was
dead code — nothing called it — but left a trap for the next person who called `build("news",
articles=...)` expecting the documented dict contract.

**Fix:** deleted the dead first definition.
**Test:** `tests/test_context_builder_news.py` — asserts the source file defines
`build_news_context` exactly once.

---

## New defects found during implementation

Stubbed, hermetic tests cannot catch these — they only surfaced by running the finished
code against the live OpenAI API.

### 9. Translation JSON wrapped in a markdown fence — FIXED

`gpt-4.1-mini` wraps its JSON response in a ` ```json ... ``` ` fence even when the prompt
explicitly says "respond with ONLY a JSON object." The original `json.loads()` call raised
on the fence, silently triggering `TranslationService`'s fallback-to-source-text path —
**for every one of the 40 real articles**: `title_en`/`summary_en` came back byte-identical
to the German source after the first real `news-embed` run.

Live evidence:
```
>>> response.output_text
'```json\n{\n  "title_en": "AI Boom Meets Power Shortages...",\n ... \n}\n```'
```

**Fix:** `app/ai/json_parsing.py:parse_json_object()` strips a leading/trailing code fence
before parsing; both `TranslationService` and `AgenticRagService`'s plan/verify steps use
it.
**Test:** `tests/test_translation_service.py::test_translate_strips_markdown_code_fences`,
`tests/test_json_parsing.py`.

### 10. Embedding idempotency assumed deterministic translation — FIXED

The original design (content-hash the *exact embedded text*) assumed that re-translating
unchanged German text would reproduce the same English text, so a hash of the output could
tell "unchanged" from "changed." Measured against the live API, this is false even at
`temperature=0`: a second `news-embed` run re-embedded 35–36 of 40 *unchanged* articles,
because `gpt-4.1-mini`'s English wording drifted slightly each call.

**Fix:** hash the *source* (German title + summary + the translation model's name) instead,
and gate the `translate()` call itself on that hash — not just `embed()`. An unchanged
article now makes zero API calls on a re-run. Still catches an edited summary (source hash
changes) and a deliberate translation-model upgrade (the model name is part of the hash).
**Test:** `tests/test_embedding_idempotency.py`.
**Verified live:** `{'embedded': 0, 'skipped': 40}` on a second real run.

### 11b. `_filter_relevant` crashed on a plausible malformed verify response — FIXED

Found by a fresh-context code review of this branch, then reproduced directly:
`AgenticRagService._filter_relevant` passed `verify["relevant_ids"]` straight into `set()`.
`SufficiencyPrompt` shows `"relevant_ids": ["..."]` directly above `"rejected": [{"id": "...",
"reason": "..."}]` — a model conflating the two shapes (`relevant_ids` as objects, or as a
bare scalar) is an ordinary mini-model deviation, not an exotic one.

Live reproduction:
```
>>> AgenticRagService._filter_relevant([...], {"relevant_ids": [{"id": "a1", "reason": "x"}]})
TypeError: cannot use 'dict' as a set element
```
With `_safe_call` only wrapping the model/tool calls (not `_filter_relevant`, which runs on
their output), this exception reached `_agentic_news` → `ask()` → the UI's blanket
`except Exception`, surfacing as *"AI Error: cannot use 'dict' as a set element"* instead of
an answer — breaking the plan's explicit "never raises" requirement on exactly the step the
plan calls out it most.

**Fix:** `_verify()` now sanitizes `relevant_ids` through `_as_id_list()` (non-list → `[]`,
non-hashable items dropped) before anything downstream treats them as a set. Also fixed the
adjacent `bool(data.get("sufficient", True))`, where `bool("false") is True` in Python would
have silently suppressed the refinement round on a model returning the literal string
`"false"`.
**Test:** `tests/test_agentic_rag.py::test_verify_tolerates_relevant_ids_as_objects_instead_of_strings`,
`::test_verify_tolerates_relevant_ids_as_a_non_list_scalar`, `::test_verify_treats_the_string_false_as_false`.

### 11c. OpenAI clients were constructed eagerly, defeating the documented degradation path — FIXED

Found by the same review. `EmbeddingService`, `AIRecommendationService`, `TranslationService`,
and `OpenAIExtractor` all built their `OpenAI()` client in `__init__`, which raises
immediately when `OPENAI_API_KEY` is unset — **before** `NewsRetrievalService.search()`'s own
`try/except` (documented, here and in the service's own docstring, to degrade a missing key
to `[]`) ever got a chance to catch anything.

Live reproduction:
```
$ env -u OPENAI_API_KEY python -c "NewsRetrievalService(None)"
RAISED: OpenAIError Missing credentials...
```
Same root cause broke 5 tests that merely construct `AIAdvisorService` (which eagerly builds
`AgenticRagService` → `NewsRetrievalService` → `EmbeddingService`) with no key set —
`env -u OPENAI_API_KEY uv run pytest` → 5 failed, despite none of those tests making a
network call. A reviewer who follows the README's own `cp .env.example .env` setup (leaving
`OPENAI_API_KEY` empty) hits this.

**Fix:** all four classes now build their client lazily via a `client` property, constructed
on first access rather than at `__init__`. The missing-key failure now surfaces inside the
`try/except` that was always meant to catch it.
**Test:** a `test_construction_does_not_require_an_api_key` test added to each of the four
services' test files, plus `tests/test_news_retrieval.py::test_search_degrades_to_empty_list_with_no_api_key_at_all`,
which exercises the real `EmbeddingService()` end-to-end with the env var genuinely unset
(the pre-existing degradation test only exercised an injected failing stub, which tested a
different failure mode).
**Verified:** `env -u OPENAI_API_KEY uv run pytest` → 97/97 passed (was 5 failed before the fix).

### 11d. Three smaller robustness gaps, also found by the review — FIXED

- **`embed_news_command.py`'s content hash named the translation model but not the embedding
  model.** Changing `OPENAI_EMBEDDING_MODEL` left every row looking "unchanged" with no way
  to force a re-embed. Fixed: the embedding model's name is now part of the hash too.
  Added `EmbeddingService.EXPECTED_DIMENSIONS` guard (raises on a non-1536-dim response)
  so a dimension mismatch from a model switch fails loudly instead of being swallowed by
  `search()`'s blanket `except` and silently returning `[]` forever.
- **`OpenAIExtractor` didn't coerce `capacity_mw`/`confidence`.** A model answering `"50 MW"`
  or `"high"` instead of a bare number would have failed the `Float` column insert. Fixed
  with a `float()`-or-`None` coercion.
- **`ExtractNewsSignalsCommand` committed once at the end of a run.** One bad value on
  article 40 of 40 would have discarded all 39 paid extractions that preceded it. Fixed:
  batches commits every 10 rows, same pattern as `EmbedNewsCommand`.

**Tests:** `tests/test_embedding_idempotency.py::test_embedding_model_change_forces_re_embedding`,
`tests/test_embedding_service.py::test_embed_raises_on_a_dimension_mismatch`,
`tests/test_openai_extractor.py::test_extract_coerces_*`,
`tests/test_extract_news_signals.py::test_a_failure_partway_through_does_not_lose_earlier_progress`.

### 11. `PowerService` and `LandService` are empty files

The plan's architecture (written from the interview, before re-reading the codebase in
detail) names four tool services: `SiteIntelligenceService`, `PowerService`, `LandService`,
`SiteRankingService`. `app/services/power_service.py` and `app/services/land_service.py` are
both **0-byte files** — dead scaffold, never implemented. Power and land signals already
live inside `SiteIntelligenceService.analyze_location()`, which queries
`PowerInfrastructureRepository` and `LandValueRepository` directly. `AgenticRagService`'s
tool registry uses `SiteIntelligenceService` + `SiteRankingService` (two services covering
all four named capabilities), not four separate ones. Not a regression — this is how the
codebase already was.

---

## Where `OpenAIExtractor` is actually wired

The plan called for replacing `MockExtractor` "at its call site"
(`app/news/entity_extractor.py:56`). Doing that literally would make `EntityExtractor` —
which runs inside the `news` pipeline step, which `phase_4` calls, which `main.py all`
calls — make a paid OpenAI call on every `all` run, contradicting the explicit design goal
(stated in the same plan) that `all` stays free and offline-safe.

Instead: `OpenAIExtractor` is a complete, tested, drop-in replacement for `MockExtractor`'s
interface, but `EntityExtractor` still defaults to `MockExtractor`. A new command,
`news-signals` (`app/commands/extract_news_signals_command.py`), runs `OpenAIExtractor` over
every already-loaded article and loads `news_signals` directly from the database — the same
opt-in pattern as `news-embed`: registered in `PipelineRunner.commands`, called by no phase.
`tests/test_news_signals_wiring.py` is the deliberate inverse of the Issue 1/7 wiring tests,
mirroring `tests/test_news_embed_wiring.py`.

## Degradation path

`NewsRetrievalService.search()` returns `[]` on any failure — missing `OPENAI_API_KEY`, no
embeddings yet, a missing `vector` extension — rather than raising
(`app/services/news_retrieval_service.py`). This claim is now verified end-to-end, not just
in the happy path: see #11c above, and `test_search_degrades_to_empty_list_with_no_api_key_at_all`.
`AgenticRagService` itself still produces an answer in that case (naming the gap), but
`AIAdvisorService._agentic_news()` distinguishes two situations: an **empty first retrieval
round** (retrieval infrastructure itself failed) falls back to the pre-RAG keyword path
(`_news()`, defect #5/#6 above) so the dashboard is never worse than before; a **non-empty
retrieval that the verify step judged mostly irrelevant** (a real question the 40-article,
single-feed corpus genuinely doesn't cover) keeps the agentic answer, which states the gap
explicitly instead of discarding a true answer in favor of "no matching news signals."

## `news_signals` is extracted but not yet joined into retrieval or the answer

Flagged by the code review, and accurate: `ExtractNewsSignalsCommand` loads real,
German-aware signals into `news_signals` (verified: 5 expansion, 10 power, 2 renewable, 7
retrofit, 8 investment across 40 real articles — see defect #4), but no code path currently
*reads* that table back out. `NewsRetrievalService._to_result()` doesn't join it;
`AgenticAnswerPrompt` never mentions it. The plan's Intended Outcome says the answer "states
which signals it found" — today it states what the *verify step* judged relevant, not these
structured signals specifically.

This is a real, honestly-disclosed gap rather than a claim this document makes falsely: the
data asset exists and is correctly populated, but surfacing it in retrieval/the answer is
unimplemented. Treated as out of scope for this fix pass (it's a feature addition, not a
defect fix) — recorded here so a reader of this document knows not to assume otherwise.

### 12. "Thin evidence" wasn't actually surfacing national context — FIXED

Found by running the real 14-question planner eval (`EVAL.md`), not by code review. The plan's
own Decision names this requirement explicitly: *"Thin evidence: Name the gap and what was
searched, then give the national context that does exist."* `AgenticRagService._filter_relevant`
already did the right thing — when `verify` finds nothing it can specifically confirm
(`relevant_ids: []`), it falls back to the raw retrieved articles rather than an empty list, so the
answer step did have real evidence available. But for three real eval questions asking about a
place not in the corpus (Dortmund, Wuppertal, Bonn), the model declined to use that evidence at
all and answered a bare "no information found" with zero citations on two of the three — the code
path was correct, the prompt wording wasn't eliciting the behavior the plan called for.

**Fix:** `AgenticAnswerPrompt` (`app/ai/prompts/agentic_answer_prompt.py`) now explicitly
separates the two things the plan's decision actually asks for: state plainly there's no
place-specific coverage, **then** separately summarize what the evidence says about the same theme
at a national/regional level, with its own citations.

**Verified live, before and after the wording change**, same three questions:

Before (q11, Bonn investment signals): *"Nach der vorliegenden Evidenz gibt es keine aktuellen
Investitions- oder Erweiterungssignale für den Raum Bonn... spezifische Informationen... liegen
nicht vor."* — zero citations, despite 11 articles having been retrieved and passed as evidence.

After (same question, re-run): states no Bonn-specific signal, then: *"Amazon is investing €2.7
billion in cloud and AI infrastructure in Germany by 2027 [3]..."* — real national context, with
citations.

**Test:** `tests/test_agentic_rag.py::test_filter_relevant_falls_back_to_retrieved_articles_when_empty`
confirms the filtering logic (which was already correct); the prompt-wording improvement itself
can only be verified against the live model, not a stub — see `EVAL.md` for the full before/after
transcripts across all three affected questions.

## Two plan items not implemented (recorded, not silently dropped)

Flagged by the code review; both are real gaps against the plan's literal text, neither
breaks the headline acceptance scenario (verified by hand-scoring the plan's own acceptance
question through `detect_intent` — NEWS wins clearly), and both are deliberately left for a
future session rather than rushed into this fix pass:

- **Decisions table: "Route `AIIntent.NEWS` through the new service and enrich
  `_site_analysis()`."** Only the first half was done. `_site_analysis()`
  (`app/services/ai_advisor_service.py`) is unchanged — a question that scores as
  `SITE_ANALYSIS`/`SEARCH_POWER`/`SEARCH_LAND`/etc. gets no news context or citations, even
  though the facility it's about might have relevant coverage.
- **Phase E: "bilingual citations in `ui/components/site_intelligence_panel.py` and the AI
  panel."** Only the AI panel (`ui/components/ai/*`) was touched;
  `ui/components/site_intelligence_panel.py` is unchanged.

## Known pre-existing limitation (out of scope, documented not fixed)

**Facilities are Germany-wide, not NRW-specific** (35 of 223 facilities, per `country_code`
spot-checks against the dashboard's NRW framing). `"NRW"` exists in this codebase only in
prompts and docstrings, never as a query filter. Pre-existing, unrelated to this feature;
noted here per the plan's risk section rather than silently left out of the record.
