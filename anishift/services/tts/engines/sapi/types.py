"""Provider-local value types for the SAPI engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from anishift.services.tts.types import ProcessArchitecture

__all__ = [
    "SapiHost",
    "SapiSynthesisResult",
    "SapiVoiceProfile",
    "SapiVoiceRecord",
]


@dataclass(frozen=True, slots=True)
class SapiVoiceProfile:
    """One selectable system voice and its native user-facing scales."""

    alias: str
    label: str
    voice_name: str
    architecture: ProcessArchitecture
    default_native_rate: int | float
    default_native_volume: int | float
    uses_wpm_rate: bool
    uses_fractional_volume: bool

    @property
    def resolved_voice_id(self) -> str:
        """Return a stable identity that includes process architecture."""
        return f"{self.voice_name}@{self.architecture.value}"


@dataclass(frozen=True, slots=True)
class SapiHost:
    """Resolved PowerShell host for one Windows process architecture."""

    architecture: ProcessArchitecture
    executable: Path


@dataclass(frozen=True, slots=True)
class SapiVoiceRecord:
    """One voice enumerated without invoking synthesis."""

    id: str
    name: str
    architecture: ProcessArchitecture


@dataclass(frozen=True, slots=True)
class SapiSynthesisResult:
    """Successful response from one persistent worker request."""

    request_id: str
    output_path: Path
    request_time_ms: float
