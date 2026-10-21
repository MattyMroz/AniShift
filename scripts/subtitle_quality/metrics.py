"""Pure subtitle quality metrics over paired English source and Polish output events."""

from __future__ import annotations

import math
import re
from bisect import bisect_left
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Final

from anishift.services.subtitles.classifier import Category, classify_styles
from anishift.services.subtitles.geometry import RenderProfile
from anishift.services.subtitles.text import is_drawing, visible_text, visible_verses

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pysubs2 import SSAEvent, SSAFile

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_LINE_CHARS: Final[int] = 42
"""Longest comfortable subtitle line in characters."""

MAX_LINES: Final[int] = 2
"""Most lines one dialogue event should show."""

ORPHAN_WORDS: Final[frozenset[str]] = frozenset("aiouwz")
"""Polish one-letter words that must not end a line."""

CPS_LIMITS: Final[tuple[int, ...]] = (15, 17, 20)
"""Reading-speed thresholds in characters per second."""

WIDTH_TOLERANCE: Final[float] = 0.10
"""Relative growth of a sign's rendered width tolerated before it counts as wider."""

OVERLAP_BADNESS: Final[float] = 0.5
"""Badness added to a sign that newly overlaps another sign."""

ORPHAN_BADNESS: Final[int] = 10
"""Badness of one line ending with a one-letter word, in characters."""

EXTRA_LINE_BADNESS: Final[int] = 10
"""Badness of every line above the limit, in characters."""

TOP_FRACTION: Final[float] = 1 / 3
"""Upper share of the screen treated as top placement."""

_RE_POSITIONED: Final[re.Pattern[str]] = re.compile(r"\\(?:pos|move)\(")
"""Explicit position or movement tag."""

_RE_SIGN_TAG: Final[re.Pattern[str]] = re.compile(r"\\(?:pos|move|i?clip)\(")
"""Typesetting tag that makes a sign worth rendering."""

_RE_CLIP: Final[re.Pattern[str]] = re.compile(r"\\i?clip\(")
"""Rectangular or vector clip tag."""

_RE_ANIMATED: Final[re.Pattern[str]] = re.compile(r"\\(?:move|t|fade)\(")
"""Tag changing a sign's position, shape or visibility over its lifetime."""

NUMBER: Final[str] = r"\s*(-?(?:\d+(?:\.\d*)?|\.\d+))\s*"
"""Regex capturing one ASS tag number argument with surrounding spaces."""

_RE_ANY_CLIP: Final[re.Pattern[str]] = re.compile(r"\\i?clip\([^)]*\)")
"""Whole clip tag of any kind."""

_RE_RECT_CLIP: Final[re.Pattern[str]] = re.compile(rf"\\clip\({NUMBER},{NUMBER},{NUMBER},{NUMBER}\)")
"""Rectangular clip tag with its corner coordinates."""

_RE_POS_Y: Final[re.Pattern[str]] = re.compile(rf"\\(?:pos|move)\({NUMBER},{NUMBER}")
"""Vertical coordinate of the first position or movement tag."""

_RE_ALIGN: Final[re.Pattern[str]] = re.compile(r"\\an([1-9])")
"""Numpad alignment override."""

_RE_LEGACY_TOP: Final[re.Pattern[str]] = re.compile(r"\\a(?:5|6|7)(?![0-9])")
"""Legacy SSA alignment override placing the line at the top."""

_RE_BLOCK: Final[re.Pattern[str]] = re.compile(r"\{[^}]*\}")
"""One override-tag block."""

_RE_BLOCK_RUN: Final[re.Pattern[str]] = re.compile(r"(?:\{[^}]*\})+")
"""Run of adjacent override-tag blocks acting as one boundary."""

_RE_STYLE_TAG: Final[re.Pattern[str]] = re.compile(r"\\(?:[ibus]-?\d+|[1-4]?c&H[0-9A-Fa-f]+&?|r[^\\}]*|fn[^\\}]*)")
"""Style-changing tag: emphasis, colour, reset or font."""

_RE_SIGN_ACTOR: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:signs?|text|sfx|ts|typeset|title|caption|note)\b", re.IGNORECASE
)
"""Actor field marking a line as on-screen text rather than speech."""

_TOP_ALIGNMENTS: Final[frozenset[int]] = frozenset((7, 8, 9))
"""Numpad alignments at the top of the screen."""


type Box = tuple[int, int, int, int]
"""Rendered extent ``(left, top, right, bottom)`` in script pixels."""

