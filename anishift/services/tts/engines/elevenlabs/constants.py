"""Constants for the official ElevenLabs TTS engine."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from anishift.services.tts.types import AudioFormat

__all__ = [
    "ADAPTER_VERSION",
    "DEFAULT_MODEL_ID",
    "DEFAULT_OUTPUT_FORMAT",
    "ELEVENLABS_ENDPOINT_ID",
    "FLASH_MODEL_ID",
    "MAX_TEXT_CHARS",
    "OUTPUT_FORMATS",
    "POLISH_TTS_MODEL_IDS",
    "VOICES_CACHE_TTL_S",
    "ElevenLabsOutputSpec",
]


@dataclass(frozen=True, slots=True)
class ElevenLabsOutputSpec:
    """Real native audio contract represented by one SDK output token."""

    token: str
    format: AudioFormat
    sample_rate: int
    channels: int
    content_type: str


ADAPTER_VERSION: Final[str] = "elevenlabs-sdk-v1"
"""Fingerprint version for the official ElevenLabs adapter."""

DEFAULT_MODEL_ID: Final[str] = "eleven_multilingual_v2"
"""Stable quality-oriented model for Polish narration."""

FLASH_MODEL_ID: Final[str] = "eleven_flash_v2_5"
"""Lower-latency ElevenLabs model supporting Polish."""

POLISH_TTS_MODEL_IDS: Final[tuple[str, ...]] = (
    DEFAULT_MODEL_ID,
    FLASH_MODEL_ID,
    "eleven_v3",
)
"""Current official text-to-speech models that support Polish."""

DEFAULT_OUTPUT_FORMAT: Final[str] = "mp3_44100_128"
"""Default provider-native output format."""

ELEVENLABS_ENDPOINT_ID: Final[str] = "elevenlabs-official-v1"
"""Stable non-secret identity of the official ElevenLabs endpoint."""

MAX_TEXT_CHARS: Final[int] = 5_000
"""Shared safe request limit including the smaller Eleven v3 context."""

VOICES_CACHE_TTL_S: Final[float] = 300.0
"""In-memory voice-list cache lifetime."""

_MP3_FORMATS: Final[tuple[tuple[str, int], ...]] = (
    ("mp3_22050_32", 22_050),
    ("mp3_24000_48", 24_000),
    ("mp3_44100_32", 44_100),
    ("mp3_44100_64", 44_100),
    ("mp3_44100_96", 44_100),
    ("mp3_44100_128", 44_100),
    ("mp3_44100_192", 44_100),
)
"""Supported ElevenLabs MP3 tokens and sample rates."""

_OPUS_FORMATS: Final[tuple[tuple[str, int], ...]] = (
    ("opus_48000_32", 48_000),
    ("opus_48000_64", 48_000),
    ("opus_48000_96", 48_000),
    ("opus_48000_128", 48_000),
    ("opus_48000_192", 48_000),
)
"""Supported ElevenLabs Ogg Opus tokens and sample rates."""

_WAV_FORMATS: Final[tuple[tuple[str, int], ...]] = (
    ("wav_8000", 8_000),
    ("wav_16000", 16_000),
    ("wav_22050", 22_050),
    ("wav_24000", 24_000),
    ("wav_32000", 32_000),
    ("wav_44100", 44_100),
    ("wav_48000", 48_000),
)
"""Supported ElevenLabs WAV tokens and sample rates."""

OUTPUT_FORMATS: Final[MappingProxyType[str, ElevenLabsOutputSpec]] = MappingProxyType(
    {
        **{
            token: ElevenLabsOutputSpec(
                token=token,
                format=AudioFormat.MP3,
                sample_rate=sample_rate,
                channels=1,
                content_type="audio/mpeg",
            )
            for token, sample_rate in _MP3_FORMATS
        },
        **{
            token: ElevenLabsOutputSpec(
                token=token,
                format=AudioFormat.OPUS,
                sample_rate=sample_rate,
                channels=1,
                content_type="audio/ogg",
            )
            for token, sample_rate in _OPUS_FORMATS
        },
        **{
            token: ElevenLabsOutputSpec(
                token=token,
                format=AudioFormat.WAV,
                sample_rate=sample_rate,
                channels=1,
                content_type="audio/wav",
            )
            for token, sample_rate in _WAV_FORMATS
        },
    },
)
"""Allowlisted SDK output tokens with their real native audio contract."""
