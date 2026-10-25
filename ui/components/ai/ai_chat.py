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

def render_ai_chat(*, compact: bool = True) -> str | None:
    """
    Render the AI conversation.

    The dashboard uses a bounded, auto-scrolling transcript while the
    dedicated assistant page lets the conversation grow with its content.
    """

    chat_messages = messages()

    container_options = (
        {
            "height": 320,
            "key": "ai_messages",
            "autoscroll": True,
        }
        if compact
        else {
            "height": "content",
            "key": "ai_messages",
        }
    )

    # ------------------------------------------------------
    # Conversation
    # ------------------------------------------------------

    with st.container(**container_options):

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

        if not isinstance(trace, dict):

            trace = {}

        plan = trace.get("plan") or {}

        if not isinstance(plan, dict):

            plan = {}

        tools = plan.get("tools") or []

        if isinstance(tools, (str, int, float)):

            tools = [tools]

        elif not isinstance(tools, (list, tuple, set)):

            tools = []

        st.markdown(
            f"**Plan** — tools: `{', '.join(str(tool) for tool in tools)}`, "
            f"query: `{plan.get('query', '')}`, k: {plan.get('k', '')}"
        )

        rounds = trace.get("rounds") or []

        if not isinstance(rounds, (list, tuple)):

            rounds = []

        for index, round_ in enumerate(rounds, start=1):

            if not isinstance(round_, dict):

                round_ = {}

            result_ids = round_.get("result_ids") or []

            if not isinstance(result_ids, (list, tuple, set)):

                result_ids = []

            st.markdown(
                f"**Round {index}** — query: `{round_.get('query')}`, "
                f"{len(result_ids)} result(s)"
            )

        verify = trace.get("verify") or {}

        if not isinstance(verify, dict):

            verify = {}

        st.markdown(
            f"**Verify** — sufficient: {verify.get('sufficient')}"
        )

        if verify.get("missing"):

            st.caption(f"Missing: {verify['missing']}")

        rejected_items = verify.get("rejected") or []

        if isinstance(rejected_items, dict):

            rejected_items = [rejected_items]

        elif not isinstance(rejected_items, (list, tuple)):

            rejected_items = [rejected_items]

        if rejected_items:

            for rejected in rejected_items:

                if isinstance(rejected, dict):

                    st.caption(
                        f"Rejected {rejected.get('id')}: "
                        f"{rejected.get('reason')}"
                    )

                else:

                    st.caption(f"Rejected: {rejected}")

        if trace.get("site"):

            st.markdown("**Site intelligence used**")
            st.json(trace["site"], expanded=False)

        if trace.get("ranking"):

            ranking = trace["ranking"]
            ranking_count = (
                len(ranking)
                if isinstance(ranking, (list, tuple, dict, set))
                else 1
            )

            st.markdown(
                f"**Facility ranking used** ({ranking_count})"
            )
            st.json(ranking, expanded=False)
