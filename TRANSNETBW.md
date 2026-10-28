# IRIS-SIG-30 — TransnetBW Project Radar Harvester

Harvests **grid-capacity-constraint** and **transformer-modernization** signals for
**Baden-Württemberg** from TransnetBW's public website into
**`iris_staging.signal_ingest`** on PostgreSQL 16 / PostGIS 3.4, with EPSG:25832 points.

- Integration pattern **B (HTML)**: the project listing, project pages and press-release
  pages are parsed as HTML. The press feed JSON is used only to *discover* articles; dates
  come from the article pages and are cross-checked against the feed.
- **Re-runs are idempotent.** The natural key is `(source_system, source_record_id)`. A
  content hash decides whether anything changed, and a version table keeps the history.
  The sitemap's `lastmod` drives incremental fetching.
- **Nothing is silently accepted or dropped.** Points must lie inside the official BW
  boundary (checked in Python *and* by a database trigger). Lines and regions get no
  invented point. Every exclusion, gap and failure is logged with a reason.
- **It can be demonstrated without production access**: `--offline` replays committed
  fixtures, with no network.

Observed on the live site (harvest of 2026-10-28; see [`artifacts/transnetbw/run_log.txt`](artifacts/transnetbw/run_log.txt)):

- **Records:** 25 projects discovered and 108 press releases fetched → **120 staged records**
  (23 projects, 97 press releases).
- **Signal types:** 75 grid capacity constraint, 45 transformer modernization.
- **Locations:** **52 points** (46 substation, 6 settlement level), 22 ambiguous lines or
  areas with their endpoints, and 46 unresolved, mostly national SuedLink milestones.
- **Dates:** **97 / 97** press dates confirmed by both the article page and the feed.
- **Exclusions:** 13, each with a reason; 11 records are held for review.
- **Re-run:** a second live run made **4 requests** and changed **nothing**.

---

## Contents

