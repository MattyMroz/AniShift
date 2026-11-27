"""Validated configuration for the ElevenReader engine and the files under its profile root."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from .constants import CHROME_LOCATIONS, CHROME_STEM, VOICES
from .host import UNKNOWN_VOICE_HINT, ErrorCode, ErrorContext, TtsVoiceError, find_installed
from .types import ElevenReaderVoice

if TYPE_CHECKING:
    from pathlib import Path

    from .types import Redo

__all__ = ["ElevenReaderConfig", "find_chrome", "lock_file", "profile_dir", "resolve_voice", "session_file"]

# ── Constants ─────────────────────────────────────────────────────────────────

_PROFILE_DIR_NAME: Final[str] = "chrome-profile"
"""Chrome user data directory inside the ElevenReader root."""

_SESSION_FILE_NAME: Final[str] = "session.json"
"""Last session check result inside the ElevenReader root."""

_LOCK_FILE_NAME: Final[str] = "chrome.lock"
"""Lock file guarding the profile against a second browser of this program, inside the ElevenReader root."""

_VOICE_ID_LENGTH: Final[int] = 20
"""Length of an ElevenLabs voice id; any such id from the voice library is accepted as a voice."""


@dataclass(frozen=True, slots=True)
class ElevenReaderConfig:
    """Voice, profile root and redo mode of one ElevenReader engine."""

    voice: ElevenReaderVoice
    profile_root: Path
    redo: Redo


def profile_dir(root: Path) -> Path:
    """Return the Chrome user data directory under the ElevenReader *root*."""
    return root / _PROFILE_DIR_NAME


def session_file(root: Path) -> Path:
    """Return the session check record under the ElevenReader *root*."""
    return root / _SESSION_FILE_NAME


def lock_file(root: Path) -> Path:
    """Return the lock file held while this program uses the Chrome profile under *root*."""
    return root / _LOCK_FILE_NAME


def find_chrome() -> Path | None:
    """Return the Google Chrome executable from a standard install location, then from ``PATH``, or None."""
    return find_installed(CHROME_LOCATIONS, CHROME_STEM)


def resolve_voice(alias_or_id: str) -> ElevenReaderVoice:
    """Return the offered voice named by alias (any case) or id, or the voice library voice with that id."""
    wanted: str = alias_or_id.strip()
    by_alias: ElevenReaderVoice | None = VOICES.get(wanted.casefold())
    if by_alias is not None:
        return by_alias
    for voice in VOICES.values():
        if voice.voice_id == wanted:
            return voice
    if len(wanted) == _VOICE_ID_LENGTH and wanted.isalnum() and wanted.isascii():
        return ElevenReaderVoice(alias=wanted, label=wanted, voice_id=wanted)
    offered: str = ", ".join(VOICES)
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_VOICE_INVALID,
        message=f"Unknown ElevenReader voice. Offered: {offered}",
        suggestion=UNKNOWN_VOICE_HINT.format(offered=offered),
        details={"voice_id": wanted},
    )
    raise TtsVoiceError(context=context)
