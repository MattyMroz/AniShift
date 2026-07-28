"""OpenAI provider using the shared Chat Completions transport."""

from __future__ import annotations

from typing import Final

from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines._openai_compatible import (
    ClientFactory,
    OpenAiCompatibleProvider,
    OpenAiCompatibleTransport,
)

__all__ = ["OpenaiService"]

_PROVIDER: Final[OpenAiCompatibleProvider] = OpenAiCompatibleProvider(
    engine_id="openai",
    default_base_url=None,
    requires_api_key=True,
    api_key_env_var="ANISHIFT_OPENAI_API_KEY",
    max_tokens_parameter="max_completion_tokens",
)
"""OpenAI-specific settings for the shared transport."""


class OpenaiService(OpenAiCompatibleTransport):
    """Synchronous OpenAI Chat Completions provider."""

    def __init__(
        self,
        config: LlmConfig,
        *,
        _client_factory: ClientFactory | None = None,
    ) -> None:
        """Initialize OpenAI without creating its SDK client."""
        super().__init__(config, _PROVIDER, client_factory=_client_factory)
