"""
Signal classification and lifecycle stage.

Signal type. The record's subject (title, category label, overline) decides:
a substation-type object → transformer_modernization; otherwise a line,
corridor or congestion cue → grid_capacity_constraint. A cue found only in
the body still includes the record, with low confidence (→ needs_review).
The other type's cues in the body become secondary types.

Exclusions are checked first, on the subject, each with a reason:
like-for-like maintenance, grid-expansion policy, and electricity-market
items whose vocabulary ("Kapazität…") only resembles grid capacity.

Stage. Plans are not facts: a cue in a sentence that speaks of the future
("…ist für 2035 vorgesehen") does not count. For projects the strongest
evidence is structural — the listing's completed section, or a construction
diary in the chapter navigation — and body text can never make a project
"in operation".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.transnetbw.normalize import cap


TRANSFORMER_SUBJECT = re.compile(
    r"umspann|(?<![a-zäöüß])uw\b|schaltanlage|schaltwerk|netzknoten|konverter|"
    r"phasenschieber|transformator|standort neckarwestheim",
    re.IGNORECASE,
)

CAPACITY_SUBJECT = re.compile(
    r"netzverst[äa]rkung|netzausbau|netzbooster|suedlink|südlink|ultranet|engpass|"
    r"überlast|übertragungskapazität|transportkapazität|höchstspannungsleitung|"
    r"(?<!\d)(?:380|220)\s?-?\s?kv|leitungsbau|stromleitung|gleichstrom|"
    r"freileitung|erdkabel|trasse|netzoptimierung",
    re.IGNORECASE,
)

BODY_TRANSFORMER = re.compile(
    r"umspannwerk|schaltanlage|transformator|phasenschieber|konverter|netzknoten",
    re.IGNORECASE,
)

BODY_CAPACITY = re.compile(
    r"netzverst[äa]rkung|netzausbau|übertragungskapazität|transportkapazität|"
    r"engpass|überlast|netzbooster",
    re.IGNORECASE,
)

EXCLUSIONS = (
    (
        "out_of_scope_back_office",
        re.compile(r"abrechnung|rechnungsprüfung", re.IGNORECASE),
    ),
    (
        "out_of_scope_maintenance",
        re.compile(r"seiltausch|leiterseil(?:wechsel|tausch)|korrosionsschutz|mastsanierung|isolatortausch", re.IGNORECASE),
    ),
    (
        "out_of_scope_market",
        re.compile(r"kapazitätsreserve|kapazitätsmarkt|kapazitätsmechanism|strompreis|netzentgelt|regelenergie|bilanzkreis", re.IGNORECASE),
    ),
    (
        "out_of_scope_policy",
        re.compile(
            r"freileitungsvorrang|bundesbedarfsplan|szenariorahmen|netzentwicklungsplan|"
            r"gesetzentwurf|positionspapier|stellungnahme|bündnis|netzplanungsgrundsätze",
            re.IGNORECASE,
        ),
    ),
)

PREFILTER = re.compile(
    r"umspann|transformator|trafo|schaltanlage|phasenschieber|netzbooster|netzknoten|"
    r"konverter|engpass|überlast|netzverst[äa]rkung|netzausbau|höchstspannungsleitung|"
    r"leitung|suedlink|südlink|ultranet|kabel|trasse",
    re.IGNORECASE,
)

TRANSFORMER = "transformer_modernization"

CAPACITY = "grid_capacity_constraint"

EVIDENCE_LIMIT = 200


@dataclass(frozen=True)
class Classification:

    included: bool

    signal_type: str | None

    secondary_types: tuple[str, ...]

    confidence: str | None

    rule: str

    evidence: str | None

    exclusion: str | None = None


SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9„\"])")


def sentences(text: str) -> list[str]:
    return [sentence for sentence in SENTENCE_END.split(text or "") if sentence.strip()]


def _snippet(text: str, match: re.Match) -> str:
    """
    The sentence containing the match, capped.
    """

    start = text.rfind(". ", 0, match.start())

    start = 0 if start < 0 else start + 2

    end = text.find(". ", match.end())

    end = len(text) if end < 0 else end + 1

    return cap(text[start:end].strip(), EVIDENCE_LIMIT)


def title_is_candidate(title: str | None) -> bool:
    """
    Cheap pre-filter on a feed title: is the article worth fetching?
    Classification proper happens after the fetch.
    """

    return bool(title and PREFILTER.search(title))


def classify(subject: str, body: str = "") -> Classification:

    for reason, pattern in EXCLUSIONS:

        found = pattern.search(subject)

        if found:
            return Classification(
                included=False,
                signal_type=None,
                secondary_types=(),
                confidence=None,
                rule=f"exclude:{reason}",
                evidence=_snippet(subject, found),
                exclusion=reason,
            )

    transformer = TRANSFORMER_SUBJECT.search(subject)

    capacity = CAPACITY_SUBJECT.search(subject)

    confidence = "high"

    if transformer:
        signal_type, found, rule, text = TRANSFORMER, transformer, "subject:transformer", subject

    elif capacity:
        signal_type, found, rule, text = CAPACITY, capacity, "subject:capacity", subject

    else:

        body_transformer = BODY_TRANSFORMER.search(body)

        body_capacity = BODY_CAPACITY.search(body)

        candidates = [
            (match.start(), kind, match)
            for kind, match in ((TRANSFORMER, body_transformer), (CAPACITY, body_capacity))
            if match
        ]

        if not candidates:
            return Classification(
                included=False,
                signal_type=None,
                secondary_types=(),
                confidence=None,
                rule="exclude:no_signal",
                evidence=None,
                exclusion="out_of_scope_no_signal",
            )

        _, signal_type, found = min(candidates, key=lambda candidate: candidate[0])

        rule = f"body:{'transformer' if signal_type == TRANSFORMER else 'capacity'}"

        text = body

        confidence = "low"

    other = BODY_CAPACITY if signal_type == TRANSFORMER else BODY_TRANSFORMER

    secondary = ()

    if other.search(subject) or other.search(body):
        secondary = (CAPACITY if signal_type == TRANSFORMER else TRANSFORMER,)

    return Classification(
        included=True,
        signal_type=signal_type,
        secondary_types=secondary,
        confidence=confidence,
        rule=rule,
        evidence=_snippet(text, found),
    )


# =========================================================
# STAGE
# =========================================================


STAGE_CUES = {
    # "abgeschlossen" counts only after a construction noun: a completed
    # award procedure or research project commissions nothing.
    "in_operation": re.compile(
        r"inbetriebnahme|in betrieb genommen|in betrieb gegangen|ans netz gegangen|fertiggestellt|"
        r"einweihung|eingeweiht|"
        r"(?:(?<![a-zäöüß])bau|umbau|neubau|ausbau|modernisierung|erweiterung)\w*(?:\W+\w+){0,8}?\W+abgeschlossen",
        re.IGNORECASE,
    ),
    "construction": re.compile(
        r"baubeginn|baustart|bauauftakt|spatenstich|bauarbeiten|baustelle|bauaktivität|"
        r"baufortschritt|bauphase|leitungsbau|im bau\b|rückbau|"
        r"\bbau (?:des|der|eines|einer|von)\b|\bmit dem (?:um- und )?(?:neu|um)?bau\b|"
        r"\bstartet\s+(?:den\s+)?(?:um- und )?(?:neu|um)?bau\b|\bbeginnt mit (?:der|dem|den)\b|\bbegonnen\b",
        re.IGNORECASE,
    ),
    "approval": re.compile(
        r"planfeststellung|teilbeschluss|genehmigung|genehmigt|antragskonferenz|"
        r"\bantrag\b|anträge|bundesfachplanung|untersuchungsrahmen|bimschg",
        re.IGNORECASE,
    ),
    "planning": re.compile(
        r"netzentwicklungsplan|\bnep\b|bedarfsplan|trassenkorridor|raumordnung|vorplanung|"
        r"standortfindung|standortsuche|(?:bundesnetzagentur|bnetza)\s+bestätigt",
        re.IGNORECASE,
    ),
}

FUTURE = re.compile(
    r"vorgesehen|geplant|planmäßig|\bsoll(?:en|te|ten)?\b|voraussichtlich|künftig|zukünftig|"
    r"\bab (?:19|20)\d{2}\b|\bbis (?:19|20)\d{2}\b|nach aktuelle[rm] plan|in planung",
    re.IGNORECASE,
)

DIARY = re.compile(r"projekttagebuch|bautagebuch|baufortschritt", re.IGNORECASE)

STATUS_SECTION = re.compile(r"aktuell|zeitplan|projektstand|meilenstein|status", re.IGNORECASE)

ADVANCEMENT = ("construction", "approval", "planning")


def _first_cue(text: str | None) -> tuple[str, str] | None:
    """
    The earliest stage cue in a short text (a title), ignoring sentences
    that speak of the future.
    """

    for sentence in sentences(text or ""):

        if FUTURE.search(sentence):
            continue

        found = {
            stage: match
            for stage, pattern in STAGE_CUES.items()
            if (match := pattern.search(sentence))
        }

        if not found:
            continue

        # Permission to build is approval ("Bau des Konverters … ist genehmigt").
        if "approval" in found and "construction" in found:
            return "approval", cap(sentence, EVIDENCE_LIMIT)

        stage = min(found, key=lambda name: found[name].start())

        return stage, cap(sentence, EVIDENCE_LIMIT)

    return None


def press_stage(title: str, subheads: list[str], lead: str | None) -> tuple[str, str | None]:
    """
    The milestone a release announces: the first stage cue in its title,
    else in its subheads, else in its lead.
    """

    for text in (title, *subheads, lead):

        found = _first_cue(text)

        if found:
            return found

    return "unknown", None


def project_stage(overview, portrait=None, completed: bool = False) -> tuple[str, str | None]:
    """
    A project's stage from its own pages only.
    """

    if completed:
        return "in_operation", "listing section: Abgeschlossene Projekte"

    for label in overview.chapter_links:

        if DIARY.search(label):
            return "construction", f"chapter navigation: {label}"

    pages = [page for page in (portrait, overview) if page is not None]

    status = [
        section
        for page in pages
        for section in page.sections
        if STATUS_SECTION.search(" ".join(filter(None, (section.heading, section.anchor, section.preheadline))))
    ]

    scopes = [status] if status else []

    scopes.append([section for page in pages for section in page.sections])

    for scope in scopes:

        # Paragraphs and list items only: headings ("Planung und
        # Genehmigung") name a chapter, not the project's state.
        texts = [
            sentence
            for section in scope
            for part in (*section.paragraphs, *section.items)
            for sentence in sentences(part)
        ]

        for stage in ADVANCEMENT:

            for sentence in texts:

                if not STAGE_CUES[stage].search(sentence) or FUTURE.search(sentence):
                    continue

                # Permission to build is still approval: "…einen Antrag auf
                # vorzeitigen Baubeginn genehmigt" names construction only
                # as the object of an approval.
                if stage == "construction" and STAGE_CUES["approval"].search(sentence):
                    continue

                return stage, cap(sentence, EVIDENCE_LIMIT)

    return "unknown", None
