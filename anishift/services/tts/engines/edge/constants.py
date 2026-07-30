"""Constants for the Microsoft Edge speech engine."""

from __future__ import annotations

from typing import Final

__all__ = [
    "ADAPTER_VERSION",
    "DEFAULT_PITCH",
    "DEFAULT_RATE",
    "DEFAULT_VOLUME",
    "EDGE_PROVIDER_MODEL_ID",
    "MAREK_VOICE_ID",
    "MAX_TEXT_BYTES",
    "OUTPUT_FORMAT",
    "SUPPORTED_EDGE_TTS_VERSION",
    "ZOFIA_VOICE_ID",
]

SUPPORTED_EDGE_TTS_VERSION: Final[str] = "7.2.8"
"""Exact edge-tts release supported by the source quality patch."""

ADAPTER_VERSION: Final[str] = "edge-v1"
"""Version of AniShift's Edge request and output contract."""

EDGE_PROVIDER_MODEL_ID: Final[str] = "edge-default"
"""Stable provider model identity used by Edge synthesis profiles."""

OUTPUT_FORMAT: Final[str] = "audio-24khz-96kbitrate-mono-mp3"
"""Required provider-native Edge output format."""

MAX_TEXT_BYTES: Final[int] = 4096
"""Maximum UTF-8 payload size submitted in one Edge request."""

DEFAULT_RATE: Final[str] = "+40%"
"""Default native Edge speech-rate adjustment."""

DEFAULT_VOLUME: Final[str] = "+0%"
"""Default native Edge volume adjustment."""

DEFAULT_PITCH: Final[str] = "+0Hz"
"""Default native Edge pitch adjustment."""

MAREK_VOICE_ID: Final[str] = "pl-PL-MarekNeural"
"""Provider identifier of the Polish Marek neural voice."""

ZOFIA_VOICE_ID: Final[str] = "pl-PL-ZofiaNeural"
"""Provider identifier of the Polish Zofia neural voice."""
