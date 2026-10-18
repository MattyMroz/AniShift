"""Episode and system fonts: libass-like face choice and glyph metrics."""

from __future__ import annotations

from anishift.services.fonts.index import FontIndex, polish_missing, read_faces, system_font_paths
from anishift.services.fonts.metrics import REFERENCE_SIZE, GlyphMetrics, font_scale, glyph_metrics
from anishift.services.fonts.types import FontFace, FontMatch

__all__ = [
    "REFERENCE_SIZE",
    "FontFace",
    "FontIndex",
    "FontMatch",
    "GlyphMetrics",
    "font_scale",
    "glyph_metrics",
    "polish_missing",
    "read_faces",
    "system_font_paths",
]
