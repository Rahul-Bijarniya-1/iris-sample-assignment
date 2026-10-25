# Project Context — Session Handoff

**Purpose of this file:** a fresh agent session should be able to read only this file and resume work
without re-deriving anything. Keep it current at the end of every session.

Last updated: **2026-10-25** · Last verified against live code + DB: **2026-10-25**

---

## START HERE

1. Read this whole file. It supersedes the README for project *state*; the README was corrected this
   session (see "README corrections" below) and should now be consistent with it.
2. **Work is on branch `feat/agentic-rag`, 21 commits ahead of `main`**, checked out in place (not a
   worktree — the user has this directory open in their IDE). `main` itself is 15 commits ahead of
   `upstream/main` and pushed to the user's private `origin`. Remotes: `origin` →
   `Rahul-Bijarniya-1/iris-sample-assignment` (private), `upstream` → `amaurisantosjr/iris-sample`
   (public, READ only).
3. **`feat/agentic-rag` is NOT yet pushed or merged.** Opening a PR needs the user's explicit go-ahead —
   not given yet this session. Don't push without asking.
4. Re-verify state before acting on it:
   ```bash
   cd ~/Assignment/iris-sample
   git log --oneline main..feat/agentic-rag              # expect 21 commits
   git status -sb                                        # expect feat/agentic-rag, clean
   uv run pytest                                          # expect 89 passed
   uv run alembic current                                 # expect d88d670b067f (head)
   psql -h localhost -p 5433 -U postgres -d nrw_dc_bi -c "
     select count(*) articles, count(published_at) dated, count(summary_en) translated,
            count(embedding) embedded from iris_core.news_articles;"   # expect 40/40/40/40
   psql -h localhost -p 5433 -U postgres -d nrw_dc_bi -c "
     select count(*) from iris_core.news_signals;"         # expect 40
   ```
5. **Guardrail (unchanged):** don't run the full data pipeline (`main.py all`) without asking the user
   first. `news-embed` and `news-signals` additionally make real (cheap) paid OpenAI calls — see below.
6. Time constraint: 48-hour take-home, started 2026-10-24. **Amauri is not reachable** — don't plan
   around asking him; blockers have been resolved independently throughout.
7. **Blocked on the user:** the eval set (10-15 planner questions, "the one input I should not author"
   per the plan) has not been received yet. Everything else in the plan is done or in progress without
   it — see "What's left" below.

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
| Python | 3.12 via `uv`, `.venv` at repo root |
| Alembic head | `d88d670b067f` — 15 migrations applied |
| Tests | pytest, **89 tests**, `uv run pytest` |

`.env` at repo root: `DATABASE_URL` + `OPENAI_API_KEY` (a **real key**, confirmed working this session —
no longer the `sk-...` placeholder noted in the previous handoff) + optionally `OPENAI_MODEL` (mini,
default `gpt-4.1-mini`) and `OPENAI_ANSWER_MODEL` (default `gpt-4.1`) + `OPENAI_EMBEDDING_MODEL` (default
`text-embedding-3-small`, 1536 dims, matching the migration's `vector(1536)` column).

---

## Verified current state (2026-10-25, after this session's work)

- Environment, migrations, tests: **working.** 89/89 passing.
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
| `news_signals` | 40 | **new** — real OpenAI-extracted signals: 5 expansion, 10 power, 2 renewable, 7 retrofit, 8 investment |

**The caveat that still matters:** `facilities` is still OpenStreetMap-derived, not datacentermap
(pre-existing, out of scope this session). **New caveat:** the news corpus is 40 articles from one feed
— the README now says so explicitly; see "Thin evidence" framing below.

---

## This session's commits (on `feat/agentic-rag`, `main`..`feat/agentic-rag`)

21 commits. By phase:

**Phase A — five pre-existing defects, each its own commit + regression test:**
`published_at` never parsed · NaN leaking into `news_matches.city` · duplicate dead
`build_news_context` · `_news()` discarding its own keyword-search result · `search_news` matching the
whole question as one substring instead of tokenizing it.

**Phase B — translation, embeddings, retrieval:**
migration `d88d670b067f` (vector extension, `news_articles` embedding columns + HNSW index,
`news_signals` table) · `EmbeddingService` / `TranslationService` (thin, injectable, hermetic tests) ·
`EmbedNewsCommand` + `news-embed` command (registered, **not** called by any phase — paid step) ·
`NewsRetrievalService` (pgvector cosine search, degrades to `[]` on any failure) · two live-API bugs
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
every model/tool call wrapped so failures degrade instead of raising; `on_step` callback for live
status) · 3 new prompts (`RetrievalPlanPrompt`, `SufficiencyPrompt`, `AgenticAnswerPrompt`) ·
`LandValueRepository.find_municipality_location()` (place-name → centroid, for "near <place>" without a
selected facility) · `AIIntent.NEWS` now routes through `AgenticRagService` via `_agentic_news()`,
falling back to the old keyword path only when retrieval infrastructure itself degraded (empty first
round), not when a real question's evidence was thin.