1. [Quick start](#quick-start)
2. [Source and its verification](#source-and-its-verification)
3. [What is staged](#what-is-staged)
4. [Mapping assumptions](#mapping-assumptions)
5. [Re-runs, increments and history](#re-runs-increments-and-history)
6. [Errors, exit codes and quality gates](#errors-exit-codes-and-quality-gates)
7. [How to run](#how-to-run)
8. [Tests](#tests)
9. [Outputs](#outputs)
10. [Known limitations](#known-limitations)
11. [Licences and attribution](#licences-and-attribution)
12. [Configuration](#configuration)
13. [Files](#files)

---

## Quick start

Offline, from the committed fixtures (no network):

```bash
uv sync
cp .env.example .env                       # set STAGING_POSTGRES_PASSWORD (any value)
docker compose up -d postgis16             # PostgreSQL 16 / PostGIS 3.4 on port 5434

# A database for the fixture demo; live runs use another one (see "Mode guard").
docker exec iris-postgis16 psql -U postgres -c "create database iris_signals_offline"
docker exec iris-postgis16 psql -U postgres -d iris_signals_offline -c "create extension postgis"
export OFFLINE_URL="postgresql://postgres:<password>@localhost:5434/iris_signals_offline"

DATABASE_URL="$OFFLINE_URL" uv run alembic upgrade head
uv run python -m app.transnetbw.cli harvest --offline --database-url "$OFFLINE_URL" --no-report
uv run python -m app.transnetbw.cli harvest --offline --database-url "$OFFLINE_URL" --no-report   # again: nothing changes
```

The first offline run:

```
TransnetBW Project Radar   run eadfb426  mode=offline
discovery sitemap 176 urls · listing 23 cards · 25 projects (gap 3)
projects  seen 25  fetched 8  unchanged-lastmod 0
press     feed 14 → candidates 9 → fetched 9  unchanged-lastmod 0
fetch     requests 27  failed 0  not-captured 17
classify  in 14  needs_review 1  excluded 3
geocode   resolved 9 (substation 9, municipality 0)
          ambiguous 3  unresolved 2  invalid 0
load      inserted 14  updated 0  unchanged 0  reverted 0  rejected 0  retired 0
issues    error 0  warning 5  info 24
status    SUCCEEDED  (exit 0)
```

The fixtures hold 8 of the 25 projects. The other 17 are reported as `not_captured`
(info, not a failure).

Live: `uv run python main.py transnetbw`, or `uv run python -m app.transnetbw.cli harvest`
for flags.

---

## Source and its verification

All facts below were checked by hand on **2026-10-27**. The live drift test
(`--run-live`) and the quality gates re-check them on every run.

| Fact | Consequence |
|---|---|
| The brief's URL `https://www.transnetbw.de/de/netzentwicklung` answers **HTTP 303** and lands on `/de/netzentwicklung/planung/netzentwicklungsplan`, an overview with no project data. | The harvester reads the real catalogue, `/de/netzentwicklung/projekte/alle-projekte`. |
| The catalogue is **server-rendered HTML on one page**: 23 project cards (`a.card-project`) in sections, including "Abgeschlossene Projekte". No pagination. The map is a schematic SVG with no coordinates. | Discovery parses cards by the site's own markup. A redesign yields zero cards and fails the run, rather than producing a guess. |
| `robots.txt` disallows only `/neos/`. | The fetcher honours it, and fails closed if it cannot be read (RFC 9309). |
| `/de/sitemap.xml` lists every URL with `<lastmod>`. It names 24 projects; the listing names 23. Two are sitemap-only (`seiltausch-hoellental`, `schaltanlage-obermooweiler`) and one is listing-only (`stalldorf-main-tauber`). | The project set is the **union** of both, and the difference is logged. `lastmod` drives incremental fetching. |
| Project pages carry **no publication date and no coordinates**. The portrait subpage's slug varies (`projektportraet` / `projektportrait`). | `published_at` stays NULL for projects (never invented). The portrait page is found through each page's own chapter navigation. |
| The newsroom list is rendered **by JavaScript** from the public JSON `/de/api/press-releases` (564 entries, 2009-10-15 to 2026-10-15). One URL is listed twice with two different dates, and titles contain literal `&shy;` / `&nbsp;`. Each article page states its date as text ("15. Oktober 2026"). | **Justified deviation from pure HTML:** the JSON is the only machine-readable index of the press releases, so it is used **for discovery only**. The date is parsed from the article page and **verified** against the feed (a mismatch is flagged). The feed is deduplicated, keeping the latest date, and the conflict is logged. |
| The CMS **reuses URL slugs for unrelated articles**, e.g. `…/transnetbw-startet-um-und-neubau-des-umspannwerkes-wendlingen-1` is a release about underground-cable priority. Feed and page titles agree. | The URL is the stable identifier, and the **page title is authoritative**. A feed/page title disagreement raises `feed_title_mismatch`. |
| `/de/strommarkt/engpassmanagement/engpass` describes *cross-border market* congestion. | Out of scope. It is not a grid project signal. |

---

## What is staged

One Alembic revision (`alembic/versions/c41f7a2e9b10_create_iris_staging.py`) creates the
`iris_staging` schema. The models are in `app/database/models/signal_ingest.py`. The table is
source-agnostic, so other IRIS-SIG harvesters can write to it.

| Table | Purpose |
|---|---|
| `signal_ingest` | One row per source record. Natural key `(source_system, source_record_id)`, e.g. `transnetbw` / `project:umspannwerk-pulverdingen`, `press:<url-slug>`. |
| `signal_ingest_version` | One row per distinct content version of a record. |
| `ingest_run` | One row per run: mode, status, exit code, stats, gates, configuration (password masked), code version. |
| `ingest_issue` | Every error, warning and info of a run (exclusions, gaps, failures), with the record and URL. |
| `source_document` | The fetch ledger: every URL fetched, its sitemap `lastmod`, HTTP status, raw SHA-256 and outcome. |
| `ref_region` | Reference boundaries. Seeded with **Baden-Württemberg** from BKG VG250. |

Key `signal_ingest` columns:

- `signal_type` (`grid_capacity_constraint` | `transformer_modernization`);
- `project_stage` (`planning` | `approval` | `construction` | `in_operation` | `unknown`);
- `review_status` (`auto` | `needs_review`);
- `title`, `summary` (lead, ≤ 500 characters), `source_url`;
- `published_at` + `published_at_verified`, and `source_last_modified` (sitemap lastmod);
- `location_status` (`resolved` | `ambiguous` | `unresolved` | `invalid_coordinates`), plus
  `location_precision`, `location_method`, `location_text` and **`geom geometry(Point,25832)`**;
- `attributes` (jsonb, part of the content hash): category, measures, voltages, line IDs,
  endpoints, classification rule and evidence, stage evidence, related project;
- `derived` (jsonb, *not* hashed): first-reported date, latest press milestone, press count;
- `quality_flags`, `content_hash`, `raw_sha256`;
- first/last seen run and time, `missing_run_count`, `retired_at`.

**The database enforces** what the brief says must not be accepted silently:

- CHECK constraints: `resolved ⇔ geom IS NOT NULL`; geometry must be a valid point
  (NaN is rejected); precision and method go with a point; the summary is ≤ 500 characters.
- The `geometry(Point,25832)` type rejects any other SRID.
- Trigger `iris_staging.enforce_signal_geom()`: the point must lie **inside the record's
  region polygon**. It fails closed if the region is unknown. A direct SQL insert of a point
  in Strasbourg or Neu-Ulm, both inside BW's bounding box, is refused.

---

## Mapping assumptions

### Signal type and scope (`app/transnetbw/classify.py`)

- **The subject decides.** The subject is the title, plus the listing category and the
  page overline for projects.
  - A substation-type object (Umspannwerk, Schaltanlage, Netzknoten, Konverter,
    Phasenschieber/Transformator, Standort Neckarwestheim) → `transformer_modernization`.
  - Otherwise, a line, corridor or congestion cue (Netzverstärkung, Netzausbau, 380-kV /
    380-Kilovolt, SuedLink, ULTRANET, Netzbooster, Engpass, Überlastung, …) →
    `grid_capacity_constraint`.
  - The other type's cues in the body become `attributes.secondary_signal_types`.
- **In scope by decision:** HVDC corridors (SuedLink, ULTRANET), grid boosters (Netzbooster
  Kupferzell) and converter stations (as transformer modernization).
- **Excluded, each logged with a reason:**
  - like-for-like maintenance (Seiltausch Höllental);
  - grid-expansion policy (Freileitungsvorrang, Erdkabelvorrang, Bundesbedarfsplan,
    Szenariorahmen/NEP);
  - electricity-market items whose vocabulary only *looks* like grid capacity
    (Kapazitätsreserve, Kapazitätsmarkt);
  - back-office systems (billing for congestion management);
  - no signal at all.
- **Confidence:** a cue only in the body gives `low` → `needs_review`. A press release that
  names several projects, or has neither a project link nor a location, is also held for
  review.

### Lifecycle stage

- **Projects** take their stage from their own pages only:
  - listing section "Abgeschlossene Projekte" → `in_operation`;
  - a construction diary in the chapter navigation (Projekttagebuch, Bautagebuch) →
    `construction`;
  - otherwise the first construction, approval or planning cue in the status sections
    ("Aktueller Stand", "Zeitplan"), else in the body.
  - Body text never makes a project `in_operation`.
- **Press releases** carry the milestone they announce: the first cue in the title, else in
  the subheads, else in the lead.
- **Plans are not facts.** A cue in a future-tense sentence ("…ist für 2035 vorgesehen",
  "soll", "bis 2028") does not count.
- **Permission to build is approval.** "Bau des Konverters … ist genehmigt" and "Antrag auf
  vorzeitigen Baubeginn genehmigt" both count as approval.
- **"abgeschlossen" counts only after a construction noun.** A completed award procedure or
  research project commissions nothing.
- The sentence that decided the stage is stored as `attributes.stage_evidence`.

### Press → project links (`app/transnetbw/link.py`, `data/project_aliases.json`)

- Links use curated **project-name patterns only**, never a bare place name. One substation
  (Kupferzell) serves several projects.
- Two different projects named in one release → no link, and the release is held for review.
- 79 of the 97 press releases are linked.
- A project row carries `derived.first_reported_at` and `derived.latest_event` from its
  linked releases, outside the content hash. A new release therefore never "changes" a
  project, and the page's own stage stays separate from the latest news.

### Locations (`app/transnetbw/geocode.py`)

Places come from **structure, never from scanning free text** for known names. BW has
municipalities called Au, Berg, Lauf and Wald, and nine municipality names occur twice.

- **Project titles** are split on their separators after type words are stripped:
  "Weinheim – Karlsruhe", "Hochrhein | Herbertingen – Waldshut-Tiengen",
  "Stalldorf / Main-Tauber", "Birkenfeld – Punkt Ötisheim".
- **Press releases:**
  - first, explicit station mentions in the title, subheads or lead ("Umspannwerk Beuren",
    "Umspannwerks in Wendlingen", "Umspannwerke Gurtweil/Tiengen", "ULTRANET-Konverters in
    Philippsburg");
  - else the line ends ("zwischen Herbertingen und Hoheneck");
  - else the linked project's location (`via_project`).
- **Resolution order:**
  1. a substation (OSM; a TransnetBW-operated station breaks a tie; a converter context
     prefers the converter station);
  2. a settlement (OSM place);
  3. a municipality (BKG).
  - Steps 2 and 3 are marked `location_precision = municipality`.
  - A tie that cannot be broken is **ambiguous, not guessed**: 13 settlements are called
    Beuren, and two BW municipalities are called Altdorf.
- **Lines, regions and multi-station releases** → `ambiguous`, with NULL geometry. Their
  endpoints (name, EPSG:25832 x/y, `in_bw`) go into `attributes.endpoints`. Cross-border
  lines are kept and flagged `cross_border`.
- **Validation:** finite values, a plausible EPSG:25832 range, not (0,0), and **inside the
  BKG polygon of BW**. A failure gives `invalid_coordinates` plus an error issue.
- **BW filter:**
  - a record whose only places lie outside BW is **excluded** as `excluded_outside_bw`;
  - Umspannwerk Stalldorf is a TransnetBW project, but the station is in Bavaria;
  - press releases titled "… in Bayern / Hessen / Unterfranken" are excluded the same way.
- The dateline ("Stuttgart / Bayreuth.") names the issuing office and is stripped before any
  place is read. Footers and contact blocks are never read.

### Dates

- **Press:** the article's own date ("15. Oktober 2026") is compared with the feed date.
  - Equal → `published_at_verified = true`.
  - Mismatch → the article's date is kept and flagged.
  - Article without a date → the feed date is used, flagged `date_unverified`.
  - An impossible date (31 February) → None, never guessed.
- **Projects:** `published_at` is NULL (the pages state none), and `source_last_modified`
  carries the sitemap lastmod.

---

## Re-runs, increments and history

- **Identity:** `(source_system, source_record_id)` is unique in the database.
  `source_record_id` is `project:<slug>` or `press:<url-slug>`.
- **Change detection:** `content_hash` is a SHA-256 over the *signal* fields and attributes.
  It excludes fetch time, raw page bytes, sitemap lastmod and `derived`.
  - The same content again refreshes only the "last seen" audit fields.
  - Changed content updates the row, keeps `first_seen_*` and adds a version.
  - Content flipping back reuses the old version (`reverted`).
  - A page edit that leaves the signal alone (e.g. a new press contact) is audit only.
- **Incremental fetching:** a document is fetched again only when it has never been fetched,
  its last fetch failed, or its sitemap `lastmod` is newer than the ledger's (or with
  `--full`). Discovery (sitemap, listing, feed) runs every time.
- **Soft retirement:** a record the source no longer lists gets `missing_run_count += 1`,
  and `retired_at` after 2 consecutive misses. Only runs that passed every gate count, and
  only when discovery for that record kind was complete. A record seen again is un-retired.
  Nothing is ever deleted.
- **After upgrading the harvester:** incremental runs re-process only pages whose
  `lastmod` changed. To re-classify everything with new rules, run once with `--full`, or
  with `--replay` on the last raw capture to avoid contacting the site. Changed records are
  then updated with a new version, and `ingest_run.code_version` records which code
  produced them.
- **Concurrency:** a per-source PostgreSQL advisory lock. A second run exits with code 3.
- **Mode guard:** fixture (`--offline`) runs and live runs never share a database. A run
  refuses a database that already holds runs of the other mode.

---

## Errors, exit codes and quality gates

| Exit | Status | When |
|---|---|---|
| 0 | `succeeded` | Clean run. Data-quality observations (unresolved places, exclusions) do not degrade it. |
| 2 | `partial` | A document or record failed (fetch, parse, DB rejection), or the sitemap or press feed was unavailable or truncated. Everything else is loaded. |
| 1 | `failed` / `refused` | Listing unavailable or empty, a quality gate breached, an unexpected error, or fixture/live mode mixing. **Data is rolled back.** |
| 3 | `refused` | Another run of this source holds the lock. |

- **Saving:** one transaction per run, with a **savepoint per record**, so a record the
  database rejects rolls back alone.
- **Run audit:** `ingest_run` and `ingest_issue` are written on their own autocommit
  connection, so a failed run is always visible.
- **Network:** `HttpClient` retries timeouts, 5xx and 429 (honouring `Retry-After`) with
  backoff. After that, a failed fetch is one `fetch_failed` issue, not a crash.

**Quality gates** are evaluated before commit and are configurable. A breach rolls the run
back, so a broken parse can never retire records.

| Gate | Default | Catches |
|---|---|---|
| `listing_cards` | ≥ 15 | a redesign or error page that still parses |
| `fetch_failure_ratio` | ≤ 0.30 | an outage or a block |
| `resolved_rows` | ≥ 1 | a geocoding or gazetteer failure |
| `discovery_gap` | ≤ 5 | listing and sitemap drifting apart |

A press feed with fewer than 100 items (`TRANSNETBW_GATE_MIN_FEED_ITEMS`; 10 offline) is
treated as truncated. Its items are processed, but nothing is retired on its strength.

---

## How to run

### Setup

1. `uv sync`
2. `cp .env.example .env`, then set `STAGING_POSTGRES_PASSWORD` and
   `TRANSNETBW_DATABASE_URL`. The dashboard's `DATABASE_URL` stays as it is; the harvester
   prefers its own URL and falls back to `DATABASE_URL`.
3. `docker compose up -d postgis16` starts PostgreSQL 16.4 / PostGIS 3.4.3 on port 5434.
   The service sits behind a profile, so a plain `docker compose up` is unchanged.
4. Create the database, enable PostGIS, and migrate:

   ```bash
   docker exec iris-postgis16 psql -U postgres -d iris_signals -c "create extension if not exists postgis"
   DATABASE_URL="$TRANSNETBW_DATABASE_URL" uv run alembic upgrade head
   ```

### Commands

```bash
uv run python -m app.transnetbw.cli harvest              # live, incremental
uv run python -m app.transnetbw.cli harvest --full       # refetch every document
uv run python -m app.transnetbw.cli harvest --dry-run    # do everything, roll the data back
uv run python -m app.transnetbw.cli harvest --offline    # committed fixtures, no network
uv run python -m app.transnetbw.cli harvest --replay data/raw/transnetbw/run-<stamp>
                                                         # re-process a live run's raw capture
uv run python -m app.transnetbw.cli harvest -v           # a line per fetch, record and issue
uv run python -m app.transnetbw.cli harvest --log-json   # JSON lines for schedulers
uv run python -m app.transnetbw.cli report [--run-id ID] # regenerate artifacts/transnetbw
uv run python main.py transnetbw                         # live harvest via the pipeline runner
```

- `main.py transnetbw` is **not part of any phase**, so `main.py all` never contacts
  TransnetBW.
- Live runs keep every fetched document under `data/raw/transnetbw/run-<stamp>/`
  (gitignored), named by SHA-256, with an `index.jsonl`.

Validation after a run:

```bash
psql "$TRANSNETBW_DATABASE_URL" -f artifacts/transnetbw/validation_queries.sql
```

### Politeness

- One request at a time, at least **1.5 s apart**, or longer if `robots.txt` sets a
  `Crawl-delay`.
- Only `www.transnetbw.de` is contacted.
- User-Agent: `IRIS-ProjectRadar/0.1 (+https://github.com/Rahul-Bijarniya-1/iris-sample-assignment)`.
- A full first harvest is about 160 requests (≈ 6.5 min). A routine re-run is 4.

---

## Tests

```bash
uv run pytest tests/test_transnetbw_*.py                       # the slice: 252 tests (198 unit, 53 integration, 1 live)
uv run pytest                                                  # whole repository
uv run pytest -m "not integration" tests/test_transnetbw_*.py  # without a database
DATABASE_URL="$TRANSNETBW_DATABASE_URL" uv run pytest          # against PostgreSQL 16 / PostGIS 3.4
uv run pytest --run-live -m live                               # drift check: 5 requests to the live site
```

- Integration tests create and drop their own scratch databases. They never touch a project
  database.
- The full suite passes on PostgreSQL 16.4 / PostGIS 3.4.3 and on 17 / 3.5.
- The tests are written against **real captured markup** (`fixtures/transnetbw/`) and real
  reference data, and only the network is faked. They cover:
  - re-runs and duplicates: an unchanged re-run, a full re-run, a duplicated feed URL;
  - history: an edited page producing exactly one update with history; a flip-back;
  - failures: a gate breach rolling back, an empty listing, a failed fetch giving `partial`;
  - run control: lock contention, mode mixing;
  - geometry: points near the Swiss border, Strasbourg / Neu-Ulm rejection by the trigger;
  - privacy: no press-contact data reaches the table;
  - the validation queries, every one of them executed.

---

## Outputs

All in `artifacts/transnetbw/`, from the live harvest of 2026-10-28:

| File | What |
|---|---|
| `sample_signal_ingest.geojson` | All 120 records, **WGS84 per RFC 7946**, which GitHub renders as a map. Records without a point have `geometry: null`. |
| `sample_signal_ingest.csv` | The same records with native **EPSG:25832** `x_25832`, `y_25832`, `wkt_25832`. |
| `quality_report.md` / `.json` | Source verification; counts by kind, type and stage; gates; **every unresolved or ambiguous location with its reason**; date verification; exclusions; listing/sitemap differences; review queue; issues by code. |
| `validation_queries.sql` | Invariants ("expect: 0 rows") and review queries. All invariants return 0 rows on the live data. |
| `run_log.txt` | The crawl, the replay and the idempotent re-run, with the validation results. |

---

## Known limitations

- **Lines and areas have no point.** That is by design: 22 records are `ambiguous`, with
  their endpoints in attributes.
- **46 records are unresolved.** Most are national SuedLink and ULTRANET milestones (the
  project pages name no place) and system-wide releases (studies, congestion management).
  They are listed with reasons in the quality report.
- **Stage derivation is heuristic.** The deciding sentence is stored, and some pages state no
  stage (SuedLink → `unknown`). Fixed rules from the live run are covered by regression tests.
- **Press candidates are chosen by title keywords** before any fetch. A relevant release
  whose title has no grid or substation term is not fetched.
- **The gazetteer is a snapshot.**
  - OSM substations (165 at transmission level), OSM settlements for the names in
    `PLACE_NAMES`, and the 1,103 BKG municipalities.
  - A new place name needs a gazetteer rebuild
    (`uv run python -m scripts.build_transnetbw_gazetteer`).
  - The optional **Nominatim fallback was not built**; it was one of the two items agreed as
    cuttable.
- **The BW boundary is generalized to 25 m.** The closest real stations (Schwörstadt, 386 m
  from the Rhine border) are tested.
- **The fixtures freeze the markup of 2026-10-27** and cover 8 of 25 projects and 9 articles.
  Drift is caught by the opt-in live test and by the gates on real runs.
- **URL identity:** if TransnetBW moves a page, it appears as a new record and the old one
  retires after two runs.
- **Text is kept short on purpose** (summary ≤ 500 characters, snippets ≤ 200), out of
  respect for TransnetBW's copyright.
- **CI** (`.github/workflows/ci.yml`) runs the whole suite on every push and pull request
  against a `postgis/postgis:16-3.4` service container. Live-site tests never run there. The
  first run, on 2026-10-28, passed: 278 passed, 1 skipped, on PostgreSQL 16.4 / PostGIS 3.4.3.

---

## Licences and attribution

- **TransnetBW content** (fixtures, summaries): © TransnetBW GmbH. Only short excerpts are
  stored. Fixtures are trimmed to the parts the parsers read and carry an attribution header.
- **Administrative boundaries and municipalities:** © GeoBasis-DE / BKG (2026), VG250,
  [dl-de/by-2-0](https://www.govdata.de/dl-de/by-2-0)
  (`app/transnetbw/data/de_bw_boundary_25832.wkt`, `bw_municipalities.json`).
- **Substations and settlements:** © OpenStreetMap contributors,
  [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)
  (`app/transnetbw/data/osm_gazetteer.json`).

---

## Configuration

Every setting is a `TRANSNETBW_*` environment variable or `.env` entry. No credentials are in
the source, and the stored run configuration masks the database password.

| Setting | Default |
|---|---|
| `TRANSNETBW_DATABASE_URL` | falls back to `DATABASE_URL` |
| `TRANSNETBW_REQUEST_DELAY_S` / `TIMEOUT_S` / `MAX_RETRIES` | 1.5 / 30 / 3 |
| `TRANSNETBW_USER_AGENT` | `IRIS-ProjectRadar/0.1 (+https://github.com/Rahul-Bijarniya-1/iris-sample-assignment)` |
| `TRANSNETBW_SINCE` | `2020-01-01`, the earliest press release to fetch |
| `TRANSNETBW_RETIRE_AFTER_MISSES` | 2 |
| `TRANSNETBW_GATE_MIN_LISTING_CARDS` / `GATE_MAX_FETCH_FAILURE_RATIO` / `GATE_MIN_RESOLVED` / `GATE_MAX_DISCOVERY_GAP` / `GATE_MIN_FEED_ITEMS` | 15 / 0.30 / 1 / 5 / 100 |
| `TRANSNETBW_BASE_URL`, `LISTING_PATH`, `SITEMAP_PATH`, `PRESS_FEED_PATH` | the live site |
| `TRANSNETBW_RAW_DIR` / `ARTIFACTS_DIR` / `FIXTURES_DIR` | `data/raw/transnetbw` / `artifacts/transnetbw` / `fixtures/transnetbw` |

---

## Files

```
app/transnetbw/        config · fetch · discovery · project_parser · press_parser · htmltext · normalize
                       classify · link · geocode · store · harvester · report · cli · errors
app/transnetbw/data/   BW boundary + provenance · BKG municipalities · OSM gazetteer · curated aliases
app/database/models/signal_ingest.py          ORM models (iris_staging)
alembic/versions/c41f7a2e9b10_create_iris_staging.py
app/runners/transnetbw_runner.py              main.py transnetbw
scripts/capture_transnetbw_fixtures.py        fixture capture (through the harvester's own fetcher)
scripts/build_bw_boundary.py                  BKG VG250 → boundary + municipalities
scripts/build_transnetbw_gazetteer.py         Overpass → substations + settlements
fixtures/transnetbw/   trimmed captures of 2026-10-27
artifacts/transnetbw/  sample outputs, quality report, validation queries, run log
tests/test_transnetbw_*.py
```