type Size = tuple[int, int]
"""Script resolution ``(width, height)``."""

type Span = tuple[int, int]
"""Event timing ``(start, end)`` in milliseconds."""


@dataclass(frozen=True, slots=True)
class Sign:
    """One paired positioned sign with its full unclipped rendered extents and clip rectangles."""

    source_index: int
    output_index: int
    start: int
    end: int
    style: str
    source_text: str
    output_text: str
    has_clip: bool = False
    animated: bool = False
    source_clip: Box | None = None
    output_clip: Box | None = None
    source_box: Box | None = None
    output_box: Box | None = None
    font_fallback: bool = False

    @property
    def rendered(self) -> bool:
        """Tell whether both full extents were measured."""
        return self.source_box is not None and self.output_box is not None

    @property
    def visible_known(self) -> bool:
        """Tell whether the visible extent follows from the full extent and a static rectangular clip."""
        if not self.has_clip:
            return True
        return self.source_clip is not None and self.output_clip is not None and not self.animated

    @property
    def source_visible(self) -> Box | None:
        """Return the visible source extent, None when fully clipped or not rendered."""
        return visible_box(self.source_box, self.source_clip)

    @property
    def output_visible(self) -> Box | None:
        """Return the visible output extent, None when fully clipped or not rendered."""
        return visible_box(self.output_box, self.output_clip)


@dataclass(frozen=True, slots=True)
class SignFinding:
    """Derived sign metrics comparable across episodes."""

    sign: Sign
    length_ratio: float
    width_ratio: float | None
    overflow_px: int
    new_offscreen_px: int
    new_overlaps: int
    badness: float
    offscreen_measured: bool = True
    overlap_measured: bool = True


@dataclass(frozen=True, slots=True)
class BreakCheck:
    """Line-breaking shape of one dialogue event."""

    index: int
    start: int
    end: int
    text: str
    lines: int
    max_len: int
    balance: float
    orphans: int
    long_lines: int

    @property
    def badness(self) -> float:
        """Return a combined line-breaking badness in characters."""
        extra_lines: int = max(0, self.lines - MAX_LINES)
        overflow: int = max(0, self.max_len - MAX_LINE_CHARS)
        return overflow + ORPHAN_BADNESS * self.orphans + EXTRA_LINE_BADNESS * extra_lines


@dataclass(frozen=True, slots=True)
class StyleCheck:
    """Style-tag agreement of one paired event."""

    index: int
    start: int
    mismatch: bool
    emptied: int
    split_words: bool = False
    added: bool = False


@dataclass(frozen=True, slots=True)
class ClassificationRow:
    """Features and classifier verdict of one source line for manual labelling."""

    index: int
    start: int
    end: int
    style: str
    actor: str
    verdict: str
    positioned: bool
    alignment: int
    top: bool
    chars: int
    overlaps: int
    flags: tuple[str, ...]


# ── Events and pairing ────────────────────────────────────────────────────────


def dialogue(subs: SSAFile) -> list[SSAEvent]:
    """Return the Dialogue events of a subtitle file in file order."""
    return [event for event in subs.events if event.type == "Dialogue"]


def play_size(subs: SSAFile) -> Size:
    """Return the script resolution libass renders the file at, completing missing header values as it does."""
    profile: RenderProfile = RenderProfile.from_subs(subs, None)
    return profile.play_res_x, profile.play_res_y


def style_verdicts(subs: SSAFile) -> dict[str, Category]:
    """Map every style to the AniShift classifier category."""
    return {verdict.style: verdict.category for verdict in classify_styles(subs)}


def pair_events(source: Sequence[SSAEvent], output: Sequence[SSAEvent]) -> list[tuple[int, int]]:
    """Pair source and output events with equal timing and style, in order."""
    source_keys: list[tuple[int, int, str]] = [(event.start, event.end, event.style) for event in source]
    output_keys: list[tuple[int, int, str]] = [(event.start, event.end, event.style) for event in output]
    matcher: SequenceMatcher[tuple[int, int, str]] = SequenceMatcher(None, source_keys, output_keys, autojunk=False)
    return [
        (block.a + offset, block.b + offset) for block in matcher.get_matching_blocks() for offset in range(block.size)
    ]


