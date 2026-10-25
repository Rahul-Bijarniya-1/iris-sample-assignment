"""
AI Workspace Chat

Responsible for rendering the AI conversation.

Author:
NRW BI Platform
"""

from __future__ import annotations

import streamlit as st

from ui.components.ai.ai_state import messages


# ==========================================================
# Chat
# ==========================================================

def render_ai_chat() -> str | None:
    """
    Render the AI conversation.
    """

    chat_messages = messages()

    user_messages = [
        message
        for message in chat_messages
        if message["role"] == "user"
    ]

    # ------------------------------------------------------
    # Conversation
    # ------------------------------------------------------

    with st.container(height=320):

        if not user_messages:

            st.markdown(
                """
#### 👋 Welcome

Ask me anything about your Data Center Business Intelligence.

**Examples**

- Analyze this site
- Show data centers in Berlin
- Compare Microsoft vs Equinix
- Top 10 data centers
"""
            )

            st.divider()

        for message in chat_messages:

            with st.chat_message(message["role"]):

                st.markdown(message["content"])

                if message.get("sources"):

                    st.caption(
                        "📚 "
                        + ", ".join(message["sources"])
                    )

                if message.get("citations"):

                    _render_citations(
                        message["citations"]
                    )

                if message.get("trace"):

                    _render_trace(
                        message["trace"]
                    )

        if st.session_state.ai_pending:

            with st.chat_message("assistant"):

                st.status(
                    "AI Assistant is typing...",
                    expanded=False,
                )

    # ------------------------------------------------------
    # Input
    # ------------------------------------------------------

    return st.chat_input(
        "Ask about infrastructure..."
    )


# ==========================================================
# Citations / Trace
# ==========================================================

def _render_citations(
    citations: list[dict],
) -> None:
    """
    Source list: English title prominent, German original muted,
    plus date, source, and link — bilingual per the project's "Context"
    (the English translation is what the planner reads; the German
    original stays visible for provenance).
    """

    st.caption("Sources")

    for citation in citations:

        title = citation.get("title") or "Untitled"
        title_de = citation.get("title_de")
        published = citation.get("published_at")
        source = citation.get("source")
        url = citation.get("url")

        line = f"**[{citation.get('index')}] {title}**"

        if url:

            line = f"[{citation.get('index')}] [{title}]({url})"

        st.markdown(line)

        if title_de and title_de != title:

            st.caption(title_de)

        meta = " · ".join(
            str(part)
            for part in (source, published)
            if part
        )

        if meta:

            st.caption(meta)


def _render_trace(
    trace: dict,
) -> None:
    """
    Collapsed "how I got this" expander: the plan, the queries issued,
    the retrieval rounds, and the verify verdict with any rejections.
    """

    with st.expander("🔍 How I got this"):

        plan = trace.get("plan") or {}

        st.markdown(
            f"**Plan** — tools: `{', '.join(plan.get('tools', []))}`, "
            f"query: `{plan.get('query', '')}`, k: {plan.get('k', '')}"
        )

        for index, round_ in enumerate(
            trace.get("rounds") or [], start=1
        ):

            st.markdown(
                f"**Round {index}** — query: `{round_.get('query')}`, "
                f"{len(round_.get('result_ids') or [])} result(s)"
            )

        verify = trace.get("verify") or {}

        st.markdown(
            f"**Verify** — sufficient: {verify.get('sufficient')}"
        )

        if verify.get("missing"):

            st.caption(f"Missing: {verify['missing']}")

        if verify.get("rejected"):

            for rejected in verify["rejected"]:

                st.caption(
                    f"Rejected {rejected.get('id')}: "
                    f"{rejected.get('reason')}"
                )