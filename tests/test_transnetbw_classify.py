"""
Classification turns pages into the two signal types the brief asks for —
grid capacity constraints and transformer modernization — and leaves out,
with a stated reason, what only looks related: conductor maintenance,
grid-expansion policy and electricity-market items ("Kapazitätsreserve"
is about market capacity, not grid capacity).

Stage derivation must not read a plan as a fact: "Die Inbetriebnahme ist
für 2035 vorgesehen" is not "in operation".
"""

from pathlib import Path

import pytest

from app.transnetbw.classify import (
    classify,
    press_stage,
    project_stage,
    title_is_candidate,
)
from app.transnetbw.project_parser import parse_project_page


PAGES = Path("fixtures/transnetbw/pages")

BASE = "https://www.transnetbw.de"

PROJECTS = f"{BASE}/de/netzentwicklung/projekte"


def project(slug: str, portrait: str | None = "projektportraet"):
    overview = parse_project_page(
        (PAGES / f"project-{slug}.html").read_text(encoding="utf-8"),
        f"{PROJECTS}/{slug}",
        BASE,
    )

    detail = None

    if portrait:
        detail = parse_project_page(
            (PAGES / f"project-{slug}--{portrait}.html").read_text(encoding="utf-8"),
            f"{PROJECTS}/{slug}/{portrait}",
            BASE,
        )

    return overview, detail


# =========================================================
# SIGNAL TYPE
# =========================================================


@pytest.mark.parametrize(
    "subject, expected",
    [
        ("Umspannwerk Pulverdingen Erweiterung", "transformer_modernization"),
        ("Netzknoten Kühmoos Umbau", "transformer_modernization"),
        ("Projekte am Standort Neckarwestheim Umbau", "transformer_modernization"),
        ("Feierliche Inbetriebnahme des ULTRANET-Konverters in Philippsburg", "transformer_modernization"),
        ("Weinheim – Karlsruhe 380-KV-Netzverstärkung", "grid_capacity_constraint"),
        ("SuedLink Netzausbau Die Windstromleitung", "grid_capacity_constraint"),
        ("Netzbooster Kupferzell Netzausbau Intelligenter Batteriespeicher", "grid_capacity_constraint"),
        ("Kleinstflexibilitäten als Beitrag für das Netzengpassmanagement", "grid_capacity_constraint"),
    ],
)
def test_the_subject_decides_the_primary_signal_type(subject, expected):
    result = classify(subject)

    assert result.included
    assert result.signal_type == expected
    assert result.confidence == "high"


def test_a_substation_named_in_the_subject_outranks_line_cues():
    """
    "Spatenstich am Umspannwerk Beuren … Projekt Hochrhein": the works are at
    a substation, even though they serve a line reinforcement.
    """

    result = classify(
        "Spatenstich am Umspannwerk Beuren: TransnetBW startet Bauarbeiten für das Projekt Hochrhein",
        "Die 380-kV-Netzverstärkung Hochrhein erhöht die Übertragungskapazität.",
    )

    assert result.signal_type == "transformer_modernization"
    assert result.secondary_types == ("grid_capacity_constraint",)


def test_secondary_types_record_the_other_signal_found_in_the_body():
    overview, portrait = project("netzbooster-kupferzell")

    result = classify(
        "Netzbooster Kupferzell Netzausbau Intelligenter Batteriespeicher",
        overview.text() + " " + portrait.text(),
    )

    assert result.signal_type == "grid_capacity_constraint"
    assert result.secondary_types == ("transformer_modernization",)


@pytest.mark.parametrize(
    "subject, reason",
    [
        ("Seiltausch Höllental (LA5120)", "out_of_scope_maintenance"),
        ("Freileitungsvorrang stärkt Netzausbau – Einschränkungen schaffen Unsicherheit", "out_of_scope_policy"),
        ("Szenariorahmen für den Netzentwicklungsplan", "out_of_scope_policy"),
        ("Übertragungsnetzbetreiber veröffentlichen Ergebnisse der dritten Kapazitätsreserve-Ausschreibung", "out_of_scope_market"),
        ("Versorgungssicherheit mit einem zentralen Kapazitätsmarkt mit lokaler Komponente", "out_of_scope_market"),
        ("TransnetBW veröffentlicht Nachhaltigkeitsbericht 2025", "out_of_scope_no_signal"),
    ],
)
def test_lookalikes_are_excluded_with_a_reason(subject, reason):
    result = classify(subject)

    assert not result.included
    assert result.signal_type is None
    assert result.exclusion == reason


def test_a_cue_found_only_in_the_body_is_included_with_low_confidence():
    result = classify(
        "TransnetBW informiert in Merdingen",
        "Vorgestellt wurden die Pläne für das Umspannwerk Eichstetten.",
    )

    assert result.included
    assert result.signal_type == "transformer_modernization"
    assert result.confidence == "low"
    assert "Umspannwerk" in result.evidence


