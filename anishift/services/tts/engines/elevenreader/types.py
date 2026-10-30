"""Provider-local value types for ElevenReader."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

__all__ = [
    "AccountCleanup",
    "AccountSettings",
    "AlignmentChunk",
    "ElevenReaderVoice",
    "LibraryState",
    "PlayerState",
    "SessionRecord",
    "SignInOutcome",
    "UploadedRead",
]


@dataclass(frozen=True, slots=True)
class ElevenReaderVoice:
    """One selectable ElevenReader voice."""

    alias: str
    label: str
    voice_id: str


class LibraryState(StrEnum):
    """What the library page showed."""

    READY = "ready"
    SIGNED_OUT = "signed_out"
    UNAVAILABLE = "unavailable"


class SignInOutcome(StrEnum):
    """Result of the visible sign-in action."""

    SIGNED_IN = "signed_in"
    SIGNED_OUT = "signed_out"
    BUSY = "busy"
    NO_CHROME = "no_chrome"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """Last observed sign-in state, without any secret."""

    signed_in: bool
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class AccountSettings:
    """Default voice and playback speed of the account; None marks a field the account did not report."""

    voice_id: str | None
    speed: float | None


@dataclass(slots=True)
class AccountCleanup:
    """Account changes still to undo: settings to restore and an uploaded read to delete."""

    restore: AccountSettings | None = None
    read_id: str | None = field(default=None, repr=False)

    @property
    def pending(self) -> tuple[str, ...]:
        """Return the kinds of steps still to run, in execution order."""
        kinds: list[str] = []
        if self.restore is not None:
            kinds.append("restore_settings")
        if self.read_id is not None:
            kinds.append("delete_read")
        return tuple(kinds)


@dataclass(frozen=True, slots=True)
class UploadedRead:
    """Library entry created by one upload; id and token stay in memory only."""

    read_id: str = field(repr=False)
    char_count: int
    token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class PlayerState:
    """Player position and document length, both in characters."""

    value: float
    length: float


@dataclass(frozen=True, slots=True)
class AlignmentChunk:
    """Characters of one audio chunk with times relative to the chunk start, placed at its recording offset."""

    offset_ms: float
    chars: tuple[str, ...]
    starts_ms: tuple[float, ...]
    durations_ms: tuple[float, ...]
