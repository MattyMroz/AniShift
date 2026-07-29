"""Provider-local value types for the Edge speech engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from anishift.services.tts.types import AudioFormat, VoiceInfo

__all__ = [
    "EdgeAttempt",
    "EdgeAudioResponse",
    "EdgePatchResult",
    "EdgePatchStatus",
    "EdgeVoiceList",
]


@dataclass(frozen=True, slots=True)
class EdgeAttempt:
    """Resolved inputs for one provider payload submission."""

    text: str
    voice_id: str
    rate: str
    volume: str
    pitch: str
    deadline_s: float


class EdgePatchStatus(StrEnum):
    """Outcome of preparing the installed edge-tts package."""

    READY = "ready"
    PACKAGE_MISSING = "package_missing"
    UNSUPPORTED_VERSION = "unsupported_version"
    UNKNOWN_LAYOUT = "unknown_layout"
    READ_ONLY = "read_only"
    IO_ERROR = "io_error"


@dataclass(frozen=True, slots=True)
class EdgePatchResult:
    """Result of strict edge-tts source validation and patching."""

    status: EdgePatchStatus
    message: str
    detected_version: str
    changed: bool

    @property
    def is_ready(self) -> bool:
        """Whether importing the Edge runtime is safe."""
        return self.status is EdgePatchStatus.READY


@dataclass(frozen=True, slots=True)
class EdgeAudioResponse:
    """Native MP3 bytes returned by one Edge provider attempt."""

    audio: bytes
    format: AudioFormat
    request_time_ms: float


type EdgeVoiceList = tuple[VoiceInfo, ...]
"""Normalized Edge voices returned by the provider."""