**Phase E — UI surface:**
removed the blanket "select a facility first" gate (news questions can now name a place instead); live
`st.status` stepping (Planning/Retrieving/Verifying/Refining/Answering); bilingual citations (English
linked/bold, German muted) with date+source; collapsed "How I got this" trace expander. Verified live
in a browser.

**Phase F (partial):** README corrections (Agentic RAG + Intent Detection + Tool Routing + Context
Awareness moved to Completed everywhere, with a scope line on the RAG claim; LangGraph moved to
Planned/Future, the inverse fix) · `FINDINGS.md`.

Test suite: 27 pre-existing + 62 new = **89 tests**. No test in the default run touches the network —
every OpenAI/embedding call is stubbed via an injectable client.

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
   changed on an immediate re-run). Redesigned to hash German source + translation-model name, gating
   the `translate()` call itself. Verified: a real re-run is now `{'embedded': 0, 'skipped': 40}`.
3. **`OpenAIExtractor` is not `EntityExtractor`'s default** — the plan's literal "replace MockExtractor
   at its call site" would make every `main.py all` run cost money, since `EntityExtractor` runs inside
   the `news` step that `phase_4`/`all` calls. Kept the opt-in-command pattern (`news-signals`) instead,
   consistent with `news-embed`.
4. **The degradation fallback to the old keyword path triggers on an *empty first retrieval round***,
   not on "verify found nothing relevant." The latter is often a legitimate, correctly-framed answer
   (thin local coverage, stated honestly) that the old path would have replaced with a worse
   "no matching news signals" message.

None of these are disputed or unresolved — each was a judgment call made and tested during
implementation, documented for a reviewer to weigh.

---

## What's left (Phase F, remaining)

- [ ] **The eval.** BLOCKED — needs the user's 10-15 planner questions ("the one input I should not
      author," per the plan). Once received: label which articles should surface for each, run them
      through `AgenticRagService`, report recall@5 before/after. Capture the literal before/after
      acceptance-test text (`"No matching news signals were found."` vs. the new grounded answer) for
      the submission.
- [ ] **`context.md` diagram check** — the plan flagged a stale `repositories` reference at the old
      line 52; the diagram above already reflects the real `app/database/repositories/` layer, so this
      looks already resolved, but re-verify against the actual directory tree if anything changed.
- [ ] **Open the PR** — needs the user's explicit go-ahead before any push (not asked yet this
      session). `feat/agentic-rag` → `main`, both on the user's own private `origin`.
- [ ] **Whole-branch review** — a fresh-context review (not self-review) was dispatched this session on
      the most capable available model before any PR; check this file's own later revision (or git log
      on this file) for whether it landed and what it found before treating the branch as done.

**Deferred minors (deliberately not done, from the prior session, still true):**
- [ ] README doesn't mention `uv run pytest -m "not integration"` for running without a database
- [ ] `app/exporters/factsheet_exporter.py:41` and `map_renderer.py:76` still hardcode `Path("data")`

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
