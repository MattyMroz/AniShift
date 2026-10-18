"""Glyph metrics at one reference size, scaled linearly to ASS font sizes like libass."""

from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Final

from PIL import ImageFont

if TYPE_CHECKING:
    from pathlib import Path

    from anishift.services.fonts.types import FontFace

__all__ = ["REFERENCE_SIZE", "GlyphMetrics", "font_scale", "glyph_metrics"]

# ── Constants ─────────────────────────────────────────────────────────────────

REFERENCE_SIZE: Final[int] = 1000
"""Em size in pixels at which glyphs are measured."""

_BASELINE_ANCHOR: Final[str] = "ls"
"""Pillow anchor placing the origin at the left end of the baseline."""

_GLYPH_CACHE_SIZE: Final[int] = 65536
"""Measured glyphs kept per process."""

_FONT_CACHE_SIZE: Final[int] = 64
"""Loaded reference-size faces kept per process."""


@dataclass(frozen=True, slots=True)
class GlyphMetrics:
    """Advance and ink box of one glyph in reference-size pixels; a blank glyph has an empty box."""

    advance: float
    ink_left: float
    ink_right: float
    ink_ascent: float
    ink_descent: float

    @property
    def has_ink(self) -> bool:
        """Return whether the glyph draws any pixel."""
        return self.ink_right > self.ink_left


def font_scale(face: FontFace, font_size: float) -> float:
    """Return script pixels per reference-size pixel for an ASS font size, which libass maps to ascent + descent."""
    return font_size * face.units_per_em / (face.ascent + face.descent) / REFERENCE_SIZE


def glyph_metrics(face: FontFace, char: str) -> GlyphMetrics:
    """Measure one character of a face at the reference size without kerning."""
    return _glyph_metrics(face.path, face.face_index, char)


@lru_cache(maxsize=_GLYPH_CACHE_SIZE)
def _glyph_metrics(path: Path, face_index: int, char: str) -> GlyphMetrics:
    font: ImageFont.FreeTypeFont = _reference_font(path, face_index)
    advance: float = font.getlength(char)
    mask, (x, y) = font.getmask2(char, anchor=_BASELINE_ANCHOR)
    box: tuple[int, int, int, int] | None = mask.getbbox()
    if box is None:
        return GlyphMetrics(advance, 0.0, 0.0, 0.0, 0.0)
    left, top, right, bottom = box
    return GlyphMetrics(advance, float(x + left), float(x + right), float(-(y + top)), float(y + bottom))


@lru_cache(maxsize=_FONT_CACHE_SIZE)
def _reference_font(path: Path, face_index: int) -> ImageFont.FreeTypeFont:
    data: io.BytesIO = io.BytesIO(path.read_bytes())
    return ImageFont.truetype(data, REFERENCE_SIZE, index=face_index, layout_engine=ImageFont.Layout.BASIC)
