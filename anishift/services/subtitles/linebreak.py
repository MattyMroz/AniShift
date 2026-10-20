"""Lay out translated dialogue with the layout core and measure tagged lines for it and for displayed text."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from functools import cache
from typing import TYPE_CHECKING, Final

from anishift.services.subtitles.geometry import measure_text, safe_width, style_changes, wrap_text
from anishift.services.subtitles.layout import (
    DIALOGUE_MAX_WIDTH,
    Field,
    Flag,
    Layout,
    chars_measure,
    dialogue_field,
    lay_out,
)
from anishift.services.subtitles.text import (
    RE_TAG_BLOCK,
    reflow_visible_text,
    replace_visible_text,
    restore_markers,
    visible_text,
)
from anishift.text.boundaries import BREAKABLE_SPACES
from anishift.text.markers import strip_span_markers

if TYPE_CHECKING:
    from pysubs2 import SSAEvent, SSAStyle

    from anishift.services.subtitles.geometry import RenderProfile, TextBox
    from anishift.services.subtitles.layout import Measure

# ── Constants ──────────────────────────────────────────────────────────────

_RE_WORD_BREAK: Final[re.Pattern[str]] = re.compile(r"(\{[^}]*\}|\\[Nn]|" + BREAKABLE_SPACES.pattern + ")")
"""Override block, line break escape or breakable whitespace run of tagged event text."""

NO_WRAP: Final[str] = "{\\q2}"
"""Override that stops libass from wrapping the lines the layout core chose."""

_RE_WRAP_BLOCK: Final[re.Pattern[str]] = re.compile(r"\{[^}]*\\q[^}]*\}")
"""Override block setting a wrap style; libass keeps the last one of the event."""


@dataclass(frozen=True, slots=True)
class DialogueLayout:
    """Laid-out event text of one dialogue line, the rescue steps its layout needed and its measurement quality."""

    text: str
    flags: frozenset[Flag]
    approximate: bool = False
    untagged: bool = False


def layout_dialogue(event: SSAEvent, text: str, profile: RenderProfile | None) -> DialogueLayout:
    """Lay out the unbroken translation ``text`` of a dialogue event with the layout core and place its tags."""
    tagged: str = tagged_line(event, text, profile)
    plain: str = visible_text(tagged, preserve_hard_spaces=True)
    words: tuple[str, ...] = tuple(word for word in BREAKABLE_SPACES.split(plain) if word)
    if profile is None:
        chosen: Layout = lay_out(plain, dialogue_field(), chars_measure)
        return DialogueLayout(reflow_visible_text(tagged, chosen.lines), chosen.flags)
    field: Field = dialogue_field(max_width=safe_width(event, profile, DIALOGUE_MAX_WIDTH) / profile.play_res_x)
    changes: tuple[bool, ...] = style_changes(event, tagged, profile)
    if len(changes) == len(words) - 1:
        field = replace(field, style_breaks=frozenset(index for index, change in enumerate(changes) if change))
    pieces: tuple[str, ...] | None = tagged_words(tagged, words)
    chosen = lay_out(plain, field, _measure(event, profile, words, pieces or words))
    laid_out: str = without_wrap(event, reflow_visible_text(tagged, chosen.lines), profile)
    approximate: bool = measure_text(event, laid_out, profile).status == "approximate"
    untagged: bool = pieces is None or len(changes) != len(words) - 1
    return DialogueLayout(laid_out, chosen.flags, approximate, untagged)


def tagged_line(event: SSAEvent, text: str, profile: RenderProfile | None) -> str:
    """Return the event text with the unbroken translation ``text`` in place of its visible text, tags kept."""
    plain: str = strip_span_markers(text)
    if visible_text(event.text) == visible_text(plain):
        return event.text
    style: SSAStyle | None = profile.styles.get(event.style) if profile is not None else None
    return replace_visible_text(event.text, restore_markers(text, (plain,))[0], style)


def tagged_measure(event: SSAEvent, tagged: str, profile: RenderProfile) -> Measure:
    """Return the measure of lines of the one-line ``tagged`` text, each with the tags that fall on it."""
    words: tuple[str, ...] = tuple(
        word for word in BREAKABLE_SPACES.split(visible_text(tagged, preserve_hard_spaces=True)) if word
    )
    return _measure(event, profile, words, tagged_words(tagged, words) or words)


def without_wrap(event: SSAEvent, text: str, profile: RenderProfile) -> str:
    """Return ``text`` with a no-wrap override when libass would wrap its lines automatically."""
    return text if wrap_text(event, text, profile) == text else _no_wrap(text)


def _no_wrap(text: str) -> str:
    blocks: list[re.Match[str]] = list(_RE_WRAP_BLOCK.finditer(text))
    if not blocks:
        return NO_WRAP + text
    end: int = blocks[-1].end()
    return text[:end] + NO_WRAP + text[end:]


def tagged_words(tagged: str, words: tuple[str, ...]) -> tuple[str, ...] | None:
    """Return each word of ``tagged`` with the tags attached to it, or None when its words differ from ``words``."""
    found: list[str] = [""]
    for piece in _RE_WORD_BREAK.split(tagged):
        if RE_TAG_BLOCK.fullmatch(piece) or not _RE_WORD_BREAK.fullmatch(piece):
            found[-1] += piece
        elif visible_text(found[-1]):
            found.append("")
    if len(found) > 1 and not visible_text(found[-1]):
        found[-2] += found.pop()
    visible: tuple[str, ...] = tuple(visible_text(word, preserve_hard_spaces=True) for word in found)
    return tuple(found) if visible == words else None


def _measure(event: SSAEvent, profile: RenderProfile, words: tuple[str, ...], tagged: tuple[str, ...]) -> Measure:
    spans: dict[str, list[str]] = {}
    prefix: str = ""
    for start in range(len(words)):
        for end in range(start + 1, len(words) + 1):
            spans.setdefault(" ".join(words[start:end]), []).append(prefix + " ".join(tagged[start:end]))
        prefix += "".join(RE_TAG_BLOCK.findall(tagged[start]))

    @cache
    def unscaled(line: str) -> TextBox:
        return max((measure_text(event, text, profile) for text in spans.get(line, [line])), key=lambda box: box.width)

    def width(line: str, fx: float) -> float:
        box: TextBox = unscaled(line)
        return ((box.width - box.edge) * fx + box.edge if box.width > 0 else 0.0) / profile.play_res_x

    return width


__all__ = [
    "NO_WRAP",
    "DialogueLayout",
    "layout_dialogue",
    "tagged_line",
    "tagged_measure",
    "tagged_words",
    "without_wrap",
]
