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
(`app/services/news_retrieval_service.py`). `AgenticRagService` itself still produces an
answer in that case (naming the gap), but `AIAdvisorService._agentic_news()` distinguishes
two situations: an **empty first retrieval round** (retrieval infrastructure itself failed)
falls back to the pre-RAG keyword path (`_news()`, defect #5/#6 above) so the dashboard is
never worse than before; a **non-empty retrieval that the verify step judged mostly
irrelevant** (a real question the 40-article, single-feed corpus genuinely doesn't cover)
keeps the agentic answer, which states the gap explicitly instead of discarding a true
answer in favor of "no matching news signals."

## Known pre-existing limitation (out of scope, documented not fixed)

**Facilities are Germany-wide, not NRW-specific** (35 of 223 facilities, per `country_code`
spot-checks against the dashboard's NRW framing). `"NRW"` exists in this codebase only in
prompts and docstrings, never as a query filter. Pre-existing, unrelated to this feature;
noted here per the plan's risk section rather than silently left out of the record.
