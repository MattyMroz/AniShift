"""Validated configuration for narration, mixing, and encoding."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Final

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.audio.errors import AudioConfigError
from anishift.services.audio.types import AudioCodecProfile, TimelinePolicy

__all__ = ["AudioConfig"]

# ── Constants ────────────────────────────────────────────────────────────────

_BITRATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"[1-9][0-9]*[kKmM]\Z")
"""Accepted FFmpeg bitrate syntax at the domain boundary."""

_LOSSY_PROFILES: Final[frozenset[AudioCodecProfile]] = frozenset(
    {
        AudioCodecProfile.AAC,
        AudioCodecProfile.EAC3,
        AudioCodecProfile.MP3,
        AudioCodecProfile.OPUS,
    },
)
"""Profiles for which a target bitrate is meaningful."""

_PCM_S16LE_WIDTH: Final[int] = 2
"""Byte width of the narrator's signed 16-bit PCM samples."""

_MAX_FLAC_COMPRESSION: Final[int] = 12
"""Maximum FLAC compression level accepted by FFmpeg."""


@dataclass(frozen=True, slots=True)
class AudioConfig:
    """Audio-only rendering settings independent from TTS providers."""

    codec_profile: AudioCodecProfile = AudioCodecProfile.EAC3
    bitrate: str | None = None
    narrator_sample_rate: int = 48_000
    narrator_sample_width: int = 2
    narrator_channels: int = 1
    narrator_mix_base_gain_db: float = 7.0
    voice_mix_offset_db: float = 0.0
    original_gain_db: float = 0.0
    timeline_policy: TimelinePolicy = TimelinePolicy.SERIALIZE
    operation_timeout_s: float = 30.0
    shutdown_grace_s: float = 5.0
    flac_compression_level: int = 5

    def __post_init__(self) -> None:
        """Reject settings unsupported by the v1 audio contract."""
        if type(self.codec_profile) is not AudioCodecProfile:
            _raise_config("codec_profile must use AudioCodecProfile")
        if type(self.timeline_policy) is not TimelinePolicy or self.timeline_policy is not TimelinePolicy.SERIALIZE:
            _raise_config("timeline_policy must be serialize")
        if self.narrator_sample_rate <= 0:
            _raise_config("narrator_sample_rate must be positive")
        if self.narrator_sample_width != _PCM_S16LE_WIDTH:
            _raise_config("narrator_sample_width must be 2 for PCM S16LE")
        if self.narrator_channels != 1:
            _raise_config("narrator_channels must be mono in v1")
        if not math.isfinite(self.operation_timeout_s) or self.operation_timeout_s <= 0:
            _raise_config("operation_timeout_s must be finite and positive")
        if not math.isfinite(self.shutdown_grace_s) or self.shutdown_grace_s <= 0:
            _raise_config("shutdown_grace_s must be finite and positive")
        if any(
            not math.isfinite(value)
            for value in (
                self.narrator_mix_base_gain_db,
                self.voice_mix_offset_db,
                self.original_gain_db,
            )
        ):
            _raise_config("audio gains must be finite")
        if self.bitrate is not None and self.codec_profile not in _LOSSY_PROFILES:
            _raise_config("bitrate is supported only for lossy output profiles")
        if self.bitrate is not None and _BITRATE_PATTERN.fullmatch(self.bitrate) is None:
            _raise_config("bitrate must use FFmpeg syntax such as 192k")
        if not 0 <= self.flac_compression_level <= _MAX_FLAC_COMPRESSION:
            _raise_config("flac_compression_level must be between 0 and 12")


def _raise_config(message: str) -> None:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.AUDIO_FAILED,
        message=message,
        suggestion="Choose supported values in the audio settings.",
    )
    raise AudioConfigError(context=context)
