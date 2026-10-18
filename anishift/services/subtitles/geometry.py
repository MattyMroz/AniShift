"""Measure and place ASS event text on the script canvas."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Final, Literal

from PIL import ImageFont
from pysubs2 import SSAStyle

from anishift.services.subtitles.text import is_drawing, reflow_visible_text, visible_verses

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pysubs2 import SSAEvent, SSAFile

    from anishift.services.fonts import FontIndex

__all__ = ["Rect", "RenderProfile", "TextBox", "available_width", "measure_text", "screen_rects", "wrap_text"]

# ── Constants ─────────────────────────────────────────────────────────────────

_REFERENCE_FONT: Final[str] = "arial.ttf"
"""Font file measuring every text until the episode fonts are measured."""

_REFERENCE_SIZE: Final[int] = 64
"""Reference font size for language-independent advance-width ratios."""

_DEFAULT_PLAY_RES: Final[tuple[int, int]] = (384, 288)
"""ASS script size assumed when the header omits ``PlayResX`` or ``PlayResY``."""

_NO_WRAP_STYLE: Final[int] = 2
"""ASS ``WrapStyle`` value that disables automatic line wrapping."""

_FALLBACK_STYLE: Final[SSAStyle] = SSAStyle()
"""Style measuring an event whose style the file does not define."""

_NUMBER: Final[str] = r"(-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))"
"""One signed decimal tag argument, captured."""

_RE_NO_WRAP: Final[re.Pattern[str]] = re.compile(r"\\q\s*2")
"""Inline override disabling automatic line wrapping."""

_RE_PREFIX: Final[re.Pattern[str]] = re.compile(r"^(?:\{[^}]*\})*")
"""Leading override blocks setting the initial font size and horizontal scale."""

_RE_SIZE: Final[re.Pattern[str]] = re.compile(r"\\fs(cx)?\s*(-?[0-9]+(?:\.[0-9]*)?)")
"""Font size or horizontal scale override with an explicit value."""

_RE_ALIGNMENT: Final[re.Pattern[str]] = re.compile(r"\\an\s*([1-9])")
"""Inline numpad alignment override."""

_RE_POSITION: Final[re.Pattern[str]] = re.compile(rf"\\pos\s*\(\s*{_NUMBER}\s*,\s*{_NUMBER}\s*\)")
"""Position override anchoring the event at one point."""

_RE_MOVE: Final[re.Pattern[str]] = re.compile(
    rf"\\move\s*\(\s*{_NUMBER}\s*,\s*{_NUMBER}\s*,\s*{_NUMBER}\s*,\s*{_NUMBER}"
)
"""Movement override with its start and end anchor points."""


@dataclass(frozen=True, slots=True)
class Rect:
    """Axis-aligned box on the script canvas, in script pixels."""

    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True, slots=True)
class RenderProfile:
    """Script canvas, wrapping rules, styles and fonts one file is rendered with."""

    play_res_x: int
    play_res_y: int
    wrap_style: int
    scaled_border: bool
    styles: Mapping[str, SSAStyle]
    fonts: FontIndex | None

    @classmethod
    def from_subs(cls, subs: SSAFile, fonts: FontIndex | None) -> RenderProfile:
        """Read the render settings of a subtitle file's header and styles."""
        return cls(
            play_res_x=_header_int(subs, "PlayResX", _DEFAULT_PLAY_RES[0]),
            play_res_y=_header_int(subs, "PlayResY", _DEFAULT_PLAY_RES[1]),
            wrap_style=_header_int(subs, "WrapStyle", 0),
            scaled_border=subs.info.get("ScaledBorderAndShadow", "").strip().casefold() == "yes",
            styles=dict(subs.styles),
            fonts=fonts,
        )


@dataclass(frozen=True, slots=True)
class TextBox:
    """Measured visible lines of one text; ``edge`` is the unscaled horizontal outline, shadow and blur."""

    line_widths: tuple[float, ...]
    width: float
    height: float
    edge: float
    status: Literal["exact", "approximate"]
    fallback_glyphs: int


def measure_text(event: SSAEvent, text: str, profile: RenderProfile, *, fx: float = 1.0, fy: float = 1.0) -> TextBox:
    """Measure the visible lines of ``text`` with the reference Arial at the size the event starts with."""
    style: SSAStyle = _style(event, profile)
    size: float
    pixels: float
    size, pixels = _starting_size(event.text, style)
    verses: tuple[str, ...] = visible_verses(text)
    return TextBox(
        line_widths=tuple(_verse_width(verse) * pixels * fx for verse in verses),
        width=_reference_width(text) * pixels * fx,
        height=len(verses) * size * style.scaley / 100 * fy,
        edge=0.0,
        status="approximate",
        fallback_glyphs=0,
    )


