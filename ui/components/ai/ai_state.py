"""
AI Workspace State

Centralized Streamlit session state for the
AI Infrastructure Advisor.

Responsibilities
- Initialize session state
- Reset conversations
- Manage pending requests

Author:
NRW BI Platform
"""

from __future__ import annotations

import streamlit as st


# ==========================================================
# Initialize
# ==========================================================

def initialize_ai_state() -> None:
    """
    Initialize all AI session state variables.
    """

    if "ai_messages" not in st.session_state:

        st.session_state.ai_messages = [
            {
                "role": "assistant",
                "content": (
                    "👋 Welcome to the AI Infrastructure Advisor.\n\n"
                    "I can help you analyze infrastructure, compare "
                    "operators, rank facilities, search nearby data "
                    "centers, and answer questions using the Business "
                    "Intelligence available in the platform."
                ),
            }
        ]

    if "ai_pending" not in st.session_state:
        st.session_state.ai_pending = False

    if "ai_input" not in st.session_state:
        st.session_state.ai_input = ""

    if "ai_current_prompt" not in st.session_state:
        st.session_state.ai_current_prompt = None

    if "ai_processing" not in st.session_state:
        st.session_state.ai_processing = False

# ==========================================================
# Messages
# ==========================================================

def add_user_message(
    content: str,
) -> None:

    st.session_state.ai_messages.append(
        {
            "role": "user",
            "content": content,
        }
    )


def add_assistant_message(
    content: str,
    sources: list[str] | None = None,
    trace: dict | None = None,
    citations: list | None = None,
) -> None:

    message = {
        "role": "assistant",
        "content": content,
    }

    if sources:
        message["sources"] = sources

    if trace:
        message["trace"] = trace

    if citations:
        message["citations"] = citations

    st.session_state.ai_messages.append(
        message
    )


# ==========================================================
# Conversation
# ==========================================================

def clear_chat() -> None:
    """
    Clears the conversation and starts a new chat.
    """

    st.session_state.ai_messages = [
        {
            "role": "assistant",
            "content": (
                "👋 New conversation started.\n\n"
                "How can I help you today?"
            ),
        }
    ]

    st.session_state.ai_pending = False
    st.session_state.ai_input = ""
    st.session_state.ai_last_prompt = None


# ==========================================================
# Pending State
# ==========================================================

def set_pending(
    value: bool,
) -> None:

    st.session_state.ai_pending = value


def is_pending() -> bool:

    return st.session_state.ai_pending


# ==========================================================
# Getters
# ==========================================================

def messages():

    return st.session_state.ai_messages

def set_processing(value: bool):

    st.session_state.ai_processing = value


def is_processing():

    return st.session_state.ai_processing