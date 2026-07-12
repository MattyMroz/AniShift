"""Application settings loaded from environment / ``.env`` file.

Type-safe API-key configuration via pydantic-settings. Every field maps to an
``ANISHIFT_``-prefixed env var (or the same key in ``.env``). All keys are
optional — a missing key only disables the engine that needs it, not the app.

Usage:
    >>> from anishift.config.settings import Settings
    >>> s = Settings()
    >>> bool(s.deepl_api_key)
    False
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings"]


class Settings(BaseSettings):
    """API keys and env-driven settings — loaded from env vars and ``.env``.

    Field names map to env vars with the ``ANISHIFT_`` prefix, e.g.
    ``deepl_api_key`` <- ``ANISHIFT_DEEPL_API_KEY``. System environment
    variables take precedence over ``.env``.

    Attributes:
        deepl_api_key: DeepL API key (translation engine ``deepl``).
        elevenlabs_api_key: Official ElevenLabs API key (TTS engine
            ``elevenlabs``). NOT used by ``elevenbytes`` — that proxy engine
            ships its own built-in key.
        anthropic_api_key: LLM provider ``anthropic``.
        gemini_api_key: LLM provider ``gemini``.
        openai_api_key: LLM provider ``openai``.
        deepseek_api_key: LLM provider ``deepseek``.
        openrouter_api_key: LLM provider ``openrouter``.
        openai_compatible_api_key: LLM provider ``openai_compatible``.
        openai_compatible_base_url: Base URL for the ``openai_compatible``
            provider (self-hosted / gateway endpoint).
    """

    model_config = SettingsConfigDict(
        env_prefix="ANISHIFT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Translation
    deepl_api_key: str = Field(default="", description="DeepL API key")

    # TTS
    elevenlabs_api_key: str = Field(default="", description="Official ElevenLabs API key")

    # LLM providers
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    gemini_api_key: str = Field(default="", description="Google Gemini API key")
    openai_api_key: str = Field(default="", description="OpenAI API key")
    deepseek_api_key: str = Field(default="", description="DeepSeek API key")
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openai_compatible_api_key: str = Field(default="", description="OpenAI-compatible endpoint key")
    openai_compatible_base_url: str = Field(default="", description="OpenAI-compatible endpoint base URL")
