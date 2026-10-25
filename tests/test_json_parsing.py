"""
parse_json_object: shared defensive JSON parsing for mini-model
responses. A model told to "respond with ONLY JSON" still sometimes
wraps it in a markdown code fence, or returns prose instead — this must
degrade to None, never raise, so callers can fall back to a default.
"""

from app.ai.json_parsing import parse_json_object


def test_parses_a_plain_json_object():
    assert parse_json_object('{"a": 1}') == {"a": 1}


def test_strips_a_markdown_code_fence():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('```\n{"a": 1}\n```') == {"a": 1}


def test_returns_none_for_prose():
    assert parse_json_object("Sorry, I cannot help with that.") is None


def test_returns_none_for_a_json_array():
    assert parse_json_object("[1, 2, 3]") is None


def test_returns_none_for_non_string_input():
    assert parse_json_object(None) is None