def concurrent_pairs(spans: Sequence[Span]) -> list[tuple[int, int]]:
    """Return every index pair of spans that overlap in time, found by a sweep over start times."""
    order: list[int] = sorted(range(len(spans)), key=lambda index: spans[index][0])
    starts: list[int] = [spans[index][0] for index in order]
    pairs: list[tuple[int, int]] = []
    for position, first in enumerate(order):
        stop: int = bisect_left(starts, spans[first][1], lo=position + 1)
        pairs.extend((first, second) for second in order[position + 1 : stop] if spans[first][0] < spans[second][1])
    return pairs


def is_dialogue_line(event: SSAEvent, verdicts: dict[str, Category]) -> bool:
    """Tell whether an event is visible dialogue by its style verdict."""
    if verdicts.get(event.style) is not Category.DIALOG or is_drawing(event.text):
        return False
    return bool(visible_text(event.text))


# ── Metric 1: signs ───────────────────────────────────────────────────────────


def select_signs(
    source: Sequence[SSAEvent],
    output: Sequence[SSAEvent],
    pairs: Sequence[tuple[int, int]],
    verdicts: dict[str, Category],
) -> list[Sign]:
    """Return paired sign-style text events carrying position, movement or clip tags."""
    signs: list[Sign] = []
    for source_index, output_index in pairs:
        event: SSAEvent = source[source_index]
        if verdicts.get(event.style) is not Category.SIGN or is_drawing(event.text):
            continue
        source_text: str = visible_text(event.text)
        if not source_text or not _RE_SIGN_TAG.search(event.text):
            continue
        output_raw: str = output[output_index].text
        signs.append(
            Sign(
                source_index=source_index,
                output_index=output_index,
                start=event.start,
                end=event.end,
                style=event.style,
                source_text=source_text,
                output_text=visible_text(output_raw),
                has_clip=bool(_RE_CLIP.search(event.text) or _RE_CLIP.search(output_raw)),
                animated=bool(_RE_ANIMATED.search(event.text) or _RE_ANIMATED.search(output_raw)),
                source_clip=clip_rect(event.text),
                output_clip=clip_rect(output_raw),
            )
        )
    return signs


def clip_rect(text: str) -> Box | None:
    """Return the rectangle of the effective clip when it is a plain ``\\clip(x1,y1,x2,y2)``."""
    clips: list[str] = _RE_ANY_CLIP.findall(text)
    match: re.Match[str] | None = _RE_RECT_CLIP.fullmatch(clips[-1]) if clips else None
    if match is None:
        return None
    x1, y1, x2, y2 = (round(float(match.group(index))) for index in range(1, 5))
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def visible_box(box: Box | None, clip: Box | None) -> Box | None:
    """Intersect a full extent with a rectangular clip; None when nothing stays visible."""
    if box is None or clip is None:
        return box
    left, top = max(box[0], clip[0]), max(box[1], clip[1])
    right, bottom = min(box[2], clip[2]), min(box[3], clip[3])
    if left >= right or top >= bottom:
        return None
    return left, top, right, bottom


def offscreen_px(box: Box, size: Size) -> int:
    """Return how many pixels a box extends beyond the screen on all sides."""
    left, top, right, bottom = box
    width, height = size
    return max(0, -left) + max(0, -top) + max(0, right - width) + max(0, bottom - height)


def _intersects(first: Box | None, second: Box | None) -> bool:
    if first is None or second is None:
        return False
    return first[0] < second[2] and second[0] < first[2] and first[1] < second[3] and second[1] < first[3]


def _static_geometry(sign: Sign) -> bool:
    return sign.rendered and sign.visible_known and not sign.animated


def new_overlaps(signs: Sequence[Sign]) -> list[tuple[int, bool]]:
    """Return per sign its new visible output overlaps and whether every concurrent pair was static and measured."""
    counts: list[int] = [0] * len(signs)
    measured: list[bool] = [True] * len(signs)
    for first_index, second_index in concurrent_pairs([(sign.start, sign.end) for sign in signs]):
        first, second = signs[first_index], signs[second_index]
        if not (_static_geometry(first) and _static_geometry(second)):
            measured[first_index] = measured[second_index] = False
            continue
        new: bool = not _intersects(first.source_visible, second.source_visible) and _intersects(
            first.output_visible, second.output_visible
        )
        counts[first_index] += new
        counts[second_index] += new
    return list(zip(counts, measured, strict=True))


def sign_findings(signs: Sequence[Sign], size: Size) -> list[SignFinding]:
    """Derive width, off-screen and overlap metrics for rendered signs."""
    overlaps: list[tuple[int, bool]] = new_overlaps(signs)
    return [_finding(sign, overlap, size) for sign, overlap in zip(signs, overlaps, strict=True)]


