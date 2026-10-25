"""
Defensive JSON parsing for mini-model responses.

A model told to respond with ONLY a JSON object still sometimes wraps
it in a markdown code fence, or returns prose instead of JSON. Callers
need a clean "did this parse into the shape I asked for" signal so a
malformed response degrades to a default rather than raising.

Author:
NRW BI Platform
"""

from __future__ import annotations

import json


def parse_json_object(
    text,
) -> dict | None:
    """
    Parse `text` into a dict, stripping a ```json ... ``` or ``` ... ```
    fence first if present. Returns None for anything that is not text
    containing a JSON object — malformed JSON, prose, or a JSON array.
    """

    if not isinstance(text, str):

        return None

    stripped = text.strip()

    if stripped.startswith("```"):

        stripped = stripped.removeprefix(
            "```json"
        ).removeprefix("```")

        stripped = stripped.removesuffix("```")

        stripped = stripped.strip()

    try:

        data = json.loads(stripped)

    except json.JSONDecodeError:

        return None

    return data if isinstance(data, dict) else None
