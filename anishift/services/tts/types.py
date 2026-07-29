"""Provider-neutral value types for speech synthesis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from anishift.errors import ErrorContext

__all__ = [
    "AudioFormat",
    "AvailabilityProbeKind",
    "AvailabilitySource",
    "AvailabilityStatus",
    "ClipExpectation",
    "ClipValidation",
    "EngineAvailability",
    "EngineCapabilities",
    "EngineClipResult",
    "EngineLocality",
    "EngineOptionValue",
    "EngineOptions",
    "ProcessArchitecture",
    "SpeechBatch",
    "SpeechBatchResult",
    "SpeechBatchStats",
    "SpeechBatchStatus",
    "SpeechClip",
    "SpeechPreparationStatus",
    "SpeechRequest",
    "SynthesisRequest",
    "SynthesisStatus",
    "SynthesizedRequest",
    "VoiceInfo",
]

type EngineOptionValue = str | int | float | bool | None
"""Scalar value accepted by provider-specific synthesis options."""

type EngineOptions = Mapping[str, EngineOptionValue]
"""Read-only provider-specific synthesis options."""


class AudioFormat(StrEnum):
    """Audio formats that a TTS provider may return natively."""

    AAC = "aac"
    FLAC = "flac"
    MP3 = "mp3"
    OGG = "ogg"
    OPUS = "opus"
    WAV = "wav"


class EngineLocality(StrEnum):
    """Location where an engine performs synthesis."""

    REMOTE = "remote"
    SYSTEM = "system"


class AvailabilityProbeKind(StrEnum):
    """Most detailed availability probe supported by an engine."""

    CONFIG = "config"
    LOCAL = "local"
    REMOTE = "remote"


class AvailabilitySource(StrEnum):
    """Source of one dynamic availability result."""

    CACHED = "cached"
    CONFIG = "config"
    LIVE = "live"
    LOCAL = "local"


class AvailabilityStatus(StrEnum):
    """Detailed reason why an engine is or is not usable."""

    READY = "ready"
    MISSING_KEY = "missing_key"
    MISSING_VOICE = "missing_voice"
    MISSING_BINARY = "missing_binary"
    OFFLINE = "offline"
    SERVICE_UNAVAILABLE = "service_unavailable"
    UNSUPPORTED_PLATFORM = "unsupported_platform"


class ProcessArchitecture(StrEnum):
    """Process architecture required by a system voice."""

    X64 = "x64"
    X86 = "x86"


class SpeechPreparationStatus(StrEnum):
    """Outcome of validating and preparing one neutral request."""

    READY = "ready"
    SKIPPED_NON_SPEECH = "skipped_non_speech"
    UNSUPPORTED_INPUT = "unsupported_input"
    INVALID_CONTRACT = "invalid_contract"


class SynthesisStatus(StrEnum):
    """Final synthesis state of one speech request."""

    SYNTHESIZED = "synthesized"
    RESUME_HIT = "resume_hit"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SpeechBatchStatus(StrEnum):
    """Aggregate state of one caller-owned speech batch."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class SpeechRequest:
    """One ordered, provider-neutral text request."""

    request_id: str
    text: str
    request_rank: int


@dataclass(frozen=True, slots=True)
class SpeechBatch:
    """One caller-owned group of neutral speech requests."""

    scope_id: str
    batch_rank: int
    requests: tuple[SpeechRequest, ...]


@dataclass(frozen=True, slots=True)
class ClipExpectation:
    """Expected provider-native container for a clip."""

    format: AudioFormat

    def __post_init__(self) -> None:
        """Reject raw strings crossing the clip-validation boundary."""
        if type(self.format) is not AudioFormat:
            message: str = "Clip expectation format must use AudioFormat"
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class ClipValidation:
    """Trusted technical metadata returned by a full decode validator."""

    format: AudioFormat
    sample_rate: int
    channels: int
    duration_ms: int

    def __post_init__(self) -> None:
        """Reject unusable metadata before it enters resume state."""
        if type(self.format) is not AudioFormat:
            message: str = "Validated clip format must use AudioFormat"
            raise ValueError(message)
        if any(type(value) is not int or value <= 0 for value in (self.sample_rate, self.channels, self.duration_ms)):
            message = "Validated TTS clip metadata must be positive integers"
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class EngineCapabilities:
    """Static synthesis capabilities declared by an engine."""

    locality: EngineLocality
    native_output_formats: tuple[AudioFormat, ...]
    supports_concurrency: bool
    supports_native_rate: bool
    supports_native_volume: bool
    supports_pitch: bool
    supports_voice_settings: bool
    requires_api_key: bool
    min_text_chars: int
    max_text_chars: int | None
    max_text_bytes: int | None
    availability_probe: AvailabilityProbeKind


@dataclass(frozen=True, slots=True)
class VoiceInfo:
    """Metadata describing one selectable engine voice."""

    id: str
    label: str
    engine_id: str
    language: str
    gender: str = ""
    architecture: ProcessArchitecture | None = None
    experimental: bool = False


@dataclass(frozen=True, slots=True)
class EngineAvailability:
    """Dynamic availability state reported by an engine."""

    status: AvailabilityStatus
    message: str
    checked_at: datetime
    source: AvailabilitySource
    voices: tuple[VoiceInfo, ...] = ()


@dataclass(frozen=True, slots=True)
class SynthesisRequest:
    """Validated request passed from the TTS scheduler to one engine."""

    request_id: str
    text: str
    voice_id: str
    provider_model_id: str
    native_rate: str | float | None
    native_volume: str | float | None
    native_pitch: str | float | None
    options: EngineOptions
    destination: Path
    deadline_s: float


@dataclass(frozen=True, slots=True)
class EngineClipResult:
    """Validated output produced by one engine attempt."""

    request_id: str
    path: Path
    format: AudioFormat
    sample_rate: int
    channels: int
    duration_ms: int
    engine_id: str
    provider_model_id: str
    voice_id: str
    request_time_ms: float


@dataclass(frozen=True, slots=True)
class SpeechClip:
    """Committed TTS result enriched with scheduler and resume metadata."""

    request_id: str
    path: Path
    format: AudioFormat
    sample_rate: int
    channels: int
    duration_ms: int
    engine_id: str
    provider_model_id: str
    voice_id: str
    attempts: int
    request_time_ms: float
    from_resume: bool


@dataclass(frozen=True, slots=True)
class SynthesizedRequest:
    """Result of one request within a speech batch."""

    request: SpeechRequest
    status: SynthesisStatus
    speech_clip: SpeechClip | None
    error_code: str
    retries: int


@dataclass(frozen=True, slots=True)
class SpeechBatchStats:
    """Provider and request counters for one speech batch."""

    total_requests: int
    synthesized: int
    resume_hits: int
    skipped: int
    failed: int
    provider_calls: int
    retries: int
    synthesis_time_ms: float
    engine_id: str
    provider_model_id: str
    voice_id: str


@dataclass(frozen=True, slots=True)
class SpeechBatchResult:
    """Complete TTS-domain result for exactly one speech batch."""

    scope_id: str
    status: SpeechBatchStatus
    requests: tuple[SynthesizedRequest, ...]
    stats: SpeechBatchStats
    failure: ErrorContext | None
