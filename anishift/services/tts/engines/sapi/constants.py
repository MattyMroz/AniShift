"""Constants and built-in voice profiles for the SAPI engine."""

from __future__ import annotations

from types import MappingProxyType
from typing import Final

from anishift.services.tts.types import ProcessArchitecture

from .types import SapiVoiceProfile

__all__ = [
    "ADAPTER_VERSION",
    "MAX_IPC_MESSAGE_BYTES",
    "OUTPUT_ID",
    "PROTOCOL_VERSION",
    "SAPI_PROFILES",
    "SAPI_RATE_MAX",
    "SAPI_RATE_MIN",
    "WAV_ENVELOPE_BYTES",
    "WAV_HEADER_BYTES",
]

PROTOCOL_VERSION: Final[int] = 1
"""JSON Lines protocol version shared with the PowerShell worker."""

ADAPTER_VERSION: Final[str] = "sapi-worker-v1"
"""Stable adapter version included in synthesis fingerprints."""

OUTPUT_ID: Final[str] = "wav-pcm"
"""Provider-native PCM WAV output identity."""

MAX_IPC_MESSAGE_BYTES: Final[int] = 256 * 1024
"""Maximum encoded size of one worker request or response."""

WAV_HEADER_BYTES: Final[int] = 44
"""Minimum canonical PCM WAV header size before any audio samples."""

WAV_ENVELOPE_BYTES: Final[int] = 12
"""Bytes needed to identify the RIFF/WAVE container envelope."""

SAPI_RATE_MIN: Final[int] = -10
"""Minimum native SAPI rate."""

SAPI_RATE_MAX: Final[int] = 10
"""Maximum native SAPI rate."""

SAPI_PROFILES: Final[MappingProxyType[str, SapiVoiceProfile]] = MappingProxyType(
    {
        "agnieszka": SapiVoiceProfile(
            alias="agnieszka",
            label="Agnieszka — Ivona",
            voice_name="IVONA 2 Agnieszka - polski głos żeński [22kHz]",
            architecture=ProcessArchitecture.X86,
            default_native_rate=5,
            default_native_volume=65,
            uses_wpm_rate=False,
            uses_fractional_volume=False,
        ),
        "zosia": SapiVoiceProfile(
            alias="zosia",
            label="Zosia — Harpo",
            voice_name="Vocalizer Expressive Zosia Harpo 22kHz",
            architecture=ProcessArchitecture.X64,
            default_native_rate=200,
            default_native_volume=0.7,
            uses_wpm_rate=True,
            uses_fractional_volume=True,
        ),
    },
)
"""Built-in SAPI voices with their exact architecture-specific names."""
