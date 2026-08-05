"""Detect ASS font references missing from a container's attachments."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

__all__ = ["attachment_font_names", "font_names", "missing_fonts"]

# ── Constants ────────────────────────────────────────────────────────────────

_STYLE_LINE: Final[re.Pattern[str]] = re.compile(r"^Style:\s*([^,]*),([^,]*),", re.MULTILINE)
"""V4+ style line whose second field carries the font name."""

_INLINE_FONT: Final[re.Pattern[str]] = re.compile(r"\\fn([^\\}]+)")
"""Inline font override inside an event's override block."""

_FONT_SUFFIXES: Final[frozenset[str]] = frozenset({".ttf", ".otf", ".ttc", ".woff", ".woff2"})
"""Attachment extensions treated as fonts."""


def font_names(subtitle: Path) -> frozenset[str]:
    """Return every font referenced by styles and inline overrides."""
    try:
        text: str = subtitle.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return frozenset()
    names: set[str] = {match.group(2).strip() for match in _STYLE_LINE.finditer(text)}
    names.update(match.group(1).strip() for match in _INLINE_FONT.finditer(text))
    return frozenset(name.lstrip("@") for name in names if name)


def attachment_font_names(attachment_names: tuple[str, ...]) -> frozenset[str]:
    """Return normalized font names available as container attachments."""
    return frozenset(
        Path(name).stem.casefold() for name in attachment_names if Path(name).suffix.casefold() in _FONT_SUFFIXES
    )


def missing_fonts(subtitle: Path, available: frozenset[str]) -> tuple[str, ...]:
    """Return referenced fonts absent from the available set, sorted."""
    referenced: frozenset[str] = font_names(subtitle)
    missing: set[str] = {name for name in referenced if name.casefold() not in available}
    return tuple(sorted(missing))
