# Project Context — Session Handoff

**Purpose of this file:** a fresh agent session should be able to read only this file and resume work
without re-deriving anything. Keep it current at the end of every session.

Last updated: **2026-10-26** (hardening pass + final reviews) · Last verified against live code + DB: **2026-10-26**

---

## START HERE

1. Read this whole file. It supersedes the README for project *state*; the README was corrected this
   session (see "README corrections" below) and should now be consistent with it.
2. **Work is on branch `feat/agentic-rag`, 30 commits ahead of `main`**, checked out in place (not a
   worktree — the user has this directory open in their IDE). `main` itself is 15 commits ahead of
   `upstream/main` and pushed to the user's private `origin`. Remotes: `origin` →
   `Rahul-Bijarniya-1/iris-sample-assignment` (private), `upstream` → `amaurisantosjr/iris-sample`
   (public, READ only). The follow-up hardening changes are currently uncommitted pending the
   required pre-commit confirmation gate.
3. **`feat/agentic-rag` is NOT yet pushed or merged.** Opening a PR needs the user's explicit go-ahead —
   not given yet this session. Don't push without asking.
4. **The follow-up 25-finding hardening plan is implemented.** It closes model-output, trace,
   transaction, keyword-search, extraction, loader, embed, and structured-signal-consumption gaps.
   Low-risk Group 9 work centralized lazy OpenAI configuration and deferred vector loading; embedding
   batching and broad shared-fixture refactoring remain deliberately deferred. See `FINDINGS.md`.
5. Re-verify state before acting on it:
   ```bash
   cd ~/Assignment/iris-sample
   git log --oneline main..feat/agentic-rag              # expect 30 committed revisions
   git status -sb                                        # hardening diff remains until Gate 2 approval
   .venv/bin/pytest                                       # expect 176 passed, 2 skipped
   .venv/bin/pytest -m "not integration"                 # expect 136 passed, 2 skipped, 40 deselected
   .venv/bin/pytest -m "not live"                        # expect 176 passed, 2 deselected
   uv run alembic current                                 # expect d88d670b067f (head)
   psql -h localhost -p 5433 -U postgres -d nrw_dc_bi -c "
     select count(*) articles, count(published_at) dated, count(summary_en) translated,
            count(embedding) embedded from iris_core.news_articles;"   # expect 40/40/40/40
   psql -h localhost -p 5433 -U postgres -d nrw_dc_bi -c "
     select count(*) from iris_core.news_signals;"         # expect 40
   ```
6. **Guardrail (unchanged):** don't run the full data pipeline (`main.py all`) without asking the user
   first. `news-embed` and `news-signals` additionally make real paid OpenAI calls — see below.
   `uv run pytest -m live` also makes two small real OpenAI calls (opt-in only, never runs by default).
7. Time constraint: 48-hour take-home, started 2026-10-24. **Amauri is not reachable** — don't plan
   around asking him; blockers have been resolved independently throughout.
8. **The eval is done and rerun after hardening.** The 2026-10-26 live result is recorded in
   `EVAL.md` and `eval/results.json`: coverage recall@5 `0.50`, partial recall@5 `0.33`; q9–q11
   correctly carry no citations when the verifier explicitly rejects every retrieved candidate.

---

## What the project is

**IRIS Core / NRW Data Center BI** — a geospatial decision-support platform for siting data centers in
North Rhine-Westphalia, Germany, now with an **Agentic RAG** news-intelligence feature: a planner asks a
natural-language question (optionally naming a place instead of selecting a facility) and gets a
grounded, cited answer over a 40-article German news corpus via a plan → retrieve → verify → refine →
answer loop backed by pgvector.

