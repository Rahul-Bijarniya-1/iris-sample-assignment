"""Shared, runtime-resolved OpenAI configuration."""

from __future__ import annotations

import os

from openai import OpenAI


DEFAULT_CHAT_MODEL = "gpt-4.1-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_ANSWER_MODEL = "gpt-4.1"


def get_chat_model() -> str:
    """Return the configured model for routine structured calls."""

    return os.getenv("OPENAI_MODEL", DEFAULT_CHAT_MODEL)


def get_embedding_model() -> str:
    """Return the configured embeddings model."""

    return os.getenv(
        "OPENAI_EMBEDDING_MODEL",
        DEFAULT_EMBEDDING_MODEL,
    )


def get_answer_model() -> str:
    """Return the configured model for final agentic answers."""

    return os.getenv("OPENAI_ANSWER_MODEL", DEFAULT_ANSWER_MODEL)


class LazyOpenAIClient:
    """Own an injected client or construct one on first use."""

    def __init__(self, client=None):

        self._client = client

    @property
    def client(self):

        if self._client is None:

            self._client = OpenAI(
                api_key=os.getenv("OPENAI_API_KEY")
            )

        return self._client