def available_width(event: SSAEvent, profile: RenderProfile) -> float:
    """Return the canvas width left for the event between its left and right margins."""
    style: SSAStyle = _style(event, profile)
    return profile.play_res_x - (event.marginl or style.marginl) - (event.marginr or style.marginr)


def wrap_text(event: SSAEvent, text: str, profile: RenderProfile) -> str:
    """Return ``text`` with the line breaks automatic wrapping adds, estimated by greedy word wrapping."""
    if is_drawing(text) or not _wraps(event, text, profile):
        return text
    limit: float = available_width(event, profile)
    pixels: float = _starting_size(event.text, _style(event, profile))[1]
    lines: list[str] = [line for verse in visible_verses(text) for line in _greedy_lines(verse, pixels, limit)]
    return reflow_visible_text(text, tuple(lines))


def screen_rects(
    event: SSAEvent, text: str, profile: RenderProfile, *, fx: float = 1.0, fy: float = 1.0
) -> tuple[Rect, ...]:
    """Return the text box on the canvas where the event starts and, when it moves, where it ends."""
    box: TextBox = measure_text(event, text, profile, fx=fx, fy=fy)
    alignment: int = _alignment(event, text, profile)
    return tuple(_placed(box, anchor, alignment) for anchor in _anchors(event, text, profile, alignment))


@lru_cache(maxsize=1)
def _font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(_REFERENCE_FONT, _REFERENCE_SIZE)
    except OSError:
        return ImageFont.load_default(size=_REFERENCE_SIZE)


@lru_cache(maxsize=4096)
def _verse_width(verse: str) -> float:
    return float(_font().getlength(verse))


@lru_cache(maxsize=4096)
def _reference_width(text: str) -> float:
    return max((_verse_width(verse) for verse in visible_verses(text)), default=0.0)


def _wraps(event: SSAEvent, text: str, profile: RenderProfile) -> bool:
    if profile.wrap_style == _NO_WRAP_STYLE or _RE_NO_WRAP.search(event.text):
        return False
    return measure_text(event, text, profile).width > available_width(event, profile)


def _greedy_lines(verse: str, pixels: float, limit: float) -> list[str]:
    lines: list[list[str]] = [[]]
    for word in verse.split():
        if lines[-1] and _verse_width(" ".join((*lines[-1], word))) * pixels > limit:
            lines.append([])
        lines[-1].append(word)
    return [" ".join(line) for line in lines]


def _style(event: SSAEvent, profile: RenderProfile) -> SSAStyle:
    return profile.styles.get(event.style, _FALLBACK_STYLE)


def _starting_size(text: str, style: SSAStyle) -> tuple[float, float]:
    """Return the font size the text starts with and its reference-width scale to script pixels."""
    size: float = style.fontsize
    scale: float = style.scalex
    prefix: re.Match[str] | None = _RE_PREFIX.match(text)
    for match in _RE_SIZE.finditer(prefix[0] if prefix else ""):
        if match[1]:
            scale = abs(float(match[2]))
        else:
            size = float(match[2])
    return size, size * scale / 100 / _REFERENCE_SIZE


def _header_int(subs: SSAFile, key: str, default: int) -> int:
    try:
        return int(float(subs.info.get(key) or default))
    except ValueError, OverflowError:
        return default


def _alignment(event: SSAEvent, text: str, profile: RenderProfile) -> int:
    match: re.Match[str] | None = _RE_ALIGNMENT.search(text)
    return int(match[1]) if match else int(_style(event, profile).alignment)


def _anchors(event: SSAEvent, text: str, profile: RenderProfile, alignment: int) -> tuple[tuple[float, float], ...]:
    move: re.Match[str] | None = _RE_MOVE.search(text)
    if move:
        return (float(move[1]), float(move[2])), (float(move[3]), float(move[4]))
    position: re.Match[str] | None = _RE_POSITION.search(text)
    if position:
        return ((float(position[1]), float(position[2])),)
    style: SSAStyle = _style(event, profile)
    left: float = event.marginl or style.marginl
    right: float = profile.play_res_x - (event.marginr or style.marginr)
    vertical: float = event.marginv or style.marginv
    column: int = (alignment - 1) % 3
    row: int = (alignment - 1) // 3
    x: float = (left, (left + right) / 2, right)[column]
    y: float = (profile.play_res_y - vertical, profile.play_res_y / 2, vertical)[row]
    return ((x, y),)


def _placed(box: TextBox, anchor: tuple[float, float], alignment: int) -> Rect:
    column: int = (alignment - 1) % 3
    row: int = (alignment - 1) // 3
    left: float = anchor[0] - box.width * column / 2 - box.edge
    top: float = anchor[1] - box.height * (2 - row) / 2
    return Rect(left, top, left + box.width + 2 * box.edge, top + box.height)
