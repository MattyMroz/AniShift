"""Value objects describing one composition request and its outcome."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

__all__ = [
    "AttachedSubtitle",
    "CompositionPlan",
    "CompositionResult",
    "CompositionStatus",
    "ContainerCompositionRequest",
    "ContainerCompositionResult",
    "ContainerTarget",
    "OutputVariant",
    "QualityPreset",
    "SubtitleRole",
]


class ContainerTarget(StrEnum):
    """One independently produced media container."""

    MKV = "mkv"
    MP4 = "mp4"


class OutputVariant(StrEnum):
    """Final artifact the user asked for."""

    PLAYERS = "players"
    MERGE = "merge"
    BURN = "burn"


class QualityPreset(StrEnum):
    """Named quality target for hardsub rendering."""

    HIGH = "high"
    BALANCED = "balanced"
    COMPACT = "compact"


class SubtitleRole(StrEnum):
    """Role a subtitle file plays in the finished container."""

    FULL = "full"
    DISPLAYED = "displayed"


class CompositionStatus(StrEnum):
    """Terminal state of one composition attempt."""

    COMPLETED = "completed"
    SKIPPED_NOTHING_TO_ADD = "skipped_nothing_to_add"


@dataclass(frozen=True, slots=True)
class AttachedSubtitle:
    """One subtitle file muxed into the result with its track metadata."""

    path: Path
    role: SubtitleRole
    language: str
    track_name: str


@dataclass(frozen=True, slots=True)
class ContainerCompositionRequest:
    """Exact inputs and destination for one container product."""

    source_video: Path
    destination: Path
    target: ContainerTarget
    burn_subtitle: Path | None
    attached_subtitles: tuple[AttachedSubtitle, ...]
    narration_audio: Path | None
    keep_original_audio: bool

    def __post_init__(self) -> None:
        if self.source_video == self.destination:
            msg = "Composition source and destination must differ"
            raise ValueError(msg)
        expected_suffix: str = f".{self.target.value}"
        if self.destination.suffix.casefold() != expected_suffix:
            msg = f"Container destination must end with {expected_suffix}"
            raise ValueError(msg)
        if self.target is ContainerTarget.MKV and self.burn_subtitle is not None:
            msg = "MKV composition attaches subtitles instead of burning them"
            raise ValueError(msg)
        if self.target is ContainerTarget.MP4 and self.attached_subtitles:
            msg = "MP4 composition does not attach subtitle sidecars"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ContainerCompositionResult:
    """Outcome of producing exactly one target container."""

    source_path: Path
    target: ContainerTarget
    output_path: Path
    output_size_bytes: int
    source_size_bytes: int
    duration_ms: float
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompositionPlan:
    """Neutral description of what to assemble for one source file."""

    source_path: Path
    variant: OutputVariant
    narration_audio: Path | None = None
    subtitles: tuple[AttachedSubtitle, ...] = ()
    burn_subtitle: Path | None = None
    source_subtitle_kind: str = "ass"
    scope_id: str = ""
    temporary_root: Path = Path()
    destination_dir: Path = Path()

    @property
    def has_material(self) -> bool:
        """Return whether anything would actually be added to the result."""
        return self.narration_audio is not None or bool(self.subtitles) or self.burn_subtitle is not None


@dataclass(frozen=True, slots=True)
class CompositionResult:
    """Outcome of one composition attempt."""

    source_path: Path
    variant: OutputVariant
    status: CompositionStatus
    output_path: Path | None = None
    output_size_bytes: int = 0
    source_size_bytes: int = 0
    duration_ms: float = 0.0
    warnings: tuple[str, ...] = ()
    moved_paths: tuple[Path, ...] = field(default_factory=tuple)
