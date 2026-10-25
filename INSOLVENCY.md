# IRIS-48H-13 — Incremental Insolvency Notices and Conservative Entity Matching

A fixture-only vertical slice: ingest insolvency notices, deduplicate across repeated
batches, and match them to a corporate registry with explainable confidence.

Runs with **no database and no network access**.

---

## Run it

```bash
uv sync                                  # once
uv run python main.py insolvency         # ingest, resolve, write audit
```

Re-run it as often as you like — ingestion is idempotent on content.

Output lands in `artifacts/insolvency/`:

| File | What |
|---|---|
| `audit.csv` | one row per notice, for sorting and filtering |
| `audit.json` | the full record, including every candidate considered |
| `notice_store.json` | the incremental store, with version history per notice |

### Tests

```bash
uv run pytest tests/test_insolvency_notice_parsing.py \
              tests/test_insolvency_incremental.py \
              tests/test_insolvency_resolver.py \
              tests/test_insolvency_audit.py \
              tests/test_insolvency_wiring.py
```

```
32 passed in 0.32s
```

Whole suite, including the pre-existing pipeline tests: `uv run pytest` → `59 passed`.

### Observed output

First run, then the same command twice more:

```
batch_001.json   read   5  new   5  changed   0  replayed   0
batch_002.json   read   4  new   2  changed   1  replayed   1
Notices held : 7      Superseded : 1

batch_001.json   read   5  new   0  changed   0  replayed   5
batch_002.json   read   4  new   0  changed   0  replayed   4
Notices held : 7      Superseded : 1
```

```
Registry companies : 5
Auto-matched       : 5
Needs review       : 2
Unmatched          : 2
Active notices     : 5
```

---

## Acceptance tests

**1. Repeated batches create zero duplicate notices; a changed notice keeps history.**

Dedup key is the publisher's `notice_id`. Change is detected by a SHA-256 fingerprint of the
notice's substance, deliberately **excluding retrieval time** — otherwise every replay would
read as an update.

The fingerprint is compared against **every version ever held**, not just the latest. This
matters more than it first appears: `NOT-2026-000105` occurs in both batches with different
status, so comparing only against the latest version made re-running the sequence re-append
the older content as a "change". The record oscillated and grew by two versions per run. The
guarding test is `test_replaying_the_whole_batch_sequence_adds_no_versions`.

Versions are ordered by publication date, so `current` is the most recently published notice
rather than whichever batch was ingested last (`test_the_current_version_is_the_most_recently_published`).

**2. Similar company names at different addresses do not auto-match.** See below.

**3. No source access bypass, and no unsupported assumption that the property is for sale.**
Everything reads from `fixtures/`; there is no scraper, no credential, no network call. No
output field describes a debtor's property. A notice is a court record about a *legal entity*
— it says nothing about whether a site is available, and `test_no_result_claims_anything_about_the_property`
asserts the rationale text never implies otherwise.

---

## Matching: why it refuses more than it accepts

The brief's rationale is that legal insolvency must not be inferred from name similarity
alone. A false positive publishes, in an auditable artefact, that a solvent company is
insolvent. That is far more damaging than leaving a true match for a human to confirm, so
every tie-break favours *needs review*.

Decision order:

1. **Stable identifier present and known** → authoritative match, confidence 1.00.
2. **Identifier present but unknown to the registry** → not matched, flagged. Falling back to
   name matching here would quietly contradict the identifier the notice itself published.
   This is a provenance problem, not a naming one.
3. **No identifier** → name candidates above a 0.92 similarity floor, then address decides:
   - address **conflicts** → disqualified outright, no match
   - address **agrees** on postal code → 0.95, auto-matched
   - address agrees on **city only** → 0.75, held for review
   - address **unknown** → 0.50, held for review
   - **several** surviving candidates → 0.40, held for review

Auto-match threshold is 0.90, so **name similarity alone can never auto-match** — the ceiling
without address corroboration is 0.50. `test_a_name_alone_never_auto_matches` asserts this
across every fixture.

### Negative controls

The fixtures are built around the cases that should *fail*:

