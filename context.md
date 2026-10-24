# Project Context — Session Handoff

**Purpose of this file:** a fresh agent session should be able to read only this file and resume work
without re-deriving anything. Keep it current at the end of every session.

Last updated: **2026-10-24** · Last verified against live code + DB: **2026-10-24**

---

## START HERE

1. Read this whole file. It supersedes the README for project *state*; the README is now correct for
   setup and pipeline usage (it was rewritten this session — see Issue 6).
2. **Work is on branch `fix/pipeline-defects`, 6 commits ahead of `main`.** Not merged, not pushed.
   `main` is still the single squashed `76d448e Iris-Sample`.
3. **Do not trust `pipeline_context.md`** — a stale code dump. It now carries a warning header saying so.
4. Re-verify state before acting on it — claims below were true on the date above:
   ```bash
   cd ~/Assignment/iris-sample
   git log --oneline main..HEAD                             # expect 6 commits
   uv run pytest                                            # expect 20 passed
   uv run alembic current                                   # expect b18ad888465f (head)
   psql -h localhost -p 5433 -U postgres -d nrw_dc_bi -c "
     select relname, n_live_tup from pg_stat_user_tables
     where schemaname='iris_core' order by relname;"         # all still 0 rows
   ```
5. **Guardrail:** do not run the full data pipeline (`main.py all`) without asking the user first. It
   makes many live external requests, takes a long time, and has already triggered one rate-limit ban.
6. Time constraint: 48-hour take-home. Exact deadline not recorded — confirm with the user if it
   affects prioritisation. Contact for scope questions / data: **Amauri**.

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
| Tests | pytest, 20 tests, `uv run pytest` |

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
- **Defects: fixed.** Issues 1, 2, 3 and 6 below are closed with tests. See the branch.
- Database: **all 7 `iris_core` tables still at 0 rows.** No data has ever loaded.
- One failed pipeline attempt staged at `data/runs/2026-10-24_144227/` →
  `run_status.json: {"status": "FAILED", "error": "429 ... datacentermap.com/germany/"}`. Left in place
  as evidence.
- Dashboard: now loads against the empty database and renders "no data" states instead of crashing.

**Net:** the code defects that blocked a working dashboard are fixed; **the remaining blocker is purely
that no data has been acquired** (Issue 4, external rate limit).

---

## Branch `fix/pipeline-defects`

| Commit | What |
|---|---|
| `b4f6fd3` | `.gitignore` + pytest scaffolding |
| `e7760b8` | root migration creates the `app` schema (Issue 2) |
| `717a2e3` | wire facility loading into the pipeline (Issue 1) |
| `43605a7` | guard the site score lookup on the dashboard (Issue 3) |
| `528960a` | document the data pipeline, fix README defects (Issue 6) |
| `5665ed6` | derive test DB server from `DATABASE_URL` |

Test suite (20 tests, `tests/`):

- `test_migration_chain.py` — `alembic upgrade head` on a genuinely fresh DB
- `test_facility_load_wiring.py` — `facility-load` is a command, phase 1 calls it, path comes from DataPaths
- `test_facility_loading.py` — facilities actually land in `iris_core.facilities`, idempotently, with PostGIS geometry
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

### 4. `main.py all` aborts on a live-scraping rate limit — **STILL OPEN**

Phase 1's country scraper hit `429 Too Many Requests` on `https://www.datacentermap.com/germany/`,
retried 3× with backoff (~7.7 min), then aborted cleanly without promoting. Not a code bug.

**This is routable around.** `app/runners/country_runner.py:18-33` documents a three-tier strategy:
run-dir file → legacy `data/raw/datacentermap/de.json` → fresh scrape. **Seeding that one JSON file skips
the rate-limited call entirely.** No such cache ships with the repo. `facility_runner` likewise caches per
market and sleeps 8–15 s between fresh requests, so it is far less likely to be throttled than the
one-shot country scrape.

Phases 2–4 hit entirely different hosts (Overpass, MaStR, BORIS, RSS) and **have never been attempted.**

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

---

## Next steps

Direction A (fix the defects as the deliverable) is **complete**. What remains:

**Get data flowing — the only thing still blocking a working dashboard**
- [ ] Ask Amauri for a DB dump, or for a cached `data/raw/datacentermap/de.json` to seed past the 429
- [ ] Or try Phases 2–4 independently — different hosts, unaffected by the datacentermap.com 429
      *(ask the user before running: live external requests)*
- [ ] Or retry Phase 1 later and let the new `facility-load` step populate the table
- [ ] Put a real `OPENAI_API_KEY` in `.env` — required for the AI Advisor
- [ ] Once facilities exist, confirm the dashboard renders end to end with real data

**Deferred minors (deliberately not done)**
- [ ] README doesn't mention `uv run pytest -m "not integration"` for running without a database
- [ ] `app/exporters/factsheet_exporter.py:41` and `map_renderer.py:76` still hardcode `Path("data")`
- [ ] `app/commands/load_facilities.py` is a dead near-duplicate wrapper around `FacilityLoader`

**Decide**
- [ ] Whether to merge `fix/pipeline-defects` into `main`, and whether a fresh code review is wanted first
- [ ] Whether to report the migration bug and missing docs to Amauri as findings (there is no upstream
      remote to open a PR against — `main` is one squashed commit)

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
