"""Provider-local value types for ElevenBytes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from anishift.services.tts.types import AudioFormat

__all__ = [
    "ElevenBytesEndpointVariant",
    "ElevenBytesResponse",
    "ElevenBytesV3Settings",
]

type ElevenBytesEndpointVariant = Literal["run6", "run7"]
"""Validated ElevenBytes endpoint variant."""


@dataclass(frozen=True, slots=True)
class ElevenBytesV3Settings:
    """Voice controls accepted exclusively by the experimental run7 endpoint."""

    stability: float = 0.5
    similarity_boost: float = 0.75
    style: float = 0.0
    use_speaker_boost: bool = True

    def __post_init__(self) -> None:
        """Reject values outside the proxy form contract."""
        for field_name, value in (
            ("stability", self.stability),
            ("similarity_boost", self.similarity_boost),
            ("style", self.style),
        ):
            if not 0.0 <= value <= 1.0:
                message: str = f"ElevenBytes {field_name} must be between 0 and 1"
                raise ValueError(message)

    def as_form(self) -> dict[str, str]:
        """Return exact run7 form fields."""
        return {
            "similarity_boost": str(self.similarity_boost),
            "stability": str(self.stability),
            "style": str(self.style),
            "use_speaker_boost": str(self.use_speaker_boost).lower(),
        }


@dataclass(frozen=True, slots=True)
class ElevenBytesResponse:
    """Provider-native response accepted by the transport boundary."""

    audio: bytes
    format: AudioFormat
    content_type: str
    request_time_ms: float
