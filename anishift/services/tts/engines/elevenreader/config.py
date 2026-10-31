"""Validated configuration for the ElevenReader engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.installed import find_installed
from anishift.services.tts.errors import TtsConfigError, TtsVoiceError

from .constants import CHROME_LOCATIONS, CHROME_STEM, PROVIDER_MODEL_ID, VOICES
from .types import ElevenReaderVoice

if TYPE_CHECKING:
    from anishift.services.tts.config import TtsConfig

__all__ = ["ElevenReaderConfig", "find_chrome", "profile_dir", "resolve_voice", "session_file"]

# ── Constants ─────────────────────────────────────────────────────────────────

_PROFILE_DIR_NAME: Final[str] = "chrome-profile"
"""Chrome user data directory inside the ElevenReader root."""

_SESSION_FILE_NAME: Final[str] = "session.json"
"""Last session check result inside the ElevenReader root."""


@dataclass(frozen=True, slots=True)
class ElevenReaderConfig:
    """ElevenReader settings resolved from the shared TTS configuration."""

    voice: ElevenReaderVoice
    profile_root: Path

    @classmethod
    def from_tts_config(cls, config: TtsConfig) -> ElevenReaderConfig:
        """Resolve the voice and profile, refusing any model, concurrency or option ElevenReader cannot honour."""
        if config.provider_model_id.strip().casefold() != PROVIDER_MODEL_ID:
            _raise_config_error(f"ElevenReader reads only with {PROVIDER_MODEL_ID}", field_name="provider_model_id")
        if config.max_concurrency != 1:
            _raise_config_error("ElevenReader records one document at a time", field_name="max_concurrency")
        if config.engine_options:
            _raise_config_error("ElevenReader accepts no engine options", field_name="engine_options")
        if config.elevenreader_profile_root is None:
            _raise_config_error(
                "ElevenReader needs a browser profile directory", field_name="elevenreader_profile_root"
            )
        return cls(voice=resolve_voice(config.voice_id), profile_root=config.elevenreader_profile_root)


def profile_dir(root: Path) -> Path:
    """Return the Chrome user data directory under the ElevenReader *root*."""
    return root / _PROFILE_DIR_NAME


def session_file(root: Path) -> Path:
    """Return the session check record under the ElevenReader *root*."""
    return root / _SESSION_FILE_NAME


def find_chrome() -> Path | None:
    """Return the installed Google Chrome executable, or None."""
    return find_installed(CHROME_LOCATIONS, CHROME_STEM)


def resolve_voice(alias_or_id: str) -> ElevenReaderVoice:
    """Return the offered voice named by alias (any case) or provider voice id."""
    wanted: str = alias_or_id.strip()
    by_alias: ElevenReaderVoice | None = VOICES.get(wanted.casefold())
    if by_alias is not None:
        return by_alias
    for voice in VOICES.values():
        if voice.voice_id == wanted:
            return voice
    offered: str = ", ".join(VOICES)
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_VOICE_INVALID,
        message=f"Unknown ElevenReader voice. Offered: {offered}",
        suggestion="Wybierz głos Piotr Fronczewski albo Adam w Ustawienia → Lektor.",
        details={"voice_id": wanted},
    )
    raise TtsVoiceError(context=context)


def _raise_config_error(message: str, *, field_name: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CONFIG_INVALID,
        message=message,
        suggestion="Select ElevenReader with model eleven_v4, one synthesis at a time and the application profile.",
        details={"field": field_name},
    )
    raise TtsConfigError(context=context)
