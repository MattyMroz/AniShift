"""Subtitles domain value objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pathlib import Path

    from pysubs2 import SSAFile

    from anishift.services.subtitles.classifier import StyleVerdict

__all__ = [
    "Decision",
    "DisplayedLine",
    "FontSources",
    "LayoutReport",
    "SignCandidate",
    "SignWeight",
    "SplitStats",
    "SpokenLine",
    "SubtitleKind",
    "SubtitleSplit",
    "TranslatedLayout",
]

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
    order: int = 0


@dataclass(frozen=True, slots=True)
class DisplayedLine:
    """One translatable on-screen event in source-file order."""

    start: int
    end: int
    text: str
    order: int


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
class SignWeight:
    """Static weights of one on-screen sign group the narrator may read, shared by every member event."""

    group: int
    weight_for: float
    weight_against: float


@dataclass(frozen=True, slots=True)
class SignCandidate:
    """One sign group the narrator may read: its screen window, text, comparison key and static weights."""

    group: int
    start: int
    end: int
    text: str
    key: str
    weight_for: float
    weight_against: float


@dataclass(frozen=True, slots=True)
class SubtitleSplit:
    """Complete result of splitting one subtitle file; ``sign_weights`` runs parallel to ``decisions``."""

    kind: SubtitleKind
    subs: SSAFile
    decisions: tuple[Decision, ...]
    verdicts: tuple[StyleVerdict, ...]
    spoken: tuple[SpokenLine, ...]
    stats: SplitStats
    sign_weights: tuple[SignWeight | None, ...] = ()


@dataclass(frozen=True, slots=True)
class FontSources:
    """Font files a layout may measure with: the episode's own fonts before the system fonts."""

    episode: tuple[Path, ...]
    system: tuple[Path, ...]


@dataclass(slots=True)
class LayoutReport:
    """Counters of one laid-out file: fitted signs, rescue layouts, approximate measurements and restyled styles."""

    signs_fitted: int = 0
    signs_fallback_screen: int = 0
    signs_fallback_collision: int = 0
    signs_relaxed: int = 0
    signs_small: int = 0
    signs_approximate: int = 0
    sign_dialogue_collisions: int = 0
    dialogue_unmeasured: int = 0
    dialogue_relaxed_phrases: int = 0
    dialogue_three_lines: int = 0
    dialogue_overflow: int = 0
    dialogue_untagged: int = 0
    fallback_glyph_events: int = 0
    restyled_styles: int = 0
    signs_restyled: int = 0
    sign_sets_scaled: int = 0


@dataclass(frozen=True, slots=True)
class TranslatedLayout:
    """Translated subtitle file laid out for writing and the report of its layout."""

    subs: SSAFile
    report: LayoutReport
