"""Measure and place ASS event text on the script canvas the way libass renders it."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from functools import lru_cache
from itertools import accumulate, pairwise
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal

from PIL import ImageFont
from pysubs2 import SSAStyle

from anishift.services.fonts import REFERENCE_SIZE, font_scale, glyph_metrics
from anishift.services.subtitles.text import is_drawing, reflow_visible_text, visible_verses

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping, Sequence

    from pysubs2 import SSAEvent, SSAFile

    from anishift.services.fonts import FontFace, FontIndex, FontMatch, GlyphMetrics

__all__ = [
    "Rect",
    "RenderProfile",
    "TextBox",
    "alignment",
    "anchor_reach",
    "available_width",
    "font_size",
    "measure_text",
    "rotated",
    "safe_width",
    "screen_rects",
    "style_changes",
    "wrap_text",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_REFERENCE_FONT: Final[str] = "arial.ttf"
"""Font file measuring a text that no episode or system face can draw."""

_REFERENCE_SIZE: Final[int] = 64
"""Reference font size of the substitute Arial measurement."""

_DEFAULT_PLAY_RES: Final[tuple[int, int]] = (384, 288)
"""Script size libass assumes when the header gives neither ``PlayResX`` nor ``PlayResY``."""

_SXGA_PLAY_RES: Final[tuple[int, int]] = (1280, 1024)
"""Script size libass completes from either of its dimensions instead of the 4:3 ratio."""

_NO_WRAP_STYLE: Final[int] = 2
"""Wrap style that disables automatic wrapping and turns ``\\n`` into a hard break."""

_GREEDY_WRAP_STYLE: Final[int] = 1
"""Wrap style that wraps at the end of a line without balancing the lines."""

_WRAP_STYLES: Final[range] = range(4)
"""Wrap styles an inline ``\\q`` override accepts."""

_NUMPAD: Final[range] = range(1, 10)
"""Alignments an ``\\an`` override accepts."""

_LEGACY_ALIGNMENTS: Final[range] = range(1, 12)
"""Alignments a legacy ``\\a`` override accepts."""

_LEGACY_COLUMN_BITS: Final[int] = 3
"""Bits of a legacy SSA alignment holding the column."""

_LEGACY_ROW_BITS: Final[int] = 12
"""Bits of a legacy SSA alignment holding the row."""

_LEGACY_ROW_OFFSETS: Final[Mapping[int, int]] = MappingProxyType({0: 0, 4: 6, 8: 3})
"""Numpad offset of each legacy SSA row: bottom, top and middle."""

_LEGACY_INVALID_COLUMN: Final[int] = 5
"""Legacy alignment libass draws the column-less ``\\a4`` and ``\\a8`` with."""

_POINT_ARGUMENTS: Final[int] = 2
"""Arguments of a ``\\pos`` override."""

_MOVE_ARGUMENTS: Final[frozenset[int]] = frozenset({4, 6})
"""Argument counts of a valid ``\\move`` override."""

_REGULAR_WEIGHT: Final[int] = 400
"""Font weight of an upright, non-bold request."""

_BOLD_WEIGHT: Final[int] = 700
"""Font weight of a bold request."""

_EXACT_WEIGHT: Final[int] = 100
"""Smallest ``\\b`` value read as an exact font weight."""

_RELATIVE_SIZE_STEP: Final[float] = 10.0
"""Divisor of a relative ``\\fs+N`` step: each unit changes the size by a tenth."""

_BE_ROUNDING: Final[float] = 0.5
"""Amount VSFilter and libass add to a ``\\be`` strength before truncating it."""

_PERCENT: Final[float] = 100.0
"""Scale of ASS percentage values."""

_TRANSPARENT: Final[int] = 0xFF
"""Alpha of a fully transparent ASS colour."""

_OPAQUE_BOX: Final[int] = 3
"""``BorderStyle`` drawing an opaque box behind each line instead of an outline."""

_OPAQUE_BOX_GROWTH: Final[float] = 1.0
"""Script pixels libass draws an opaque box beyond its lines and border above and below, measured."""

_BLUR_REACH: Final[float] = 1.83
"""Visible reach of ``\\blur`` and ``\\be`` per side in blur radii, calibrated against libass."""

_TRUETYPE_SHEAR: Final[float] = 0x5700 / 0x10000
"""Slant libass gives a TrueType face drawn as synthetic italic, matching GDI."""

_POSTSCRIPT_SHEAR: Final[float] = 0x2D24 / 0x10000
"""Slant libass gives a PostScript-outline face drawn as synthetic italic: tan 10°."""

_EMPTY_LINE_SCALE: Final[float] = 0.5
"""Share of the font height libass gives a line without any character."""

_BREAK: Final[str] = "\n"
"""Character standing for a hard line break at the end of the line it closes."""

_SPACE: Final[str] = " "
"""The only character libass wraps at."""

_TRIMMED: Final[frozenset[str]] = frozenset({_SPACE, _BREAK})
"""Characters libass trims at both ends of a line."""

_ESCAPES: Final[Mapping[str, str]] = MappingProxyType({"\\n": _SPACE, "\\h": "\u00a0", "\t": _SPACE})
"""Escapes and characters with the character libass draws for them; ``\\n`` breaks only in wrap style 2."""

_TAG_NAMES: Final[tuple[str, ...]] = (
    "xbord", "ybord", "xshad", "yshad", "fax", "fay", "iclip", "blur", "fscx", "fscy", "fsc", "fsp", "fs", "bord",
    "move", "frx", "fry", "frz", "fr", "fn", "alpha", "an", "a", "pos", "fade", "fad", "org", "t", "clip", "c", "1c",
    "2c", "3c", "4c", "1a", "2a", "3a", "4a", "r", "be", "b", "i", "kt", "kf", "K", "ko", "k", "shad", "s", "u",
    "pbo", "p", "q", "fe",
)  # fmt: skip
"""Override tag names in the order libass matches them by prefix."""

_SIZE_TAGS: Final[frozenset[str]] = frozenset({"fs", "fscx", "fscy", "fsc", "fsp"})
"""Tags changing the font size, scale or letter spacing."""

_EDGE_TAGS: Final[frozenset[str]] = frozenset({"bord", "xbord", "ybord", "shad", "xshad", "yshad", "blur", "be"})
"""Tags changing the outline, shadow or blur."""

_ALPHA_TAGS: Final[frozenset[str]] = frozenset({"alpha", "1a", "3a", "4a"})
"""Tags changing the opacity of the fill, outline or shadow."""

_FACE_TAGS: Final[frozenset[str]] = frozenset({"fn", "b", "i"})
"""Tags changing the requested font face."""

_STATE_TAGS: Final[frozenset[str]] = _SIZE_TAGS | _EDGE_TAGS | _ALPHA_TAGS | _FACE_TAGS
"""Tags changing the drawing state of the following characters."""

_ROTATION_TAGS: Final[frozenset[str]] = frozenset({"frx", "fry", "frz", "fr", "fax", "fay"})
"""Rotation and shearing tags the measurement does not model."""

_STYLE_ROTATIONS: Final[frozenset[str]] = frozenset({"frz", "fr"})
"""Rotation tags that fall back to the style angle without an argument."""

_TILT_TAGS: Final[frozenset[str]] = frozenset({"frx", "fry"})
"""Rotation tags turning the text out of the screen plane, which the screen box only approximates."""

_FULL_TURN: Final[float] = 360.0
"""Degrees of a full rotation."""

_COLOUR_TAGS: Final[frozenset[str]] = frozenset({"c", "1c", "2c", "3c", "4c", "2a"})
"""Tags a ``\\t`` may animate without changing where or how large the text is drawn."""

_FALLBACK_STYLE: Final[SSAStyle] = SSAStyle()
"""Style measuring an event whose style the file does not define."""

_RE_TOKEN: Final[re.Pattern[str]] = re.compile(r"\{[^}]*\}|\\[Nnh]|[^{\\]+|.", re.DOTALL)
"""Override block, text escape, run of plain text or one leftover character."""

_RE_TAG: Final[re.Pattern[str]] = re.compile(r"\\([^\\(]*)(?:\(([^)]*)\)?)?")
"""One override tag: its name with an inline argument, then optional parenthesised arguments."""

_RE_NUMBER: Final[re.Pattern[str]] = re.compile(r"\s*[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
"""Leading decimal number of a tag argument."""

_RE_INTEGER: Final[re.Pattern[str]] = re.compile(r"\s*[+-]?[0-9]+")
"""Leading integer of a tag argument."""

_RE_ALPHA: Final[re.Pattern[str]] = re.compile(r"[&H]*([0-9A-Fa-f]+)")
"""Hexadecimal alpha of an alpha tag after its ``&H`` prefix."""

_RE_HEADER_INT: Final[re.Pattern[str]] = re.compile(r"\s*([+-]?)(?:(?:&[hH]|0[xX])([0-9A-Fa-f]+)|([0-9]+))")
"""Leading signed decimal or ``&H``/``0x`` hexadecimal integer of a script header value."""

_RE_PREFIX: Final[re.Pattern[str]] = re.compile(r"^(?:\{[^}]*\})*")
"""Leading override blocks setting the initial font size and horizontal scale."""

_RE_SIZE: Final[re.Pattern[str]] = re.compile(r"\\fs(cx)?\s*(-?[0-9]+(?:\.[0-9]*)?)")
"""Font size or horizontal scale override with an explicit value."""


# ── Public types ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Rect:
    """Axis-aligned box on the script canvas, in script pixels."""

    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True, slots=True)
class RenderProfile:
    """Script canvas, wrapping, border scaling, kerning, styles and fonts one file is rendered with."""

    play_res_x: int
    play_res_y: int
    wrap_style: int
    scaled_border: bool
    styles: Mapping[str, SSAStyle]
    fonts: FontIndex | None
    kerning: bool = False

    @classmethod
    def from_subs(cls, subs: SSAFile, fonts: FontIndex | None) -> RenderProfile:
        """Read the render settings of a subtitle file's header and styles as libass does."""
        play_res_x, play_res_y = _play_res(subs.info)
        return cls(
            play_res_x=play_res_x,
            play_res_y=play_res_y,
            wrap_style=_header_int(subs.info, "WrapStyle"),
            scaled_border=_header_bool(subs.info, "ScaledBorderAndShadow"),
            styles=dict(subs.styles),
            fonts=fonts,
            kerning=_header_bool(subs.info, "Kerning"),
        )


