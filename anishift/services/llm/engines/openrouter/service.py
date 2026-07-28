"""OpenRouter provider using the shared Chat Completions transport."""

from __future__ import annotations

from typing import Final

from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines._openai_compatible import (
    ClientFactory,
    OpenAiCompatibleProvider,
    OpenAiCompatibleTransport,
)

__all__ = ["OpenrouterService"]

_OPENROUTER_BASE_URL: Final[str] = "https://openrouter.ai/api/v1"
"""Official OpenRouter OpenAI-compatible base URL."""

_PROVIDER: Final[OpenAiCompatibleProvider] = OpenAiCompatibleProvider(
    engine_id="openrouter",
    default_base_url=_OPENROUTER_BASE_URL,
    requires_api_key=True,
    api_key_env_var="ANISHIFT_OPENROUTER_API_KEY",
    max_tokens_parameter="max_tokens",
)
"""OpenRouter-specific settings for the shared transport."""


class OpenrouterService(OpenAiCompatibleTransport):
    """Synchronous OpenRouter Chat Completions provider."""

    def __init__(
        self,
        config: LlmConfig,
        *,
        _client_factory: ClientFactory | None = None,
    ) -> None:
        """Initialize OpenRouter without creating its SDK client."""
        super().__init__(config, _PROVIDER, client_factory=_client_factory)
