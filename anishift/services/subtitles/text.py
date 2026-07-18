"""Tag-safe text operations on ASS/SRT event text."""

from __future__ import annotations

import re
from typing import Final

__all__ = ["is_drawing", "replace_visible_text", "visible_text"]

# ── Constants ─────────────────────────────────────────────────────────────────

_RE_TAG_BLOCK: Final[re.Pattern[str]] = re.compile(r"\{[^}]*\}")
"""One ASS override-tag block, ``{...}``."""

_RE_DRAW_TAG: Final[re.Pattern[str]] = re.compile(chr(92) + chr(92) + r"p[1-9]")
"""An ASS ``\\p1``-``\\p9`` tag switching the line into vector-drawing mode."""

_RE_HTML_TAG: Final[re.Pattern[str]] = re.compile(r"<[^>]+>")
"""One HTML-style formatting tag as found in SRT text."""

_RE_SOFT_BREAKS: Final[re.Pattern[str]] = re.compile(r"\\[Nnh]")
"""ASS line-break and hard-space escapes, normalised to a space."""

_RE_SPACES: Final[re.Pattern[str]] = re.compile(r"\s+")
"""Any whitespace run, collapsed to a single space."""


def is_drawing(text: str) -> bool:
    """Tell whether an event's raw text is a vector drawing."""
    return bool(_RE_DRAW_TAG.search(text))


def visible_text(text: str) -> str:
    """Return the human-visible text of an event as a single line.

    Removes ``{...}`` override blocks and HTML-style tags, normalises ASS
    break escapes and whitespace runs to single spaces, and strips the ends.
    """
    without_tags = _RE_TAG_BLOCK.sub("", text)
    without_html = _RE_HTML_TAG.sub("", without_tags)
    normalised = _RE_SOFT_BREAKS.sub(" ", without_html)
    return _RE_SPACES.sub(" ", normalised).strip()


def replace_visible_text(text: str, new_text: str) -> str:
    """Replace the visible text of an event, keeping every tag block intact.

    The first visible segment is replaced by *new_text*; any further visible
    segments are dropped; all ``{...}`` blocks stay in their original order.

    Args:
        text: Raw event text, possibly containing ``{...}`` blocks.
        new_text: Replacement for the visible part.

    Returns:
        The rebuilt event text with an unchanged tag-block sequence.
    """
    parts: list[str] = []
    inserted = False
    last = 0
    for match in _RE_TAG_BLOCK.finditer(text):
        if not inserted and match.start() > last:
            parts.append(new_text)
            inserted = True
        parts.append(match.group(0))
        last = match.end()
    if not inserted:
        parts.append(new_text)
    return "".join(parts)
