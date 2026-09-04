"""Wire protocol vocabulary shared by the model catalog and the LLM adapters."""

from __future__ import annotations

from enum import StrEnum

__all__ = ["ModelProtocol"]


class ModelProtocol(StrEnum):
    """Wire protocol a Foundry proxy provider speaks."""

    OPENAI_CHAT = "openai_chat"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    GOOGLE_GENERATE = "google_generate"
    XAI_RESPONSES = "xai_responses"
