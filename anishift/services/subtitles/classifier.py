"""Classify subtitle styles using the measured mm_avh heuristic."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pysubs2 import SSAEvent, SSAFile

__all__ = ["Category", "StyleVerdict", "classify_styles", "dedup_animation"]

# Constants

_BACKSLASH: Final[str] = chr(92)
"""Literal backslash used to build ASS tag expressions."""

_RE_DRAW: Final[re.Pattern[str]] = re.compile(_BACKSLASH + _BACKSLASH + r"p[1-9]")
_RE_POS: Final[re.Pattern[str]] = re.compile(_BACKSLASH + _BACKSLASH + r"(pos|move|clip|frz|fad|org|t\()")
_RE_KARA: Final[re.Pattern[str]] = re.compile(_BACKSLASH + _BACKSLASH + r"[kK][fo]?[0-9]")
_RE_PUNCT: Final[re.Pattern[str]] = re.compile(r'[.!?…»"]')
_RE_SONG: Final[re.Pattern[str]] = re.compile(
    r"\bop\b|\bed\b|opening|ending|song|lyric|piosenk|karaoke|insert.?song|theme", re.I
)
_RE_NOTE: Final[re.Pattern[str]] = re.compile(r"disclaimer|\bnote\b|notka|przypis|tln|t/n|credit|copyright", re.I)
_RE_SIGN: Final[re.Pattern[str]] = re.compile(
    r"sign|znak|kartka|title|next_ep|acquired|chyron|chapter|^ts$|typeset|caption.?box|box$", re.I
)
_RE_DLG: Final[re.Pattern[str]] = re.compile(
    r"default|main|dialog|narrat|italic|flashback|tirets|thought|mysli|myśli|alter|overlap", re.I
)

_DEDUP_MIN_REPEAT: Final[int] = 5
"""Minimum repeated lines required for animation deduplication."""

_DEDUP_WINDOW_MS: Final[int] = 2000
"""Maximum median start gap for animation deduplication."""

_DRAW_SIGN_RATIO: Final[float] = 0.30
_KARA_SONG_RATIO: Final[float] = 0.30
_DLG_MAX_POS_RATIO: Final[float] = 0.50
_SCORE_DIALOG: Final[float] = 0.55
_SCORE_SIGN: Final[float] = 0.25
_FRAC_DIALOG_MIN: Final[float] = 0.20
"""File-share ratio at or above which a style earns the share score."""

_POS_LOW_MAX: Final[float] = 0.40
"""Positioning ratio below which a style earns the low-positioning score."""

_PUNCT_MIN: Final[float] = 0.30
"""Punctuation ratio above which a style earns the punctuation score."""

_AVG_TEXT_MIN: Final[int] = 12
"""Average plain-text length at or above which a style earns the length score."""

_POS_HIGH_MIN: Final[float] = 0.60
"""Positioning ratio above which a style is penalised as typesetting."""


class Category(Enum):
    """Subtitle style category for auto mode."""

    DIALOG = "DIALOG"
    SIGN = "SIGN"
    UNCERTAIN = "UNCERTAIN"


@dataclass(slots=True, frozen=True)
class StyleVerdict:
    """Classification verdict for a single style."""

    style: str
    category: Category
    confidence: float
    line_count: int
    raw_line_count: int


@dataclass(slots=True)
class _StyleMetrics:
    n: int = 0
    raw_n: int = 0
    pos: int = 0
    draw: int = 0
    kara: int = 0
    punct: int = 0
    txt: int = 0


def dedup_animation(events: list[SSAEvent]) -> tuple[list[SSAEvent], int]:
    """Collapse repeated typesetting animation lines into one occurrence."""
    by_key: dict[tuple[str, str], list[SSAEvent]] = defaultdict(list)
    for event in events:
        by_key[(event.style, event.plaintext.strip())].append(event)

    keep: list[SSAEvent] = []
    removed = 0
    for (_style, text), group in by_key.items():
        if len(group) < _DEDUP_MIN_REPEAT or not text:
            keep.extend(group)
            continue
        starts = sorted(event.start for event in group)
        diffs = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
        median_gap = sorted(diffs)[len(diffs) // 2] if diffs else 0
        if median_gap >= _DEDUP_WINDOW_MS:
            keep.extend(group)
            continue
        keep.append(min(group, key=lambda event: event.start))
        removed += len(group) - 1
    return keep, removed


def _classify_metrics(metrics: _StyleMetrics, style: str, total: int) -> tuple[Category, float]:
    n = metrics.n
    pos, draw, kara, punct = metrics.pos / n, metrics.draw / n, metrics.kara / n, metrics.punct / n
    avg, frac = metrics.txt / n, metrics.n / total
    if draw > _DRAW_SIGN_RATIO or kara > _KARA_SONG_RATIO:
        return Category.SIGN, 0.95
    if _RE_SONG.search(style) or _RE_NOTE.search(style):
        return Category.SIGN, 0.9
    if _RE_DLG.search(style) and pos < _DLG_MAX_POS_RATIO and draw == 0:
        return Category.DIALOG, 0.85
    score = 0.0
    if frac >= _FRAC_DIALOG_MIN:
        score += 0.35
    if pos < _POS_LOW_MAX:
        score += 0.25
    if punct > _PUNCT_MIN:
        score += 0.20
    if avg >= _AVG_TEXT_MIN:
        score += 0.10
    if _RE_DLG.search(style):
        score += 0.15
    if _RE_SIGN.search(style):
        score -= 0.25
    if pos > _POS_HIGH_MIN:
        score -= 0.30
    if score >= _SCORE_DIALOG:
        return Category.DIALOG, round(min(score, 0.99), 2)
    if score <= _SCORE_SIGN:
        return Category.SIGN, round(min(1 - score, 0.95), 2)
    return Category.UNCERTAIN, 0.5


def classify_styles(subs: SSAFile) -> list[StyleVerdict]:
    """Classify every style used by Dialogue events."""
    events = [event for event in subs.events if event.type == "Dialogue"]
    if not events:
        return []
    deduped, _ = dedup_animation(events)
    total = len(deduped)
    metrics: dict[str, _StyleMetrics] = defaultdict(_StyleMetrics)
    for event in events:
        metrics[event.style].raw_n += 1
    for event in deduped:
        entry = metrics[event.style]
        entry.n += 1
        if _RE_POS.search(event.text):
            entry.pos += 1
        if _RE_DRAW.search(event.text):
            entry.draw += 1
        if _RE_KARA.search(event.text):
            entry.kara += 1
        plain = event.plaintext
        entry.txt += len(plain)
        if _RE_PUNCT.search(plain):
            entry.punct += 1
    verdicts: list[StyleVerdict] = []
    for style, entry in sorted(metrics.items(), key=lambda kv: -kv[1].n):
        if entry.n == 0:
            continue
        category, confidence = _classify_metrics(entry, style, total)
        verdicts.append(StyleVerdict(style, category, confidence, entry.n, entry.raw_n))
    return verdicts