def _finding(sign: Sign, overlap: tuple[int, bool], size: Size) -> SignFinding:
    overlaps, overlap_measured = overlap
    length_ratio: float = len(sign.output_text) / len(sign.source_text)
    overlap_badness: float = OVERLAP_BADNESS * bool(overlaps)
    if sign.source_box is None or sign.output_box is None:
        return SignFinding(
            sign,
            length_ratio,
            None,
            0,
            0,
            overlaps,
            overlap_badness,
            offscreen_measured=False,
            overlap_measured=overlap_measured,
        )
    source_width: int = max(1, sign.source_box[2] - sign.source_box[0])
    output_width: int = sign.output_box[2] - sign.output_box[0]
    overflow: int = max(0, output_width - source_width)
    offscreen: int = _new_offscreen(sign, size) if sign.visible_known else 0
    badness: float = (overflow + offscreen) / source_width + overlap_badness
    return SignFinding(
        sign,
        length_ratio,
        output_width / source_width,
        overflow,
        offscreen,
        overlaps,
        badness,
        offscreen_measured=sign.visible_known,
        overlap_measured=overlap_measured,
    )


def _new_offscreen(sign: Sign, size: Size) -> int:
    source: Box | None = sign.source_visible
    output: Box | None = sign.output_visible
    source_px: int = offscreen_px(source, size) if source else 0
    output_px: int = offscreen_px(output, size) if output else 0
    return max(0, output_px - source_px)


def summarise_signs(findings: Sequence[SignFinding]) -> dict[str, object]:
    """Summarise sign findings; growth uses full text extents, off-screen and overlaps visible extents."""
    rendered: list[SignFinding] = [finding for finding in findings if finding.width_ratio is not None]
    ratios: list[float] = [finding.length_ratio for finding in findings]
    widths: list[float] = [finding.width_ratio for finding in rendered if finding.width_ratio is not None]
    return {
        "signs": len(findings),
        "rendered": len(rendered),
        "with_clip": sum(finding.sign.has_clip for finding in findings),
        "animated": sum(finding.sign.animated for finding in findings),
        "font_fallback": sum(finding.sign.font_fallback for finding in findings),
        "length_ratio": distribution(ratios),
        "width_ratio": distribution(widths),
        "wider_than_source": sum(ratio > 1 + WIDTH_TOLERANCE for ratio in widths),
        "new_offscreen": sum(finding.new_offscreen_px > 0 for finding in rendered),
        "offscreen_unmeasured": sum(not finding.offscreen_measured for finding in findings),
        "new_overlaps": sum(finding.new_overlaps > 0 for finding in findings),
        "overlap_unmeasured": sum(not finding.overlap_measured for finding in findings),
    }


# ── Metric 2: dialogue and sign split ─────────────────────────────────────────


def classification_rows(subs: SSAFile, verdicts: dict[str, Category]) -> list[ClassificationRow]:
    """Return one feature row per source Dialogue line with suspicion flags."""
    events: list[SSAEvent] = dialogue(subs)
    height: int = play_size(subs)[1]
    overlaps: list[int] = [0] * len(events)
    for first, second in concurrent_pairs([(event.start, event.end) for event in events]):
        overlaps[first] += 1
        overlaps[second] += 1
    return [
        _classification_row(index, event, overlaps[index], subs, verdicts, height) for index, event in enumerate(events)
    ]


def _classification_row(  # noqa: PLR0913 - one row gathers every labelling feature
    index: int,
    event: SSAEvent,
    overlaps: int,
    subs: SSAFile,
    verdicts: dict[str, Category],
    height: int,
) -> ClassificationRow:
    category: Category = verdicts.get(event.style, Category.UNCERTAIN)
    style_alignment: int = subs.styles[event.style].alignment if event.style in subs.styles else 2
    align_match: re.Match[str] | None = _RE_ALIGN.search(event.text)
    alignment: int = int(align_match.group(1)) if align_match else int(style_alignment)
    positioned: bool = bool(_RE_POSITIONED.search(event.text))
    top: bool = _inline_top(event.text, height)
    flags: tuple[str, ...] = _flags(event, category, positioned=positioned, top=top)
    return ClassificationRow(
        index=index,
        start=event.start,
        end=event.end,
        style=event.style,
        actor=event.name,
        verdict=category.value,
        positioned=positioned,
        alignment=alignment,
        top=top,
        chars=len(visible_text(event.text)),
        overlaps=overlaps,
        flags=flags,
    )