@pytest.mark.parametrize(
    "title, candidate",
    [
        ("Feierlicher Baubeginn des Netzboosters", True),
        ("Spatenstich am Umspannwerk Beuren: TransnetBW startet Bauarbeiten", True),
        ("Baustart für SuedLink in Bayern – Netzausbau schreitet voran", True),
        ("Versorgungssicherheit mit einem zentralen Kapazitätsmarkt mit lokaler Komponente", False),
        ("TransnetBW veröffentlicht Nachhaltigkeitsbericht 2025", False),
    ],
)
def test_the_press_title_prefilter_decides_what_is_worth_fetching(title, candidate):
    assert title_is_candidate(title) is candidate


# =========================================================
# STAGE
# =========================================================


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Feierlicher Baubeginn des Netzboosters", "construction"),
        ("TransnetBW erhält Planfeststellungsbeschluss für den Netzbooster in Kupferzell", "approval"),
        ("Netzverstärkung Badische Rheinschiene (NBR): Teilbeschluss ebnet Weg für weitere Bauaktivitäten", "approval"),
        ("TransnetBW und TenneT Germany feiern symbolische Inbetriebnahme der Netzverstärkung", "in_operation"),
        ("Modernisierung des Umspannwerkes Schwörstadt abgeschlossen", "in_operation"),
        ("Bundesnetzagentur bestätigt Netzbooster im Raum Kupferzell", "planning"),
        ("Kleinstflexibilitäten als Beitrag für das Netzengpassmanagement", "unknown"),
    ],
)
def test_a_press_release_carries_the_milestone_its_title_announces(title, expected):
    stage, _ = press_stage(title, [], None)

    assert stage == expected


def test_a_planned_milestone_is_not_a_reached_one():
    stage, _ = press_stage("Inbetriebnahme des Netzboosters ist für 2026 geplant", [], None)

    assert stage != "in_operation"


def test_a_construction_diary_marks_a_project_as_under_construction():
    overview, portrait = project("umspannwerk-pulverdingen")

    stage, evidence = project_stage(overview, portrait, completed=False)

    # The portrait also says "Die Inbetriebnahme des Gesamtprojekts ist für
    # das Jahr 2035 vorgesehen" — a plan, which must not make it in_operation.
    assert stage == "construction"
    assert "Projekttagebuch" in evidence


def test_an_open_approval_procedure_marks_a_project_in_approval():
    overview, portrait = project("netzverstaerkung-weinheim-karlsruhe")

    stage, evidence = project_stage(overview, portrait, completed=False)

    assert stage == "approval"
    assert evidence


def test_the_completed_section_of_the_listing_marks_a_project_in_operation():
    overview, portrait = project("umspannwerk-schwoerstadt", "projektportrait")

    stage, evidence = project_stage(overview, portrait, completed=True)

    assert stage == "in_operation"
    assert "Abgeschlossene Projekte" in evidence


# =========================================================
# REGRESSIONS FROM THE FIRST LIVE HARVEST (2026-10-28)
# =========================================================


@pytest.mark.parametrize(
    "title, subheads, expected",
    [
        # Permission to build is approval, even when construction is named.
        ("SuedLink: Bau des Konverters in Leingarten ist genehmigt", [], "approval"),
        ("TransnetBW startet vorzeitig mit dem Bau des Netzboosters Kupferzell", [], "construction"),
        ("TransnetBW startet Um- und Neubau des Umspannwerkes Wendlingen", [], "construction"),
        ("TransnetBW beginnt mit der Erweiterung des Umspannwerks Pulverdingen", [], "construction"),
        ("Einweihung der gasisolierten Schaltanlage am Standort Philippsburg", [], "in_operation"),
    ],
)
def test_live_press_titles_carry_the_right_milestone(title, subheads, expected):
    stage, _ = press_stage(title, subheads, None)

    assert stage == expected


@pytest.mark.parametrize(
    "title, subheads",
    [
        (
            "Nächster Schritt der Realisierung: Regionale SuedLink-Planungsbüros nehmen Arbeit auf",
            ["Vergabe der Regionalen Planungsbüros (RPB) abgeschlossen", "Erste Planungsbüros im Norden am Start"],
        ),
        (
            "HydrogREenBoost: Studie bestätigt Wirtschaftlichkeit und großes Potenzial für hybride Netzbooster",
            ["Das nun abgeschlossene Forschungsprojekt zeigt, dass die Technologie überzeugt."],
        ),
    ],
)
def test_a_completed_procedure_or_study_is_not_a_commissioned_asset(title, subheads):
    """
    "abgeschlossen" alone (an award procedure, a research project) says
    nothing about an asset going into operation.
    """

    stage, _ = press_stage(title, subheads, None)

    assert stage != "in_operation"


def test_back_office_systems_are_not_grid_capacity_signals():
    result = classify("TransnetBW nimmt neue Lösung für die Abrechnungsprüfung im Engpass-Management in Betrieb")

    assert not result.included
    assert result.exclusion == "out_of_scope_back_office"


def test_a_spelled_out_voltage_is_a_capacity_cue():
    result = classify("Transnet BW startet mit dem Neubau der 380-Kilovolt-Leitung zwischen Birkenfeld und Ötisheim")

    assert result.signal_type == "grid_capacity_constraint"
    assert result.confidence == "high"


def test_the_underground_cable_priority_debate_is_policy():
    result = classify("Expertenkommission rät zur Überprüfung des Erdkabelvorrangs")

    assert result.exclusion == "out_of_scope_policy"
