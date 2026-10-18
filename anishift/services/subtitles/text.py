"""Tag-safe text operations on ASS/SRT event text."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from itertools import accumulate, groupby, pairwise
from typing import TYPE_CHECKING, Final, Literal

from anishift.text.boundaries import BREAKABLE_SPACES
from anishift.text.graphemes import split_graphemes
from anishift.text.markers import SPAN_MARKER, span_marker

if TYPE_CHECKING:
    from pysubs2 import SSAStyle

__all__ = [
    "RE_TAG_BLOCK",
    "is_drawing",
    "marked_text",
    "reflow_visible_text",
    "replace_visible_text",
    "restore_markers",
    "visible_text",
    "visible_verses",
]

# ── Constants ─────────────────────────────────────────────────────────────────

RE_TAG_BLOCK: Final[re.Pattern[str]] = re.compile(r"\{[^}]*\}")
"""One ASS override-tag block, ``{...}``."""

_RE_DRAW_TAG: Final[re.Pattern[str]] = re.compile(chr(92) + chr(92) + r"p[1-9]")
"""An ASS ``\\p1``-``\\p9`` tag switching the line into vector-drawing mode."""

_RE_HTML_TAG: Final[re.Pattern[str]] = re.compile(r"<[^>]+>")
"""One HTML-style formatting tag as found in SRT text."""

_RE_SOFT_BREAKS: Final[re.Pattern[str]] = re.compile(r"\\[Nnh]")
"""ASS line-break and hard-space escapes, normalised to a space."""

_RE_SPACES: Final[re.Pattern[str]] = re.compile(r"\s+")
"""Any whitespace run, collapsed to a single space."""

_RE_LAYOUT_TOKEN: Final[re.Pattern[str]] = re.compile(r"(\{[^}]*\}|<[^>]+>|\\[Nnh]|\r?\n)")
"""Formatting or layout token embedded in subtitle event text."""

_RE_REFLOW_TOKEN: Final[re.Pattern[str]] = re.compile(_RE_LAYOUT_TOKEN.pattern + "|" + BREAKABLE_SPACES.pattern + "|.")
"""Layout tokens, breakable whitespace runs, and individual visible characters."""

_BREAK_TOKENS: Final[frozenset[str]] = frozenset(("\\N", "\\n", "\n", "\r\n"))
"""ASS and SRT line-break tokens."""

_ASS_HARD_SPACE: Final[str] = "\\h"
"""ASS non-breaking hard-space token."""

_MAX_MARKED_BOUNDARIES: Final[int] = 4
"""Most mid-verse style boundaries, two ranges, sent to the translator as span markers."""

_RE_EMPHASIS: Final[re.Pattern[str]] = re.compile(r"\\([ibus])([01])(?![0-9])")
"""ASS command switching italic, bold, underline or strikeout on or off, captured as attribute letter and state."""

type _Edge = Literal["start", "end", "inside", "outside"]
"""Where a source tag sits relative to the word graphemes around it."""

_EDGE_PRIORITY: Final[tuple[_Edge, ...]] = ("start", "end", "inside", "outside")
"""Edge kept when tags from both sides of a verse break meet at one position."""


@dataclass(frozen=True, slots=True)
class _Anchor:
    """One non-visible token anchored before a visible character offset."""

    segment: int
    offset: int
    value: str


@dataclass(frozen=True, slots=True)
class _TextLayout:
    """Visible segments and out-of-band formatting/layout metadata."""

    segments: tuple[str, ...]
    breaks: tuple[str, ...]
    tags: tuple[_Anchor, ...]
    hard_spaces: tuple[_Anchor, ...]


@dataclass(frozen=True, slots=True)
class _Boundary:
    """Source tags sharing one visible position and the word edge that position touches."""

    segment: int
    offset: int
    edge: _Edge
    values: tuple[str, ...]


def is_drawing(text: str) -> bool:
    """Tell whether an event's raw text is a vector drawing."""
    return bool(_RE_DRAW_TAG.search(text))