def _inline_top(text: str, height: int) -> bool:
    align_match: re.Match[str] | None = _RE_ALIGN.search(text)
    if align_match and int(align_match.group(1)) in _TOP_ALIGNMENTS:
        return True
    if _RE_LEGACY_TOP.search(text):
        return True
    pos_match: re.Match[str] | None = _RE_POS_Y.search(text)
    return pos_match is not None and float(pos_match.group(2)) < height * TOP_FRACTION


def _flags(event: SSAEvent, category: Category, *, positioned: bool, top: bool) -> tuple[str, ...]:
    sign_actor: bool = bool(_RE_SIGN_ACTOR.search(event.name))
    candidates: tuple[tuple[str, bool], ...] = (
        ("uncertain", category is Category.UNCERTAIN),
        ("sign_actor_on_dialog", sign_actor and category is Category.DIALOG),
        ("positioned_dialog", positioned and category is Category.DIALOG),
        ("top_dialog", top and category is Category.DIALOG),
        ("named_actor_on_sign", bool(event.name.strip()) and not sign_actor and category is Category.SIGN),
    )
    return tuple(name for name, active in candidates if active)


def summarise_flags(rows: Sequence[ClassificationRow]) -> dict[str, int]:
    """Count lines per suspicion flag and lines with any flag."""
    counts: dict[str, int] = {"lines": len(rows), "flagged": sum(bool(row.flags) for row in rows)}
    for row in rows:
        for flag in row.flags:
            counts[flag] = counts.get(flag, 0) + 1
    return counts


# ── Metric 3: style tags ──────────────────────────────────────────────────────


def style_tokens(text: str) -> tuple[str, ...]:
    """Return the ordered, normalised style-changing tags of an event."""
    tokens: list[str] = []
    for block in _RE_BLOCK.findall(text):
        tokens.extend(_normalise_tag(match.group(0)) for match in _RE_STYLE_TAG.finditer(block))
    return tuple(tokens)


def _normalise_tag(tag: str) -> str:
    head, separator, colour = tag.rstrip("&").replace("\\1c", "\\c").partition("&H")
    return head + separator + colour.upper()


def emptied_spans(source: str, output: str) -> int:
    """Count spans between tag blocks that hold visible source text but are empty in the output."""
    source_parts: list[str] = _RE_BLOCK.split(source)
    output_parts: list[str] = _RE_BLOCK.split(output)
    if len(source_parts) != len(output_parts):
        return 0
    return sum(
        1
        for source_part, output_part in zip(source_parts, output_parts, strict=True)
        if visible_text(source_part) and not visible_text(output_part)
    )


def word_splits(text: str) -> int:
    """Count tag blocks with a style tag that sit between two letters or digits of one word."""
    count: int = 0
    for block in _RE_BLOCK_RUN.finditer(text):
        if not _RE_STYLE_TAG.search(block.group(0)):
            continue
        before: str = visible_text(text[: block.start()] + "|")[:-1]
        after: str = visible_text("|" + text[block.end() :])[1:]
        count += bool(before[-1:].isalnum() and after[:1].isalnum())
    return count


def style_checks(
    source: Sequence[SSAEvent],
    output: Sequence[SSAEvent],
    pairs: Sequence[tuple[int, int]],
) -> list[StyleCheck]:
    """Compare style tags of paired events that carry any on either side."""
    checks: list[StyleCheck] = []
    for source_index, output_index in pairs:
        source_text: str = source[source_index].text
        output_text: str = output[output_index].text
        tokens: tuple[str, ...] = style_tokens(source_text)
        output_tokens: tuple[str, ...] = style_tokens(output_text)
        if not (tokens or output_tokens) or is_drawing(source_text):
            continue
        checks.append(
            StyleCheck(
                index=source_index,
                start=source[source_index].start,
                mismatch=tokens != output_tokens,
                emptied=emptied_spans(source_text, output_text),
                split_words=word_splits(output_text) > word_splits(source_text),
                added=not tokens,
            )
        )
    return checks


def summarise_styles(checks: Sequence[StyleCheck]) -> dict[str, int]:
    """Count paired events by style-tag disagreement between source and output."""
    return {
        "events_with_style_tags": len(checks),
        "tag_sequence_changed": sum(check.mismatch for check in checks),
        "emptied_span_events": sum(check.emptied > 0 for check in checks),
        "split_word_events": sum(check.split_words for check in checks),
        "added_style_events": sum(check.added for check in checks),
    }


