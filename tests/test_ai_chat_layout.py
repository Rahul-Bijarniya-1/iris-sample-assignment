"""Layout contracts for the compact and full-page AI assistant."""

from contextlib import nullcontext
from types import SimpleNamespace

from ui.components.ai import ai_chat, ai_panel


class _FakeChatStreamlit:
    def __init__(self):
        self.session_state = SimpleNamespace(ai_pending=False)
        self.container_calls = []
        self.markdown_calls = []

    def container(self, **kwargs):
        self.container_calls.append(kwargs)
        return nullcontext()

    def chat_message(self, *_args, **_kwargs):
        return nullcontext()

    def markdown(self, value, *_args, **_kwargs):
        self.markdown_calls.append(value)

    def chat_input(self, *_args, **_kwargs):
        return None

    def caption(self, *_args, **_kwargs):
        return None

    def status(self, *_args, **_kwargs):
        return nullcontext()


def test_compact_chat_is_fixed_height_and_autoscrolls(monkeypatch):
    fake_st = _FakeChatStreamlit()
    monkeypatch.setattr(ai_chat, "st", fake_st)
    monkeypatch.setattr(ai_chat, "messages", lambda: [])

    ai_chat.render_ai_chat(compact=True)

    assert fake_st.container_calls == [
        {"height": 320, "key": "ai_messages", "autoscroll": True}
    ]


def test_full_page_chat_flows_to_content_height(monkeypatch):
    fake_st = _FakeChatStreamlit()
    monkeypatch.setattr(ai_chat, "st", fake_st)
    monkeypatch.setattr(ai_chat, "messages", lambda: [])

    ai_chat.render_ai_chat(compact=False)

    assert fake_st.container_calls == [
        {"height": "content", "key": "ai_messages"}
    ]


def test_empty_conversation_renders_single_welcome(monkeypatch):
    fake_st = _FakeChatStreamlit()
    welcome = "Welcome to the AI Infrastructure Advisor."
    monkeypatch.setattr(ai_chat, "st", fake_st)
    monkeypatch.setattr(
        ai_chat,
        "messages",
        lambda: [{"role": "assistant", "content": welcome}],
    )

    ai_chat.render_ai_chat(compact=False)

    assert fake_st.markdown_calls == [welcome]


def test_panel_forwards_full_page_layout(monkeypatch):
    captured = []
    fake_st = SimpleNamespace(
        container=lambda **_kwargs: nullcontext(),
        session_state=SimpleNamespace(ai_pending=False),
    )
    monkeypatch.setattr(ai_panel, "st", fake_st)
    monkeypatch.setattr(ai_panel, "initialize_ai_state", lambda: None)
    monkeypatch.setattr(ai_panel, "render_ai_header", lambda: None)
    monkeypatch.setattr(
        ai_panel,
        "render_ai_chat",
        lambda *, compact: captured.append(compact),
    )

    ai_panel.render_ai_panel(compact=False)

    assert captured == [False]
