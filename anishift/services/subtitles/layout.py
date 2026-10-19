"""Line limits of a run and the layout core: one scored choice of lines and scale for any displayed text in a field."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from functools import cache, lru_cache
from itertools import combinations, pairwise
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from anishift.services.subtitles.fuzzy import fall
from anishift.text.boundaries import BREAKABLE_SPACES
from anishift.text.gaps import DASHES, Gap, GapKind, gaps, list_markers, quote_spans
from anishift.text.graphemes import split_graphemes
from anishift.text.morphology import agrees, modifies

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

__all__ = [
    "CHAR_WIDTH",
    "DEFAULT_MAX_CHARS",
    "DIALOGUE_MAX_WIDTH",
    "HARMS",
    "MAX_LINES",
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


DEFAULT_MAX_CHARS: Final[int] = 42
"""Preferred readable line length for on-screen subtitles (Netflix/BBC-ish)."""

MAX_LINES: Final[int] = 2
"""Maximum on-screen verses before an over-length line is accepted."""


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
    JOINED = "joined"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class Scale:
    """Horizontal and vertical size factors of the text."""

    fx: float = 1.0
    fy: float = 1.0


@dataclass(frozen=True, slots=True)
class Field:
    """Where a text has to fit and how it may look; widths are script width fractions, breaks are gap indices."""

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
    style_breaks: frozenset[int] = frozenset()
    style_rescue: bool = True
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

_CHARS_CACHE: Final[int] = 1 << 16
"""Line texts whose grapheme count is remembered."""

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
    "mixed_style",
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
        "length_comfortable": 422.175,
        "length_wide": 36.3444,
        "cut_sentence": 0.001,
        "cut_clause": 0.001,
        "cut_ellipsis": 0.001,
        "cut_parenthetical": 0.001,
        "cut_dash": 0.001,
        "cut_before_subordinator": 0.001,
        "cut_before_coordinator": 0.60857,
        "cut_before_preposition": 6.82371,
        "cut_phrase": 6.82371,
        "cut_auxiliary": 41.4227,
        "cut_modifier": 7.82371,
        "cut_abbreviation": 6.82371,
        "cut_after_opener": 41.0267,
        "cut_degree": 44.2096,
        "cut_particle": 19.8194,
        "cut_prepositional": 6.82371,
        "cut_name": 44.2096,
        "cut_after_preposition": 44.2096,
        "cut_negation": 44.2096,
        "cut_reflexive": 44.2096,
        "cut_number": 44.2096,
        "cut_idiom": 44.2096,
        "cut_label": 44.2096,
        "cut_repetition": 44.2096,
        "cut_after_single_letter": 44.2096,
        "agreement": 6.78055,
        "imbalance_20": 0.697147,
        "top_longer": 0.434595,
        "extra_line": 87.6558,
        "missing_line": 5.17293,
        "squeeze": 19.3825,
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
        style_rescue=False,
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
    best: Layout = min(found, key=lambda layout: (layout.rescue, layout.score(weights)))
    if field.rescue_lines > _ENUMERATED_LINES:
        found.extend(_programmed(case, weights, (best.rescue, best.score(weights))))
    return min(found, key=lambda layout: (layout.rescue, layout.score(weights)))


# ── Text analysis ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Case:
    words: tuple[str, ...]
    gaps: tuple[Gap, ...]
    quotes: tuple[tuple[int, int], ...]
    forced: frozenset[int]
    released: frozenset[int]
    chars: int
    field: Field
    measure: Measure
    morphology: bool


def _case(text: str, field: Field, measure: Measure, *, morphology: bool) -> _Case:
    words: tuple[str, ...] = tuple(word for word in BREAKABLE_SPACES.split(text.strip()) if word)
    found: tuple[Gap, ...] = gaps(words, modifies if morphology else None)
    turns: frozenset[int] = frozenset(index for index, gap in enumerate(found) if gap.turn and field.speaker_lines)
    cached: Measure = cache(measure)
    forced: frozenset[int] = field.breaks | _list_breaks(words, field, cached) | turns
    fits: bool = len(forced) < field.rescue_lines
    return _Case(
        words=words,
        gaps=found,
        quotes=quote_spans(words),
        forced=forced if fits else frozenset(),
        released=frozenset() if fits else forced,
        chars=_chars(" ".join(words)),
        field=field,
        measure=cached,
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
    return not case.gaps[index].banned or index in case.forced | case.released


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
    steps: set[float] = {
        rounded(point * _PERCENT) / _PERCENT for point in points if 0 < point < 1 for rounded in (math.floor, math.ceil)
    }
    steps -= {0.0, 1.0}
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
    shape: _Part = _line_shape(case, place)
    size: _Part = _line_size(case, place[0], place[1], scale.fx)
    return _Part(harms=shape.harms | size.harms, outside=size.outside, flags=shape.flags + size.flags)


def _line_shape(case: _Case, place: tuple[int, int, int, int]) -> _Part:
    start, end, index, count = place
    harms: dict[str, float] = _imbalance_harms(case, _chars(" ".join(case.words[start:end])), index, count)
    flags: list[Flag] = [Flag.JOINED for cut in case.released if start <= cut < end - 1]
    mixed: int = sum(start <= cut < end - 1 for cut in case.field.style_breaks - case.forced)
    if mixed:
        harms["mixed_style"] = float(mixed)
    if mixed and case.field.style_rescue:
        flags.append(Flag.MIXED)
    if count > 1 and end - start == 1 and not _exempt_orphan(case, start):
        flags.append(Flag.ORPHAN)
    if end < len(case.words):
        cut: int = end - 1
        gap: Gap = case.gaps[cut]
        harms[f"cut_{gap.kind.value}"] = 1.0
        if case.morphology and agrees(case.words[cut], case.words[end]):
            harms["agreement"] = 1.0
        if gap.protected and cut not in case.forced | case.released:
            flags.append(Flag.BOUND_PAIR)
    return _Part(harms=harms, outside=0, flags=tuple(flags))


def _line_size(case: _Case, start: int, end: int, fx: float) -> _Part:
    field: Field = case.field
    text: str = " ".join(case.words[start:end])
    width: float = case.measure(text, fx)
    harms: dict[str, float] = _length_harms(field, width, _chars(text))
    if field.comfort_width is not None:
        harms["over_comfort"] = max(0.0, width - field.comfort_width)
    quote: bool = end < len(case.words) and _inside_fitting_quote(case, end - 1, fx)
    return _Part(harms=harms, outside=int(width > field.max_width), flags=(Flag.QUOTE,) if quote else ())


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
    if start - 1 in case.forced | case.released or (start > 0 and case.gaps[start - 1].turn):
        return True
    return start == 0 and case.words[0][:1] in DASHES and any(gap.turn for gap in case.gaps)


def _inside_fitting_quote(case: _Case, cut: int, fx: float) -> bool:
    for first, last in case.quotes:
        if first <= cut < last:
            return case.measure(" ".join(case.words[first : last + 1]), fx) <= _one_line_width(case.field)
    return False


def _one_line_width(field: Field) -> float:
    return field.length_knots[-1] if field.length_knots else field.max_width


def _lines(words: Sequence[str], cuts: tuple[int, ...]) -> tuple[str, ...]:
    bounds: tuple[int, ...] = (0, *(cut + 1 for cut in cuts), len(words))
    return tuple(" ".join(words[start:end]) for start, end in pairwise(bounds))


@lru_cache(maxsize=_CHARS_CACHE)
def _chars(text: str) -> int:
    return len(split_graphemes(text))


# ── Dynamic programming ───────────────────────────────────────────────────────


type _Key = tuple[int, int, float]
"""Partial layout key: lines outside the field, avoided harms and weighted harm."""

type _Bound = tuple[tuple[int, int, int], float]
"""Rescue level and weighted harm of a whole layout, or a lower bound of them."""


def _programmed(case: _Case, weights: Mapping[str, float], best: _Bound) -> list[Layout]:
    found: list[Layout] = []
    costs: _Costs = _Costs(case, weights)
    widths: list[float] = _programmed_widths(case)
    for count in range(_ENUMERATED_LINES + 1, min(case.field.rescue_lines, len(case.words)) + 1):
        floor: _Key | None = _line_floor(costs, count, widths[-1])
        if floor is None:
            continue
        for fx in widths:
            if _lower_bound(case, weights, (count, fx), floor) >= best:
                continue
            fewest: int | None = _fewest_fitting_lines(costs, fx)
            solver: _Solver = _Solver(costs, count, fx, fitting=fewest is not None and count >= fewest)
            cuts: tuple[int, ...] | None = solver.best_cuts()
            if cuts is None:
                continue
            layouts: list[Layout] = [_evaluate(case, cuts, scale) for scale in _heights(case, fx)]
            found.extend(layouts)
            best = min([best, *((layout.rescue, layout.score(weights)) for layout in layouts)])
    return found


def _line_floor(costs: _Costs, count: int, fx: float) -> _Key | None:
    fewest: int | None = _fewest_fitting_lines(costs, fx)
    return _Solver(costs, count, fx, fitting=fewest is not None and count >= fewest, floor=True).best_key()


def _lower_bound(case: _Case, weights: Mapping[str, float], size: tuple[int, float], floor: _Key) -> _Bound:
    count, fx = size
    field: Field = case.field
    bounds: list[_Bound] = []
    for scale in _heights(case, fx):
        tall: int = int(field.height_lines is not None and count * scale.fy > field.height_lines)
        harms: dict[str, float] = _global_harms(field, count, scale)
        score: float = sum(weights.get(name, 0.0) * degree for name, degree in harms.items())
        bounds.append(((tall + floor[0], max(0, count - field.max_lines), floor[1]), score + floor[2]))
    return min(bounds)


def _programmed_widths(case: _Case) -> list[float]:
    if not case.field.scalable:
        return [1.0]
    size: int = len(case.words)
    widths: list[float] = [
        case.measure(" ".join(case.words[start:end]), 1.0)
        for start in range(size)
        for end in range(start + 1, size + 1)
    ]
    return sorted({scale.fx for scale in _scale_options(_breakpoints(case.field, widths))}, reverse=True)


def _fewest_fitting_lines(costs: _Costs, fx: float) -> int | None:
    case: _Case = costs.case
    size: int = len(case.words)
    start: int = 0
    lines: int = 0
    while start < size:
        reach: int | None = None
        for end in range(start + 1, size + 1):
            if costs.size(start, end, fx)[0]:
                break
            if end == size or _allowed_cut(case, end - 1):
                reach = end
            if end - 1 in case.forced:
                break
        if reach is None:
            return None
        start, lines = reach, lines + 1
    return lines


def _heights(case: _Case, fx: float) -> list[Scale]:
    if not case.field.scalable or fx == 1.0:
        return [Scale()]
    return [Scale(fx, fx), Scale(fx)]


class _Costs:
    """Weighted harms of one line, split into the part fixed by its words and the part set by its width."""

    def __init__(self, case: _Case, weights: Mapping[str, float]) -> None:
        self.case: _Case = case
        self.top_longer: float = weights.get("top_longer", 0.0) if case.field.pyramid else 0.0
        self._weights: Mapping[str, float] = weights
        self.shape: Callable[[int, int, int, int], tuple[int, float]] = cache(self._shape)
        self.size: Callable[[int, int, float], tuple[int, int, float]] = cache(self._size)
        self.chars: Callable[[int, int], int] = cache(self._chars)

    def _shape(self, start: int, end: int, index: int, count: int) -> tuple[int, float]:
        part: _Part = _line_shape(self.case, (start, end, index, count))
        return len(part.flags), self._score(part)

    def _size(self, start: int, end: int, fx: float) -> tuple[int, int, float]:
        part: _Part = _line_size(self.case, start, end, fx)
        return part.outside, len(part.flags), self._score(part)

    def _chars(self, start: int, end: int) -> int:
        return _chars(" ".join(self.case.words[start:end]))

    def _score(self, part: _Part) -> float:
        return sum(self._weights.get(name, 0.0) * degree for name, degree in part.harms.items())


class _Solver:
    """Best split into a fixed number of lines at one horizontal scale; ``floor`` leaves out the quotation flags."""

    def __init__(self, costs: _Costs, count: int, fx: float, *, fitting: bool, floor: bool = False) -> None:
        self._costs: _Costs = costs
        self._case: _Case = costs.case
        self._count: int = count
        self._fx: float = fx
        self._fitting: bool = fitting
        self._floor: bool = floor
        self._best: Callable[[int, int, int], tuple[_Key, tuple[int, ...]] | None] = cache(self._solve)

    def best_cuts(self) -> tuple[int, ...] | None:
        """Return the cuts of the best split, or None when no allowed split exists."""
        result: tuple[_Key, tuple[int, ...]] | None = self._best(0, 0, -1)
        return None if result is None else result[1]

    def best_key(self) -> _Key | None:
        """Return the key of the best split, or None when no allowed split exists."""
        result: tuple[_Key, tuple[int, ...]] | None = self._best(0, 0, -1)
        return None if result is None else result[0]

    def _solve(self, start: int, index: int, above: int) -> tuple[_Key, tuple[int, ...]] | None:
        size: int = len(self._case.words)
        if index == self._count - 1:
            if self._skips_forced(start, size) or self._outside(start, size):
                return None
            return self._key(start, size, index, above), ()
        options: list[tuple[_Key, tuple[int, ...]]] = []
        for end in range(start + 1, size - (self._count - index - 1) + 1):
            if self._skips_forced(start, end) or self._outside(start, end):
                break
            if not _allowed_cut(self._case, end - 1):
                continue
            line: int = self._costs.chars(start, end) if self._costs.top_longer else -1
            rest: tuple[_Key, tuple[int, ...]] | None = self._best(end, index + 1, line)
            if rest is None:
                continue
            key: _Key = self._key(start, end, index, above)
            options.append(((key[0] + rest[0][0], key[1] + rest[0][1], key[2] + rest[0][2]), (end - 1, *rest[1])))
        return min(options, default=None, key=lambda option: option[0])

    def _skips_forced(self, start: int, end: int) -> bool:
        return any(start <= cut < end - 1 for cut in self._case.forced)

    def _outside(self, start: int, end: int) -> bool:
        return self._fitting and bool(self._costs.size(start, end, self._fx)[0])

    def _key(self, start: int, end: int, index: int, above: int) -> _Key:
        shape_flags, shape_score = self._costs.shape(start, end, index, self._count)
        outside, size_flags, size_score = self._costs.size(start, end, self._fx)
        score: float = shape_score + size_score
        if above >= 0:
            score += self._costs.top_longer * max(0, above - self._costs.chars(start, end))
        return outside, shape_flags + (0 if self._floor else size_flags), score