def visible_text(text: str, *, preserve_hard_spaces: bool = False) -> str:
    """Return the human-visible text of an event as a single line."""
    without_tags = RE_TAG_BLOCK.sub("", text)
    without_html = _RE_HTML_TAG.sub("", without_tags)
    if preserve_hard_spaces:
        without_html = without_html.replace(_ASS_HARD_SPACE, "\u00a0")
    normalised = _RE_SOFT_BREAKS.sub(" ", without_html)
    if preserve_hard_spaces:
        return BREAKABLE_SPACES.sub(" ", normalised).strip()
    return _RE_SPACES.sub(" ", normalised).strip()


def visible_verses(text: str) -> tuple[str, ...]:
    """Return visible source verses while retaining authored line boundaries."""
    layout = _parse_layout(text)
    return tuple(_RE_SPACES.sub(" ", segment).strip() for segment in layout.segments)


def marked_text(text: str, style: SSAStyle | None = None) -> str:
    """Return visible text with up to two mid-verse style ranges, over the event's base ``style``, as span markers."""
    layout: _TextLayout = _parse_layout(text)
    boundaries: tuple[_Boundary, ...] = _marked_boundaries(layout, style)
    if not boundaries:
        return visible_text(text)
    markers: tuple[str, ...] = _span_markers(len(boundaries))
    inserts: dict[tuple[int, int], str] = {}
    for boundary, marker in zip(boundaries, markers[: len(boundaries)], strict=True):
        graphemes: tuple[str, ...] = split_graphemes(layout.segments[boundary.segment])
        key: tuple[int, int] = (boundary.segment, _hugged_offset(graphemes, boundary.offset, closing=marker[1] == "/"))
        inserts[key] = inserts.get(key, "") + marker
    verses: list[str] = [_with_markers(segment, index, inserts) for index, segment in enumerate(layout.segments)]
    marked: str = " ".join(verses) + "".join(markers[len(boundaries) :])
    return _RE_SPACES.sub(" ", marked).strip()


def restore_markers(marked: str, verses: tuple[str, ...]) -> tuple[str, ...]:
    """Re-insert the span markers of ``marked`` into verses re-broken from its marker-free text."""
    if not verses or not SPAN_MARKER.search(marked):
        return verses
    openings: dict[int, str] = {}
    closings: dict[int, str] = {}
    seen: int = 0
    cursor: int = 0
    for match in SPAN_MARKER.finditer(marked):
        seen += sum(not character.isspace() for character in marked[cursor : match.start()])
        bucket: dict[int, str] = closings if match.group(0)[1] == "/" else openings
        bucket[seen] = bucket.get(seen, "") + match.group(0)
        cursor = match.end()
    restored: list[list[str]] = [[] for _ in verses]
    seen = 0
    for index, character in ((index, character) for index, verse in enumerate(verses) for character in verse):
        if character.isspace():
            restored[index].append(character)
            continue
        restored[index].extend((openings.pop(seen, ""), character))
        seen += 1
        restored[index].append(closings.pop(seen, ""))
    restored[-1].extend((*closings.values(), *openings.values()))
    return tuple("".join(parts) for parts in restored)


def replace_visible_text(text: str, new_text: str, style: SSAStyle | None = None) -> str:
    """Replace visible text while retaining authored formatting anchors over the event's base ``style``."""
    if visible_text(text) == visible_text(new_text):
        return text
    source = _parse_layout(text)
    target = _parse_layout(new_text)
    tags: tuple[_Anchor, ...] = _placed_tags(source, target, style)
    hard_spaces = _map_anchors(source.hard_spaces, source.segments, target.segments)
    rendered = [_render_segment(segment, index, tags, hard_spaces) for index, segment in enumerate(target.segments)]
    breaks = source.breaks if len(source.segments) == len(target.segments) else target.breaks
    return _join_segments(rendered, breaks)