@dataclass(frozen=True, slots=True)
class TextBox:
    """Ink of measured lines; ``width`` includes ``edge``, the unscaled outline, shadow and blur of both sides."""

    line_widths: tuple[float, ...]
    width: float
    height: float
    edge: float
    status: Literal["exact", "approximate"]
    fallback_glyphs: int


# ── Public functions ──────────────────────────────────────────────────────────


def measure_text(event: SSAEvent, text: str, profile: RenderProfile, *, fx: float = 1.0, fy: float = 1.0) -> TextBox:
    """Measure the explicit lines of ``text``, tags included, as libass draws them before automatic wrapping."""
    layout: _Layout = _layout(event, text, profile, _View(fx, fy))
    ink: Rect | None = layout.ink
    return TextBox(
        line_widths=layout.line_widths,
        width=0.0 if ink is None else ink.right - ink.left,
        height=0.0 if ink is None else ink.bottom - ink.top,
        edge=layout.edge,
        status="approximate" if layout.approximate else "exact",
        fallback_glyphs=layout.fallback_glyphs,
    )


def available_width(event: SSAEvent, profile: RenderProfile) -> float:
    """Return the canvas width left for the event between its left and right margins."""
    style: SSAStyle = _style(event, profile)
    return profile.play_res_x - (event.marginl or style.marginl) - (event.marginr or style.marginr)


def safe_width(event: SSAEvent, profile: RenderProfile, share: float) -> float:
    """Return the widest line the event may draw from its horizontal anchor inside the canvas share ``share``."""
    low: float = profile.play_res_x * (1 - share) / 2
    return anchor_reach(event, profile, low, profile.play_res_x - low)


