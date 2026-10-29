"""
Press release → project linking, from curated project names only.

Patterns live in data/project_aliases.json. A release naming exactly one
project is linked; one naming two different projects is linked to neither
and flagged for review, because picking one would be a guess.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.transnetbw.normalize import cap, clean_text


ALIASES_FILE = Path(__file__).parent / "data" / "project_aliases.json"

DASHES = re.compile(r"[‐-―−]")


@dataclass(frozen=True)
class LinkResult:

    slug: str | None

    ambiguous: bool

    candidates: tuple[str, ...]

    evidence: str | None


def load_aliases(path: Path = ALIASES_FILE) -> dict[str, list[re.Pattern]]:

    data = json.loads(path.read_text(encoding="utf-8"))

    return {
        slug: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
        for slug, patterns in data["aliases"].items()
    }


def matching_text(text: str | None) -> str:
    """
    Lower-cased, cleaned, with every dash variant written as '-'. Lower,
    not casefold: casefold turns ß into ss and would hide "Großgartach".
    """

    return DASHES.sub("-", clean_text(text) or "").lower()


def link_project(text: str | None, aliases: dict[str, list[re.Pattern]]) -> LinkResult:

    haystack = matching_text(text)

    matches = {}

    for slug, patterns in aliases.items():

        for pattern in patterns:

            found = pattern.search(haystack)

            if found:
                matches[slug] = found
                break

    if len(matches) == 1:

        slug, found = next(iter(matches.items()))

        return LinkResult(
            slug=slug,
            ambiguous=False,
            candidates=(slug,),
            evidence=cap(found.group(0), 200),
        )

    return LinkResult(
        slug=None,
        ambiguous=len(matches) > 1,
        candidates=tuple(sorted(matches)),
        evidence=None,
    )
