"""Sensitive data scrubber for log messages.

Mask API keys, tokens, passwords, and secrets before they reach log sinks.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

__all__ = ["scrub_message", "scrub_patcher"]

if TYPE_CHECKING:
    from loguru import Record

# Patterns that match common secret formats in log messages.
# Each tuple: (compiled regex, replacement string).
_SCRUB_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # API keys: sk-..., api_key=..., apikey=..., key=...
    (re.compile(r"(api[_-]?key|apikey|secret[_-]?key|access[_-]?key)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***"),
    # Bearer tokens
    (re.compile(r"(Bearer\s+)\S+", re.IGNORECASE), r"\1***"),
    # OpenAI-style keys (sk-...)
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "sk-***"),
    # Google API keys
    (re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b"), "AIza***"),
    # Generic password fields
    (re.compile(r"(password|passwd|pwd)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***"),
    # Generic token fields
    (re.compile(r"(token|auth)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***"),
    # ElevenLabs-style keys (32-char lowercase hex that is NOT a UUID with dashes).
    # Require mixed digits+letters to avoid matching MD5 hashes of common strings.
    (re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{32}\b"), "***"),
]


def scrub_message(text: str) -> str:
    """Replace sensitive patterns in a log message.

    Args:
        text: Raw log message.

    Returns:
        Message with secrets masked as ``***``.
    """
    for pattern, replacement in _SCRUB_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def scrub_patcher(record: Record) -> None:
    """Scrub sensitive data from a loguru record in-place.

    Install via ``logger.configure(patcher=scrub_patcher)``.

    Args:
        record: Loguru record to sanitize.
    """
    record["message"] = scrub_message(record["message"])
