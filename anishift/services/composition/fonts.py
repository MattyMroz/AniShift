"""Find the fonts ASS subtitles name, check them by family and choose the font files a container gains."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING, Final

from anishift.services.fonts import FontIndex, FontMatch

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["attachment_font_names", "font_attachments", "font_embedding_warnings", "font_names", "used_font_files"]

# ── Constants ────────────────────────────────────────────────────────────────

_STYLE_LINE: Final[re.Pattern[str]] = re.compile(r"^Style:\s*([^,]*),([^,]*),", re.MULTILINE)
"""V4+ style line whose second field carries the font name."""

_INLINE_FONT: Final[re.Pattern[str]] = re.compile(r"\\fn([^\\}]+)")
"""Inline font override inside an event's override block."""

_FONT_SUFFIXES: Final[frozenset[str]] = frozenset({".ttf", ".otf", ".ttc", ".woff", ".woff2"})
"""Attachment extensions treated as fonts."""

_PRESENCE_WEIGHT: Final[int] = 400
"""Weight asked for when only whether a font name is carried matters, not which variant draws it."""


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
    """Return normalized filename stems of font attachments, not family names."""
    return frozenset(
        Path(name).stem.casefold() for name in attachment_names if Path(name).suffix.casefold() in _FONT_SUFFIXES
    )


def font_embedding_warnings(subtitles: Sequence[Path], fonts: Sequence[Path]) -> tuple[str, ...]:
    """Return a warning for every font the subtitles name that no face of the given font files carries."""
    index: FontIndex = FontIndex.build(fonts, ())
    return tuple(f"font not embedded: {name}" for name in sorted(_used_names(subtitles)) if not _carried(index, name))


def used_font_files(fonts: Sequence[Path], subtitles: Sequence[Path]) -> tuple[Path, ...]:
    """Return the font files carrying a font name the subtitles use in a style or an inline override."""
    names: frozenset[str] = _used_names(subtitles)
    return tuple(path for path in fonts if _carries_any(FontIndex.build((path,), ()), names))


def font_attachments(fonts: Sequence[Path], present: Sequence[Path]) -> tuple[tuple[Path, str], ...]:
    """Return each font file to add with a free attachment name, skipping content the container already has."""
    digests: set[str] = {_digest(path) for path in present}
    names: set[str] = {path.name.casefold() for path in present}
    chosen: list[tuple[Path, str]] = []
    for path in fonts:
        digest: str = _digest(path)
        if digest in digests:
            continue
        name: str = _free_name(path, names)
        digests.add(digest)
        names.add(name.casefold())
        chosen.append((path, name))
    return tuple(chosen)


def _used_names(subtitles: Sequence[Path]) -> frozenset[str]:
    return frozenset(name for subtitle in subtitles for name in font_names(subtitle))


def _carries_any(index: FontIndex, names: frozenset[str]) -> bool:
    return any(_carried(index, name) for name in names)


def _carried(index: FontIndex, name: str) -> bool:
    match: FontMatch | None = index.match(name, weight=_PRESENCE_WEIGHT, italic=False)
    return match is not None and match.exact


def _free_name(path: Path, taken: set[str]) -> str:
    name: str = path.name
    number: int = 1
    while name.casefold() in taken:
        number += 1
        name = f"{path.stem} ({number}){path.suffix}"
    return name


def _digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()
