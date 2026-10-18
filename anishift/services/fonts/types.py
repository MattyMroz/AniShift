"""Font domain value objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["FontFace", "FontMatch"]


@dataclass(frozen=True, slots=True)
class FontFace:
    """One face of a font file with the casefolded names, style and metrics libass uses; descent is positive."""

    path: Path
    face_index: int
    family_names: frozenset[str]
    full_names: frozenset[str]
    postscript_name: str | None
    weight: int
    bold: bool
    italic: bool
    units_per_em: int
    ascent: int
    descent: int
    codepoints: frozenset[int]


@dataclass(frozen=True, slots=True)
class FontMatch:
    """Face libass draws a request with; ``exact`` is false for a substitute face."""

    face: FontFace
    exact: bool
    synthetic_bold: bool
    synthetic_italic: bool
    requested_weight: int
    requested_italic: bool
