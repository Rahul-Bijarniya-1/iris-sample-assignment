"""
AI Workspace

Main AI workspace for the
AI Infrastructure Advisor.

Author:
NRW BI Platform
"""

from __future__ import annotations

import logging

import streamlit as st

from app.database.session import SessionLocal
from app.services.ai_advisor_service import AIAdvisorService

from ui.components.ai.ai_state import (
    initialize_ai_state,
    add_user_message,
    add_assistant_message,
    set_pending,
)

from ui.components.ai.ai_header import (
    render_ai_header,
)

from ui.components.ai.ai_chat import (
    render_ai_chat,
)


logger = logging.getLogger(__name__)


# ==========================================================
# Public
# ==========================================================

def render_ai_panel() -> None:

    initialize_ai_state()

    with st.container(
        border=True,
        key="ai_workspace",
    ):

        render_ai_header()

        prompt = render_ai_chat()

    # --------------------------------------------
    # New Prompt
    # --------------------------------------------

    if (
        prompt
        and prompt.strip()
    ):

        add_user_message(
            prompt.strip(),
        )

        st.session_state.ai_current_prompt = (
            prompt.strip()
        )

        set_pending(True)

        st.rerun()

    # --------------------------------------------
    # Pending Request
    # --------------------------------------------

    if not st.session_state.ai_pending:
        return

    facility_id = st.session_state.get(
        "selected_facility_id"
    )

    # No blanket gate here: a selected facility is required for site
    # intelligence questions, but a news question can name a place
    # instead — ask() already handles facility_id=None gracefully for
    # every intent (e.g. _site_analysis's own "please select a Data
    # Center" message), so the UI no longer needs to pre-empt it.

    prompt = st.session_state.ai_current_prompt

    response, trace, citations = _call_ai(
        question=prompt,
        facility_id=facility_id,
    )

    add_assistant_message(
        response,
        ["AI Infrastructure Advisor"],
        trace=trace,
        citations=citations,
    )

    st.session_state.ai_current_prompt = None

    set_pending(False)

    st.rerun()


# ==========================================================
# AI
# ==========================================================

def _call_ai(
    question: str,
    facility_id: int | None,
) -> tuple[str, dict | None, list | None]:

    session = SessionLocal()

    try:

        advisor = AIAdvisorService(
            session,
        )

        with st.status(
            "Thinking...",
            expanded=False,
        ) as status:

            def on_step(stage: str) -> None:

                status.update(
                    label=f"{stage}..."
                )

            answer = advisor.ask(
                question=question,
                selected_facility_id=facility_id,
                on_step=on_step,
            )

            status.update(
                label="Done",
                state="complete",
            )

        return (
            answer,
            advisor.last_trace,
            advisor.last_citations,
        )

    except Exception:

        logger.exception("AI advisor request failed")

        return (
            "AI unavailable right now. Please try again later.",
            None,
            None,
        )

    finally:

        session.close()
