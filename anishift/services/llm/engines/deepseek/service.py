"""DeepSeek provider using the shared Chat Completions transport."""

from __future__ import annotations

from typing import Final

from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines._openai_compatible import (
    ClientFactory,
    OpenAiCompatibleProvider,
    OpenAiCompatibleTransport,
)

__all__ = ["DeepseekService"]

_DEEPSEEK_BASE_URL: Final[str] = "https://api.deepseek.com"
"""Official DeepSeek OpenAI-compatible base URL."""

_PROVIDER: Final[OpenAiCompatibleProvider] = OpenAiCompatibleProvider(
    engine_id="deepseek",
    default_base_url=_DEEPSEEK_BASE_URL,
    requires_api_key=True,
    api_key_env_var="ANISHIFT_DEEPSEEK_API_KEY",
    max_tokens_parameter="max_tokens",
    unavailable_finish_reasons=frozenset({"insufficient_system_resource"}),
)
"""DeepSeek-specific settings for the shared transport."""


class DeepseekService(OpenAiCompatibleTransport):
    """Synchronous DeepSeek Chat Completions provider."""

    def __init__(
        self,
        config: LlmConfig,
        *,
        _client_factory: ClientFactory | None = None,
    ) -> None:
        """Initialize DeepSeek without creating its SDK client."""
        super().__init__(config, _PROVIDER, client_factory=_client_factory)
