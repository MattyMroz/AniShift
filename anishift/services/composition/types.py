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
    "OutputVariant",
    "QualityPreset",
    "SubtitleRole",
]


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
class CompositionPlan:
    """Neutral description of what to assemble for one source file.

    Attributes:
        source_path: Original container the result is built from.
        variant: Requested output variant.
        narration_audio: Rendered lector sidecar, when one exists.
        subtitles: Subtitle files to mux, in final track order.
        burn_subtitle: Subtitle file to render into the picture.
        source_subtitle_kind: ``ass`` or ``srt`` for the burned file.
        scope_id: Opaque per-source identifier owned by the pipeline.
        temporary_root: Directory for filter-safe copies and partial files.
        destination_dir: Directory the finished artifact is written to.
    """

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
    """Outcome of one composition attempt.

    Attributes:
        source_path: Container the result was built from.
        variant: Variant that produced the result.
        status: Terminal state of the attempt.
        output_path: Finished artifact, or the directory for ``players``.
        output_size_bytes: Size of the produced artifact.
        source_size_bytes: Size of the source, for the size budget.
        duration_ms: Wall time spent assembling this file.
        warnings: Human-readable notes worth showing in the report.
        moved_paths: Products relocated next to the source in ``players``.
    """

    source_path: Path
    variant: OutputVariant
    status: CompositionStatus
    output_path: Path | None = None
    output_size_bytes: int = 0
    source_size_bytes: int = 0
    duration_ms: float = 0.0
    warnings: tuple[str, ...] = ()
    moved_paths: tuple[Path, ...] = field(default_factory=tuple)
