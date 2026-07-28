"""Tag-safe text operations on ASS/SRT event text."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final

__all__ = [
    "is_drawing",
    "replace_visible_text",
    "visible_text",
    "visible_verses",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_RE_TAG_BLOCK: Final[re.Pattern[str]] = re.compile(r"\{[^}]*\}")
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

_BREAK_TOKENS: Final[frozenset[str]] = frozenset(("\\N", "\\n", "\n", "\r\n"))
"""ASS and SRT line-break tokens."""

_ASS_HARD_SPACE: Final[str] = "\\h"
"""ASS non-breaking hard-space token."""

_ZERO_WIDTH_JOINER: Final[str] = "\u200d"
"""Unicode joiner that binds adjacent emoji code points into one grapheme."""

_RE_EMPHASIS_COMMAND: Final[re.Pattern[str]] = re.compile(r"\\(?P<style>[ibus])(?P<state>-?1|0)")
"""ASS italic, bold, underline, or strikeout state command."""

_GRAPHEME_EXTENDER_RANGES: Final[tuple[tuple[int, int], ...]] = (
    (0xFE00, 0xFE0F),
    (0xE0100, 0xE01EF),
    (0x1F3FB, 0x1F3FF),
)
"""Unicode ranges for variation selectors and emoji skin-tone modifiers."""

_REGIONAL_INDICATOR_RANGE: Final[tuple[int, int]] = (0x1F1E6, 0x1F1FF)
"""Unicode regional indicators paired into flag grapheme clusters."""


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


def is_drawing(text: str) -> bool:
    """Tell whether an event's raw text is a vector drawing."""
    return bool(_RE_DRAW_TAG.search(text))


def visible_text(text: str) -> str:
    """Return the human-visible text of an event as a single line.

    Removes ``{...}`` override blocks and HTML-style tags, normalises ASS
    break escapes and whitespace runs to single spaces, and strips the ends.
    """
    without_tags = _RE_TAG_BLOCK.sub("", text)
    without_html = _RE_HTML_TAG.sub("", without_tags)
    normalised = _RE_SOFT_BREAKS.sub(" ", without_html)
    return _RE_SPACES.sub(" ", normalised).strip()


def visible_verses(text: str) -> tuple[str, ...]:
    """Return visible source verses while retaining authored line boundaries."""
    layout = _parse_layout(text)
    return tuple(_RE_SPACES.sub(" ", segment).strip() for segment in layout.segments)


def replace_visible_text(text: str, new_text: str) -> str:
    """Replace visible text while retaining authored formatting anchors.

    Args:
        text: Raw event text with formatting and layout metadata.
        new_text: Replacement for the visible part.

    Returns:
        Rebuilt text with tags and hard spaces anchored to the translation.
    """
    if visible_text(text) == visible_text(new_text):
        return text
    source = _parse_layout(text)
    target = _parse_layout(new_text)
    tags = _map_anchors(source.tags, source.segments, target.segments)
    tags = _snap_emphasis_anchors(tags, target.segments)
    hard_spaces = _map_anchors(source.hard_spaces, source.segments, target.segments)
    rendered = [_render_segment(segment, index, tags, hard_spaces) for index, segment in enumerate(target.segments)]
    breaks = source.breaks if len(source.segments) == len(target.segments) else target.breaks
    return _join_segments(rendered, breaks)


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


def _snap_emphasis_anchors(
    anchors: tuple[_Anchor, ...],
    target: tuple[str, ...],
) -> tuple[_Anchor, ...]:
    """Move paired emphasis commands away from translated word interiors."""
    profiles = tuple(_emphasis_profile(anchor.value) for anchor in anchors)
    paired: set[int] = set()
    stacks: dict[frozenset[str], list[int]] = {}
    for index, profile in enumerate(profiles):
        if profile is None:
            continue
        styles, state = profile
        if state == "open":
            stacks.setdefault(styles, []).append(index)
            continue
        openings = stacks.get(styles)
        if openings:
            paired.update((openings.pop(), index))
    snapped: list[_Anchor] = []
    for index, (anchor, profile) in enumerate(zip(anchors, profiles, strict=True)):
        if index not in paired or profile is None:
            snapped.append(anchor)
            continue
        _, state = profile
        spans = _word_spans(target[anchor.segment])
        if not spans:
            snapped.append(anchor)
            continue
        offset = (
            _closing_boundary(anchor.offset, spans) if state == "close" else _opening_boundary(anchor.offset, spans)
        )
        snapped.append(_Anchor(anchor.segment, offset, anchor.value))
    return _monotonic_anchors(tuple(snapped))


