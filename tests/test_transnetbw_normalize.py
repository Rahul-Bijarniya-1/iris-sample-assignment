"""
Normalization decides two things the brief cares about directly: whether
source text arrives clean (the press feed ships literal "&shy;" and
"&nbsp;" entities and some URLs carry decomposed umlauts), and whether a
re-run counts as an update.

The content hash must change exactly when the signal changes — never
because of when it was fetched, which page bytes changed around it, or
what was derived from other records.
"""

from dataclasses import replace
from datetime import date, datetime, timezone

from app.transnetbw.normalize import SignalRecord, cap, clean_text


def test_entities_soft_hyphens_and_nbsp_are_removed():
    raw = "Übertragungs&shy;netz&shy;betreiber laden zum „Tag&nbsp;der&nbsp;offenen&nbsp;Tür”"

    assert clean_text(raw) == "Übertragungsnetzbetreiber laden zum „Tag der offenen Tür”"


def test_literal_soft_hyphen_characters_are_removed():
    assert clean_text("Planfest­stellungs­beschluss") == "Planfeststellungsbeschluss"


def test_decomposed_umlauts_are_composed():
    decomposed = "Netzverstärkung"

    cleaned = clean_text(decomposed)

    assert cleaned == "Netzverstärkung"
    assert len(cleaned) == len("Netzverstärkung")


def test_whitespace_runs_collapse_and_blank_becomes_none():
    assert clean_text("  Umspannwerk \n\t Pulverdingen  ") == "Umspannwerk Pulverdingen"
    assert clean_text("   ") is None
    assert clean_text(None) is None


def test_cap_keeps_short_text_unchanged():
    assert cap("Kurzer Text.", 500) == "Kurzer Text."


def test_cap_cuts_at_a_word_boundary_within_the_limit():
    text = "Die Netzverstärkung erhöht die Transportkapazität deutlich"

    capped = cap(text, 30)

    assert capped == "Die Netzverstärkung erhöht…"
    assert len(capped) <= 30


# =========================================================
# CONTENT HASH
# =========================================================


def record(**changes) -> SignalRecord:
    base = SignalRecord(
        source_system="transnetbw",
        source_record_id="project:umspannwerk-pulverdingen",
        record_kind="project",
        signal_type="transformer_modernization",
        project_stage="construction",
        review_status="auto",
        title="Umspannwerk Pulverdingen",
        summary="Seit Langem trägt das Umspannwerk in Pulverdingen zur sicheren Stromversorgung bei.",
        source_url="https://www.transnetbw.de/de/netzentwicklung/projekte/umspannwerk-pulverdingen",
        published_at=None,
        published_at_verified=False,
        source_last_modified=datetime(2024, 1, 30, 15, 11, 17, tzinfo=timezone.utc),
        location_text="Pulverdingen",
        location_status="resolved",
        location_precision="substation",
        location_method="gazetteer",
        x=502_101.4,
        y=5_417_380.2,
        attributes={"category_label": "Erweiterung", "voltages_kv": [110, 380]},
        quality_flags=[],
        raw_sha256="a" * 64,
    )

    return replace(base, **changes)


def test_the_hash_is_stable_for_identical_content():
    assert record().content_hash() == record().content_hash()


def test_page_edits_that_do_not_change_the_signal_do_not_change_the_hash():
    """
    A new raw page hash or a newer sitemap lastmod (e.g. a rotated contact
    person) is audit information, not a new version of the signal.
    """

    edited_page = record(
        raw_sha256="b" * 64,
        source_last_modified=datetime(2026, 9, 10, 15, 53, 41, tzinfo=timezone.utc),
    )

    assert edited_page.content_hash() == record().content_hash()


def test_a_changed_stage_changes_the_hash():
    assert record(project_stage="in_operation").content_hash() != record().content_hash()


def test_a_changed_attribute_changes_the_hash():
    changed = record(attributes={"category_label": "Erweiterung", "voltages_kv": [110, 220, 380]})

    assert changed.content_hash() != record().content_hash()


def test_attribute_key_order_does_not_change_the_hash():
    reordered = record(attributes={"voltages_kv": [110, 380], "category_label": "Erweiterung"})

    assert reordered.content_hash() == record().content_hash()


def test_sub_decimetre_coordinate_noise_does_not_change_the_hash():
    """
    Floating-point noise from a reprojection must not read as a move; a
    genuine relocation of a metre or more must.
    """

    assert record(x=502_101.43).content_hash() == record().content_hash()
    assert record(x=502_103.4).content_hash() != record().content_hash()


def test_flag_order_does_not_change_the_hash():
    a = record(quality_flags=["cross_border", "date_mismatch"])
    b = record(quality_flags=["date_mismatch", "cross_border"])

    assert a.content_hash() == b.content_hash()


def test_a_publication_date_change_changes_the_hash():
    dated = record(record_kind="press_release", published_at=date(2026, 10, 15))
    redated = record(record_kind="press_release", published_at=date(2026, 10, 16))

    assert dated.content_hash() != redated.content_hash()