# ── Metric 4: line breaks ─────────────────────────────────────────────────────


def break_check(index: int, event: SSAEvent) -> BreakCheck:
    """Measure the authored line shape of one dialogue event."""
    verses: list[str] = [verse for verse in visible_verses(event.text) if verse]
    lengths: list[int] = [len(verse) for verse in verses] or [0]
    orphans: int = sum(1 for verse in verses[:-1] if verse.split()[-1].casefold() in ORPHAN_WORDS)
    return BreakCheck(
        index=index,
        start=event.start,
        end=event.end,
        text=" / ".join(verses),
        lines=len(verses),
        max_len=max(lengths),
        balance=min(lengths) / max(lengths) if max(lengths) else 1.0,
        orphans=orphans,
        long_lines=sum(length > MAX_LINE_CHARS for length in lengths),
    )


def break_checks(events: Sequence[SSAEvent], verdicts: dict[str, Category]) -> list[BreakCheck]:
    """Measure line shape of every visible dialogue event."""
    return [break_check(index, event) for index, event in enumerate(events) if is_dialogue_line(event, verdicts)]


def summarise_breaks(checks: Sequence[BreakCheck]) -> dict[str, object]:
    """Summarise line counts, lengths, balance and orphan endings."""
    multi: list[BreakCheck] = [check for check in checks if check.lines > 1]
    return {
        "events": len(checks),
        "multi_line": len(multi),
        "over_max_lines": sum(check.lines > MAX_LINES for check in checks),
        "long_line_events": sum(check.long_lines > 0 for check in checks),
        "orphan_events": sum(check.orphans > 0 for check in checks),
        "max_line_len": distribution([float(check.max_len) for check in checks]),
        "balance_multi_line": distribution([check.balance for check in multi]),
    }


# ── Metric 5: reading speed ───────────────────────────────────────────────────


def cps(event: SSAEvent) -> float | None:
    """Return visible characters per second, or None for empty or zero-length events."""
    chars: int = len(visible_text(event.text))
    duration_s: float = (event.end - event.start) / 1000
    if chars == 0 or duration_s <= 0:
        return None
    return chars / duration_s


def cps_values(events: Sequence[SSAEvent], verdicts: dict[str, Category]) -> list[float]:
    """Return reading speed of every visible dialogue event."""
    values: list[float | None] = [cps(event) for event in events if is_dialogue_line(event, verdicts)]
    return [value for value in values if value is not None]


def common_dialogue(
    source: Sequence[SSAEvent],
    output: Sequence[SSAEvent],
    pairs: Sequence[tuple[int, int]],
    verdicts: dict[str, Category],
) -> tuple[list[tuple[int, int]], int]:
    """Return pairs of timed dialogue visible on both sides, and how many paired dialogue outputs are empty."""
    timed: list[tuple[int, int]] = [
        (source_index, output_index)
        for source_index, output_index in pairs
        if source[source_index].end > source[source_index].start and is_dialogue_line(source[source_index], verdicts)
    ]
    common: list[tuple[int, int]] = [pair for pair in timed if is_dialogue_line(output[pair[1]], verdicts)]
    return common, len(timed) - len(common)


def length_ratios(
    source: Sequence[SSAEvent],
    output: Sequence[SSAEvent],
    pairs: Sequence[tuple[int, int]],
) -> list[float]:
    """Return output-to-source visible length ratios of the given pairs."""
    return [
        len(visible_text(output[output_index].text)) / len(visible_text(source[source_index].text))
        for source_index, output_index in pairs
    ]


def summarise_cps(values: Sequence[float]) -> dict[str, object]:
    """Summarise reading speed with the share of events above each limit."""
    summary: dict[str, object] = dict(distribution(values))
    for limit in CPS_LIMITS:
        summary[f"over_{limit}"] = round(sum(value > limit for value in values) / len(values), 3) if values else 0.0
    return summary


# ── Statistics ────────────────────────────────────────────────────────────────


def percentile(values: Sequence[float], fraction: float) -> float:
    """Return the nearest-rank percentile, zero for no values."""
    if not values:
        return 0.0
    ordered: list[float] = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def distribution(values: Sequence[float]) -> dict[str, float]:
    """Return count, median, 90th percentile and maximum."""
    return {
        "count": len(values),
        "p50": round(percentile(values, 0.5), 2),
        "p90": round(percentile(values, 0.9), 2),
        "max": round(max(values, default=0.0), 2),
    }