def anchor_reach(event: SSAEvent, profile: RenderProfile, left: float, right: float) -> float:
    """Return the widest line the event may draw from its horizontal anchor between canvas x ``left`` and ``right``."""
    parse: _Parse = _parse(event, event.text, profile, final=False)
    column: int = (parse.alignment - 1) % 3
    style: SSAStyle = _style(event, profile)
    start: float = (event.marginl or style.marginl) + available_width(event, profile) * column / 2
    anchor: float = start if parse.anchors is None else parse.anchors[0][0]
    reach: float = (right - anchor, 2 * min(anchor - left, right - anchor), anchor - left)[column]
    return min(max(0.0, reach), right - left)


def alignment(event: SSAEvent, profile: RenderProfile) -> int:
    """Return the numpad alignment libass places the event with."""
    return _parse(event, event.text, profile, final=False).alignment


def rotated(event: SSAEvent, text: str, profile: RenderProfile) -> bool:
    """Tell whether the event draws ``text`` turned or tilted at its start or at its end."""
    return any(
        parse.angle % _FULL_TURN != 0 or parse.tilted
        for parse in (_parse(event, text, profile, final=final) for final in (False, True))
    )


def font_size(event: SSAEvent, profile: RenderProfile) -> float:
    """Return the font size the event text starts with, in script pixels."""
    return _starting_size(event.text, _style(event, profile))[0]


def style_changes(event: SSAEvent, text: str, profile: RenderProfile) -> tuple[bool, ...]:
    """Return for every gap between the words of ``text`` whether the font, size, scale or weight changes across it."""
    parse: _Parse = _parse(event, text, profile, final=False)
    words: list[tuple[_State, _State]] = []
    first: _State | None = None
    last: _State | None = None
    for char in (char for line in parse.lines for char in line):
        if char.text in _TRIMMED:
            if first is not None and last is not None:
                words.append((first, last))
            first = None
            continue
        first = char.state if first is None else first
        last = char.state
    if first is not None and last is not None:
        words.append((first, last))
    return tuple(_typeface(left[1]) != _typeface(right[0]) for left, right in pairwise(words))


def wrap_text(event: SSAEvent, text: str, profile: RenderProfile) -> str:
    """Return ``text`` with the line breaks libass adds when it wraps the event automatically."""
    verses: tuple[str, ...] | None = _wrapped_verses(event, text, profile)
    return text if verses is None else reflow_visible_text(text, verses)


def screen_rects(
    event: SSAEvent, text: str, profile: RenderProfile, *, fx: float = 1.0, fy: float = 1.0
) -> tuple[Rect, ...]:
    """Return the wrapped ink box on the canvas at the event start and, when it moves or transforms, at its end."""
    start: _Layout = _layout(event, text, profile, _View(fx, fy, wrap=True))
    rects: list[Rect | None] = [_on_canvas(start, event, profile)]
    if start.animated:
        rects.append(_on_canvas(_layout(event, text, profile, _View(fx, fy, final=True, wrap=True)), event, profile))
    return tuple(dict.fromkeys(rect for rect in rects if rect is not None))


# ── Header ────────────────────────────────────────────────────────────────────


