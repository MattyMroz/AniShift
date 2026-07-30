"""Typed failures raised by the audio domain."""

from __future__ import annotations

from anishift.errors import AniShiftError, FatalError

__all__ = [
    "AudioCancelledError",
    "AudioConfigError",
    "AudioDecodeError",
    "AudioError",
    "AudioLayoutError",
    "AudioProbeError",
    "AudioProcessError",
    "AudioResumeError",
]


class AudioError(AniShiftError):
    """Base error for narration, mixing, and output operations."""


class AudioConfigError(AudioError, FatalError):
    """Audio configuration cannot produce a valid render."""


class AudioProbeError(AudioError, FatalError):
    """Audio metadata cannot be read or trusted."""


class AudioDecodeError(AudioError, FatalError):
    """An audio file fails a complete decode check."""


class AudioLayoutError(AudioError, FatalError):
    """A channel layout has no explicit supported mapping."""


class AudioProcessError(AudioError, FatalError):
    """An FFmpeg-family subprocess failed."""


class AudioCancelledError(AudioError, FatalError):
    """An audio operation was cancelled before commit."""


class AudioResumeError(AudioError, FatalError):
    """Audio-owned resume metadata is invalid or inaccessible."""
