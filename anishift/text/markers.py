"""Numbered inline span markers that carry style ranges through translation."""

from __future__ import annotations

import re
from typing import Final

__all__ = ["SPAN_MARKER", "span_marker", "strip_span_markers"]

# ── Constants ─────────────────────────────────────────────────────────────────

SPAN_MARKER: Final[re.Pattern[str]] = re.compile(r"</?s[1-9][0-9]*>")
"""One opening ``<sN>`` or closing ``</sN>`` span marker."""

_RE_SPACES: Final[re.Pattern[str]] = re.compile(r"\s+")
"""Whitespace run collapsed after markers are removed."""


def span_marker(number: int, *, closing: bool = False) -> str:
    """Return the opening or closing marker of one numbered span."""
    return f"</s{number}>" if closing else f"<s{number}>"


def strip_span_markers(text: str) -> str:
    """Remove span markers and collapse the whitespace they leave behind."""
    if not SPAN_MARKER.search(text):
        return text
    return _RE_SPACES.sub(" ", SPAN_MARKER.sub("", text)).strip()
