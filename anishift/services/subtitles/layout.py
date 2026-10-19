"""Line limits of a run and the layout core: one scored choice of lines and scale for any displayed text in a field."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from itertools import combinations, pairwise
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from anishift.services.subtitles.fuzzy import fall
from anishift.services.subtitles.linebreak import DEFAULT_MAX_CHARS, MAX_LINES
from anishift.text.boundaries import BREAKABLE_SPACES
from anishift.text.gaps import DASHES, Gap, GapKind, gaps, list_markers, quote_spans
from anishift.text.graphemes import split_graphemes
from anishift.text.morphology import agrees, modifies

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

__all__ = [
    "CHAR_WIDTH",
    "DIALOGUE_MAX_WIDTH",
    "HARMS",
    "WEIGHTS",
    "Field",
    "Flag",
    "Layout",
    "LayoutLimits",
    "Measure",
    "Scale",
    "candidates",
    "chars_measure",
    "dialogue_field",
    "lay_out",
]


@dataclass(frozen=True, slots=True)
class LayoutLimits:
    """Line length and line count chosen by the user for one run."""

    max_chars: int = DEFAULT_MAX_CHARS
    max_lines: int = MAX_LINES

    def __post_init__(self) -> None:
        """Reject limits that would make the line breaker unable to produce output."""
        if self.max_chars <= 0:
            msg = "Maximum characters per line must be positive"
            raise ValueError(msg)
        if self.max_lines <= 0:
            msg = "Maximum lines per event must be positive"
            raise ValueError(msg)


type Measure = Callable[[str, float], float]
"""Width of one line at a horizontal scale, as a fraction of the script width."""


class Flag(StrEnum):
    """Rescue step or avoided harm a chosen layout carries, for the run report."""

    OUTSIDE = "outside"
    EXTRA_LINE = "extra_line"
    BOUND_PAIR = "bound_pair"
    QUOTE = "quote"
    ORPHAN = "orphan"


@dataclass(frozen=True, slots=True)
class Scale:
    """Horizontal and vertical size factors of the text."""

    fx: float = 1.0
    fy: float = 1.0


@dataclass(frozen=True, slots=True)
class Field:
    """Where a text has to fit and how it may look; widths are fractions of the script width."""

    max_width: float
    preferred_lines: int = 1
    max_lines: int = 2
    rescue_lines: int = 3
    pyramid: bool = False
    length_knots: tuple[float, ...] = ()
    count_chars: bool = False
    comfort_width: float | None = None
    scalable: bool = False
    letter_height: float = 0.0
    height_lines: float | None = None
    pattern: tuple[float, ...] = ()
    breaks: frozenset[int] = frozenset()
    speaker_lines: bool = False


@dataclass(frozen=True, slots=True)
class Layout:
    """Lines and scale of one candidate with its harm degrees, rescue level and report flags."""

    lines: tuple[str, ...]
    scale: Scale
    harms: Mapping[str, float]
    rescue: tuple[int, int, int]
    flags: frozenset[Flag]

    def score(self, weights: Mapping[str, float]) -> float:
        """Return the weighted sum of the harm degrees."""
        return sum(weights.get(name, 0.0) * degree for name, degree in self.harms.items())


# ── Constants ─────────────────────────────────────────────────────────────────

DIALOGUE_MAX_WIDTH: Final[float] = 0.9
"""Safe screen area a dialogue line must fit even when the style margins are narrower (text-layout spec §3.2, r7)."""

_DIALOGUE_RESCUE_LINES: Final[int] = 3
"""Dialogue lines allowed in rescue only (text-layout spec §3.2, q13, r6, r7)."""

_LENGTH_KNOTS: Final[tuple[float, float]] = (0.55, 0.76)
"""Widths where the long line harm starts and turns steeper (text-layout spec §4.1; 0.76 is the q17 limit)."""

_KNEE_CHARS: Final[int] = 56
"""Characters of the longest one-line answer the owner still accepted (q17; q11 at 57 lost)."""

CHAR_WIDTH: Final[float] = _LENGTH_KNOTS[1] / _KNEE_CHARS
"""Screen width a character stands for, so the character and width knees coincide (text-layout spec §4.1)."""

_IMBALANCE_KNOTS: Final[tuple[int, ...]] = (6, 10, 20, 25, 30)
"""Line length differences in characters where the exchange rate of punctuation for balance changes (spec §4.4)."""

_SMALL_LETTERS: Final[tuple[float, float]] = (16.0, 30.0)
"""Letter heights in screen pixels where the too small harm is full and where it starts (text-layout spec §4.6)."""

_PERCENT: Final[float] = 100.0
"""Scale steps per unit: ASS writes ``\\fscx`` and ``\\fscy`` in whole percent."""

_ENUMERATED_LINES: Final[int] = 3
"""Most lines whose every split is enumerated; longer layouts come from dynamic programming (spec §5.1)."""

_MIN_LIST_ITEMS: Final[int] = 2
"""Numbered markers needed before the text counts as a list."""

HARMS: Final[tuple[str, ...]] = (
    "length_comfortable",
    "length_wide",
    *(f"cut_{kind.value}" for kind in GapKind),
    "agreement",
    *(f"imbalance_{knot}" for knot in _IMBALANCE_KNOTS),
    "top_longer",
    "extra_line",
    "missing_line",
    "squeeze",
    "shrink",
    "small",
    "over_comfort",
)
"""Names of the harm degrees a layout is scored on, in the order of the calibration report."""


WEIGHTS: Final[Mapping[str, float]] = MappingProxyType(
    {
        "length_comfortable": 157.087,
        "length_wide": 130.474,
        "cut_sentence": 0.001,
        "cut_clause": 0.001,
        "cut_ellipsis": 0.001,
        "cut_parenthetical": 0.001,
        "cut_dash": 0.001,
        "cut_before_subordinator": 1.80557,
        "cut_before_coordinator": 0.00919162,
        "cut_before_preposition": 6.02557,
        "cut_phrase": 5.02557,
        "cut_auxiliary": 29.0231,
        "cut_modifier": 6.02557,
        "cut_abbreviation": 6.02557,
        "cut_after_opener": 17.1909,
        "cut_degree": 18.1805,
        "cut_name": 29.0231,
        "cut_after_preposition": 29.0231,
        "cut_negation": 29.0231,
        "cut_reflexive": 29.0231,
        "cut_number": 29.0231,
        "cut_idiom": 29.0231,
        "cut_after_single_letter": 29.0231,
        "agreement": 5.68168,
        "imbalance_20": 0.818867,
        "top_longer": 0.334699,
        "extra_line": 31.9874,
        "missing_line": 3.37479,
        "squeeze": 18.7006,
        "shrink": 13.9387,
        "over_comfort": 40.3125,
    }
)
"""Harm weights from the layout calibration (docs/work/10-quality/research/text-layout-calibration.md)."""


# ── Public functions ──────────────────────────────────────────────────────────


def dialogue_field(*, max_width: float = DIALOGUE_MAX_WIDTH) -> Field:
    """Return the field of the main dialogue: one line while it is comfortable, two when wide, three in rescue."""
    return Field(
        max_width=max_width,
        rescue_lines=_DIALOGUE_RESCUE_LINES,
        pyramid=True,
        length_knots=_LENGTH_KNOTS,
        count_chars=True,
        speaker_lines=True,
    )


def chars_measure(line: str, fx: float) -> float:
    """Measure a line by its graphemes when no render profile exists (text-layout spec §4.1, e10)."""
    return len(split_graphemes(line)) * CHAR_WIDTH * fx


def candidates(text: str, field: Field, measure: Measure, *, morphology: bool = True) -> list[Layout]:
    """Return every allowed layout of up to three lines, each at every scale the field may use."""
    return _enumerated(_case(text, field, measure, morphology=morphology))


def lay_out(
    text: str, field: Field, measure: Measure, weights: Mapping[str, float] = WEIGHTS, *, morphology: bool = True
) -> Layout:
    """Return the layout with the lowest rescue level and then the lowest weighted harm."""
    case: _Case = _case(text, field, measure, morphology=morphology)
    found: list[Layout] = _enumerated(case)
    if field.rescue_lines > _ENUMERATED_LINES:
        found.extend(_programmed(case, weights))
    return min(found, key=lambda layout: (layout.rescue, layout.score(weights)))


# ── Text analysis ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Case:
    words: tuple[str, ...]
    gaps: tuple[Gap, ...]
    quotes: tuple[tuple[int, int], ...]
    forced: frozenset[int]
    chars: int
    field: Field
    measure: Measure
    morphology: bool


def _case(text: str, field: Field, measure: Measure, *, morphology: bool) -> _Case:
    words: tuple[str, ...] = tuple(word for word in BREAKABLE_SPACES.split(text.strip()) if word)
    found: tuple[Gap, ...] = gaps(words, modifies if morphology else None)
    turns: frozenset[int] = frozenset(index for index, gap in enumerate(found) if gap.turn and field.speaker_lines)
    return _Case(
        words=words,
        gaps=found,
        quotes=quote_spans(words),
        forced=field.breaks | _list_breaks(words, field, measure) | turns,
        chars=_chars(" ".join(words)),
        field=field,
        measure=measure,
        morphology=morphology,
    )


def _list_breaks(words: tuple[str, ...], field: Field, measure: Measure) -> frozenset[int]:
    markers: tuple[int, ...] = list_markers(words)
    if len(markers) < _MIN_LIST_ITEMS or markers[0] != 0:
        return frozenset()
    bounds: tuple[int, ...] = (*markers, len(words))
    if any(measure(" ".join(words[start:end]), 1.0) > field.max_width for start, end in pairwise(bounds)):
        return frozenset()
    return frozenset(marker - 1 for marker in markers[1:])


def _enumerated(case: _Case) -> list[Layout]:
    return [_evaluate(case, cuts, scale) for cuts in _splits(case) for scale in _scales(case, cuts)]


def _splits(case: _Case) -> Iterator[tuple[int, ...]]:
    allowed: list[int] = [index for index in range(len(case.gaps)) if _allowed_cut(case, index)]
    for lines in range(1, min(case.field.rescue_lines, _ENUMERATED_LINES) + 1):
        for cuts in combinations(allowed, lines - 1):
            if case.forced <= set(cuts):
                yield cuts


def _allowed_cut(case: _Case, index: int) -> bool:
    return not case.gaps[index].banned or index in case.forced


# ── Scales ────────────────────────────────────────────────────────────────────


def _scales(case: _Case, cuts: tuple[int, ...]) -> list[Scale]:
    if not case.field.scalable:
        return [Scale()]
    return _scale_options(_breakpoints(case.field, [case.measure(line, 1.0) for line in _lines(case.words, cuts)]))


def _breakpoints(field: Field, widths: Sequence[float]) -> set[float]:
    targets: list[float] = [field.max_width] + ([] if field.comfort_width is None else [field.comfort_width])
    points: set[float] = {target / width for target in targets for width in widths if width > 0}
    if field.letter_height > 0:
        points.update(height / field.letter_height for height in _SMALL_LETTERS)
    return points


def _scale_options(points: set[float]) -> list[Scale]:
    steps: set[float] = {math.floor(point * _PERCENT) / _PERCENT for point in points if 0 < point < 1}
    steps.discard(0.0)
    return [Scale()] + [option for step in sorted(steps) for option in (Scale(step, step), Scale(step))]


# ── Harm degrees ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Part:
    harms: dict[str, float]
    outside: int
    flags: tuple[Flag, ...]


def _evaluate(case: _Case, cuts: tuple[int, ...], scale: Scale) -> Layout:
    field: Field = case.field
    bounds: tuple[int, ...] = (0, *(cut + 1 for cut in cuts), len(case.words))
    count: int = len(bounds) - 1
    harms: dict[str, float] = _global_harms(field, count, scale)
    outside: int = int(field.height_lines is not None and count * scale.fy > field.height_lines)
    flags: list[Flag] = []
    for index, (start, end) in enumerate(pairwise(bounds)):
        part: _Part = _line_part(case, (start, end, index, count), scale)
        for name, degree in part.harms.items():
            harms[name] = harms.get(name, 0.0) + degree
        outside += part.outside
        flags.extend(part.flags)
    if field.pyramid:
        chars: list[int] = [_chars(" ".join(case.words[start:end])) for start, end in pairwise(bounds)]
        harms["top_longer"] = float(sum(max(0, upper - lower) for upper, lower in pairwise(chars)))
    extra: int = max(0, count - field.max_lines)
    rescue_flags: list[Flag] = [flag for flag, on in ((Flag.OUTSIDE, outside), (Flag.EXTRA_LINE, extra)) if on]
    return Layout(
        lines=_lines(case.words, cuts),
        scale=scale,
        harms=harms,
        rescue=(outside, extra, len(flags)),
        flags=frozenset(flags + rescue_flags),
    )


def _line_part(case: _Case, place: tuple[int, int, int, int], scale: Scale) -> _Part:
    start, end, index, count = place
    field: Field = case.field
    text: str = " ".join(case.words[start:end])
    width: float = case.measure(text, scale.fx)
    chars: int = _chars(text)
    harms: dict[str, float] = _length_harms(field, width, chars) | _imbalance_harms(case, chars, index, count)
    if field.comfort_width is not None:
        harms["over_comfort"] = max(0.0, width - field.comfort_width)
    flags: list[Flag] = []
    if count > 1 and end - start == 1 and not _exempt_orphan(case, start):
        flags.append(Flag.ORPHAN)
    if end < len(case.words):
        cut: int = end - 1
        gap: Gap = case.gaps[cut]
        harms[f"cut_{gap.kind.value}"] = 1.0
        if case.morphology and agrees(case.words[cut], case.words[end]):
            harms["agreement"] = 1.0
        if gap.protected and cut not in case.forced:
            flags.append(Flag.BOUND_PAIR)
        if _inside_fitting_quote(case, cut, scale):
            flags.append(Flag.QUOTE)
    return _Part(harms=harms, outside=int(width > field.max_width), flags=tuple(flags))


def _global_harms(field: Field, count: int, scale: Scale) -> dict[str, float]:
    harms: dict[str, float] = {
        "extra_line": float(max(0, count - field.preferred_lines)),
        "missing_line": float(max(0, field.preferred_lines - count)),
    }
    if field.scalable:
        harms["squeeze"] = 1.0 - scale.fx / scale.fy
        harms["shrink"] = 1.0 - scale.fy
    if field.scalable and field.letter_height > 0:
        harms["small"] = fall(field.letter_height * scale.fy, *_SMALL_LETTERS)
    return harms


def _length_harms(field: Field, width: float, chars: int) -> dict[str, float]:
    if not field.length_knots:
        return {}
    length: float = max(width, chars * CHAR_WIDTH) if field.count_chars else width
    comfortable, wide = field.length_knots
    return {"length_comfortable": max(0.0, length - comfortable), "length_wide": max(0.0, length - wide)}


def _imbalance_harms(case: _Case, chars: int, index: int, count: int) -> dict[str, float]:
    if count == 1:
        return {}
    pattern: tuple[float, ...] = case.field.pattern
    content: int = case.chars - (count - 1)
    share: float = pattern[index] / sum(pattern) if len(pattern) == count else 1 / count
    deviation: float = abs(chars - content * share)
    return {f"imbalance_{knot}": max(0.0, deviation - knot / 2) for knot in _IMBALANCE_KNOTS}


def _exempt_orphan(case: _Case, start: int) -> bool:
    if start - 1 in case.forced or (start > 0 and case.gaps[start - 1].turn):
        return True
    return start == 0 and case.words[0][:1] in DASHES and any(gap.turn for gap in case.gaps)


def _inside_fitting_quote(case: _Case, cut: int, scale: Scale) -> bool:
    for first, last in case.quotes:
        if first <= cut < last:
            return case.measure(" ".join(case.words[first : last + 1]), scale.fx) <= case.field.max_width
    return False


def _lines(words: Sequence[str], cuts: tuple[int, ...]) -> tuple[str, ...]:
    bounds: tuple[int, ...] = (0, *(cut + 1 for cut in cuts), len(words))
    return tuple(" ".join(words[start:end]) for start, end in pairwise(bounds))


def _chars(text: str) -> int:
    return len(split_graphemes(text))


# ── Dynamic programming ───────────────────────────────────────────────────────


type _Key = tuple[int, int, float]
"""Partial layout key: lines outside the field, avoided harms and weighted harm."""


def _programmed(case: _Case, weights: Mapping[str, float]) -> list[Layout]:
    found: list[Layout] = []
    for count in range(_ENUMERATED_LINES + 1, min(case.field.rescue_lines, len(case.words)) + 1):
        unscaled: tuple[int, ...] | None = _Solver(case, weights, count, Scale()).best_cuts()
        if unscaled is None:
            continue
        found.append(_evaluate(case, unscaled, Scale()))
        for scale in _scales(case, unscaled)[1:]:
            cuts: tuple[int, ...] | None = _Solver(case, weights, count, scale).best_cuts()
            if cuts is not None:
                found.append(_evaluate(case, cuts, scale))
    return found


class _Solver:
    """Best split into a fixed number of lines at one scale, line by line."""

    def __init__(self, case: _Case, weights: Mapping[str, float], count: int, scale: Scale) -> None:
        self._case: _Case = case
        self._weights: Mapping[str, float] = weights
        self._count: int = count
        self._scale: Scale = scale
        self._best: Callable[[int, int], tuple[_Key, tuple[int, ...]] | None] = cache(self._solve)

    def best_cuts(self) -> tuple[int, ...] | None:
        """Return the cuts of the best split, or None when no allowed split exists."""
        result: tuple[_Key, tuple[int, ...]] | None = self._best(0, 0)
        return None if result is None else result[1]

    def _solve(self, start: int, index: int) -> tuple[_Key, tuple[int, ...]] | None:
        size: int = len(self._case.words)
        if index == self._count - 1:
            return None if self._skips_forced(start, size) else (self._key(start, size, index), ())
        options: list[tuple[_Key, tuple[int, ...]]] = []
        for end in range(start + 1, size - (self._count - index - 1) + 1):
            rest: tuple[_Key, tuple[int, ...]] | None = self._best(end, index + 1)
            if rest is None or not _allowed_cut(self._case, end - 1) or self._skips_forced(start, end):
                continue
            key: _Key = self._key(start, end, index)
            options.append(((key[0] + rest[0][0], key[1] + rest[0][1], key[2] + rest[0][2]), (end - 1, *rest[1])))
        return min(options, default=None, key=lambda option: option[0])

    def _skips_forced(self, start: int, end: int) -> bool:
        return any(start <= cut < end - 1 for cut in self._case.forced)

    def _key(self, start: int, end: int, index: int) -> _Key:
        part: _Part = _line_part(self._case, (start, end, index, self._count), self._scale)
        score: float = sum(self._weights.get(name, 0.0) * degree for name, degree in part.harms.items())
        return part.outside, len(part.flags), score
