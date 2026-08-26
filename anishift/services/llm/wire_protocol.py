"""Wire protocol vocabulary shared by the model catalog and the LLM adapters.

This is a leaf module on purpose: it imports nothing from AniShift and no
provider SDK. Both the configuration layer, which validates the local catalog,
and the provider adapters, which build requests, depend on this single enum
instead of on each other, so the vocabulary cannot drift into two parallel sets
and the dependency direction stays configuration → services.

Public API:
    ModelProtocol: The four supported Foundry proxy wire protocols.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["ModelProtocol"]


class ModelProtocol(StrEnum):
    """Wire protocol a Foundry proxy provider speaks."""

    OPENAI_CHAT = "openai_chat"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    GOOGLE_GENERATE = "google_generate"
    XAI_CHAT = "xai_chat"
