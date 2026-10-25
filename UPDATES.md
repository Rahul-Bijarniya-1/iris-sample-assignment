# Updates — IRIS-48H-13

Submission summary for **Incremental Insolvency Notices and Conservative Entity Matching**.

| | |
|---|---|
| Branch | `feat/insolvency-notices` |
| Tests | 32 for this task, 59 for the whole suite |
| Dependencies added | none |

Design rationale, trade-offs, licence limitations and the integration plan are in
**[INSOLVENCY.md](INSOLVENCY.md)**. This file is the short version: what changed, and how to
check it.

---

## Run it

```bash
uv sync
uv run python main.py insolvency
```

No database, no network, no credentials. Reads `fixtures/`, writes `artifacts/insolvency/`.
Safe to re-run — ingestion is idempotent on content.

```bash
uv run pytest tests/test_insolvency_notice_parsing.py \
              tests/test_insolvency_incremental.py \
              tests/test_insolvency_resolver.py \
              tests/test_insolvency_audit.py \
              tests/test_insolvency_wiring.py
# 32 passed in 0.32s

uv run pytest
# 59 passed
```

Output of three consecutive runs — the first ingests, the rest are pure replay:

```
batch_001.json   read 5  new 5  changed 0  replayed 0
batch_002.json   read 4  new 2  changed 1  replayed 1

batch_001.json   read 5  new 0  changed 0  replayed 5
batch_002.json   read 4  new 0  changed 0  replayed 4

batch_001.json   read 5  new 0  changed 0  replayed 5
batch_002.json   read 4  new 0  changed 0  replayed 4

Notices held : 7      Superseded : 1
Auto-matched : 5      Needs review : 2      Unmatched : 2      Active : 5
```

---

## What was added

| Path | Purpose |
|---|---|
| `app/insolvency/notice.py` | normalised `Notice`, status mapping, content fingerprint |
| `app/insolvency/notice_parser.py` | German portal field names → normalised records |
| `app/insolvency/notice_store.py` | replay-safe incremental store with version history |
| `app/insolvency/registry.py` | corporate registry lookup |
| `app/insolvency/resolver.py` | conservative entity matching |
| `app/insolvency/audit.py` | audit CSV + JSON |
| `app/runners/insolvency_runner.py` | end-to-end run |
| `fixtures/insolvency/` | synthetic notices and registry, with negative controls |
| `artifacts/insolvency/` | generated audit output, committed as evidence |
| `tests/test_insolvency_*.py` | 32 tests |

Wired as `main.py insolvency` and **deliberately excluded from every phase**, enforced by
`test_insolvency_is_not_run_by_any_phase`. `main.py all` must not write audit artefacts as a
side effect, and a fixture-only slice should not inherit the geospatial pipeline's failure
modes.

---

## Acceptance tests

**1 — Repeated batches create zero duplicate notices; a changed notice keeps history.**

Notices are keyed on the publisher's `notice_id`. Change is detected by a SHA-256 fingerprint
of the notice's substance, excluding retrieval time, and compared against **every version ever
held** rather than only the latest.

That last detail is load-bearing. `NOT-2026-000105` appears in both batches with different
status; comparing only against the latest version made a re-run re-append the older content as
a change, so the record oscillated and grew by two versions on every pass. I found it by
running the command a second time, not from the unit tests — those replayed a single batch,
where the fault cannot appear. Guarded by
`test_replaying_the_whole_batch_sequence_adds_no_versions`.

Versions are ordered by publication date, so batch order cannot decide which version is
current (`test_the_current_version_is_the_most_recently_published`).

**2 — Similar company names at different addresses do not auto-match.**

A stable registry identifier is authoritative. Without one, name candidates above a 0.92
similarity floor are gated on address evidence:

| Evidence | Confidence | Outcome |
|---|---|---|
| registry identifier | 1.00 | auto-matched |
| name + postal code | 0.95 | auto-matched |
| name + city only | 0.75 | review |
| name, address unknown | 0.50 | review |
| name, several candidates | 0.40 | review |
| name, address conflicts | 0.00 | **not matched** |

The auto-match threshold is 0.90, so name similarity alone can never auto-match — its ceiling
without address corroboration is 0.50. An identifier the registry does not know is flagged
rather than quietly name-matched, because that is a provenance problem rather than a naming
one.

**3 — No source access bypass; nothing assumes the property is for sale.**

No scraper, no network call, no credential. No output field describes the debtor's property,
and `test_no_result_claims_anything_about_the_property` asserts the rationale text never
implies availability.

### Negative controls

The fixtures are built around the cases that should fail:

| Notice | Control | Result |
|---|---|---|
| `NOT-2026-000101` | positive — registry id | auto-matched, 1.00 |
| `NOT-2026-000102` | positive — name + postal code | auto-matched, 0.95 |
| `NOT-2026-000103` | **ambiguous** — name matches two companies, no address | review, 0.40 |
| `NOT-2026-000104` | **false positive** — exact name, different city | **not matched**, 0.00 |
| `NOT-2026-000106` | withdrawn notice | resolves, reported inactive |

The registry holds two genuinely distinct companies both named "Rheinmetall Logistik GmbH" at
different addresses. Collapsing them would hide the ambiguity the resolver exists to surface.

Status handling whitelists rather than blacklists: only `eroeffnet` reads as a live
insolvency, so an unrecognised value from a future feed fails safe.

---

## Limitations

- **Fixtures are synthetic** and carry no coordinates at all, since the delivery rules prohibit
  fabricated real-world coordinates.
- **No live source.** `insolvenzbekanntmachungen.de` was not scraped: the scope limit rules out
  a live government scraper and its terms restrict automated bulk retrieval. That access
  question needs settling before any scraper is written.
- **JSON store, not Postgres**, to keep the slice runnable without project access.
- **No street-level address comparison** and **no legal-form normalisation**, so "AG" would not
  match "Aktiengesellschaft".
- Registry holds five companies — enough to exercise every decision path, not a scale test.

---

## One finding worth raising

`app/news/entity_matcher.py` matches company names by substring with no address
corroboration — the exact inference this task is designed to prevent. It fired once across 40
articles and 223 facilities. It should adopt the same address gating before anything
downstream relies on it.

---

## Context, not part of this submission

The `main` branch carries earlier work from getting the project running: a migration chain that
failed on any fresh database, two loaders that were unreachable from `main.py`, a shapefile
read in the wrong encoding, and news matches that could never load on a first run. Each is
fixed with a test. Listed only so the branch diff is not surprising.