def _play_res(info: Mapping[str, str]) -> tuple[int, int]:
    width: int = _header_int(info, "PlayResX")
    height: int = _header_int(info, "PlayResY")
    if width > 0 and height > 0:
        return width, height
    if width <= 0 and height <= 0:
        return _DEFAULT_PLAY_RES
    if height <= 0:
        return width, _SXGA_PLAY_RES[1] if width == _SXGA_PLAY_RES[0] else max(1, (width - 1) - (width - 1) // 4)
    return _SXGA_PLAY_RES[0] if height == _SXGA_PLAY_RES[1] else height + height // 3, height


def _header_int(info: Mapping[str, str], key: str) -> int:
    match: re.Match[str] | None = _RE_HEADER_INT.match(info.get(key, ""))
    if match is None:
        return 0
    sign, hexadecimal, decimal = match.groups()
    value: int = int(hexadecimal, 16) if hexadecimal else int(decimal)
    return -value if sign == "-" else value


def _header_bool(info: Mapping[str, str], key: str) -> bool:
    value: str = info.get(key, "").lstrip()
    return value[:3].casefold() == "yes" or _integer(value) > 0


# ── Parsing ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _State:
    """Font request, scale, spacing, outline, shadow, blur and opacities one character is drawn with."""

    font: str
    size: float
    scale_x: float
    scale_y: float
    spacing: float
    weight: int
    italic: bool
    border_x: float
    border_y: float
    shadow_x: float
    shadow_y: float
    blur: float
    be: float
    border_style: int
    fill_alpha: int
    border_alpha: int
    shadow_alpha: int


@dataclass(frozen=True, slots=True)
class _Char:
    """One drawn character with its state; ``_BREAK`` closes a hard line."""

    text: str
    state: _State


@dataclass(frozen=True, slots=True)
class _Parse:
    """Characters of an event by hard line, with the alignment, anchors and wrap style libass uses."""

    lines: tuple[tuple[_Char, ...], ...]
    alignment: int
    anchors: tuple[tuple[float, float], tuple[float, float]] | None
    wrap_style: int
    approximate: bool
    transformed: bool
    angle: float = 0.0
    origin: tuple[float, float] | None = None
    tilted: bool = False

    @property
    def moving(self) -> bool:
        """Tell whether the event moves between two different anchor points."""
        return self.anchors is not None and self.anchors[0] != self.anchors[1]


class _Parser:
    """One pass over an event text in libass order, at the event start or, with ``final``, at its end."""

    def __init__(self, event: SSAEvent, profile: RenderProfile, *, final: bool) -> None:
        self._profile: RenderProfile = profile
        self._final: bool = final
        self._style: SSAStyle = _style(event, profile)
        self._base: _State = _style_state(self._style)
        self._state: _State = self._base
        self._lines: list[tuple[_Char, ...]] = []
        self._line: list[_Char] = []
        self._alignment: int | None = None
        self._anchors: tuple[tuple[float, float], tuple[float, float]] | None = None
        self._wrap_style: int = profile.wrap_style
        self._drawing: bool = False
        self._approximate: bool = self._style.angle != 0
        self._transformed: bool = False
        self._angle: float = float(self._style.angle)
        self._origin: tuple[float, float] | None = None
        self._tilted: bool = False

    def parse(self, text: str) -> _Parse:
        """Return the characters, placement and wrapping of ``text``."""
        for piece in _RE_TOKEN.findall(text):
            self._piece(piece)
        if self._line:
            self._lines.append(tuple(self._line))
        return _Parse(
            lines=tuple(self._lines),
            alignment=self._alignment or int(self._style.alignment),
            anchors=self._anchors,
            wrap_style=self._wrap_style,
            approximate=self._approximate,
            transformed=self._transformed,
            angle=self._angle,
            origin=self._origin,
            tilted=self._tilted,
        )

    def _piece(self, piece: str) -> None:
        if piece.startswith("{") and piece.endswith("}") and len(piece) > 1:
            self._tags(piece[1:-1], nested=False)
        elif piece == "\\N" or (piece == "\\n" and self._wrap_style == _NO_WRAP_STYLE):
            self._line.append(_Char(_BREAK, self._state))
            self._lines.append(tuple(self._line))
            self._line = []
        elif not self._drawing:
            self._line.extend(_Char(_ESCAPES.get(char, char), self._state) for char in _ESCAPES.get(piece, piece))

    def _tags(self, content: str, *, nested: bool) -> None:
        for name, value, arguments in _tag_tokens(content):
            self._tag(name, value, arguments, nested=nested)

    def _tag(self, name: str, value: str, arguments: list[str], *, nested: bool) -> None:
        if name in _STATE_TAGS:
            self._state = _changed(self._state, name, value, self._base)
        elif name == "r":
            self._state = _style_state(self._profile.styles[value]) if value in self._profile.styles else self._base
        elif name in {"an", "a"}:
            self._align(name, value)
        elif name in {"pos", "move"}:
            self._place(name, arguments)
        elif name == "t":
            self._transform(arguments, nested=nested)
        elif name == "org":
            self._set_origin(arguments)
        elif name in _ROTATION_TAGS:
            self._rotate(name, value)
        elif name == "p":
            self._drawing = _integer(value) > 0
            self._approximate = self._approximate or self._drawing
        elif name == "q":
            wrap_style: int = _integer(value)
            self._wrap_style = wrap_style if value and wrap_style in _WRAP_STYLES else self._profile.wrap_style

    def _align(self, name: str, value: str) -> None:
        if self._alignment is not None:
            return
        number: int = _integer(value)
        alignment: int | None = number if name == "an" and number in _NUMPAD else None
        if name == "a" and number in _LEGACY_ALIGNMENTS:
            legacy: int = _LEGACY_INVALID_COLUMN if not number & _LEGACY_COLUMN_BITS else number
            alignment = (legacy & _LEGACY_COLUMN_BITS) + _LEGACY_ROW_OFFSETS[legacy & _LEGACY_ROW_BITS]
        self._alignment = alignment or int(self._style.alignment)

    def _place(self, name: str, arguments: list[str]) -> None:
        if self._anchors is not None:
            return
        numbers: list[float] = [_number(argument) for argument in arguments]
        if name == "pos" and len(numbers) == _POINT_ARGUMENTS:
            self._anchors = ((numbers[0], numbers[1]), (numbers[0], numbers[1]))
        elif name == "move" and len(numbers) in _MOVE_ARGUMENTS:
            self._anchors = ((numbers[0], numbers[1]), (numbers[2], numbers[3]))

    def _transform(self, arguments: list[str], *, nested: bool) -> None:
        self._transformed = True
        inner: str = arguments[-1] if arguments and "\\" in arguments[-1] else ""
        if any(name not in _COLOUR_TAGS for name, _, _ in _tag_tokens(inner)):
            self._approximate = True
        if nested or not self._final:
            return
        self._tags(inner, nested=True)

    def _set_origin(self, arguments: list[str]) -> None:
        self._approximate = True
        numbers: list[float] = [_number(argument) for argument in arguments]
        if self._origin is None and len(numbers) == _POINT_ARGUMENTS:
            self._origin = (numbers[0], numbers[1])

    def _rotate(self, name: str, value: str) -> None:
        turned: bool = self._rotated(name, value)
        self._approximate = self._approximate or turned
        if name in _STYLE_ROTATIONS:
            self._angle = _number(value) if value else float(self._style.angle)
        elif name in _TILT_TAGS:
            self._tilted = self._tilted or turned

    def _rotated(self, name: str, value: str) -> bool:
        if not value:
            return name in _STYLE_ROTATIONS and self._style.angle != 0
        return _number(value) != 0


def _parse(event: SSAEvent, text: str, profile: RenderProfile, *, final: bool) -> _Parse:
    return _Parser(event, profile, final=final).parse(text)


def _tag_tokens(content: str) -> Iterator[tuple[str, str, list[str]]]:
    """Yield the known override tags of a block as name, first argument and parenthesised arguments."""
    for match in _RE_TAG.finditer(content):
        body: str = match[1].lstrip()
        name: str | None = next((tag for tag in _TAG_NAMES if body.startswith(tag)), None)
        if name is None:
            continue
        arguments: list[str] = _arguments(match[2])
        yield name, arguments[0] if arguments else body[len(name) :].rstrip(), arguments


def _arguments(content: str | None) -> list[str]:
    if content is None:
        return []
    slash: int = content.find("\\")
    if slash < 0:
        parts: list[str] = content.split(",")
    else:
        head, _, last = content[:slash].rpartition(",")
        parts = [*(head.split(",") if head else []), last + content[slash:]]
    return [part.strip() for part in parts if part.strip()]


def _typeface(state: _State) -> tuple[str, float, float, float, int]:
    return state.font, state.size, state.scale_x, state.scale_y, state.weight


def _style(event: SSAEvent, profile: RenderProfile) -> SSAStyle:
    return profile.styles.get(event.style, _FALLBACK_STYLE)


def _style_state(style: SSAStyle) -> _State:
    return _State(
        font=style.fontname,
        size=float(style.fontsize),
        scale_x=float(style.scalex),
        scale_y=float(style.scaley),
        spacing=float(style.spacing),
        weight=_BOLD_WEIGHT if style.bold else _REGULAR_WEIGHT,
        italic=bool(style.italic),
        border_x=float(style.outline),
        border_y=float(style.outline),
        shadow_x=float(style.shadow),
        shadow_y=float(style.shadow),
        blur=0.0,
        be=0.0,
        border_style=int(style.borderstyle),
        fill_alpha=style.primarycolor.a,
        border_alpha=style.outlinecolor.a,
        shadow_alpha=style.backcolor.a,
    )


def _changed(state: _State, name: str, value: str, base: _State) -> _State:
    if name in _SIZE_TAGS:
        return _sized(state, name, value, base)
    if name in _EDGE_TAGS:
        return _edged(state, name, value, base)
    if name in _ALPHA_TAGS:
        return _faded(state, name, value, base)
    return _faced(state, name, value, base)


def _sized(state: _State, name: str, value: str, base: _State) -> _State:
    number: float = _number(value)
    size, scale_x, scale_y, spacing = state.size, state.scale_x, state.scale_y, state.spacing
    if name == "fs":
        size = state.size * (1 + number / _RELATIVE_SIZE_STEP) if value.startswith(("+", "-")) else number
        size = size if value and size > 0 else base.size
    elif name == "fscx":
        scale_x = max(0.0, number) if value else base.scale_x
    elif name == "fscy":
        scale_y = max(0.0, number) if value else base.scale_y
    elif name == "fsc":
        scale_x, scale_y = base.scale_x, base.scale_y
    else:
        spacing = number if value else base.spacing
    return replace(state, size=size, scale_x=scale_x, scale_y=scale_y, spacing=spacing)


def _edged(state: _State, name: str, value: str, base: _State) -> _State:
    number: float = _number(value)
    positive: float = max(0.0, number)
    border_x, border_y, shadow_x, shadow_y = state.border_x, state.border_y, state.shadow_x, state.shadow_y
    blur, be = state.blur, state.be
    if name == "bord":
        border_x = border_y = positive if value else base.border_x
    elif name == "xbord":
        border_x = positive if value else base.border_x
    elif name == "ybord":
        border_y = positive if value else base.border_y
    elif name == "shad":
        shadow_x = shadow_y = positive if value else base.shadow_x
    elif name == "xshad":
        shadow_x = number if value else base.shadow_x
    elif name == "yshad":
        shadow_y = number if value else base.shadow_y
    elif name == "blur":
        blur = positive if value else 0.0
    else:
        be = float(max(0, int(number + _BE_ROUNDING))) if value else 0.0
    return replace(state, border_x=border_x, border_y=border_y, shadow_x=shadow_x, shadow_y=shadow_y, blur=blur, be=be)


def _faded(state: _State, name: str, value: str, base: _State) -> _State:
    alpha: int = _alpha(value)
    fill, border, shadow = state.fill_alpha, state.border_alpha, state.shadow_alpha
    if name == "alpha":
        fill, border, shadow = (
            (alpha, alpha, alpha) if value else (base.fill_alpha, base.border_alpha, base.shadow_alpha)
        )
    elif name == "1a":
        fill = alpha if value else base.fill_alpha
    elif name == "3a":
        border = alpha if value else base.border_alpha
    else:
        shadow = alpha if value else base.shadow_alpha
    return replace(state, fill_alpha=fill, border_alpha=border, shadow_alpha=shadow)


def _faced(state: _State, name: str, value: str, base: _State) -> _State:
    if name == "fn":
        font: str = value.lstrip()
        return replace(state, font=base.font if font in {"", "0"} else font)
    number: int = _integer(value)
    if name == "b":
        weight: int = _BOLD_WEIGHT if number == 1 else _REGULAR_WEIGHT if number == 0 else number
        valid: bool = bool(value) and (number in {0, 1} or number >= _EXACT_WEIGHT)
        return replace(state, weight=weight if valid else base.weight)
    return replace(state, italic=number == 1 if value and number in {0, 1} else base.italic)


def _number(value: str) -> float:
    match: re.Match[str] | None = _RE_NUMBER.match(value)
    return float(match[0]) if match else 0.0


def _integer(value: str) -> int:
    match: re.Match[str] | None = _RE_INTEGER.match(value)
    return int(match[0]) if match else 0


def _alpha(value: str) -> int:
    match: re.Match[str] | None = _RE_ALPHA.match(value)
    return int(match[1], 16) & _TRANSPARENT if match else 0


# ── Measurement ───────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Glyph:
    """One measured character in script pixels: advance, ink and outline control box from its origin, line metrics."""

    char: str
    state: _State
    advance: float
    left: float
    right: float
    box_left: float
    box_right: float
    ascent: float
    descent: float
    visible: bool
    line_ascent: float
    line_descent: float
    substitute: bool
    exact: bool


def _measured(parse: _Parse, fonts: FontIndex | None, fx: float, fy: float) -> list[list[_Glyph]] | None:
    """Measure every character with the face libass picks, or return None when a face cannot be measured."""
    if fonts is None:
        return None
    requests: dict[tuple[str, int, bool], FontMatch | None] = {}
    glyphs: list[_Glyph] = []
    for char in (char for line in parse.lines for char in line):
        request: FontMatch | None = _request(fonts, requests, char.state)
        glyph: _Glyph | None = None if request is None else _glyph(char, request, fonts, fx, fy)
        if glyph is None:
            return None
        glyphs.append(glyph)
    _widen_italic(glyphs)
    ends: list[int] = list(accumulate(len(line) for line in parse.lines))
    return [glyphs[start:end] for start, end in pairwise([0, *ends])]


def _request(
    fonts: FontIndex, requests: dict[tuple[str, int, bool], FontMatch | None], state: _State
) -> FontMatch | None:
    key: tuple[str, int, bool] = (state.font, state.weight, state.italic)
    if key not in requests:
        requests[key] = fonts.match(state.font, weight=state.weight, italic=state.italic)
    return requests[key]


def _glyph(char: _Char, request: FontMatch, fonts: FontIndex, fx: float, fy: float) -> _Glyph | None:
    state: _State = char.state
    match: FontMatch = request if char.text == _BREAK else fonts.glyph_match(request, ord(char.text))
    face: FontFace = match.face
    scale_x: float = font_scale(face, state.size) * state.scale_x / _PERCENT * fx
    scale_y: float = font_scale(face, state.size) * state.scale_y / _PERCENT * fy
    unit_y: float = scale_y * REFERENCE_SIZE / face.units_per_em
    line_ascent: float = face.ascent * unit_y
    line_descent: float = face.descent * unit_y
    if char.text == _BREAK:
        return _Glyph(_BREAK, state, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, False, line_ascent, line_descent, False, True)
    slant: float = _POSTSCRIPT_SHEAR if face.postscript_outlines else _TRUETYPE_SHEAR
    metrics: GlyphMetrics | None = _metrics(face, char.text, slant if match.synthetic_italic else 0.0)
    if metrics is None:
        return None
    return _Glyph(
        char=char.text,
        state=state,
        advance=metrics.advance * scale_x + state.spacing * state.scale_x / _PERCENT * fx,
        left=metrics.ink_left * scale_x,
        right=metrics.ink_right * scale_x,
        box_left=metrics.outline_left * scale_x,
        box_right=metrics.outline_right * scale_x,
        ascent=metrics.ink_ascent * scale_y,
        descent=metrics.ink_descent * scale_y,
        visible=metrics.has_ink and _visible(state),
        line_ascent=line_ascent,
        line_descent=line_descent,
        substitute=match is not request or not request.exact,
        exact=match.exact,
    )


def _metrics(face: FontFace, char: str, slant: float) -> GlyphMetrics | None:
    try:
        return glyph_metrics(face, char, slant=slant)
    except OSError:
        return None


def _widen_italic(glyphs: list[_Glyph]) -> None:
    """Extend the advance of the last italic glyph before upright text to its ink, as libass does."""
    for index in range(1, len(glyphs)):
        if glyphs[index - 1].state.italic and not glyphs[index].state.italic:
            _widen(glyphs, index - 1)


def _widen(glyphs: list[_Glyph], back: int) -> None:
    while back and glyphs[back].box_right == glyphs[back].box_left and glyphs[back].state.italic:
        back -= 1
    glyph: _Glyph = glyphs[back]
    if glyph.box_right > glyph.advance:
        glyphs[back] = replace(glyph, advance=glyph.box_right)


def _visible(state: _State) -> bool:
    return state.fill_alpha < _TRANSPARENT or _border_visible(state) or _shadow_visible(state)


def _border_visible(state: _State) -> bool:
    drawn: bool = state.border_alpha < _TRANSPARENT or state.border_style == _OPAQUE_BOX
    return (state.border_x > 0 or state.border_y > 0) and drawn


def _shadow_visible(state: _State) -> bool:
    return state.shadow_alpha < _TRANSPARENT and (state.shadow_x != 0 or state.shadow_y != 0)


# ── Wrapping ──────────────────────────────────────────────────────────────────


def _wrapped(line: list[_Glyph], limit: float, wrap_style: int) -> list[list[_Glyph]]:
    """Split one hard line where libass wraps it: greedily by words, then balanced unless wrap style 1."""
    pens: list[float] = [0.0, *accumulate(glyph.advance for glyph in line)]
    starts: list[int] = _greedy_starts(line, pens, limit)
    if wrap_style != _GREEDY_WRAP_STYLE:
        starts = _balanced_starts(line, pens, starts)
    return [line[start:end] for start, end in pairwise([*starts, len(line)])]


def _greedy_starts(line: list[_Glyph], pens: list[float], limit: float) -> list[int]:
    starts: list[int] = [0]
    breakable: int = -1
    for index, glyph in enumerate(line):
        if glyph.char == _BREAK:
            continue
        overflows: bool = _box_right(line, pens, index) - _box_left(line, pens, starts[-1]) >= limit
        if overflows and glyph.char != _SPACE and breakable >= 0:
            starts.append(breakable + 1)
            breakable = -1
        if glyph.char == _SPACE:
            breakable = index
    return starts


def _balanced_starts(line: list[_Glyph], pens: list[float], starts: list[int]) -> list[int]:
    balanced: list[int] = list(starts)
    moved: bool = True
    while moved:
        moved = False
        for number in range(1, len(balanced)):
            end: int = balanced[number + 1] if number + 1 < len(balanced) else len(line)
            start: int = _balanced_start(line, pens, (balanced[number - 1], balanced[number], end))
            moved = moved or start != balanced[number]
            balanced[number] = start
    return balanced


def _balanced_start(line: list[_Glyph], pens: list[float], bounds: tuple[int, int, int]) -> int:
    """Return the start of the second line after moving the last word of the first when that balances them."""
    first, second, end = bounds
    last: int = _before_spaces(line, first, second)
    word: int = last
    while word > first and line[word].char != _SPACE:
        word -= 1
    shortened: int = word
    while shortened > first and line[shortened].char == _SPACE:
        shortened -= 1
    if line[word].char == _SPACE:
        word += 1
    if word == first:
        return second
    tail_right: float = _box_right(line, pens, _before_spaces(line, second, end))
    head_left: float = _box_left(line, pens, first)
    before: float = abs(_box_right(line, pens, last) - head_left - (tail_right - _box_left(line, pens, second)))
    after: float = abs(_box_right(line, pens, shortened) - head_left - (tail_right - _box_left(line, pens, word)))
    return word if after < before else second


def _before_spaces(line: list[_Glyph], start: int, stop: int) -> int:
    index: int = stop - 1
    while index > start and line[index].char == _SPACE:
        index -= 1
    return index


def _box_left(line: list[_Glyph], pens: list[float], index: int) -> float:
    return pens[index] + line[index].box_left


def _box_right(line: list[_Glyph], pens: list[float], index: int) -> float:
    return pens[index] + line[index].box_right


def _wrapped_verses(event: SSAEvent, text: str, profile: RenderProfile) -> tuple[str, ...] | None:
    """Return every visible line after automatic wrapping, or None when libass adds no line break."""
    if is_drawing(text):
        return None
    parse: _Parse = _parse(event, text, profile, final=False)
    if parse.wrap_style == _NO_WRAP_STYLE:
        return None
    limit: float = available_width(event, profile)
    lines: list[list[_Glyph]] | None = _measured(parse, profile.fonts, 1.0, 1.0)
    if lines is None:
        return _substitute_verses(event, text, profile, limit)
    pieces: list[list[_Glyph]] = [piece for line in lines for piece in _wrapped(line, limit, parse.wrap_style)]
    if len(pieces) == len(lines):
        return None
    return tuple("".join(glyph.char for glyph in piece if glyph.char != _BREAK).strip(_SPACE) for piece in pieces)


# ── Layout ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Line:
    """One drawn line: libass advance width, ink box from its pen origin as (left, right, ascent, descent), metrics."""

    advance: float
    ink: tuple[float, float, float, float] | None
    ascent: float
    descent: float


@dataclass(frozen=True, slots=True)
class _View:
    """Axis factors, event moment and automatic wrapping one layout is computed with."""

    fx: float = 1.0
    fy: float = 1.0
    final: bool = False
    wrap: bool = False


@dataclass(frozen=True, slots=True)
class _Frame:
    """Parse of an event at one moment with the anchor and animation flag its layout carries."""

    parse: _Parse
    anchor: tuple[float, float] | None
    animated: bool


@dataclass(frozen=True, slots=True)
class _Layout:
    """Text of one parse: libass line box, ink relative to the box's top-left corner and measurement quality."""

    width: float
    height: float
    ink: Rect | None
    line_widths: tuple[float, ...]
    edge: float
    approximate: bool
    fallback_glyphs: int
    alignment: int
    anchor: tuple[float, float] | None
    animated: bool
    angle: float = 0.0
    origin: tuple[float, float] | None = None


def _layout(event: SSAEvent, text: str, profile: RenderProfile, view: _View) -> _Layout:
    parse: _Parse = _parse(event, text, profile, final=view.final)
    other: _Parse | None = _parse(event, text, profile, final=not view.final) if parse.transformed else None
    frame: _Frame = _Frame(
        parse=parse,
        anchor=None if parse.anchors is None else parse.anchors[int(view.final)],
        animated=parse.moving or (other is not None and (other.lines != parse.lines or other.angle != parse.angle)),
    )
    lines: list[list[_Glyph]] | None = _measured(parse, profile.fonts, view.fx, view.fy)
    if lines is None:
        return _substitute_layout(event, text, profile, frame, view)
    if view.wrap and parse.wrap_style != _NO_WRAP_STYLE:
        limit: float = available_width(event, profile)
        lines = [piece for line in lines for piece in _wrapped(line, limit, parse.wrap_style)]
    return _assembled(lines, profile, frame)


def _assembled(glyph_lines: list[list[_Glyph]], profile: RenderProfile, frame: _Frame) -> _Layout:
    parse: _Parse = frame.parse
    lines: list[_Line] = [_line(glyphs) for glyphs in glyph_lines]
    drawn: list[_Glyph] = [glyph for glyphs in glyph_lines for glyph in _core(glyphs) if glyph.visible]
    states: set[_State] = {glyph.state for glyph in drawn}
    edges: tuple[float, float, float, float] = _edges(states)
    blur: float = _BLUR_REACH * max((max(state.blur, state.be) for state in states), default=0.0)
    box: bool = any(state.border_style == _OPAQUE_BOX and _border_visible(state) for state in states)
    width: float = max((line.advance for line in lines), default=0.0)
    column: int = (parse.alignment - 1) % 3
    ink, line_widths = _box_ink(lines, width, column, edges) if box else _text_ink(lines, width, column, edges, blur)
    measured: list[_Glyph] = [glyph for glyphs in glyph_lines for glyph in glyphs if glyph.char != _BREAK]
    approximate: bool = (
        frame.animated
        or parse.approximate
        or profile.kerning
        or (not profile.scaled_border and any(edges))
        or any(not glyph.exact or glyph.state.font.startswith("@") for glyph in measured)
    )
    return _Layout(
        width=width,
        height=sum(line.ascent + line.descent for line in lines),
        ink=ink,
        line_widths=line_widths,
        edge=edges[0] + edges[1] + (0.0 if box else 2 * blur),
        approximate=approximate,
        fallback_glyphs=sum(glyph.substitute for glyph in measured),
        alignment=parse.alignment,
        anchor=frame.anchor,
        animated=frame.animated,
        angle=parse.angle,
        origin=parse.origin,
    )


def _line(glyphs: Sequence[_Glyph]) -> _Line:
    core: Sequence[_Glyph] = _core(glyphs)
    metric: Sequence[_Glyph] = core or glyphs
    scale: float = 1.0 if core or any(glyph.char != _BREAK for glyph in glyphs) else _EMPTY_LINE_SCALE
    pens: list[float] = [0.0, *accumulate(glyph.advance for glyph in core)]
    inked: list[tuple[float, _Glyph]] = [(pen, glyph) for pen, glyph in zip(pens, core, strict=False) if glyph.visible]
    ink: tuple[float, float, float, float] | None = None
    if inked:
        ink = (
            min(pen + glyph.left for pen, glyph in inked),
            max(pen + glyph.right for pen, glyph in inked),
            max(glyph.ascent for _, glyph in inked),
            max(glyph.descent for _, glyph in inked),
        )
    return _Line(
        advance=pens[-1],
        ink=ink,
        ascent=scale * max((glyph.line_ascent for glyph in metric), default=0.0),
        descent=scale * max((glyph.line_descent for glyph in metric), default=0.0),
    )


def _core(glyphs: Sequence[_Glyph]) -> Sequence[_Glyph]:
    kept: list[int] = [index for index, glyph in enumerate(glyphs) if glyph.char not in _TRIMMED]
    return glyphs[kept[0] : kept[-1] + 1] if kept else ()


def _edges(states: Iterable[_State]) -> tuple[float, float, float, float]:
    """Return how far visible outlines and shadows reach beyond the glyphs: left, right, top and bottom."""
    left = right = top = bottom = 0.0
    for state in states:
        border: bool = _border_visible(state)
        shadow: bool = _shadow_visible(state)
        reach_x, reach_y = (state.border_x, state.border_y) if border or shadow else (0.0, 0.0)
        if border:
            left, right, top, bottom = max(left, reach_x), max(right, reach_x), max(top, reach_y), max(bottom, reach_y)
        if shadow:
            left, right = max(left, reach_x - state.shadow_x), max(right, reach_x + state.shadow_x)
            top, bottom = max(top, reach_y - state.shadow_y), max(bottom, reach_y + state.shadow_y)
    return left, right, top, bottom


def _text_ink(
    lines: Sequence[_Line], width: float, column: int, edges: tuple[float, float, float, float], blur: float
) -> tuple[Rect | None, tuple[float, ...]]:
    left_edge, right_edge, top_edge, bottom_edge = edges
    boxes: list[Rect] = []
    baseline: float = 0.0
    previous: float = 0.0
    for line in lines:
        baseline += previous + line.ascent
        previous = line.descent
        if line.ink is not None:
            shift: float = (width - line.advance) * column / 2
            boxes.append(Rect(shift + line.ink[0], baseline - line.ink[2], shift + line.ink[1], baseline + line.ink[3]))
    widths: tuple[float, ...] = tuple(
        0.0 if line.ink is None else line.ink[1] - line.ink[0] + left_edge + right_edge + 2 * blur for line in lines
    )
    if not boxes:
        return None, widths
    ink: Rect = Rect(
        min(box.left for box in boxes) - left_edge - blur,
        min(box.top for box in boxes) - top_edge - blur,
        max(box.right for box in boxes) + right_edge + blur,
        max(box.bottom for box in boxes) + bottom_edge + blur,
    )
    return ink, widths


def _box_ink(
    lines: Sequence[_Line], width: float, column: int, edges: tuple[float, float, float, float]
) -> tuple[Rect, tuple[float, ...]]:
    left_edge, right_edge, top_edge, bottom_edge = edges
    shifts: list[float] = [(width - line.advance) * column / 2 for line in lines]
    height: float = sum(line.ascent + line.descent for line in lines)
    ink: Rect = Rect(
        min(shifts, default=0.0) - left_edge,
        -top_edge - _OPAQUE_BOX_GROWTH,
        max((shift + line.advance for shift, line in zip(shifts, lines, strict=True)), default=0.0) + right_edge,
        height + bottom_edge + _OPAQUE_BOX_GROWTH,
    )
    return ink, tuple(line.advance + left_edge + right_edge for line in lines)


def _on_canvas(layout: _Layout, event: SSAEvent, profile: RenderProfile) -> Rect | None:
    """Place the layout's ink at its anchor point, or between the margins of an unpositioned event."""
    ink: Rect | None = layout.ink
    if ink is None:
        return None
    column: int = (layout.alignment - 1) % 3
    row: int = (layout.alignment - 1) // 3
    if layout.anchor is not None:
        left: float = layout.anchor[0] - layout.width * column / 2
        top: float = layout.anchor[1] - layout.height * (2 - row) / 2
    else:
        style: SSAStyle = _style(event, profile)
        margin_v: float = event.marginv or style.marginv
        left = (event.marginl or style.marginl) + (available_width(event, profile) - layout.width) * column / 2
        top = (profile.play_res_y - margin_v - layout.height, (profile.play_res_y - layout.height) / 2, margin_v)[row]
    rect: Rect = Rect(left + ink.left, top + ink.top, left + ink.right, top + ink.bottom)
    if layout.angle % _FULL_TURN == 0:
        return rect
    pivot: tuple[float, float] = layout.origin or (
        left + layout.width * column / 2,
        top + layout.height * (2 - row) / 2,
    )
    return _turned(rect, layout.angle, pivot)


def _turned(rect: Rect, angle: float, pivot: tuple[float, float]) -> Rect:
    """Return the box around ``rect`` turned counterclockwise on screen by ``angle`` degrees around ``pivot``."""
    cos: float = math.cos(math.radians(angle))
    sin: float = math.sin(math.radians(angle))
    corners: list[tuple[float, float]] = [
        (pivot[0] + (x - pivot[0]) * cos + (y - pivot[1]) * sin, pivot[1] - (x - pivot[0]) * sin + (y - pivot[1]) * cos)
        for x in (rect.left, rect.right)
        for y in (rect.top, rect.bottom)
    ]
    return Rect(
        min(x for x, _ in corners), min(y for _, y in corners), max(x for x, _ in corners), max(y for _, y in corners)
    )


# ── Substitute measurement ────────────────────────────────────────────────────


def _substitute_layout(event: SSAEvent, text: str, profile: RenderProfile, frame: _Frame, view: _View) -> _Layout:
    """Measure with the reference Arial at the size the event starts with, when no face can be measured."""
    style: SSAStyle = _style(event, profile)
    size, pixels = _starting_size(text, style)
    widths: tuple[float, ...] = tuple(_verse_width(verse) * pixels * view.fx for verse in visible_verses(text))
    width: float = max(widths, default=0.0)
    height: float = len(widths) * size * style.scaley / _PERCENT * view.fy
    return _Layout(
        width=width,
        height=height,
        ink=Rect(0.0, 0.0, width, height),
        line_widths=widths,
        edge=0.0,
        approximate=True,
        fallback_glyphs=0,
        alignment=frame.parse.alignment,
        anchor=frame.anchor,
        animated=frame.animated,
        angle=frame.parse.angle,
        origin=frame.parse.origin,
    )


def _substitute_verses(event: SSAEvent, text: str, profile: RenderProfile, limit: float) -> tuple[str, ...] | None:
    pixels: float = _starting_size(text, _style(event, profile))[1]
    verses: tuple[str, ...] = visible_verses(text)
    lines: list[str] = [line for verse in verses for line in _greedy_lines(verse, pixels, limit)]
    return None if len(lines) == len(verses) else tuple(lines)


@lru_cache(maxsize=1)
def _font() -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(_REFERENCE_FONT, _REFERENCE_SIZE)
    except OSError:
        return ImageFont.load_default(size=_REFERENCE_SIZE)


@lru_cache(maxsize=4096)
def _verse_width(verse: str) -> float:
    return float(_font().getlength(verse))


def _greedy_lines(verse: str, pixels: float, limit: float) -> list[str]:
    lines: list[list[str]] = [[]]
    for word in verse.split():
        if lines[-1] and _verse_width(" ".join((*lines[-1], word))) * pixels > limit:
            lines.append([])
        lines[-1].append(word)
    return [" ".join(line) for line in lines]


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
