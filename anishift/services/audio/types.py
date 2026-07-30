"""Provider-neutral value types for narration and audio output."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

__all__ = [
    "AudioCodecProfile",
    "AudioFormat",
    "AudioProbe",
    "AudioRenderRequest",
    "AudioRenderResult",
    "AudioRenderStatus",
    "ChannelPlan",
    "NormalizedClip",
    "PcmStorage",
    "PlacementReason",
    "TimedClip",
    "TimelinePlacement",
    "TimelinePlan",
    "TimelinePolicy",
]


class AudioFormat(StrEnum):
    """Audio formats accepted at the audio-domain boundary."""

    AAC = "aac"
    EAC3 = "eac3"
    FLAC = "flac"
    MP3 = "mp3"
    OGG = "ogg"
    OPUS = "opus"
    WAV = "wav"


class AudioCodecProfile(StrEnum):
    """Final sidecar profiles selectable by the user."""

    AAC = "aac"
    EAC3 = "eac3"
    FLAC = "flac"
    MP3 = "mp3"
    OPUS = "opus"
    WAV = "wav"


class TimelinePolicy(StrEnum):
    """Implemented policies for placing normalized speech clips."""

    SERIALIZE = "serialize"


class PlacementReason(StrEnum):
    """Reason for a clip's actual timeline position."""

    ON_TIME = "on_time"
    SERIALIZED_OVERLAP = "serialized_overlap"


class PcmStorage(StrEnum):
    """Storage representation used by a normalized PCM clip."""

    RAW = "raw"
    WAV = "wav"


class AudioRenderStatus(StrEnum):
    """Aggregate result of one audio render."""

    COMPLETED = "completed"
    RESUME_HIT = "resume_hit"
    SKIPPED_NO_SPOKEN = "skipped_no_spoken"


@dataclass(frozen=True, slots=True)
class AudioProbe:
    """Trusted metadata for one probed audio stream."""

    path: Path
    codec_name: str
    format_name: str
    sample_rate: int
    channels: int
    channel_layout: str
    duration_ms: int
    bit_rate: int | None


@dataclass(frozen=True, slots=True)
class TimedClip:
    """One synthesized clip joined by the pipeline with subtitle timing."""

    request_id: str
    start_ms: int
    end_ms: int
    source_order: int
    clip_path: Path
    clip_format: AudioFormat
    sample_rate: int
    channels: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class NormalizedClip:
    """One mono PCM clip ready for timeline assembly."""

    timed_clip: TimedClip
    path: Path
    sample_rate: int
    sample_width: int
    channels: int
    frame_count: int
    storage: PcmStorage
    from_fast_path: bool

    @property
    def duration_ms(self) -> int:
        """Return duration derived from exact PCM frame count."""
        return (self.frame_count * 1000 + self.sample_rate // 2) // self.sample_rate


@dataclass(frozen=True, slots=True)
class TimelinePlacement:
    """Actual placement of one normalized clip on the narrator timeline."""

    request_id: str
    source_order: int
    planned_start_ms: int
    planned_end_ms: int
    actual_start_ms: int
    actual_end_ms: int
    drift_ms: int
    reason: PlacementReason
    overlap_group_id: int | None
    clip_duration_ms: int
    window_duration_ms: int
    start_frame: int
    end_frame: int


@dataclass(frozen=True, slots=True)
class TimelinePlan:
    """Stable serialized timeline and its exact PCM length."""

    clips: tuple[NormalizedClip, ...]
    placements: tuple[TimelinePlacement, ...]
    sample_rate: int
    sample_width: int
    channels: int
    total_frames: int


@dataclass(frozen=True, slots=True)
class ChannelPlan:
    """Explicit source and narrator mappings for a final codec."""

    output_layout: str
    output_channels: int
    source_filter: str | None
    narrator_filter: str
    warning: str | None


@dataclass(frozen=True, slots=True)
class AudioRenderRequest:
    """Complete caller-owned request for one narration sidecar."""

    scope_id: str
    source_path: Path
    source_audio_path: Path | None
    clips: tuple[TimedClip, ...]
    temporary_root: Path
    post_process_tempo: float = 1.0


@dataclass(frozen=True, slots=True)
class AudioRenderResult:
    """Validated final result of one audio render."""

    scope_id: str
    status: AudioRenderStatus
    narrator_path: Path | None
    output_path: Path | None
    output_probe: AudioProbe | None
    placements: tuple[TimelinePlacement, ...]
    warnings: tuple[str, ...]
    narration_fingerprint: str | None
    mix_fingerprint: str | None