def reflow_visible_text(text: str, verses: tuple[str, ...]) -> str:
    """Replace whitespace-only layout without moving tags relative to visible characters."""
    if is_drawing(text):
        return text
    if visible_text(text) != visible_text(" ".join(verses)):
        msg: str = "Reflow must preserve the visible words"
        raise ValueError(msg)
    boundaries: set[int] = set()
    boundary: int = 0
    for verse in verses[:-1]:
        boundary += len("".join(verse.split()))
        boundaries.add(boundary)
    parts: list[str] = []
    offset: int = 0
    previous_space: bool = False
    for match in _RE_REFLOW_TOKEN.finditer(text):
        token: str = match.group(0)
        space: bool = token in _BREAK_TOKENS or bool(BREAKABLE_SPACES.fullmatch(token))
        if space and offset and not previous_space:
            parts.append("\\N" if offset in boundaries else " ")
        if space:
            previous_space = True
            continue
        if token in {_ASS_HARD_SPACE, "\u00a0", "\u202f"}:
            parts.append(token)
            previous_space = False
            continue
        if RE_TAG_BLOCK.fullmatch(token) or _RE_HTML_TAG.fullmatch(token):
            parts.append(token)
            continue
        previous_space = False
        parts.append(token)
        offset += 1
    return "".join(parts)


def _parse_layout(text: str) -> _TextLayout:
    """Parse visible segments without sending formatting tokens downstream."""
    segments: list[str] = [""]
    breaks: list[str] = []
    tags: list[_Anchor] = []
    hard_spaces: list[_Anchor] = []
    cursor = 0
    for match in _RE_LAYOUT_TOKEN.finditer(text):
        segments[-1] += text[cursor : match.start()]
        token = match.group(0)
        offset = _grapheme_count(segments[-1])
        if token in _BREAK_TOKENS:
            breaks.append(token)
            segments.append("")
        elif token == _ASS_HARD_SPACE:
            hard_spaces.append(_Anchor(len(segments) - 1, offset, token))
            segments[-1] += " "
        else:
            tags.append(_Anchor(len(segments) - 1, offset, token))
        cursor = match.end()
    segments[-1] += text[cursor:]
    return _TextLayout(tuple(segments), tuple(breaks), tuple(tags), tuple(hard_spaces))


def _boundaries(layout: _TextLayout, *, merge_verses: bool) -> tuple[_Boundary, ...]:
    """Group source tags by position, across verse breaks when the verses are re-flowed."""
    graphemes: tuple[tuple[str, ...], ...] = tuple(split_graphemes(segment) for segment in layout.segments)
    starts: tuple[int, ...] = _segment_starts(layout.segments)
    boundaries: list[_Boundary] = []
    previous: tuple[int, int] | None = None
    for anchor in layout.tags:
        key: tuple[int, int] = (
            (0, starts[anchor.segment] + anchor.offset) if merge_verses else (anchor.segment, anchor.offset)
        )
        edge: _Edge = _edge(graphemes[anchor.segment], anchor.offset)
        if key == previous:
            last: _Boundary = boundaries[-1]
            edge = min(last.edge, edge, key=_EDGE_PRIORITY.index)
            boundaries[-1] = _Boundary(last.segment, last.offset, edge, (*last.values, anchor.value))
            continue
        boundaries.append(_Boundary(anchor.segment, anchor.offset, edge, (anchor.value,)))
        previous = key
    return tuple(boundaries)


def _edge(graphemes: tuple[str, ...], offset: int) -> _Edge:
    """Tell which side of a source position holds word graphemes."""
    before: bool = offset > 0 and _is_word_grapheme(graphemes[offset - 1])
    after: bool = offset < len(graphemes) and _is_word_grapheme(graphemes[offset])
    if before and after:
        return "inside"
    if after:
        return "start"
    return "end" if before else "outside"


