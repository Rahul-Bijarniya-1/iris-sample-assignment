"""Defensive rendering for traces already persisted in session state."""

from contextlib import nullcontext

from ui.components.ai import ai_chat


def test_render_trace_survives_rejected_items_as_bare_strings(monkeypatch):
    captions = []

    monkeypatch.setattr(
        ai_chat.st,
        "expander",
        lambda *args, **kwargs: nullcontext(),
    )
    monkeypatch.setattr(ai_chat.st, "markdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(ai_chat.st, "caption", captions.append)
    monkeypatch.setattr(ai_chat.st, "json", lambda *args, **kwargs: None)

    ai_chat._render_trace(
        {
            "plan": {"tools": ["news_search"], "query": "q", "k": 10},
            "rounds": [],
            "verify": {
                "sufficient": False,
                "rejected": ["legacy malformed rejection"],
            },
        }
    )

    assert "Rejected: legacy malformed rejection" in captions
