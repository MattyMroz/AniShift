"""Write translated narrator lines to an SRT file (txt -> SRT mini-feature).

Plain-text inputs carry no timings, so a readable duration is derived from each
line's length (reading speed) and the lines are laid out back to back. The file
is a lector script, not a video overlay, so the exact times only need to be
monotonic and readable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from pysubs2 import SSAEvent, SSAFile

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.subtitles.errors import SubtitleError

if TYPE_CHECKING:
    from pathlib import Path

    from anishift.services.translation.types import TranslatedLine

__all__ = ["spoken_to_srt"]

# ── Constants ──────────────────────────────────────────────────────────────

_CHARS_PER_SECOND: Final[float] = 15.0
"""Reading speed used to size a generated line duration (chars per second)."""

_MIN_DURATION_MS: Final[int] = 1200
"""Shortest generated duration, so brief lines stay on long enough to read."""

_MAX_DURATION_MS: Final[int] = 8000
"""Longest generated duration, so long lines still advance."""

_GAP_MS: Final[int] = 80
"""Silent gap inserted between consecutive generated lines."""

_ENCODING: Final[str] = "utf-8"
"""Output file encoding."""


def _duration_ms(text: str) -> int:
    """Return a readable duration for ``text`` bounded by the min/max limits."""
    raw = round(len(text) / _CHARS_PER_SECOND * 1000)
    return max(_MIN_DURATION_MS, min(raw, _MAX_DURATION_MS))


def _event(line: TranslatedLine, cursor: int) -> tuple[SSAEvent, int]:
    """Build one SRT event for ``line``; return it with the next cursor (ms)."""
    if line.end > line.start:
        start, end = line.start, line.end
    else:
        start = cursor
        end = cursor + _duration_ms(line.text)
    return SSAEvent(start=start, end=end, text=line.text), end + _GAP_MS


def spoken_to_srt(lines: tuple[TranslatedLine, ...], dest: Path) -> Path | None:
    """Write translated narrator lines to ``dest`` as SRT; None when empty.

    Args:
        lines: Translated narrator lines, in reading order.
        dest: Output ``.srt`` path (written atomically).

    Returns:
        ``dest`` on success, or ``None`` when there are no lines.

    Raises:
        SubtitleError: The file could not be written.
    """
    if not lines:
        return None
    out = SSAFile()
    cursor = 0
    for line in lines:
        event, cursor = _event(line, cursor)
        out.events.append(event)
    temporary = dest.with_name(dest.name + ".tmp")
    try:
        temporary.write_text(out.to_string(format_="srt"), encoding=_ENCODING)
        temporary.replace(dest)
    except OSError as exc:
        msg = f"Translated subtitles could not be written: {dest}"
        raise SubtitleError(context=ErrorContext(code=ErrorCode.IO_ERROR, message=msg)) from exc
    return dest
