"""Pipeline value objects and callback protocols."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from anishift.services.extraction.types import MediaInfo, TrackSelection
    from anishift.services.subtitles.classifier import StyleVerdict
    from anishift.services.translation.types import FileTranslation

__all__ = [
    "FileFailure",
    "FileOutcome",
    "FileStatus",
    "PipelineInteraction",
    "PipelineReport",
    "ProgressPhase",
    "ProgressReporter",
    "StepName",
    "TranslationSettings",
]

StepName = Literal["identify", "select", "extract", "split", "write", "translate", "txt"]
"""Pipeline step a failure is attributed to."""

FileStatus = Literal["done", "failed", "cancelled"]
"""Final state of one input file."""


@dataclass(frozen=True, slots=True)
class FileFailure:
    """Describe why one input file failed."""

    step: StepName
    code: str
    message: str
    suggestion: str


@dataclass(slots=True)
class FileOutcome:
    """Describe everything produced for one input file."""

    source: Path
    status: FileStatus
    audio_path: Path | None = None
    subtitle_path: Path | None = None
    displayed_path: Path | None = None
    translated_path: Path | None = None
    already_polish: bool = False
    spoken_lines: int = 0
    displayed_events: int = 0
    drawing_events: int = 0
    collapsed_away: int = 0
    translation: FileTranslation | None = None
    translated_lines: int = 0
    translation_engine: str = ""
    translation_failed_lines: int = 0
    warnings: tuple[str, ...] = ()
    failure: FileFailure | None = None


@dataclass(frozen=True, slots=True)
class TranslationSettings:
    """Translation parameters resolved once from AppContext for the runner.

    Attributes:
        engine: Selected translation engine id.
        fallback_chain: Ordered fallback engine ids.
        batch_size: Lines per request (0 = engine default).
        max_retries: Retry attempts per batch.
        deepl_api_key: DeepL key (used by the deepl engine, ignored by google).
    """

    engine: str
    fallback_chain: tuple[str, ...]
    batch_size: int
    max_retries: int
    deepl_api_key: str


@dataclass(frozen=True, slots=True)
class PipelineReport:
    """Collect per-file outcomes in discovery order."""

    outcomes: tuple[FileOutcome, ...]


class ProgressReporter(Protocol):
    """Define the progress display operations used by the runner."""

    def add_task(self, description: str, *, total: int = 100) -> int:
        """Register one progress row."""
        ...

    def update(self, task_id: int, completed: int) -> None:
        """Set one progress row's absolute completion."""
        ...


class ProgressPhase(Protocol):
    """A progress display for one pipeline phase, entered per phase.

    Each phase is a fresh transient display: its rows disappear on exit so
    the next phase draws its own rows in the same place.
    """

    def __enter__(self) -> ProgressReporter:
        """Start the phase display and return its reporter."""
        ...

    def __exit__(self, *exc: object) -> None:
        """Stop the phase display, clearing its rows."""
        ...


class PipelineInteraction(Protocol):
    """Define manual-mode decisions supplied by the CLI."""

    def choose_tracks(self, info: MediaInfo, proposal: TrackSelection) -> TrackSelection:
        """Confirm or override the selected tracks."""
        ...

    def choose_spoken_styles(
        self,
        source: Path,
        verdicts: Sequence[StyleVerdict],
        samples: Mapping[str, tuple[str, ...]],
    ) -> set[str] | None:
        """Choose spoken styles, or return None to accept auto selection."""
        ...