def _marked_boundaries(layout: _TextLayout, style: SSAStyle | None) -> tuple[_Boundary, ...]:
    """Return the mid-verse word-edge boundaries sent as span markers, or none when markers do not fit."""
    lengths: tuple[int, ...] = tuple(_grapheme_count(segment) for segment in layout.segments)
    interior: tuple[_Boundary, ...] = tuple(
        boundary
        for boundary in _boundaries(layout, merge_verses=False)
        if 0 < boundary.offset < lengths[boundary.segment] and not all(map(_is_comment, boundary.values))
    )
    if len(interior) > _MAX_MARKED_BOUNDARIES or any(boundary.edge == "inside" for boundary in interior):
        return ()
    if not interior or _closes_a_range(layout, interior, style):
        return ()
    starts: tuple[int, ...] = _segment_starts(layout.segments)
    cuts: list[int] = [starts[boundary.segment] + boundary.offset for boundary in interior]
    if not all(_has_words(piece) for piece in _pieces(layout.segments, cuts)[1::2]):
        return ()
    return interior


def _is_comment(value: str) -> bool:
    """Tell whether a tag token is an override block without commands, an invisible comment."""
    return value.startswith("{") and "\\" not in value


def _closes_a_range(layout: _TextLayout, interior: tuple[_Boundary, ...], style: SSAStyle | None) -> bool:
    """Tell whether the first boundary's emphasis switch-off fails to open a marked range over the line's base."""
    first: _Boundary = interior[0]
    switched_off: set[str] = _switched(first, on=False)
    if not switched_off:
        return False
    styled: dict[str, bool] = (
        {} if style is None else {"i": style.italic, "b": style.bold, "u": style.underline, "s": style.strikeout}
    )
    starts: tuple[int, ...] = _segment_starts(layout.segments)
    active: set[str] = switched_off & _emphasis_at(layout, starts[first.segment] + first.offset - 1, styled)
    base: set[str] = _emphasis_at(layout, 0, styled) & _emphasis_at(layout, starts[-1] - 1, styled)
    reopened: set[str] = {letter for boundary in interior[1:] for letter in _switched(boundary, on=True)}
    return not active or not active <= base & reopened


def _switched(boundary: _Boundary, *, on: bool) -> set[str]:
    """Return the emphasis letters a boundary's tags switch on, or off."""
    return {
        letter for value in boundary.values for letter, state in _RE_EMPHASIS.findall(value) if (state == "1") == on
    }


def _emphasis_at(layout: _TextLayout, position: int, styled: dict[str, bool]) -> set[str]:
    """Return the emphasis letters on at a global grapheme ``position`` after the tags placed before it."""
    starts: tuple[int, ...] = _segment_starts(layout.segments)
    state: dict[str, bool] = dict(styled)
    for anchor in layout.tags:
        if starts[anchor.segment] + anchor.offset > position:
            break
        state.update((letter, value == "1") for letter, value in _RE_EMPHASIS.findall(anchor.value))
    return {letter for letter, enabled in state.items() if enabled}