A staged ETL pipeline scrapes public infrastructure data (datacentermap.com facilities, OpenStreetMap
Overpass, Germany's MaStR energy registry, BORIS land values, RSS news feeds), lands it in
PostgreSQL/PostGIS, enriches it with spatial analysis and a composite site score, and serves it through a
Streamlit dashboard with an OpenAI-backed advisor — now including the agentic news loop.

```
scrapers/extractors → parsers → transformers → mergers → enrichers → scorers → loaders
                            → repositories → services → ui/
```

Key files: `app/runners/` (one runner per step), `app/config/paths.py` (`DataPaths`), `ui/app.py`. New
this session: `app/services/agentic_rag_service.py` (the orchestrator), `app/services/
news_retrieval_service.py` (pgvector search), `app/extractors/openai_extractor.py`.

---

## Environment (verified working)

| Item | Value |
|---|---|
| OS | macOS |
| Postgres | Postgres.app, PostgreSQL 17, **port 5433** |
| PostGIS | 3.5.6 |
| pgvector | 0.8.6 (extension created this session via migration `d88d670b067f`) |
| Database | `nrw_dc_bi` |
| App schema | `iris_core` (8 tables now — `news_signals` added) |
| Python | 3.14.6, `.venv` at repo root |
| Alembic head | `d88d670b067f` — 15 migrations applied |
| Tests | pytest, **166 collected** (164 default + 2 opt-in `live`) |

`.env` at repo root: `DATABASE_URL` + `OPENAI_API_KEY` (a **real key**, confirmed working this session —
no longer the `sk-...` placeholder noted in the previous handoff) + optionally `OPENAI_MODEL` (mini,
default `gpt-4.1-mini`) and `OPENAI_ANSWER_MODEL` (default `gpt-4.1`) + `OPENAI_EMBEDDING_MODEL` (default
`text-embedding-3-small`, 1536 dims, matching the migration's `vector(1536)` column).

---

## Verified current state (2026-10-26, after the hardening pass)

- Environment, migrations, tests: **working.** 164/164 non-live tests pass; the 2 paid live tests
  remain explicit opt-in tests.
- Database: **all 8 tables populated**, including the new `news_signals` (40 rows, real German-aware
  extraction — see table below).
- `news_articles`: all 40 rows have `published_at`, `title_en`/`summary_en` (real English translations,
  not fallback-to-source), and a 1536-dim `embedding`. Re-running `news-embed` is a verified true no-op.
- Dashboard: **verified live in a browser** this session (Playwright, ephemeral — not a project
  dependency). Asked a news question with **no facility selected**; got a real cited, grounded answer
  with a working "How I got this" trace expander and bilingual citations. Zero console errors.
  `uv run python ui/app.py` (bare mode) also still exits 0.

| Table | Rows | Source / note |
|---|---|---|
| `land_values` | 61,916 | BORIS NRW open data |
| `power_infrastructure` | 45,363 | Overpass |
| `osm_infrastructure` | 481 | Overpass |
| `facilities` | 223 | **OpenStreetMap fallback, not datacentermap** (unchanged this session — see prior Issue 4) |
| `energy_assets` | 100 | MaStR (capped) |
| `news_articles` | 40 | DataCenter-Insider RSS — now with translations + embeddings |
| `news_matches` | 1 | entity matcher (NaN city leak fixed this session) |
| `news_signals` | 40 | OpenAI-extracted signals: 5 expansion, 9 power, 3 renewable, 8 retrofit, 7 investment; joined into semantic retrieval |

**Caveats that still matter:** `facilities` is still OpenStreetMap-derived, not datacentermap;
the news corpus is 40 articles from one feed; and the free `EntityExtractor` intentionally retains
the weak German keyword-based `MockExtractor`. Accurate structured signals require the paid,
opt-in `news-signals` command. The signal rows are now joined into retrieval and both model prompts.

---

## This session's commits (on `feat/agentic-rag`, `main`..`feat/agentic-rag`)

**Uncommitted follow-up (awaiting Gate 2):** the eight hardening groups in
`a-planner-and-prepare-cosmic-pudding.md` are complete, plus the low-risk OpenAI-config and deferred
vector portions of Group 9. The working tree also contains the refreshed live eval result and
updated findings/context. No commit or push has been made for this follow-up yet.

The 30 committed revisions follow this historical phase sequence (the uncommitted follow-up above
is not included):

**Phase A — five pre-existing defects, each its own commit + regression test:**
`published_at` never parsed · NaN leaking into `news_matches.city` · duplicate dead
`build_news_context` · `_news()` discarding its own keyword-search result · `search_news` matching the
whole question as one substring instead of tokenizing it.

**Phase B — translation, embeddings, retrieval:**
migration `d88d670b067f` (vector extension, `news_articles` embedding columns + HNSW index,
`news_signals` table) · `EmbeddingService` / `TranslationService` (thin, injectable, hermetic tests) ·
`EmbedNewsCommand` + `news-embed` command (registered, **not** called by any phase — paid step) ·
`NewsRetrievalService` (pgvector cosine search, degrades to `[]` on recoverable failures while
surfacing embedding-dimension configuration defects) · two live-API bugs
found and fixed only by running for real (markdown-fenced JSON breaking parsing; non-deterministic
translation defeating the original hash-the-output idempotency design — redesigned to hash the source
instead). Full detail in `FINDINGS.md`.

**Phase C — real extraction:**
`OpenAIExtractor` (German-aware, structured, same output shape as the old `MockExtractor`) ·
`ExtractNewsSignalsCommand` + `news-signals` command (registered, not called by any phase, same
reasoning as `news-embed`). **Not** wired as `EntityExtractor`'s default — see FINDINGS.md's "Where
OpenAIExtractor is actually wired" for why (would make `main.py all` cost money).

**Phase D — the agentic loop:**
`AgenticRagService` (plan → retrieve → verify → refine(≤1) → answer; tool whitelist; k clamped 1-10;
recoverable failures degrade except a deliberate `EmbeddingDimensionMismatch`; `on_step` callback for live
status) · 3 new prompts (`RetrievalPlanPrompt`, `SufficiencyPrompt`, `AgenticAnswerPrompt`) ·
`LandValueRepository.find_municipality_location()` (place-name → centroid, for "near <place>" without a
selected facility) · `AIIntent.NEWS` now routes through `AgenticRagService` via `_agentic_news()`,
falling back to the old keyword path only when retrieval infrastructure itself degraded (all retrieval
rounds empty), not when a real question's evidence was thin.

**Phase E — UI surface:**
removed the blanket "select a facility first" gate (news questions can now name a place instead); live
`st.status` stepping (Planning/Retrieving/Verifying/Refining/Answering); bilingual citations (English
linked/bold, German muted) with date+source; collapsed "How I got this" trace expander. Verified live
in a browser.

**Phase F:** README corrections (Agentic RAG + Intent Detection + Tool Routing + Context
Awareness moved to Completed everywhere, with a scope line on the RAG claim; LangGraph moved to
Planned/Future, the inverse fix) · `FINDINGS.md` · a fresh-context (Opus) whole-branch review,
dispatched in the background, then a full fix pass on its findings:

- **2 Critical, both fixed:** `AgenticRagService._filter_relevant` could crash on a plausible malformed
  verify response (`relevant_ids` as objects or a bare scalar); all four OpenAI-backed services built
  their client eagerly in `__init__`, which raised before `NewsRetrievalService.search()`'s own
  try/except could catch a missing key — breaking the documented degradation guarantee and failing 5
  tests on any machine without `OPENAI_API_KEY` set. Both reproduced live before fixing, both
  re-verified live after (`env -u OPENAI_API_KEY uv run pytest` → 103/103, was 5 failed).
- **8 Important findings:** 6 fixed (site_ranking's result was computed but discarded — now reaches the
  answer and the trace; `OPENAI_API_KEY` docs corrected; embedding-model name added to the idempotency
  hash + a dimension guard; `capacity_mw`/`confidence` coercion + batch commits in `news-signals`;
  README's idempotency claim corrected; the missing `live` marker + `test_live_openai.py` added).
  Signal consumption was originally ruled out as a feature addition but is now implemented by the
  follow-up hardening pass; `_site_analysis()` enrichment remains a separate feature gap.
- Several Minor findings deferred — listed in the execution ledger, none judged to affect a planner
  using the dashboard enough to block the submission.

Eval and PR were excluded from that review's scope. **The eval is now rerun after hardening** — see
`EVAL.md`. The follow-up still needs Gate 2 commit approval; a PR remains a later, separate action.

Test suite after the follow-up pass: **164 non-live tests pass** (plus 2 opt-in `live` tests).
No test in the default run touches the OpenAI network; every model/embedding call is stubbed via an
injectable client, and construction of every OpenAI-backed class is lazy.

---

## Decisions and rulings made this session (deviations from the plan, with why)

Full detail and "cost if wrong" for each is in
`.superpowers/sdd/a-planner-and-prepare-cosmic-pudding/progress.md` (the execution ledger) — summarized
here:

1. **`PowerService`/`LandService` don't exist** (0-byte files, dead scaffold) despite the plan naming
   them as tool services. `SiteIntelligenceService.analyze_location()` already covers both via
   repositories directly. The agentic tool registry uses `SiteIntelligenceService` +
   `SiteRankingService` — two services, not four.
2. **Re-embed idempotency hashes the source, not the translated output** — the plan's literal design
   (hash the exact embedded English text) assumed deterministic translation, which is empirically false
   against `gpt-4.1-mini` even at `temperature=0` (measured 35-36/40 "unchanged" articles flagged as
   changed on an immediate re-run). Redesigned to hash German source + both model names, gating the
   `translate()` call itself. Verified: a real re-run is now
   `{'embedded': 0, 'skipped': 40, 'failed': 0}`.
3. **`OpenAIExtractor` is not `EntityExtractor`'s default** — the plan's literal "replace MockExtractor
   at its call site" would make every `main.py all` run cost money, since `EntityExtractor` runs inside
   the `news` step that `phase_4`/`all` calls. Kept the opt-in-command pattern (`news-signals`) instead,
   consistent with `news-embed`.
4. **The degradation fallback to the old keyword path triggers on an *all-empty retrieval trace***,
   not on "verify found nothing relevant." The latter is often a legitimate, correctly-framed answer
   (thin local coverage, stated honestly) that the old path would have replaced with a worse
   "no matching news signals" message.

None of these are disputed or unresolved — each was a judgment call made and tested during
implementation, documented for a reviewer to weigh.

---

## What's left (Phase F, remaining)

- [x] **The eval.** Done — 14 real user-supplied German planner questions, ground-truth labeled by
      hand against the real corpus, run for real against the live `AgenticRagService`. See `EVAL.md`
      (full report: methodology, recall@5 table, before/after literal text) and `eval/` (the
      question set, the runner, raw results). Surfaced and fixed one more real gap — see
      FINDINGS.md #12 (Thin evidence framing wasn't actually happening; fixed in
      `AgenticAnswerPrompt`, verified live before/after).
- [x] **`context.md` diagram check** — re-verified; `app/database/repositories/` is real and the
      diagram above is accurate. The plan's stale complaint predates this session.
- [ ] **Open the PR** — needs the user's explicit go-ahead before any push (not asked yet this
      session). `feat/agentic-rag` → `main`, both on the user's own private `origin`.
- [x] **Original whole-branch review** — complete; its 25-finding follow-up hardening pass is now
      implemented and verified. The final code/security reviews found no blockers; the uncommitted
      diff now waits only for Gate 2 confirmation before commits.
- [ ] **Older feature gaps** (outside this hardening plan): `_site_analysis()` is not enriched with
      news context, and the site-intelligence panel does not show the AI panel's bilingual citations.

**Deferred minors (deliberately not done, from the prior session, still true):**
- [ ] README doesn't mention `uv run pytest -m "not integration"` for running without a database
- [ ] `app/exporters/factsheet_exporter.py:41` and `map_renderer.py:76` still hardcode `Path("data")`
- [ ] Batch embedding API calls only after defining bulk failure-isolation and retry semantics
- [ ] Consolidate test fakes only in a dedicated cleanup; current fakes have materially different contracts
- [ ] Isolate untrusted prompt content, define global request/time/token limits, and validate citation URLs
- [ ] Add a migration enforcing one `news_signals` row per article for concurrent-writer safety

**Always:** update this file at the end of each session — refresh the "Last verified" date, move items
between sections, record new decisions.

---

## Issues carried over from before this session (still true, unchanged)

- **Facilities are Germany-wide, not NRW-specific** (35 of 223). Pre-existing, out of scope. `"NRW"`
  exists in this codebase only in prompts/docstrings, never as a filter.
- **MaStR scraper capped at 100 records** (`app/scrapers/mastr/mastr_scraper.py:57-58`,
  `max_pages=5, page_size=20`) — looks like a demo limit, not a defect.
- **`facilities` is OpenStreetMap-derived, not datacentermap** — the datacentermap.com 429 rate-limit
  was never confirmed lifted; this session didn't re-check it (out of scope — this session's work was
  entirely the Agentic RAG feature, not facility acquisition).

---

## Quick reference

```bash
cd ~/Assignment/iris-sample

# tests
uv run pytest
uv run pytest -m "not integration"      # skip the database tests

# connect to the DB
psql -h localhost -p 5433 -U postgres -d nrw_dc_bi

# migrations
uv run alembic current
uv run alembic upgrade head

# dashboard → http://localhost:8501
uv run streamlit run ui/app.py

# the two paid, opt-in steps (not part of `all`)
uv run python main.py news-embed     # translate + embed every article (pgvector)
uv run python main.py news-signals   # extract structured signals per article

# pipeline: individual steps are safe-ish; `all` needs the user's OK
uv run python main.py --help
```

Ad-hoc inspection helpers live in `scripts/` (`verify_boris.py`, `verify_news.py`,
`verify_geo_facility.py`, `inspect_database_indexes.py`, …) — useful after any load.
