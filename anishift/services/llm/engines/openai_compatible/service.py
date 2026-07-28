"""Custom endpoint provider using the shared Chat Completions transport."""

from __future__ import annotations

from typing import Final

from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines._openai_compatible import (
    ClientFactory,
    OpenAiCompatibleProvider,
    OpenAiCompatibleTransport,
)

__all__ = ["OpenaiCompatibleService"]

_PROVIDER: Final[OpenAiCompatibleProvider] = OpenAiCompatibleProvider(
    engine_id="openai_compatible",
    default_base_url=None,
    requires_api_key=False,
    api_key_env_var=None,
    max_tokens_parameter="max_tokens",
)
"""Custom endpoint settings for the shared transport."""


class OpenaiCompatibleService(OpenAiCompatibleTransport):
    """Synchronous provider for a caller-supplied OpenAI-compatible endpoint."""

    def __init__(
        self,
        config: LlmConfig,
        *,
        _client_factory: ClientFactory | None = None,
    ) -> None:
        """Initialize the custom provider without creating its SDK client."""
        super().__init__(config, _PROVIDER, client_factory=_client_factory)
