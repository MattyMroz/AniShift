"""Application settings loaded from environment / ``.env`` file."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Final, Self

from dotenv import dotenv_values
from pydantic import Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    NoDecode,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from pydantic_settings.sources.utils import parse_env_vars

from anishift.services.llm.palantir_token import (
    PALANTIR_TOKEN_COMPAT_ENV_VAR,
    PALANTIR_TOKEN_ENV_VAR,
    resolve_palantir_token,
)

__all__ = ["API_KEY_LIST_SEPARATOR", "Settings"]

# ── Constants ────────────────────────────────────────────────────────────────

API_KEY_LIST_SEPARATOR: Final[str] = ","
"""Separator between the keys of one LLM provider in a single environment value."""

type ApiKeyList = Annotated[tuple[str, ...], NoDecode]
"""Ordered LLM provider keys read verbatim from one comma-separated environment value."""


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
    """API keys and env-driven settings — loaded from env vars and ``.env``."""

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

    # LLM providers: each takes any number of keys, in the order they are tried
    anthropic_api_keys: ApiKeyList = Field(default=(), description="Anthropic API keys", repr=False)
    gemini_api_keys: ApiKeyList = Field(default=(), description="Google Gemini API keys", repr=False)
    openai_api_keys: ApiKeyList = Field(default=(), description="OpenAI API keys", repr=False)
    deepseek_api_keys: ApiKeyList = Field(default=(), description="DeepSeek API keys", repr=False)
    openrouter_api_keys: ApiKeyList = Field(default=(), description="OpenRouter API keys", repr=False)
    openai_compatible_api_keys: ApiKeyList = Field(
        default=(),
        description="OpenAI-compatible endpoint keys",
        repr=False,
    )
    openai_compatible_base_url: str = Field(
        default="",
        description="OpenAI-compatible endpoint base URL",
        repr=False,
    )
    palantir_token: str = Field(default="", description="Palantir Foundry token", repr=False)
    palantir_secondary_token: str = Field(
        default="",
        description="Second Palantir account token",
        repr=False,
    )
    # The compatibility name carries no ``ANISHIFT_`` prefix, so it needs an
    # explicit alias. It is a raw input of the precedence rule, not a setting.
    palantir_token_compat: str = Field(
        default="",
        description="Compatibility source of the Palantir Foundry token",
        repr=False,
        exclude=True,
        validation_alias=PALANTIR_TOKEN_COMPAT_ENV_VAR,
    )

    # Torrents
    qbittorrent_url: str = Field(default="http://127.0.0.1:8080", description="qBittorrent Web UI address")
    qbittorrent_username: str = Field(default="", description="qBittorrent Web UI user name", repr=False)
    qbittorrent_password: str = Field(default="", description="qBittorrent Web UI password", repr=False)

    # Subscriptions
    subscription_shadow: bool = Field(default=False, description="Record subscription proposals without admitting")

    # Workspace
    workspace_root: str = Field(default="", description="Workspace root override", repr=False)

    @field_validator(
        "anthropic_api_keys",
        "gemini_api_keys",
        "openai_api_keys",
        "deepseek_api_keys",
        "openrouter_api_keys",
        "openai_compatible_api_keys",
        mode="before",
    )
    @classmethod
    def _split_api_keys(cls, value: object) -> object:
        """Split one comma-separated value into unique non-empty keys in their written order."""
        if not isinstance(value, str):
            return value
        keys: list[str] = [key.strip() for key in value.split(API_KEY_LIST_SEPARATOR)]
        return tuple(dict.fromkeys(key for key in keys if key))

    @model_validator(mode="after")
    def _resolve_palantir_token(self) -> Self:
        """Apply the single token precedence rule owned by the LLM adapter."""
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
