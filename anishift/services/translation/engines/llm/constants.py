"""LLM translation engine constants (numbered [N] protocol, not JSON)."""

from __future__ import annotations

import re
from typing import Final

SYSTEM_PROMPT: Final[str] = (
    "You are a subtitle translator. Translate each numbered input line into the "
    "target language. Return ONLY the numbered lines, one per input line, in the "
    "form '[N] translation'. Keep the exact same numbers and count. Do NOT merge "
    "lines, do NOT add commentary, intro, summary, or markdown. One input line = "
    "one output line."
)
"""System prompt enforcing numbered [N] output, one line in = one line out."""

LINE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\s*\[(\d+)\]\s?(.*)$")
"""Matches a single '[N] text' output line; anything else is ignored."""


__all__ = ["LINE_PATTERN", "SYSTEM_PROMPT"]