def _span_markers(count: int) -> tuple[str, ...]:
    """Return the markers that wrap ``count`` boundaries as alternately opened and closed spans."""
    return tuple(span_marker(index // 2 + 1, closing=bool(index % 2)) for index in range(count + count % 2))


def _hugged_offset(graphemes: tuple[str, ...], offset: int, *, closing: bool) -> int:
    """Move a marker over whitespace so it touches the words it wraps."""
    while closing and offset > 0 and graphemes[offset - 1].isspace():
        offset -= 1
    while not closing and offset < len(graphemes) and graphemes[offset].isspace():
        offset += 1
    return offset


def _with_markers(segment: str, index: int, inserts: dict[tuple[int, int], str]) -> str:
    """Render one source verse with its span markers inserted."""
    graphemes: tuple[str, ...] = split_graphemes(segment)
    marked: str = "".join(inserts.get((index, offset), "") + grapheme for offset, grapheme in enumerate(graphemes))
    return marked + inserts.get((index, len(graphemes)), "")


def _placed_tags(source: _TextLayout, target: _TextLayout, style: SSAStyle | None) -> tuple[_Anchor, ...]:
    """Place every source tag on the translated text, honouring intact span markers."""
    boundaries: tuple[_Boundary, ...] = _boundaries(source, merge_verses=len(source.segments) != len(target.segments))
    positions: tuple[_Anchor, ...] = _map_anchors(
        tuple(_Anchor(boundary.segment, boundary.offset, "") for boundary in boundaries),
        source.segments,
        target.segments,
    )
    snapped: list[_Anchor] = []
    for position, boundary in zip(positions, boundaries, strict=True):
        floor: int = snapped[-1].offset if snapped and snapped[-1].segment == position.segment else -1
        snapped.append(_snapped(position, boundary.edge, target.segments, floor))
    positions = tuple(snapped)
    positions = _spread_inside(boundaries, positions, target.segments)
    marked: tuple[_Boundary, ...] = _marked_boundaries(source, style)
    markers: tuple[_Anchor, ...] | None = _marker_anchors(source, marked, target) if marked else None
    placed: dict[tuple[int, int], _Anchor] = (
        {}
        if markers is None
        else {(boundary.segment, boundary.offset): anchor for boundary, anchor in zip(marked, markers, strict=True)}
    )
    tags: list[_Anchor] = []
    for boundary, position in zip(boundaries, positions, strict=True):
        anchor: _Anchor = placed.get((boundary.segment, boundary.offset), position)
        tags.extend(_Anchor(anchor.segment, anchor.offset, value) for value in boundary.values)
    return _monotonic_anchors(tuple(tags))


def _marker_anchors(
    source: _TextLayout,
    marked: tuple[_Boundary, ...],
    target: _TextLayout,
) -> tuple[_Anchor, ...] | None:
    """Return translated positions of marked boundaries, or None when markers are broken or swallow the plain text."""
    markers: tuple[_Anchor, ...] = tuple(anchor for anchor in target.tags if SPAN_MARKER.fullmatch(anchor.value))
    if tuple(anchor.value for anchor in markers) != _span_markers(len(marked)):
        return None
    starts: tuple[int, ...] = _segment_starts(target.segments)
    offsets: list[int] = [starts[anchor.segment] + anchor.offset for anchor in markers]
    if any(offsets[index] >= offsets[index + 1] for index in range(0, len(offsets), 2)):
        return None
    source_starts: tuple[int, ...] = _segment_starts(source.segments)
    source_cuts: list[int] = [source_starts[boundary.segment] + boundary.offset for boundary in marked]
    if _has_unmarked_words(source.segments, source_cuts) and not _has_unmarked_words(
        target.segments, offsets[: len(marked)]
    ):
        return None
    return markers[: len(marked)]


def _has_unmarked_words(segments: tuple[str, ...], cuts: list[int]) -> bool:
    """Tell whether any word grapheme lies outside the spans that alternate between ``cuts``."""
    return any(_has_words(piece) for piece in _pieces(segments, cuts)[::2])


def _pieces(segments: tuple[str, ...], cuts: list[int]) -> list[tuple[str, ...]]:
    """Return the graphemes between consecutive global ``cuts`` across all verses."""
    graphemes: tuple[str, ...] = tuple(grapheme for segment in segments for grapheme in split_graphemes(segment))
    return [graphemes[start:end] for start, end in pairwise((0, *cuts, len(graphemes)))]


def _has_words(graphemes: tuple[str, ...]) -> bool:
    """Tell whether a grapheme run holds at least one word grapheme."""
    return any(_is_word_grapheme(grapheme) for grapheme in graphemes)


def _map_anchors(
    anchors: tuple[_Anchor, ...],
    source: tuple[str, ...],
    target: tuple[str, ...],
) -> tuple[_Anchor, ...]:
    """Map source offsets monotonically onto translated visible segments."""
    if len(source) == len(target):
        return tuple(_map_within_segment(anchor, source, target) for anchor in anchors)
    return tuple(_map_globally(anchor, source, target) for anchor in anchors)


def _map_within_segment(
    anchor: _Anchor,
    source: tuple[str, ...],
    target: tuple[str, ...],
) -> _Anchor:
    """Map one anchor proportionally inside the corresponding verse."""
    source_length = _grapheme_count(source[anchor.segment])
    target_length = _grapheme_count(target[anchor.segment])
    offset = _scaled_offset(anchor.offset, source_length, target_length)
    return _Anchor(anchor.segment, offset, anchor.value)


def _map_globally(
    anchor: _Anchor,
    source: tuple[str, ...],
    target: tuple[str, ...],
) -> _Anchor:
    """Map one anchor across layouts with different verse counts."""
    source_offset = sum(_grapheme_count(segment) for segment in source[: anchor.segment]) + anchor.offset
    target_offset = _scaled_offset(
        source_offset,
        sum(_grapheme_count(segment) for segment in source),
        sum(_grapheme_count(segment) for segment in target),
    )
    consumed = 0
    for segment_index, segment in enumerate(target):
        boundary = consumed + _grapheme_count(segment)
        if target_offset <= boundary or segment_index == len(target) - 1:
            return _Anchor(segment_index, target_offset - consumed, anchor.value)
        consumed = boundary
    return _Anchor(0, 0, anchor.value)


def _scaled_offset(offset: int, source_length: int, target_length: int) -> int:
    """Scale one bounded grapheme offset onto another string length."""
    if source_length <= 0:
        return 0
    return min(target_length, round(offset * target_length / source_length))


def _snapped(anchor: _Anchor, edge: _Edge, target: tuple[str, ...], floor: int) -> _Anchor:
    """Move a mapped tag out of a translated word unless it sat inside a source word, staying past ``floor``."""
    spans: tuple[tuple[int, int], ...] = _word_spans(target[anchor.segment])
    if edge == "inside" or not spans or not 0 < anchor.offset < _grapheme_count(target[anchor.segment]):
        return anchor
    offset: int
    if edge == "start":
        offset = _opening_boundary(anchor.offset, spans, floor)
    elif edge == "end":
        offset = _closing_boundary(anchor.offset, spans)
    else:
        offset = _nearest_boundary(anchor.offset, spans)
    return _Anchor(anchor.segment, offset, anchor.value)


def _spread_inside(
    boundaries: tuple[_Boundary, ...],
    anchors: tuple[_Anchor, ...],
    target: tuple[str, ...],
) -> tuple[_Anchor, ...]:
    """Give consecutive in-word effect tags distinct translated graphemes wherever the room allows."""
    spread: list[_Anchor] = list(anchors)
    end: int = 0
    runs: groupby[tuple[bool, int], tuple[_Boundary, _Anchor]] = groupby(
        zip(boundaries, anchors, strict=True), key=lambda pair: (pair[0].edge == "inside", pair[1].segment)
    )
    for (inside, segment), run in runs:
        start: int = end
        end = start + len(tuple(run))
        if not inside:
            continue
        lower: int = anchors[start - 1].offset if start and anchors[start - 1].segment == segment else 0
        upper: int = (
            anchors[end].offset
            if end < len(anchors) and anchors[end].segment == segment
            else _grapheme_count(target[segment])
        )
        offsets: list[int] = _spread([anchor.offset for anchor in anchors[start:end]], lower, upper)
        spread[start:end] = [_Anchor(segment, offset, "") for offset in offsets]
    return tuple(spread)


def _spread(offsets: list[int], lower: int, upper: int) -> list[int]:
    """Make offsets strictly increasing between ``lower`` and ``upper``, or spread them evenly when room is short."""
    room: int = upper - lower - 1
    if room <= 0:
        return [min(max(offset, lower), upper) for offset in offsets]
    if len(offsets) > room:
        return [lower + 1 + index * room // len(offsets) for index in range(len(offsets))]
    spread: list[int] = []
    previous: int = lower
    for index, offset in enumerate(offsets):
        previous = min(max(offset, previous + 1), upper - len(offsets) + index)
        spread.append(previous)
    return spread


def _monotonic_anchors(anchors: tuple[_Anchor, ...]) -> tuple[_Anchor, ...]:
    """Keep source tag order when several ranges collapse onto one word."""
    offsets: dict[int, int] = {}
    ordered: list[_Anchor] = []
    for anchor in anchors:
        offset = max(anchor.offset, offsets.get(anchor.segment, 0))
        offsets[anchor.segment] = offset
        ordered.append(_Anchor(anchor.segment, offset, anchor.value))
    return tuple(ordered)


def _word_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Return grapheme spans of each whitespace-separated word without its outer punctuation."""
    spans: list[tuple[int, int]] = []
    index: int = 0
    for _, group in groupby(split_graphemes(text), key=str.isspace):
        token: tuple[str, ...] = tuple(group)
        letters: list[int] = [index + offset for offset, grapheme in enumerate(token) if _is_word_grapheme(grapheme)]
        if letters:
            spans.append((letters[0], letters[-1] + 1))
        index += len(token)
    return tuple(spans)


def _is_word_grapheme(grapheme: str) -> bool:
    """Tell whether a grapheme is part of a word rather than whitespace or punctuation."""
    return not grapheme.isspace() and not unicodedata.category(grapheme[0]).startswith("P")


def _opening_boundary(offset: int, spans: tuple[tuple[int, int], ...], floor: int) -> int:
    """Snap an opening tag to the start of its containing or next word that lies past ``floor``."""
    for start, end in spans:
        if start > floor and (offset <= start or offset < end):
            return start
    return next((start for start, end in spans if offset <= start or offset < end), spans[-1][0])


def _closing_boundary(offset: int, spans: tuple[tuple[int, int], ...]) -> int:
    """Snap a closing tag to the end of its containing or preceding word."""
    previous_end: int = 0
    for start, end in spans:
        if offset <= start:
            return previous_end
        if offset <= end:
            return end
        previous_end = end
    return spans[-1][1]


def _nearest_boundary(offset: int, spans: tuple[tuple[int, int], ...]) -> int:
    """Snap a tag inside a word to that word's nearer edge."""
    for start, end in spans:
        if start < offset < end:
            return start if offset - start <= end - offset else end
    return offset


def _segment_starts(segments: tuple[str, ...]) -> tuple[int, ...]:
    """Return the global grapheme offset where every verse starts."""
    return tuple(accumulate((_grapheme_count(segment) for segment in segments), initial=0))


def _render_segment(
    text: str,
    segment_index: int,
    tags: tuple[_Anchor, ...],
    hard_spaces: tuple[_Anchor, ...],
) -> str:
    """Insert mapped tags and hard spaces into one translated verse."""
    graphemes = split_graphemes(text)
    tag_map: dict[int, list[str]] = {}
    for anchor in tags:
        if anchor.segment == segment_index:
            tag_map.setdefault(anchor.offset, []).append(anchor.value)
    hard_offsets = [anchor.offset for anchor in hard_spaces if anchor.segment == segment_index]
    replacements: set[int] = _hard_space_positions(graphemes, hard_offsets)
    parts: list[str] = []
    for offset in range(len(graphemes) + 1):
        parts.extend(tag_map.get(offset, ()))
        if offset < len(graphemes):
            parts.append("\\h" if offset in replacements else graphemes[offset])
    return "".join(parts)


def _hard_space_positions(graphemes: tuple[str, ...], offsets: list[int]) -> set[int]:
    """Choose nearest whitespace replacements without splitting target words."""
    spaces = [index for index, grapheme in enumerate(graphemes) if grapheme.isspace()]
    replacements: set[int] = set()
    for offset in offsets:
        available = [index for index in spaces if index not in replacements]
        if available:
            replacements.add(min(available, key=lambda index: abs(index - offset)))
    return replacements


def _grapheme_count(text: str) -> int:
    """Count extended grapheme clusters, the safe insertion boundaries."""
    return len(split_graphemes(text))


def _join_segments(segments: list[str], breaks: tuple[str, ...]) -> str:
    """Join rendered segments with their selected authored break tokens."""
    parts: list[str] = []
    for index, segment in enumerate(segments):
        if index:
            parts.append(breaks[index - 1])
        parts.append(segment)
    return "".join(parts)