| Notice | Control | Outcome |
|---|---|---|
| `NOT-2026-000101` | positive — registry id present | auto-matched, 1.00 |
| `NOT-2026-000102` | positive — name + postal code agree | auto-matched, 0.95 |
| `NOT-2026-000103` | **ambiguous** — name matches two companies, no address given | review, 0.40 |
| `NOT-2026-000104` | **false positive** — exact name, different city | **not matched**, 0.00 |
| `NOT-2026-000106` | withdrawn notice | resolves, but reported inactive |

The registry contains two companies genuinely named "Rheinmetall Logistik GmbH" at different
addresses. Collapsing them would hide the ambiguity the resolver exists to surface, so the
registry keeps both and name lookup returns both.

Status handling whitelists rather than blacklists: only `eroeffnet` reads as a live
insolvency. Lifted, withdrawn, dismissed and any **unrecognised** value are inactive, so an
unseen status value from a future feed fails safe.

---

## Trade-offs

**A JSON store, not Postgres.** The brief requires the slice to run against fixtures without
project production access. A file-backed store keeps it genuinely standalone and makes the
version history directly inspectable. It is not what I would ship for a real feed — see
integration below.

**Exact-ish name matching, not fuzzy.** `SequenceMatcher` with a 0.92 floor catches casing and
whitespace noise but not abbreviations ("Gesellschaft mit beschränkter Haftung" vs "GmbH") or
transliterations. Loosening it would raise recall and, in this domain, cost precision where
precision is the point. A real deployment should normalise legal-form suffixes explicitly
rather than by lowering the threshold.

**Address agreement is postal-code-first, city as a weaker fallback.** No street-level
comparison: street strings vary too much to compare safely without a normalisation library,
and a wrong street match is exactly the failure being guarded against.

**Replays are preferred over revert detection.** Content a notice has already had is treated
as a replay, even if it is not the latest version. A genuine revert would therefore be missed.
That is the deliberate trade: re-reading old batches is routine, genuine reverts are not, and
an unbounded oscillating history is worse than a missed revert.

---

## Source and licence limitations

The fixtures are **synthetic**. Company names, courts, case numbers and addresses are invented;
any resemblance to real entities is unintended. They carry **no coordinates at all**, by
design — the delivery rules prohibit fabricated real-world coordinates, and the safest way to
comply is to have none.

German insolvency notices are published at `insolvenzbekanntmachungen.de`. I did **not** scrape
it: the brief's scope limit rules out a live government scraper, and its terms restrict
automated bulk retrieval. Any production integration needs that access question settled
first — licence terms, permitted retrieval rate, and retention — before a line of scraper
code is written. The notice parser is deliberately isolated from acquisition so the source can
be swapped without touching matching logic.

Corporate registry data (Handelsregister) is similarly licence-encumbered. The resolver takes a
`CompanyRegistry` object, so a licensed source drops in behind the same interface.

---

## Safe integration into IRIS

The slice is wired as `main.py insolvency` but **deliberately not part of any phase**
(`test_insolvency_is_not_run_by_any_phase` enforces this). `main.py all` must not write audit
artefacts as a side effect, and a self-contained deliverable should not inherit the geospatial
pipeline's failure modes.

To integrate properly:

1. **Persist to `iris_core`.** Two tables — notices with version history, and entity-notice
   matches — replacing the JSON store. The store interface is narrow (`ingest`, `get`,
   `records`, `count`) precisely so this swap is contained.
2. **Match against `iris_core.facilities`, not just a registry.** This is where the existing
   `app/news/entity_matcher.py` is a cautionary example: it matches company names by
   substring with no address corroboration — exactly the inference this task forbids. It
   should adopt this resolver's address gating before anything downstream trusts it.
3. **Surface only `auto_matched` rows automatically.** `human_review` rows need a queue and a
   person; they are not a lower grade of match, they are undecided.
4. **Never let an insolvency match imply site availability.** The join from a legal entity to a
   physical site is an assumption, not a fact, and must stay labelled as one.

---

## What is not done

- No live notice source; fixtures only, as the scope limit allows.
- No database persistence (see integration, item 1).
- No street-level address comparison.
- No legal-form normalisation, so "AG" vs "Aktiengesellschaft" would not match.
- Registry has five companies; it exercises the decision paths but is not a scale test.
