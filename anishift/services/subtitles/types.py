"""Subtitles domain value objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from pysubs2 import SSAFile

    StyleVerdict = Any

__all__ = ["Decision", "SplitStats", "SpokenLine", "SubtitleKind", "SubtitleSplit"]

Decision = Literal["spoken", "displayed"]
"""Per-line fate: read by the narrator or kept on screen."""

SubtitleKind = Literal["ass", "srt"]
"""Working format of a subtitle file."""


@dataclass(frozen=True, slots=True)
class SpokenLine:
    """One line of narrator input, with tags stripped and runs collapsed."""

    start: int
    end: int
    text: str
    style: str


@dataclass(frozen=True, slots=True)
class SplitStats:
    """Split counters for reports and measurements."""

    total_events: int
    spoken_events: int
    spoken_lines: int
    displayed_events: int
    drawing_events: int
    collapsed_away: int


@dataclass(frozen=True, slots=True)
class SubtitleSplit:
    """Complete result of splitting one subtitle file."""

    kind: SubtitleKind
    subs: SSAFile
    decisions: tuple[Decision, ...]
    verdicts: tuple[StyleVerdict, ...]
    spoken: tuple[SpokenLine, ...]
    stats: SplitStats
