"""Application settings loaded from environment / ``.env`` file.

Type-safe API-key configuration via pydantic-settings. Every field maps to an
``ANISHIFT_``-prefixed env var (or the same key in ``.env``). All keys are
optional — a missing key only disables the engine that needs it, not the app.

The single exception is the legacy, unprefixed ``FOUNDRY_API_TOKEN``, read as a
compatibility source of the Palantir token. Which of the two variables wins is
decided by ``resolve_palantir_token`` in the LLM adapter, so the rule has one
implementation for both this class and a plain process environment.

Usage:
    >>> from anishift.config.settings import Settings
    >>> s = Settings()
    >>> bool(s.deepl_api_key)
    False
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Self

from dotenv import dotenv_values
from pydantic import Field, model_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from pydantic_settings.sources.utils import parse_env_vars

from anishift.services.llm.engines.palantir.auth import (
    PALANTIR_TOKEN_COMPAT_ENV_VAR,
    PALANTIR_TOKEN_ENV_VAR,
    resolve_palantir_token,
)

__all__ = ["Settings"]


class _LiteralDotEnvSettingsSource(DotEnvSettingsSource):
    """Read secret values literally instead of expanding ``${NAME}``."""

    @staticmethod
    def _static_read_env_file(
        file_path: Path,
        *,
        encoding: str | None = None,
        case_sensitive: bool = False,
        ignore_empty: bool = False,
        parse_none_str: str | None = None,
    ) -> Mapping[str, str | None]:
        file_vars: dict[str, str | None] = dict(
            dotenv_values(
                file_path,
                encoding=encoding or "utf8",
                interpolate=False,
            ),
        )
        return parse_env_vars(
            file_vars,
            case_sensitive,
            ignore_empty,
            parse_none_str,
        )


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
        palantir_token: Palantir Foundry token (LLM provider ``palantir``), read
            from ``ANISHIFT_PALANTIR_TOKEN``. When that value is absent or
            blank, the unprefixed ``FOUNDRY_API_TOKEN`` fills it for
            compatibility with an older setup; a writer always targets the
            canonical name.
        palantir_token_compat: Raw compatibility value of the token, folded into
            ``palantir_token`` and cleared during validation. Never read it
            directly.
        workspace_root: Optional workspace path override.
    """

    model_config = SettingsConfigDict(
        env_prefix="ANISHIFT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Translation
    deepl_api_key: str = Field(default="", description="DeepL API key", repr=False)

    # TTS
    elevenlabs_api_key: str = Field(
        default="",
        description="Official ElevenLabs API key",
        repr=False,
    )

    # LLM providers
    anthropic_api_key: str = Field(default="", description="Anthropic API key", repr=False)
    gemini_api_key: str = Field(default="", description="Google Gemini API key", repr=False)
    openai_api_key: str = Field(default="", description="OpenAI API key", repr=False)
    deepseek_api_key: str = Field(default="", description="DeepSeek API key", repr=False)
    openrouter_api_key: str = Field(default="", description="OpenRouter API key", repr=False)
    openai_compatible_api_key: str = Field(
        default="",
        description="OpenAI-compatible endpoint key",
        repr=False,
    )
    openai_compatible_base_url: str = Field(
        default="",
        description="OpenAI-compatible endpoint base URL",
        repr=False,
    )
    palantir_token: str = Field(default="", description="Palantir Foundry token", repr=False)
    # The compatibility name carries no ``ANISHIFT_`` prefix, so it needs an
    # explicit alias. It is a raw input of the precedence rule, not a setting.
    palantir_token_compat: str = Field(
        default="",
        description="Compatibility source of the Palantir Foundry token",
        repr=False,
        exclude=True,
        validation_alias=PALANTIR_TOKEN_COMPAT_ENV_VAR,
    )

    # Workspace
    workspace_root: str = Field(default="", description="Workspace root override", repr=False)

    @model_validator(mode="after")
    def _resolve_palantir_token(self) -> Self:
        """Apply the single token precedence rule owned by the LLM adapter.

        Both variables are collected by the normal source chain, so a value may
        come from the environment or from ``.env``. Choosing between them is
        delegated to ``resolve_palantir_token`` instead of being re-implemented
        here, which is what keeps a blank canonical value from resolving
        differently in the two call paths.

        Returns:
            The settings instance with ``palantir_token`` holding the resolved
            token and the compatibility field cleared.
        """
        self.palantir_token = resolve_palantir_token(
            {
                PALANTIR_TOKEN_ENV_VAR: self.palantir_token,
                PALANTIR_TOKEN_COMPAT_ENV_VAR: self.palantir_token_compat,
            },
        )
        self.palantir_token_compat = ""
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Replace only dotenv interpolation while preserving source priority."""
        if not isinstance(dotenv_settings, DotEnvSettingsSource):
            return init_settings, env_settings, dotenv_settings, file_secret_settings
        literal_dotenv = _LiteralDotEnvSettingsSource(
            settings_cls,
            env_file=dotenv_settings.env_file,
            env_file_encoding=dotenv_settings.env_file_encoding,
            dotenv_filtering=dotenv_settings.dotenv_filtering,
            case_sensitive=dotenv_settings.case_sensitive,
            env_prefix=dotenv_settings.env_prefix,
            env_prefix_target=dotenv_settings.env_prefix_target,
            env_nested_delimiter=dotenv_settings.env_nested_delimiter,
            env_nested_max_split=dotenv_settings.env_nested_max_split,
            env_ignore_empty=dotenv_settings.env_ignore_empty,
            env_parse_none_str=dotenv_settings.env_parse_none_str,
            env_parse_enums=dotenv_settings.env_parse_enums,
        )
        return init_settings, env_settings, literal_dotenv, file_secret_settings
