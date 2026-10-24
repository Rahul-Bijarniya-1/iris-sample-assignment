# Project Context — Session Handoff

**Purpose of this file:** a fresh agent session should be able to read only this file and resume work
without re-deriving anything. Keep it current at the end of every session.

Last updated: **2026-10-24** · Last verified against live code + DB: **2026-10-24**

---

## START HERE

1. Read this whole file. It supersedes the README for project *state*; the README is now correct for
   setup and pipeline usage (it was rewritten this session — see Issue 6).
2. **Work is on `main`, 15 commits, pushed to a private repo of the user's own.**
   `fix/pipeline-defects` no longer exists — its 6 commits now sit directly on `main`.
   Remotes: `origin` → **`Rahul-Bijarniya-1/iris-sample-assignment` (private)**, `upstream` →
   `amaurisantosjr/iris-sample` (public, **READ access only — you cannot push there**).
   `upstream/main` is still the single squashed `76d448e Iris-Sample`.
3. **Do not trust `pipeline_context.md`** — a stale code dump. It now carries a warning header saying so.
4. Re-verify state before acting on it — claims below were true on the date above:
   ```bash
   cd ~/Assignment/iris-sample
   git log --oneline upstream/main..HEAD                    # expect 15 commits
   git status -sb                                           # expect main...origin/main, in sync
   uv run pytest                                            # expect 27 passed
   uv run alembic current                                   # expect b18ad888465f (head)
   psql -h localhost -p 5433 -U postgres -d nrw_dc_bi -c "
     select relname, n_live_tup from pg_stat_user_tables
     where schemaname='iris_core' order by relname;"         # all 7 tables populated
   ```
5. **Guardrail:** do not run the full data pipeline (`main.py all`) without asking the user first. It
   makes many live external requests, takes a long time, and has already triggered one rate-limit ban.
6. Time constraint: 48-hour take-home. Exact deadline not recorded — confirm with the user if it
   affects prioritisation. **Amauri is not reachable** — do not plan around asking him for data or
   scope decisions; both external data blockers were resolved independently (Issues 4 and 8).

---

## What the project is

**IRIS Core / NRW Data Center BI** — a geospatial decision-support platform for siting data centers in
North Rhine-Westphalia, Germany.

