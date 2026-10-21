"""Layout core: one scored choice of lines and scale for any displayed text in a field."""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import cache, lru_cache
from itertools import accumulate, combinations, pairwise
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from anishift.services.subtitles.fuzzy import fall
from anishift.text.boundaries import BREAKABLE_SPACES
from anishift.text.gaps import DASHES, Gap, GapKind, gaps, list_markers, quote_spans
from anishift.text.graphemes import split_graphemes
from anishift.text.morphology import agrees, modifies, verb

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

__all__ = [
    "CHAR_WIDTH",
    "DIALOGUE_MAX_WIDTH",
    "HARMS",
    "MIN_SCALE",
    "WEIGHTS",
    "Field",
    "Flag",
    "Layout",
    "Measure",
    "Scale",
    "candidates",
    "chars_measure",
    "dialogue_field",
    "heading_break",
    "lay_out",
    "ranked",
    "sign_field",
]


type Measure = Callable[[str, float], float]
"""Width of one line at a horizontal scale, as a fraction of the script width."""


class Flag(StrEnum):
    """Rescue step or avoided harm, letters below the readable height included, a chosen layout carries."""

    OUTSIDE = "outside"
    EXTRA_LINE = "extra_line"
    BOUND_PAIR = "bound_pair"
    QUOTE = "quote"
    ORPHAN = "orphan"
    JOINED = "joined"
    MIXED = "mixed"
    SMALL = "small"
    SHRUNK = "shrunk"


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
    template: tuple[float, ...] = ()
    scalable: bool = False
    letter_height: float = 0.0
    height_lines: float | None = None
    pattern: tuple[float, ...] = ()
    breaks: frozenset[int] = frozenset()
    style_breaks: frozenset[int] = frozenset()
    style_rescue: bool = True
    speaker_lines: bool = False
    headings: bool = False
    fixed_height: bool = False
    blocks: tuple[int, ...] = ()
    runs: tuple[int, ...] = ()
    anchor_row: int = 0


@dataclass(frozen=True, slots=True)
class Layout:
    """Lines and scale of one candidate with its harm degrees, rescue level, report flags and block spacing.

    ``spacing`` is empty outside text blocks; for blocks it holds the empty lines before the first line, after each
    line but the last, and after the last line.
    """

    lines: tuple[str, ...]
    scale: Scale
    harms: Mapping[str, float]
    rescue: tuple[int, int, int]
    flags: frozenset[Flag]
    spacing: tuple[int, ...] = ()

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

_SIGN_LINES: Final[int] = 3
"""Fewest lines a displayed field allows, so a one-line source may still take two or three (catalogue calibration)."""

MIN_SCALE: Final[float] = 0.8
"""Smallest scale (either axis) a sign other than a song takes while any layout at or above it fits (owner 21.10)."""

_BOTTOM_ROW: Final[int] = 0
"""Alignment row of text anchored at its bottom edge: ``\\an1`` to ``\\an3``."""

_MIDDLE_ROW: Final[int] = 1
"""Alignment row of text centred on its anchor (numpad 4 to 6)."""

_TOP_ROW: Final[int] = 2
"""Alignment row of text anchored at its top edge (numpad 7 to 9)."""

_BLOCK_SCALE_STEP: Final[float] = 0.05
"""Horizontal scale step at which candidate bounds of text blocks are proposed for the core to score."""

_EMPTY_PER_LINE: Final[int] = 2
"""Empty lines taking the height of one text line: libass draws an empty line at half the font height."""

_SHAPED_WORD_SHARE: Final[float] = 0.5
"""Share of the widest source line a lone word must fill to follow the source shape of a sign, not be an orphan."""

