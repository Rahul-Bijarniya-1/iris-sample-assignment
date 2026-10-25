"""Streamlit-level regression coverage for the AI response lifecycle."""

from streamlit.testing.v1 import AppTest


APP_SCRIPT = r'''
from ui.components.ai import ai_panel


def fake_call_ai(question, facility_id):
    return (
        "## Recommendation\n\n"
        "- **Düsseldorf**: 87/100\n\n"
        "| Site | Grid |\n|---|---|\n| Düsseldorf | Strong |",
        {
            "plan": {"tools": ["ranking"], "query": question, "k": 5},
            "rounds": [],
            "verify": {"sufficient": True},
        },
        [
            {
                "index": 1,
                "title": "Grid update",
                "title_de": "Netz-Update",
                "source": "Utility",
                "published_at": "2026-10-25",
                "url": "https://example.invalid",
            }
        ],
    )


original_call_ai = ai_panel._call_ai
ai_panel._call_ai = fake_call_ai
try:
    ai_panel.render_ai_panel()
finally:
    ai_panel._call_ai = original_call_ai
'''


def test_chat_submission_renders_one_complete_response():
    app = AppTest.from_string(APP_SCRIPT, default_timeout=5).run()

    assert not app.exception
    assert sum("Welcome" in item.value for item in app.markdown) == 1

    app.chat_input[0].set_value("Compare sites").run()

    assert not app.exception
    assert [message.name for message in app.chat_message] == [
        "assistant",
        "user",
        "assistant",
    ]
    assert app.chat_message[-1].markdown[0].value.startswith(
        "## Recommendation"
    )
    assert [expander.label for expander in app.chat_message[-1].expander] == [
        "🔍 How I got this"
    ]
    assert app.session_state.ai_pending is False
    assert len(app.chat_input) == 1