A staged ETL pipeline scrapes public infrastructure data (datacentermap.com facilities, OpenStreetMap
Overpass, Germany's MaStR energy registry, BORIS land values, RSS news feeds), lands it in
PostgreSQL/PostGIS, enriches it with spatial analysis and a composite site score, and serves it through a
Streamlit dashboard with an OpenAI-backed advisor.

Architecture is conventionally layered, one directory per stage:

```
scrapers/extractors → parsers → transformers → mergers → enrichers → scorers → loaders
                            → repositories → services → ui/
```

Key files: `app/runners/` (one runner per step — the real entry points), `app/config/paths.py`
(`DataPaths`, the path convention), `app/runners/run_context.py` (staged runs), `ui/app.py`.

---

## Environment (verified working)

| Item | Value |
|---|---|
| OS | macOS |
| Postgres | Postgres.app, PostgreSQL 17, **port 5433** |
| PostGIS | 3.5.6 |
| Database | `nrw_dc_bi` |
| App schema | `iris_core` (7 tables) |
| Python | 3.12 via `uv`, `.venv` at repo root |
| Alembic head | `b18ad888465f` — all 14 migrations applied |
| Tests | pytest, 27 tests, `uv run pytest` |

`.env` at repo root uses a **single `DATABASE_URL`**, not split `POSTGRES_*` vars —
`app/database/session.py` and `alembic/env.py` both only read `DATABASE_URL`. `.env.example` now exists
and documents this.

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/nrw_dc_bi
OPENAI_API_KEY=sk-...        # STILL A PLACEHOLDER — needed for the AI Advisor
```

---

## Verified current state

- Environment, migrations, tests: **working.**
- **Defects: fixed.** Issues 1, 2, 3, 6, 7, 10, 11 and 12 below are closed with tests.
- Database: **all 7 tables populated** — see the table below.
- Data on disk (~500 MB, all gitignored): 420 MB BORIS shapefile, 66 MB raw Overpass, 18 MB processed
  Overpass, 232 KB MaStR, 24 KB news.
- One failed pipeline attempt staged at `data/runs/2026-10-24_144227/` →
  `run_status.json: {"status": "FAILED", "error": "429 ... datacentermap.com/germany/"}`. Left in place
  as evidence.
- Dashboard: **runs end to end against real data.** `uv run python ui/app.py` (bare mode) exits 0.
  Verify this way, not with `streamlit run` + HTTP 200 — see the note under Issue 3.

| Table | Rows | Source |
|---|---|---|
| `land_values` | 61,916 | BORIS NRW open data (Issue 8) |
| `power_infrastructure` | 45,363 | Overpass |
| `osm_infrastructure` | 481 | Overpass |
| `facilities` | 223 | **OpenStreetMap fallback, not datacentermap** (Issue 4) |
| `energy_assets` | 100 | MaStR (capped — Issue 9) |
| `news_articles` | 40 | DataCenter-Insider RSS |
| `news_matches` | 1 | entity matcher (Issue 12) |

**All seven tables are populated and the full stack runs end to end.** `ui/app.py` in bare mode exits 0
and computes real composite scores (e.g. `overall_score: 47, rating: Moderate`) with working news
intelligence.

**The one caveat that matters:** `facilities` is **OpenStreetMap-derived, not datacentermap**. See Issue 4.
It is a deliberate, documented substitute so the rest of the pipeline could be exercised; it carries far
fewer attributes than datacentermap (no power capacity, no floor space). Replace it with a real Phase 1
run when datacentermap is reachable — the loader upserts and the id spaces are disjoint.

---

## Commits on `main` (pushed to `origin`)

| Commit | What |
|---|---|
| `b4f6fd3` | `.gitignore` + pytest scaffolding |
| `e7760b8` | root migration creates the `app` schema (Issue 2) |
| `717a2e3` | wire facility loading into the pipeline (Issue 1) |
| `43605a7` | guard the site score lookup on the dashboard (Issue 3) |
| `528960a` | document the data pipeline, fix README defects (Issue 6) |
| `5665ed6` | derive test DB server from `DATABASE_URL` |
| `66bc109` | add this handoff document |
| `69394f0` | update handoff doc for the move to a private origin |
| `fd6b9cd` | record Phase 2 load results and Issues 7–9 |
| `89030ff` | wire energy asset loading into the pipeline (Issue 7) |
| `aae15a0` | keep `country_code` through MaStR parsing (Issue 10) |
| `480f831` | ignore acquired/derived datasets in git |
| `0cc062b` | read BORIS in the encoding its `.cpg` declares (Issue 11) |
| `1027fa2` | flush articles before resolving news matches (Issue 12) |
| `6715236` | OpenStreetMap fallback for facility acquisition (Issue 4) |

Test suite (27 tests, `tests/`):

- `test_migration_chain.py` — `alembic upgrade head` on a genuinely fresh DB
- `test_facility_load_wiring.py` — `facility-load` is a command, phase 1 calls it, path comes from DataPaths
- `test_facility_loading.py` — facilities actually land in `iris_core.facilities`, idempotently, with PostGIS geometry
- `test_energy_asset_load_wiring.py` — `energy-asset-load` is a command, phase 2 calls it after `mastr-transform`
- `test_mastr_parsing.py` — `country_code` survives parsing (Issue 10 regression guard)
- `test_boris_encoding.py` — umlauts survive the shapefile read (Issue 11 regression guard)
- `test_news_match_loading.py` — a match loads on the *first* run (Issue 12 regression guard)
- `test_dashboard_site_sections.py` — the missing-intelligence path
- `test_db_config.py` — the suite follows `DATABASE_URL`

Database tests create and drop their own `nrw_dc_bi_migtest_*` scratch databases. They never touch
`nrw_dc_bi`, and skip when no server is reachable.

---

## Issues

### 1. Facilities never loaded into the database — **FIXED** (`717a2e3`)

`app/runners/facility_load_runner.py` was the only code path writing `iris_core.facilities`, but it was
absent from `PipelineRunner.commands` and from every phase — unreachable from `main.py`. Even a
100 %-successful `main.py all` left the table empty. `load_facilities_command.py` also hardcoded a flat
path a staged run never writes to.

Fixed: added a `facility-load` command, called at the end of `phase_1`; `LoadFacilitiesCommand` now
resolves its input through `DataPaths`. `FacilityLoader` itself needed no changes — it was already a
correct idempotent upsert on `source_id`.

### 2. Migration chain assumed a pre-existing `app` schema — **FIXED** (`e7760b8`)

The root revision created `app.facilities` but no migration created the `app` schema, so
`alembic upgrade head` failed on any fresh database with
`psycopg.errors.InvalidSchemaName: schema "app" does not exist`. Original setup needed a manual
`CREATE SCHEMA IF NOT EXISTS app`.

Fixed: the root revision now runs `op.execute("CREATE SCHEMA IF NOT EXISTS app")`, mirroring how
`13108b59b03f` creates `iris_core`. Create-only, like the rest of the chain.

The leftover empty `app` schema (6 unused tables) in the project DB is from the original workaround.
Harmless — nothing reads it.

### 3. Dashboard crashed on empty data — **FIXED** (`43605a7`)

`ui/app.py` initialised `site_intelligence = None`, replaced it only when a facility was selected, then
called `site_intelligence.get("site_score")` unconditionally → `AttributeError: 'NoneType' object has no
attribute 'get'`. Both panels already handled a missing payload; only the lookup was unguarded.

Fixed with `site_section()` in `ui/site_intelligence_view.py`. Verified by running `ui/app.py` as a plain
script against the empty DB: exit 0 with the guard, original AttributeError without it.

> Note for future verification: `streamlit run` + an HTTP 200 does **not** exercise the script. Streamlit
> serves the page shell over HTTP and runs the script only when a websocket session connects — the server
> came up clean while this bug was live. Run the script directly in bare mode instead.

### 4. `main.py all` aborts on a live-scraping rate limit — **WORKED AROUND, root cause still open**

**Status 2026-10-24 23:30:** still 429 after **~9 hours**. Probe it in one second instead of paying the
8-minute retry cycle:

```bash
curl -sI -A "Mozilla/5.0" https://www.datacentermap.com/germany/ | head -1
```

**Worked around** by `scripts/build_facilities_from_osm.py`, which builds an equivalent dataset from
Overpass (`telecom=data_center`, 268 elements in Germany → 223 named facilities with coordinates) in the
shape `FacilityParser` expects. That unblocked the entire downstream chain: geo-transform → power
enricher → BORIS enricher → site score → entity matcher → news load.

**This is a substitute, not a fix.** OSM carries no power capacity, floor space or operator detail. When
datacentermap is reachable, run the real Phase 1: `FacilityLoader` upserts on `source_id` and the
generated ids are offset into a disjoint space, so the two coexist.

Original diagnosis follows.


Phase 1's country scraper hit `429 Too Many Requests` on `https://www.datacentermap.com/germany/`,
retried 3× with backoff (~7.7 min), then aborted cleanly without promoting. Not a code bug.

**This is routable around.** `app/runners/country_runner.py:18-33` documents a three-tier strategy:
run-dir file → legacy `data/raw/datacentermap/de.json` → fresh scrape. **Seeding that one JSON file skips
the rate-limited call entirely.** No such cache ships with the repo. `facility_runner` likewise caches per
market and sleeps 8–15 s between fresh requests, so it is far less likely to be throttled than the
one-shot country scrape.

Phases 2–4 hit entirely different hosts (Overpass, MaStR, BORIS, RSS) and **have never been attempted.**

### 7. `energy_assets` loader is unreachable from the pipeline — **FIXED** (`89030ff`)

`app/loaders/energy_asset_loader.py` and `app/commands/load_energy_assets.py` both exist, and the MaStR
chain (`mastr` → `mastr-parse` → `mastr-transform`) successfully produces
`data/processed/mastr/power_generation.json`. But there is **no `energy-asset-load` command** — zero
references to the loader anywhere in `app/runners/pipeline_runner.py` or any runner. `energy_assets` can
therefore never be populated via `main.py`.

This was the **identical defect to Issue 1**, fixed for facilities in `717a2e3`.

Fixed the same way: added an `energy-asset-load` command called at the end of `phase_2`, plus a
`LoadEnergyAssetsCommand` resolving its input through `DataPaths`. `EnergyAssetLoader` needed no changes —
already an idempotent upsert on `mastr_number`. Covered by `tests/test_energy_asset_load_wiring.py`.

**`energy_assets` now holds 100 rows**, verified idempotent across two runs.

### 10. `MaStRParser` dropped `country_code` — **FIXED** (`aae15a0`)

Surfaced only once Issue 7 made the loader reachable. `energy_assets.country_code` is `String(2)`
`NOT NULL` and every record in `processed/mastr/power_generation.json` carries `"DE"`, but
`MaStRParser._build_entity` never passed it to `EnergyAsset`. The load aborted on the first batch with
`psycopg.errors.NotNullViolation`, leaving the table empty.

One-line fix, covered by `tests/test_mastr_parsing.py`. Worth noting as a lesson: Issue 7 looked like a
pure wiring bug, but unreachable code had been hiding a second defect behind it.

### 11. BORIS shapefile read in the wrong encoding — **FIXED** (`0cc062b`)

`boris_transformer.py` hardcoded `encoding="cp1252"` while the NRW download ships a `.cpg` sidecar
declaring UTF-8. pyshp *warns* about the mismatch instead of failing, so it went unnoticed: 15,939 of
61,916 rows landed with mojibake names ("Köln" → "KÃ¶ln"). Zero rows had correct umlauts.

Fixed by reading the `.cpg` when present, keeping cp1252 as the fallback for older exports that ship
without one. Covered by `tests/test_boris_encoding.py`. Reloaded: mojibake count is now 0.

### 12. News matches never loaded on a first run — **FIXED** (`1027fa2`)

`NewsLoader.execute()` adds articles to the session, then resolves each match's article by URL.
`SessionLocal` sets `autoflush=False` (`app/database/session.py:18`), so those articles were still
pending and invisible to the lookup — every match was skipped and `news_matches` stayed empty.

The articles commit at the end of the run, so running the step a *second* time did load the matches.
That masked the bug in manual testing while leaving a one-shot `main.py all` with zero matches.

Fixed with `session.flush()` between the two phases — inside the existing transaction, so rollback
semantics are unchanged. Covered by `tests/test_news_match_loading.py`.

### 8. BORIS has no acquisition step — **RESOLVED** (data acquired manually)

The pipeline exposes `boris-transform` and `boris-enricher` but nothing that *fetches* BORIS data.
`boris-transform` fails immediately:

```
FileNotFoundError: BORIS shapefile not found: data/raw/boris/BRW_2026.shp
```

The repo ships no such shapefile and no step downloads one. **Resolved without Amauri:** BORIS NRW is
open data under *Datenlizenz Deutschland – Zero – 2.0* (unrestricted use, including commercial).

```bash
curl -O https://www.opengeodata.nrw.de/produkte/infrastruktur_bauen_wohnen/boris/BRW/BRW_EPSG25832_Shape.zip
unzip -d data/raw/boris/ BRW_EPSG25832_Shape.zip
cd data/raw/boris && for e in shp dbf shx prj cpg; do mv BRW_2026_Polygon.$e BRW_2026.$e; done
```

Two gotchas worth recording:

- The year-stamped archives stop at **`BRW_2025`**. The 2026 data lives only in the rolling
  `BRW_EPSG25832_Shape.zip`, which contains `BRW_2026_Polygon.*`.
- NRW names it **`BRW_2026_Polygon.shp`**, the transformer expects **`BRW_2026.shp`** — hence the rename.
  The original author evidently did this by hand; nothing in the repo records it.

A real fix would add a `boris` acquisition step, or make `FILENAME` tolerate the `_Polygon` suffix.
Deliberately not done — it is new functionality, not a defect, and the data is now in place.

### 9. MaStR scraper is capped at 100 records — **OPEN, by design?**

`app/scrapers/mastr/mastr_scraper.py:57-58` hardcodes `max_pages: int = 5, page_size: int = 20`, so a
full run yields exactly 100 records from a national registry holding millions. Looks like a demo/sample
limit rather than a defect, but it means "Data Collection — Completed" in the README overstates MaStR.

### 5. `DataPaths` convention violations — **mostly not a defect**

Corrected from the earlier reading of this file. `app/config/paths.py` says all ETL components should use
`DataPaths`, and 58 files do. Of the apparent violations:

| File | Verdict |
|---|---|
| `app/commands/load_facilities_command.py:17` | **was** the only real one — fixed in `717a2e3` |
| `app/scrapers/datacentermap/facility_scraper.py:26` | **not** a violation — `LEGACY_FACILITIES_DIR` is a deliberate legacy-cache constant; real output goes through `self.paths` |
| `app/runners/country_runner.py:79` | **not** a violation — the intentional legacy-cache fallback |
| `app/exporters/factsheet_exporter.py:41`, `map_renderer.py:76` | output destinations, not staged-run inputs — left alone (deferred) |

### 6. README was incomplete and wrong — **FIXED** (`528960a`)

It stopped at `streamlit run ui/app.py` and never mentioned that the dashboard reads from a database the
repo ships no data for; referenced a non-existent `.env.example`; used the wrong env-var shape; never said
to create the database or enable PostGIS; had a duplicate ASCII diagram whose stray code fences left a
block open, breaking rendering of every section after it; listed an `app/repositories/` that does not
exist; and linked to two TOC sections that were never written.

Fixed: added a **Data Pipeline** section (four phases and their steps, individual steps, staged runs,
external rate limits), plus Create the Database / Load the Data / Run the Tests steps, and `.env.example`.

---

## Pipeline reference

`uv run python main.py <command>` — **23** steps plus `all` (24 keys in `PipelineRunner.commands`).

- **Phase 1 — Data Acquisition:** `country` → `markets` → `facilities` → `merge` → `transform` →
  `facility-geo-transform` → `facility-load`  *(datacentermap.com)*
- **Phase 2 — Infrastructure:** `overpass` → `overpass-parse` → `overpass-transform` → `mastr` →
  `mastr-parse` → `mastr-transform` → `boris-transform`  *(Overpass, MaStR, BORIS)*
- **Phase 3 — Spatial Intelligence:** `power-enricher` → `boris-enricher` → `site-score`
- **Phase 4 — Business Intelligence:** `news` → `entity-matcher` → `news-load` → `news-intelligence` →
  `land-values` → `power-infrastructure` → `osm-infrastructure`  *(RSS via `feedparser`)*

**Staging model** (`app/runners/run_context.py`): `all` creates an isolated `RunContext` writing to
`data/runs/<run_id>/`, and on full success promotes to **`data/current/`** — a *filesystem* dataset, not
the database. Database writes happen inside individual load steps (`facility-load`, `news-load`,
`land-values`, `power-infrastructure`, `osm-infrastructure`), so they are **not** rolled back when a later
phase fails. Individual commands run without a RunContext and use the flat `data/` workspace.

---

## Decisions already made

- `.env` uses a single `DATABASE_URL` — settled by reading the code; don't re-litigate against the README.
- Defects were fixed on a branch, **not** a worktree, because the user has files from this directory open
  in their IDE.
- The `app`-schema fix is create-only (no `DROP SCHEMA` on downgrade), matching every other migration.
- `facility_load` sits at the **end** of phase 1, keeping all DB writes after all file production.
- `pipeline_context.md` was **not deleted**, only given a warning header — it is a tracked file the
  original author added.
- Individual-step path behaviour was left alone: `main.py facility-load` standalone reads flat
  `data/processed/...`, so after a staged run promoted to `data/current/` it can fail with
  FileNotFoundError. Pre-existing for all 23 steps; changing it would alter every step.
- The final code review this session was a **self-review**, not a fresh reviewer. Weigh that before merge.
- The work was pushed to a **private repo under the user's own account**
  (`Rahul-Bijarniya-1/iris-sample-assignment`) rather than a fork, accepting the loss of visible
  lineage in exchange for not publishing the solution where it could serve as an answer key for future
  candidates. `upstream` was kept so the original remains reachable for pulling or a later fork/PR.
- `context.md` is now **tracked and committed** (`66bc109`). It contains candid internal notes; keep that
  in mind if the repo visibility ever changes or it is shared with Amauri.

---

## Next steps

**Data: done.** All 7 tables are populated and the stack runs end to end. What remains is replacing the
substitute facilities with the real ones.

- [ ] **Replace OSM facilities with datacentermap** once the 429 lifts. Probe with the one-second curl in
      Issue 4; when it returns 200, run `country` → `markets` → `facilities` → `merge` → `transform` →
      `facility-geo-transform` → `facility-load`, then re-run Phase 3 and the news chain. The loader
      upserts and the id spaces are disjoint, so nothing needs deleting first.
- [ ] Put a real `OPENAI_API_KEY` in `.env` — still the literal placeholder `sk-...`, so the AI Advisor
      cannot run at all.
- [ ] Consider a fresh (non-self) code review before submitting — `/code-review`.

**README accuracy — unreported findings.** The README's status list is wrong in both directions:
- Overclaims **RAG as complete** — there is no retrieval machinery anywhere (no embeddings, vectors,
  pgvector, FAISS, cosine similarity), only SQL results stuffed into a prompt.
- Underclaims **Intent Detection** and **Tool Routing** as "In Progress" — both are fully implemented
  (12-member `AIIntent` enum, keyword scoring, a 12-branch dispatch at
  `app/services/ai_advisor_service.py:436-545`).
- Contradicts itself: line 91 marks "Context-aware Responses" complete, line 518 lists it In Progress.
- **LangGraph** is listed In Progress but is entirely absent — not in `pyproject.toml`, not installed.

**Deferred minors (deliberately not done)**
- [ ] README doesn't mention `uv run pytest -m "not integration"` for running without a database
- [ ] `app/exporters/factsheet_exporter.py:41` and `map_renderer.py:76` still hardcode `Path("data")`
- [ ] `app/commands/load_facilities.py` is a dead near-duplicate wrapper around `FacilityLoader`

**Decide**
- [ ] How to submit. **Amauri is not reachable** (user's call, 2026-10-24), so the blockers were resolved
      independently rather than by asking. The repo carries no submission instructions and `upstream`
      grants READ only, so a PR would require a fork — and a fork of a public repo cannot be made
      private, which is why the private copy was chosen.
- [ ] Whether to surface the README-accuracy findings above as part of the deliverable.

**Always**
- [ ] Update this file at the end of each session: refresh the "Last verified" date, move items between
      sections, record new decisions.

---

## Quick reference

```bash
cd ~/Assignment/iris-sample

# tests
uv run pytest
uv run pytest -m "not integration"      # skip the database tests

# connect to the DB
psql -h localhost -p 5433 -U postgres -d nrw_dc_bi

# row counts across the app schema
psql -h localhost -p 5433 -U postgres -d nrw_dc_bi -c "
  select relname, n_live_tup from pg_stat_user_tables
  where schemaname='iris_core' order by relname;"

# migrations (now work on a fresh DB with no manual schema prep)
uv run alembic current
uv run alembic upgrade head

# dashboard → http://localhost:8501
uv run streamlit run ui/app.py

# pipeline: individual steps are safe-ish; `all` needs the user's OK
uv run python main.py --help
uv run python main.py <step>
```

Ad-hoc inspection helpers live in `scripts/` (`verify_boris.py`, `verify_news.py`,
`verify_geo_facility.py`, `inspect_database_indexes.py`, …) — useful after any load.
