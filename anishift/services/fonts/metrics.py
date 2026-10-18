"""Glyph metrics at one reference size, scaled to ASS font sizes like libass."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Final

from fontTools.pens.boundsPen import BoundsPen, ControlBoundsPen  # type: ignore[import-untyped]
from fontTools.pens.transformPen import TransformPen  # type: ignore[import-untyped]
from fontTools.ttLib import TTFont  # type: ignore[import-untyped]
from PIL import ImageFont

from anishift.services.fonts.index import FONT_READ_ERRORS

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from anishift.services.fonts.types import FontFace

__all__ = ["REFERENCE_SIZE", "GlyphMetrics", "font_scale", "glyph_metrics"]

# ── Constants ─────────────────────────────────────────────────────────────────

REFERENCE_SIZE: Final[int] = 1000
"""Em size in pixels at which glyphs are measured."""

_LIBASS_GLYPH_SIZE: Final[float] = 256.0
"""Font size libass loads unhinted glyphs at before scaling them to the size of the text."""

_INTEGER_PPEM_FLAG: Final[int] = 1 << 3
"""``head.flags`` bit making FreeType round a TrueType face's pixels per em to an integer."""

_BASELINE_ANCHOR: Final[str] = "ls"
"""Pillow anchor placing the origin at the left end of the baseline."""

_GLYPH_CACHE_SIZE: Final[int] = 65536
"""Measured glyphs kept per process."""

_FONT_CACHE_SIZE: Final[int] = 64
"""Loaded reference-size faces kept per process."""


@dataclass(frozen=True, slots=True)
class GlyphMetrics:
    """Advance, ink box and outline control box of one glyph in reference-size pixels; a blank glyph has empty boxes."""

    advance: float
    ink_left: float
    ink_right: float
    ink_ascent: float
    ink_descent: float
    outline_left: float
    outline_right: float

    @property
    def has_ink(self) -> bool:
        """Return whether the glyph draws any pixel."""
        return self.ink_right > self.ink_left


@dataclass(frozen=True, slots=True)
class _Outlines:
    """fontTools view of one face: glyph outlines, character map and whether FreeType rounds its ppem."""

    glyphs: Any
    cmap: Mapping[int, str]
    integer_ppem: bool


def font_scale(face: FontFace, font_size: float) -> float:
    """Return script pixels per reference-size pixel for an ASS font size as libass draws it, ascent + descent tall."""
    return font_size / _LIBASS_GLYPH_SIZE * _libass_em(face) / REFERENCE_SIZE


def glyph_metrics(face: FontFace, char: str, *, slant: float = 0.0) -> GlyphMetrics:
    """Measure one character without kerning: advance hinted at the libass glyph size, outline slanted if asked."""
    em: float = _libass_em(face)
    advance: float = _hinted_advance(face.path, face.face_index, char, em) * REFERENCE_SIZE / em
    drawn: GlyphMetrics = replace(_glyph_metrics(face.path, face.face_index, char), advance=advance)
    if not drawn.has_ink:
        return drawn
    scale: float = REFERENCE_SIZE / face.units_per_em
    ink: tuple[float, float] | None = (
        _outline_bounds(face.path, face.face_index, char, slant, control=False) if slant else None
    )
    left, right = (ink[0] * scale, ink[1] * scale) if ink else (drawn.ink_left, drawn.ink_right)
    outline: tuple[float, float] | None = _outline_bounds(face.path, face.face_index, char, slant, control=True)
    box_left, box_right = (outline[0] * scale, outline[1] * scale) if outline else (left, right)
    return replace(drawn, ink_left=left, ink_right=right, outline_left=box_left, outline_right=box_right)


def _libass_em(face: FontFace) -> float:
    em: float = _LIBASS_GLYPH_SIZE * face.units_per_em / (face.ascent + face.descent)
    outlines: _Outlines | None = _outlines(face.path, face.face_index)
    return float(math.floor(em + 0.5)) if outlines is not None and outlines.integer_ppem else em


@lru_cache(maxsize=_GLYPH_CACHE_SIZE)
def _hinted_advance(path: Path, face_index: int, char: str, em: float) -> float:
    return float(_sized_font(path, face_index, em).getlength(char))


@lru_cache(maxsize=_GLYPH_CACHE_SIZE)
def _glyph_metrics(path: Path, face_index: int, char: str) -> GlyphMetrics:
    font: ImageFont.FreeTypeFont = _sized_font(path, face_index, REFERENCE_SIZE)
    advance: float = font.getlength(char)
    mask, (x, y) = font.getmask2(char, anchor=_BASELINE_ANCHOR)
    box: tuple[int, int, int, int] | None = mask.getbbox()
    if box is None:
        return GlyphMetrics(advance, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    left, top, right, bottom = (float(value) for value in box)
    return GlyphMetrics(advance, x + left, x + right, -(y + top), y + bottom, x + left, x + right)


@lru_cache(maxsize=_GLYPH_CACHE_SIZE)
def _outline_bounds(
    path: Path, face_index: int, char: str, slant: float, *, control: bool
) -> tuple[float, float] | None:
    """Return the horizontal bounds in font units of a glyph outline slanted by ``slant``: control points or ink."""
    outlines: _Outlines | None = _outlines(path, face_index)
    name: str | None = None if outlines is None else outlines.cmap.get(ord(char))
    if outlines is None or name is None:
        return None
    pen: Any = (ControlBoundsPen if control else BoundsPen)(outlines.glyphs)
    try:
        outlines.glyphs[name].draw(TransformPen(pen, (1, 0, slant, 1, 0, 0)))
    except FONT_READ_ERRORS:
        return None
    return None if pen.bounds is None else (float(pen.bounds[0]), float(pen.bounds[2]))


@lru_cache(maxsize=_FONT_CACHE_SIZE)
def _outlines(path: Path, face_index: int) -> _Outlines | None:
    try:
        font: Any = TTFont(io.BytesIO(path.read_bytes()), fontNumber=face_index, lazy=True)
        rounded: bool = "glyf" in font and bool(font["head"].flags & _INTEGER_PPEM_FLAG)
        return _Outlines(font.getGlyphSet(), font.getBestCmap() or {}, rounded)
    except FONT_READ_ERRORS:
        return None


@lru_cache(maxsize=_FONT_CACHE_SIZE)
def _sized_font(path: Path, face_index: int, size: float) -> ImageFont.FreeTypeFont:
    data: io.BytesIO = io.BytesIO(path.read_bytes())
    return ImageFont.truetype(data, size, index=face_index, layout_engine=ImageFont.Layout.BASIC)