def _emphasis_profile(tag: str) -> tuple[frozenset[str], str] | None:
    """Classify a block containing only emphasis commands."""
    if not tag.startswith("{") or not tag.endswith("}"):
        return None
    body = tag[1:-1]
    commands = tuple(_RE_EMPHASIS_COMMAND.finditer(body))
    if not commands or "".join(command.group(0) for command in commands) != body:
        return None
    states = {"close" if command.group("state") == "0" else "open" for command in commands}
    if len(states) != 1:
        return None
    styles = frozenset(command.group("style") for command in commands)
    return styles, states.pop()


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
    """Return non-whitespace word spans in grapheme offsets."""
    graphemes = _graphemes(text)
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for index, grapheme in enumerate(graphemes):
        if grapheme.isspace():
            if start is not None:
                spans.append((start, index))
                start = None
        elif start is None:
            start = index
    if start is not None:
        spans.append((start, len(graphemes)))
    return tuple(spans)


def _opening_boundary(offset: int, spans: tuple[tuple[int, int], ...]) -> int:
    """Snap an opening emphasis command to the next containing word start."""
    for start, end in spans:
        if offset <= start or offset < end:
            return start
    return spans[-1][0]


def _closing_boundary(offset: int, spans: tuple[tuple[int, int], ...]) -> int:
    """Snap a closing emphasis command to the preceding containing word end."""
    previous_end = 0
    for start, end in spans:
        if offset <= start:
            return previous_end
        if offset <= end:
            return end
        previous_end = end
    return spans[-1][1]


def _render_segment(
    text: str,
    segment_index: int,
    tags: tuple[_Anchor, ...],
    hard_spaces: tuple[_Anchor, ...],
) -> str:
    """Insert mapped tags and hard spaces into one translated verse."""
    graphemes = _graphemes(text)
    tag_map: dict[int, list[str]] = {}
    for anchor in tags:
        if anchor.segment == segment_index:
            tag_map.setdefault(anchor.offset, []).append(anchor.value)
    hard_offsets = [anchor.offset for anchor in hard_spaces if anchor.segment == segment_index]
    replacements, insertions = _hard_space_positions(graphemes, hard_offsets)
    parts: list[str] = []
    for offset in range(len(graphemes) + 1):
        parts.extend(tag_map.get(offset, ()))
        if offset in insertions:
            parts.append("\\h")
        if offset < len(graphemes):
            parts.append("\\h" if offset in replacements else graphemes[offset])
    return "".join(parts)


def _hard_space_positions(
    graphemes: tuple[str, ...],
    offsets: list[int],
) -> tuple[set[int], set[int]]:
    """Choose nearest whitespace replacements without splitting target words."""
    spaces = [index for index, grapheme in enumerate(graphemes) if grapheme.isspace()]
    replacements: set[int] = set()
    insertions: set[int] = set()
    for offset in offsets:
        available = [index for index in spaces if index not in replacements]
        if available:
            replacements.add(min(available, key=lambda index: abs(index - offset)))
    return replacements, insertions


def _grapheme_count(text: str) -> int:
    """Count common Unicode clusters used as safe insertion boundaries."""
    return len(_graphemes(text))


def _graphemes(text: str) -> tuple[str, ...]:
    """Group combining marks and joined emoji into insertion-safe clusters."""
    clusters: list[str] = []
    for character in text:
        if not clusters:
            clusters.append(character)
            continue
        previous = clusters[-1]
        if (
            _extends_grapheme(character)
            or character == _ZERO_WIDTH_JOINER
            or previous.endswith(_ZERO_WIDTH_JOINER)
            or (previous == "\r" and character == "\n")
            or (_is_regional_indicator(character) and len(previous) == 1 and _is_regional_indicator(previous))
        ):
            clusters[-1] += character
        else:
            clusters.append(character)
    return tuple(clusters)


def _extends_grapheme(character: str) -> bool:
    """Tell whether a code point extends the preceding grapheme cluster."""
    code_point = ord(character)
    return (
        bool(unicodedata.combining(character))
        or unicodedata.category(character) in {"Mc", "Me", "Mn"}
        or any(start <= code_point <= end for start, end in _GRAPHEME_EXTENDER_RANGES)
    )


def _is_regional_indicator(character: str) -> bool:
    """Tell whether a code point is one half of a Unicode flag pair."""
    start, end = _REGIONAL_INDICATOR_RANGE
    return start <= ord(character) <= end


def _join_segments(segments: list[str], breaks: tuple[str, ...]) -> str:
    """Join rendered segments with their selected authored break tokens."""
    parts: list[str] = []
    for index, segment in enumerate(segments):
        if index:
            parts.append(breaks[index - 1])
        parts.append(segment)
    return "".join(parts)