_HEADING_WORDS: Final[int] = 3
"""Most words of a leading label ending in a colon where a multi-line displayed text prefers to end its first line."""

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
    "heading_joined",
    *(f"imbalance_{knot}" for knot in _IMBALANCE_KNOTS),
    *(f"shape_{knot}" for knot in _IMBALANCE_KNOTS),
    "top_longer",
    "extra_line",
    "missing_line",
    "squeeze",
    "shrink",
    "squeeze_deep",
    "shrink_deep",
    "small",
    "over_comfort",
    *(f"flag_{flag.value}" for flag in Flag if flag not in {Flag.OUTSIDE, Flag.EXTRA_LINE}),
)
"""Names of the harm degrees a layout is scored on, in the order of the calibration report."""


WEIGHTS: Final[Mapping[str, float]] = MappingProxyType(
    {
        "length_comfortable": 146.222,
        "length_wide": 122.678,
        "cut_sentence": 5.78707,
        "cut_clause": 5.78707,
        "cut_ellipsis": 5.78707,
        "cut_parenthetical": 5.78707,
        "cut_dash": 5.78707,
        "cut_before_subordinator": 5.78707,
        "cut_before_coordinator": 5.78707,
        "cut_before_preposition": 8.07075,
        "cut_phrase": 7.07694,
        "cut_auxiliary": 29.4486,
        "cut_modifier": 12.3777,
        "cut_abbreviation": 8.07075,
        "cut_after_opener": 23.4762,
        "cut_degree": 22.6936,
        "cut_particle": 19.471,
        "cut_prepositional": 9.03899,
        "cut_name": 29.4486,
        "cut_after_preposition": 32.4317,
        "cut_negation": 29.4486,
        "cut_reflexive": 29.4486,
        "cut_clitic": 29.4486,
        "cut_number": 29.4486,
        "cut_idiom": 32.4317,
        "cut_label": 29.4486,
        "cut_repetition": 29.4486,
        "cut_after_single_letter": 32.4317,
        "agreement": 8.1042,
        "heading_joined": 1.0,
        "imbalance_20": 0.354799,
        "shape_25": 3.351,
        "top_longer": 0.163951,
        "extra_line": 21.6051,
        "squeeze": 226.665,
        "shrink": 136.581,
        "over_comfort": 129.7,
        "imbalance_6": 0.330617,
        "shape_6": 2.21302e-06,
        "flag_quote": 19.6934,
        "flag_orphan": 19.4178,
        "flag_shrunk": 22.8036,
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


def sign_field(  # noqa: PLR0913 - one argument per field measurement
    *,
    source_lines: int,
    template: tuple[float, ...],
    letter_height: float,
    max_width: float = 1.0,
    height_lines: float | None = None,
    breaks: frozenset[int] = frozenset(),
    style_breaks: frozenset[int] = frozenset(),
) -> Field:
    """Return the field of displayed text: the source line count and line widths as its shape, scaling allowed."""
    lines: int = max(_SIGN_LINES, source_lines + 1)
    return Field(
        max_width=max_width,
        preferred_lines=source_lines,
        max_lines=lines,
        rescue_lines=lines,
        template=template,
        pattern=template,
        scalable=True,
        letter_height=letter_height,
        height_lines=height_lines,
        breaks=breaks,
        style_breaks=style_breaks,
        headings=True,
    )


def heading_break(words: Sequence[str]) -> int | None:
    """Return the gap after a leading label of one to three words ending in a colon, when more text follows it."""
    for index, word in enumerate(words[:_HEADING_WORDS]):
        if word.endswith(":"):
            return index if index < len(words) - 1 else None
    return None


def chars_measure(line: str, fx: float) -> float:
    """Measure a line by its graphemes when no render profile exists (text-layout spec §4.1, e10)."""
    return len(split_graphemes(line)) * CHAR_WIDTH * fx


def candidates(text: str, field: Field, measure: Measure, *, morphology: bool = True) -> list[Layout]:
    """Return every allowed layout of up to three lines, each at every scale the field may use."""
    blocked: list[Layout] = _block_layouts(text, field, measure, WEIGHTS, morphology=morphology) if field.blocks else []
    return blocked or _enumerated(_case(text, field, measure, morphology=morphology))


def lay_out(
    text: str, field: Field, measure: Measure, weights: Mapping[str, float] = WEIGHTS, *, morphology: bool = True
) -> Layout:
    """Return the layout with the lowest rescue level and then the lowest weighted harm."""
    return ranked(text, field, measure, weights, morphology=morphology)[0]


def ranked(
    text: str, field: Field, measure: Measure, weights: Mapping[str, float] = WEIGHTS, *, morphology: bool = True
) -> list[Layout]:
    """Return every enumerated layout and the best programmed ones, best first by rescue level and weighted harm."""
    blocked: list[Layout] = _block_layouts(text, field, measure, weights, morphology=morphology) if field.blocks else []
    if blocked:
        return blocked
    case: _Case = _case(text, field, measure, morphology=morphology)
    found: list[Layout] = _enumerated(case)
    if field.rescue_lines > _ENUMERATED_LINES:
        best: _Bound = min(((layout.rescue, layout.score(weights)) for layout in found), default=_NO_BOUND)
        found.extend(_programmed(case, weights, best))
    return sorted(found, key=lambda layout: (layout.rescue, layout.score(weights)))


# ── Text analysis ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Case:
    words: tuple[str, ...]
    gaps: tuple[Gap, ...]
    quotes: tuple[tuple[int, int], ...]
    forced: frozenset[int]
    released: frozenset[int]
    heading: frozenset[int]
    chars: int
    field: Field
    measure: Measure
    morphology: bool


def _case(text: str, field: Field, measure: Measure, *, morphology: bool) -> _Case:
    words: tuple[str, ...] = tuple(word for word in BREAKABLE_SPACES.split(text.strip()) if word)
    found: tuple[Gap, ...] = gaps(words, modifies if morphology else None, verb if morphology else None)
    turns: frozenset[int] = frozenset(index for index, gap in enumerate(found) if gap.turn and field.speaker_lines)
    cached: Measure = cache(measure)
    heading: int | None = heading_break(words) if field.headings else None
    forced: frozenset[int] = field.breaks | _list_breaks(words, field, cached) | turns
    fits: bool = len(forced) < field.rescue_lines
    return _Case(
        words=words,
        gaps=found,
        quotes=quote_spans(words),
        forced=forced if fits else frozenset(),
        released=frozenset() if fits else forced,
        heading=frozenset() if heading is None or found[heading].banned else frozenset({heading}),
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
    if case.field.fixed_height:
        return [
            scale
            for scale in _scales(replace(case, field=replace(case.field, fixed_height=False)), cuts)
            if scale.fy == 1
        ]
    widths: list[float] = [case.measure(line, 1.0) for line in _lines(case.words, cuts)]
    shaped: set[float] = {
        _template_width(case.field, index) / width
        for index, width in enumerate(widths)
        if width > 0 and case.field.template
    }
    return _scale_options(_breakpoints(case.field, widths, ()) | shaped)


def _breakpoints(field: Field, widths: Sequence[float], targets: Sequence[float]) -> set[float]:
    points: set[float] = {target / width for target in (field.max_width, *targets) for width in widths if width > 0}
    points.add(MIN_SCALE)
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
    if field.scalable and 0 < field.letter_height * min(scale.fx, scale.fy) < _SMALL_LETTERS[0]:
        flags.append(Flag.SMALL)
    if field.scalable and field.template and min(scale.fx, scale.fy) < MIN_SCALE:
        flags.append(Flag.SHRUNK)
    for flag in flags:
        harms[f"flag_{flag.value}"] = harms.get(f"flag_{flag.value}", 0.0) + 1.0
    rescue_flags: list[Flag] = [flag for flag, on in ((Flag.OUTSIDE, outside), (Flag.EXTRA_LINE, extra)) if on]
    return Layout(
        lines=_lines(case.words, cuts),
        scale=scale,
        harms=harms,
        rescue=(outside, extra, sum(flag in {Flag.SHRUNK, Flag.MIXED} for flag in flags)),
        flags=frozenset(flags + rescue_flags),
    )


def _line_part(case: _Case, place: tuple[int, int, int, int], scale: Scale) -> _Part:
    shape: _Part = _line_shape(case, place)
    size: _Part = _line_size(case, place[0], place[1], scale.fx)
    harms: dict[str, float] = shape.harms | size.harms | _over_template(case, place, scale.fx)
    return _Part(harms=harms, outside=size.outside, flags=shape.flags + size.flags)


def _over_template(case: _Case, place: tuple[int, int, int, int], fx: float) -> dict[str, float]:
    if not case.field.template:
        return {}
    start, end, index, _ = place
    width: float = case.measure(" ".join(case.words[start:end]), fx)
    return {"over_comfort": max(0.0, width - _template_width(case.field, index))}


def _template_width(field: Field, index: int) -> float:
    return field.template[min(index, len(field.template) - 1)]


def _line_shape(case: _Case, place: tuple[int, int, int, int]) -> _Part:
    start, end, index, count = place
    harms: dict[str, float] = _imbalance_harms(case, _chars(" ".join(case.words[start:end])), index, count)
    flags: list[Flag] = [Flag.JOINED for cut in case.released if start <= cut < end - 1]
    mixed: int = sum(start <= cut < end - 1 for cut in case.field.style_breaks - case.forced - case.heading)
    if count > 1 and any(start <= cut < end - 1 for cut in case.heading):
        harms["heading_joined"] = 1.0
    if mixed:
        harms["mixed_style"] = float(mixed)
    if mixed and case.field.style_rescue:
        flags.append(Flag.MIXED)
    if count > 1 and end - start == 1 and not _follows_shape(case, place) and not _exempt_orphan(case, start):
        flags.append(Flag.ORPHAN)
    if end < len(case.words):
        cut: int = end - 1
        gap: Gap = case.gaps[cut]
        harms[f"cut_{gap.kind.value}"] = 1.0
        if case.morphology and agrees(case.words[cut], case.words[end]):
            harms["agreement"] = 1.0
        if gap.protected and cut not in case.forced | case.released | case.heading:
            flags.append(Flag.BOUND_PAIR)
    return _Part(harms=harms, outside=0, flags=tuple(flags))


def _line_size(case: _Case, start: int, end: int, fx: float) -> _Part:
    field: Field = case.field
    text: str = " ".join(case.words[start:end])
    width: float = case.measure(text, fx)
    harms: dict[str, float] = _length_harms(field, width, _chars(text))
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
        harms["squeeze_deep"] = harms["squeeze"] ** 2
        harms["shrink_deep"] = harms["shrink"] ** 2
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
    name: str = "shape" if case.field.template else "imbalance"
    return {f"{name}_{knot}": max(0.0, deviation - knot / 2) for knot in _IMBALANCE_KNOTS}


def _follows_shape(case: _Case, place: tuple[int, int, int, int]) -> bool:
    start, _, _, count = place
    if not case.field.template or count > case.field.preferred_lines:
        return False
    return case.measure(case.words[start], 1.0) >= _SHAPED_WORD_SHARE * max(case.field.template)


def _exempt_orphan(case: _Case, start: int) -> bool:
    if start - 1 in case.forced | case.released | case.heading or (start > 0 and case.gaps[start - 1].turn):
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

_NO_BOUND: Final[_Bound] = ((sys.maxsize, sys.maxsize, sys.maxsize), math.inf)
"""Bound no layout reaches, before any layout is known."""

_NO_FLOOR: Final[_Key] = (0, 0, 0.0)
"""Partial layout key no line can go below."""


def _programmed(case: _Case, weights: Mapping[str, float], best: _Bound) -> list[Layout]:
    found: list[Layout] = []
    costs: _Costs = _Costs(case, weights)
    widths: list[float] = _programmed_widths(case)
    counts: range = range(_ENUMERATED_LINES + 1, min(case.field.rescue_lines, len(case.words)) + 1)
    for count in sorted(counts, key=lambda count: abs(count - case.field.preferred_lines)):
        if min(_lower_bound(case, weights, (count, fx), _NO_FLOOR) for fx in widths) >= best:
            continue
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
        if not any(start <= cut < end - 1 for cut in case.forced)
    ]
    points: set[float] = _breakpoints(case.field, widths, case.field.template)
    return sorted({scale.fx for scale in _scale_options(points)}, reverse=True)


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
    if case.field.fixed_height:
        return [Scale(fx)]
    return [Scale(fx, fx), Scale(fx)]


class _Costs:
    """Weighted harms of one line, split into the part fixed by its words and the part set by its width."""

    def __init__(self, case: _Case, weights: Mapping[str, float]) -> None:
        self.case: _Case = case
        self.top_longer: float = weights.get("top_longer", 0.0) if case.field.pyramid else 0.0
        self._weights: Mapping[str, float] = weights
        self.shape: Callable[[int, int, int, int], tuple[int, float]] = cache(self._shape)
        self.size: Callable[[int, int, float], tuple[int, int, float]] = cache(self._size)
        self.template: Callable[[int, int, float, int], float] = cache(self._template)
        self.chars: Callable[[int, int], int] = cache(self._chars)

    def _shape(self, start: int, end: int, index: int, count: int) -> tuple[int, float]:
        part: _Part = _line_shape(self.case, (start, end, index, count))
        return 0, self._score(part)

    def _size(self, start: int, end: int, fx: float) -> tuple[int, int, float]:
        part: _Part = _line_size(self.case, start, end, fx)
        return part.outside, 0, self._score(part)

    def _template(self, start: int, end: int, fx: float, index: int) -> float:
        harms: dict[str, float] = _over_template(self.case, (start, end, index, 0), fx)
        return sum(self._weights.get(name, 0.0) * degree for name, degree in harms.items())

    def _chars(self, start: int, end: int) -> int:
        return _chars(" ".join(self.case.words[start:end]))

    def _score(self, part: _Part) -> float:
        harms: float = sum(self._weights.get(name, 0.0) * degree for name, degree in part.harms.items())
        return harms + sum(self._weights.get(f"flag_{flag.value}", 0.0) for flag in part.flags)


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
        score: float = shape_score + size_score + self._costs.template(start, end, self._fx, index)
        if above >= 0:
            score += self._costs.top_longer * max(0, above - self._costs.chars(start, end))
        return outside, shape_flags + (0 if self._floor else size_flags), score


# ── Blocks ────────────────────────────────────────────────────────────────────


type _BlockKey = tuple[int, float]
"""Overflowing or bound cuts and weighted harm of the block fills and the cuts between them, summed."""


def _block_layouts(
    text: str, field: Field, measure: Measure, weights: Mapping[str, float], *, morphology: bool
) -> list[Layout]:
    words: tuple[str, ...] = tuple(word for word in BREAKABLE_SPACES.split(text.strip()) if word)
    found: tuple[Gap, ...] = gaps(words, modifies if morphology else None, verb if morphology else None)

    @cache
    def piece(block: int, start: int, end: int) -> tuple[_Case, Layout]:
        case: _Case = _case(
            " ".join(words[start:end]), _block_field(field, block, start, end), measure, morphology=morphology
        )
        return case, lay_out(" ".join(case.words), case.field, measure, weights, morphology=morphology)

    layouts: list[Layout] = []
    for bounds in _block_bounds(field, (words, found), measure, weights, morphology=morphology):
        edges: tuple[int, ...] = (0, *(cut + 1 for cut in bounds), len(words))
        pieces: list[tuple[_Case, Layout]] = [piece(block, *span) for block, span in enumerate(pairwise(edges))]
        fx: float = min(layout.scale.fx for _, layout in pieces)
        common: list[Layout] = [_rescaled(layout, case, fx) for case, layout in pieces]
        layouts.append(_joined(field, common, [found[cut] for cut in bounds], words, bounds, morphology=morphology))
    return sorted(layouts, key=lambda layout: (layout.rescue, layout.score(weights)))


def _block_bounds(
    field: Field,
    text: tuple[tuple[str, ...], tuple[Gap, ...]],
    measure: Measure,
    weights: Mapping[str, float],
    *,
    morphology: bool,
) -> list[tuple[int, ...]]:
    """Return candidate gaps ending each block but the last: the best by cut harms and block fill at each squeeze."""
    words, found = text
    count: int = len(field.blocks)
    if len(words) < count:
        return []
    if len(field.breaks) + 1 == sum(field.blocks):
        ends: list[int] = sorted(field.breaks)
        return [tuple(ends[sum(field.blocks[: block + 1]) - 1] for block in range(count - 1))]
    width: Callable[[int, int], float] = _span_width(words, measure)
    cuts: list[_BlockKey] = [_cut_key(words, found, cut, weights, morphology=morphology) for cut in range(len(found))]
    steps: range = range(round(MIN_SCALE / _BLOCK_SCALE_STEP), round(1 / _BLOCK_SCALE_STEP) + 1)
    return list(dict.fromkeys(_bounds_at(field, width, cuts, step * _BLOCK_SCALE_STEP, weights) for step in steps))


def _cut_key(
    words: Sequence[str], found: Sequence[Gap], cut: int, weights: Mapping[str, float], *, morphology: bool
) -> _BlockKey:
    gap: Gap = found[cut]
    agreement: bool = morphology and agrees(words[cut], words[cut + 1])
    return int(gap.protected), weights.get(f"cut_{gap.kind.value}", 0.0) + agreement * weights.get("agreement", 0.0)


def _bounds_at(
    field: Field, width: Callable[[int, int], float], cuts: Sequence[_BlockKey], fx: float, weights: Mapping[str, float]
) -> tuple[int, ...]:
    size: int = len(cuts) + 1
    count: int = len(field.blocks)

    @cache
    def best(block: int, start: int) -> tuple[_BlockKey, tuple[int, ...]]:
        if block == count - 1:
            return _fill_key(field, block, width(start, size) * fx, weights), ()
        options: list[tuple[_BlockKey, tuple[int, ...]]] = []
        for end in range(start + 1, size - (count - block - 1) + 1):
            fill: _BlockKey = _fill_key(field, block, width(start, end) * fx, weights)
            if fill[0] and options:
                break
            rest, ends = best(block + 1, end)
            options.append((_summed(fill, cuts[end - 1], rest), (end - 1, *ends)))
        return min(options)

    return best(0, 0)[1]


def _span_width(words: Sequence[str], measure: Measure) -> Callable[[int, int], float]:
    lengths: list[float] = [measure(word, 1.0) for word in words]
    starts: list[float] = [0.0, *accumulate(lengths)]
    space: float = max(0.0, measure(" ".join(words), 1.0) - starts[-1]) / max(1, len(words) - 1)
    return lambda start, end: starts[end] - starts[start] + space * (end - start - 1)


def _fill_key(field: Field, block: int, width: float, weights: Mapping[str, float]) -> _BlockKey:
    first: int = sum(field.blocks[:block])
    lines: int = field.blocks[block]
    room: float = sum(field.template[first : first + lines]) / lines
    options: list[_BlockKey] = []
    for total in range(lines, _block_cap(field, block) + 1):
        excess: float = max(0.0, width - total * room)
        score: float = weights.get("extra_line", 0.0) * (total - lines) + weights.get("over_comfort", 0.0) * excess
        options.append((int(width > total * field.max_width), score))
    return min(options)


def _summed(*keys: _BlockKey) -> _BlockKey:
    return sum(key[0] for key in keys), sum(key[1] for key in keys)


def _rescaled(piece: Layout, case: _Case, fx: float) -> Layout:
    if piece.scale.fx == fx:
        return piece
    counts: list[int] = [len(BREAKABLE_SPACES.split(line)) for line in piece.lines[:-1]]
    return _evaluate(case, tuple(end - 1 for end in accumulate(counts)), Scale(fx))


def _block_field(field: Field, block: int, start: int, end: int) -> Field:
    first: int = sum(field.blocks[:block])
    template: tuple[float, ...] = field.template[first : first + field.blocks[block]]
    lines: int = _block_cap(field, block)
    return replace(
        field,
        blocks=(),
        runs=(),
        template=template,
        pattern=template,
        preferred_lines=field.blocks[block],
        max_lines=lines,
        rescue_lines=lines,
        breaks=_inside(field.breaks, start, end),
        style_breaks=_inside(field.style_breaks, start, end),
        headings=field.headings and block == 0,
        fixed_height=True,
    )


def _inside(cuts: frozenset[int], start: int, end: int) -> frozenset[int]:
    return frozenset(cut - start for cut in cuts if start <= cut < end - 1)


def _block_cap(field: Field, block: int) -> int:
    lines: int = field.blocks[block]
    gap: int | None = _drawn_gap(field, block)
    return max(_SIGN_LINES, lines + 1) if gap is None else lines + field.runs[gap] // _EMPTY_PER_LINE


def _drawn_gap(field: Field, block: int) -> int | None:
    """Return the empty run a growing block takes its lines from, or None for a block growing away from the runs."""
    last: int = len(field.blocks) - 1
    if block == (0 if field.anchor_row == _BOTTOM_ROW else last) or (field.anchor_row == _MIDDLE_ROW and block == 0):
        return None
    return block - 1 if field.anchor_row == _BOTTOM_ROW else block


def _joined(  # noqa: PLR0913 - the block layouts with the gaps between them
    field: Field,
    pieces: Sequence[Layout],
    between: Sequence[Gap],
    words: Sequence[str],
    bounds: Sequence[int],
    *,
    morphology: bool,
) -> Layout:
    harms: dict[str, float] = {}
    for piece in pieces:
        for name, degree in piece.harms.items():
            harms[name] = harms.get(name, 0.0) + degree
    for gap, cut in zip(between, bounds, strict=True):
        harms[f"cut_{gap.kind.value}"] = harms.get(f"cut_{gap.kind.value}", 0.0) + 1.0
        if gap.protected:
            harms[f"flag_{Flag.BOUND_PAIR.value}"] = harms.get(f"flag_{Flag.BOUND_PAIR.value}", 0.0) + 1.0
        if morphology and agrees(words[cut], words[cut + 1]):
            harms["agreement"] = harms.get("agreement", 0.0) + 1.0
    rescue: tuple[int, int, int] = (
        sum(piece.rescue[0] for piece in pieces),
        sum(piece.rescue[1] for piece in pieces),
        sum(piece.rescue[2] for piece in pieces),
    )
    return Layout(
        lines=tuple(line for piece in pieces for line in piece.lines),
        scale=Scale(min(piece.scale.fx for piece in pieces)),
        harms=harms,
        rescue=rescue,
        flags=frozenset(flag for piece in pieces for flag in piece.flags),
        spacing=_block_spacing(field, [len(piece.lines) for piece in pieces]),
    )


def _block_spacing(field: Field, counts: Sequence[int]) -> tuple[int, ...]:
    runs: list[int] = list(field.runs)
    for block, count in enumerate(counts):
        gap: int | None = _drawn_gap(field, block)
        if gap is not None:
            runs[gap] -= _EMPTY_PER_LINE * (count - field.blocks[block])
    middle: bool = field.anchor_row == _MIDDLE_ROW
    spacing: list[int] = [_EMPTY_PER_LINE * max(0, counts[-1] - field.blocks[-1]) if middle else 0]
    for block, count in enumerate(counts):
        spacing.extend([0] * (count - 1))
        if block < len(runs):
            spacing.append(max(0, runs[block]))
    spacing.append(_EMPTY_PER_LINE * max(0, counts[0] - field.blocks[0]) if middle else 0)
    return tuple(spacing)
