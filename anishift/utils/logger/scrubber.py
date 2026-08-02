"""Sensitive data scrubber for log messages.

Mask API keys, tokens, passwords, and secrets before they reach log sinks.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, cast

__all__ = ["scrub_message", "scrub_patcher"]

if TYPE_CHECKING:
    from loguru import Record

_SCRUB_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    (re.compile(r"(api[_-]?key|apikey|secret[_-]?key|access[_-]?key)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***"),
    (re.compile(r"(Bearer\s+)\S+", re.IGNORECASE), r"\1***"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "sk-***"),
    (re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b"), "AIza***"),
    (re.compile(r"(password|passwd|pwd)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***"),
    (re.compile(r"(token|auth)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***"),
    (re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{32}\b"), "***"),
]
"""Ordered (regex, replacement) pairs applied to mask secrets in messages."""

_SENSITIVE_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:api[_-]?key|apikey|secret|token|auth|password|passwd|pwd)",
    re.IGNORECASE,
)
"""Structured-field names whose values must never reach a sink."""

_SENSITIVE_VALUE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"(?:api[_-]?key|apikey|secret[_-]?key|access[_-]?key)\s*[=:]\s*(\S+)", re.IGNORECASE),
    re.compile(r"Bearer\s+(\S+)", re.IGNORECASE),
    re.compile(r"\b(sk-[A-Za-z0-9]{20,})\b"),
    re.compile(r"\b(AIza[A-Za-z0-9_-]{35})\b"),
    re.compile(r"(?:password|passwd|pwd)\s*[=:]\s*(\S+)", re.IGNORECASE),
    re.compile(r"(?:token|auth)\s*[=:]\s*(\S+)", re.IGNORECASE),
    re.compile(r"\b((?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{32})\b"),
)
"""Secret values copied by Loguru from formatting arguments into ``extra``."""


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
    raw_message: str = record["message"]
    sensitive_values: frozenset[str] = _sensitive_values(raw_message)
    record["message"] = scrub_message(raw_message)
    extra = record.get("extra")
    if isinstance(extra, Mapping):
        # Mapping input to _scrub_value always yields a dict via the Mapping branch.
        record["extra"] = cast("dict[Any, Any]", _scrub_value(extra, sensitive_values=sensitive_values))
    exception = record.get("exception")
    if exception is None:
        return
    original: str = str(exception.value)
    scrubbed: str = scrub_message(original)
    if scrubbed == original:
        return
    sanitized_value = RuntimeError(scrubbed)
    record["exception"] = type(exception)(
        exception.type,
        sanitized_value,
        exception.traceback,
    )


def _scrub_value(  # noqa: PLR0911 — one guard clause per type keeps dispatch flat and readable
    value: object,
    *,
    key: str = "",
    sensitive_values: frozenset[str] = frozenset(),
) -> object:
    """Return a recursively scrubbed structured log value."""
    if key and _SENSITIVE_KEY_PATTERN.search(key) is not None:
        return "***"
    if isinstance(value, str):
        if value in sensitive_values:
            return "***"
        return scrub_message(value)
    if isinstance(value, Mapping):
        return {
            str(item_key): _scrub_value(
                item_value,
                key=str(item_key),
                sensitive_values=sensitive_values,
            )
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_scrub_value(item, sensitive_values=sensitive_values) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_value(item, sensitive_values=sensitive_values) for item in value)
    if isinstance(value, set):
        return {_scrub_value(item, sensitive_values=sensitive_values) for item in value}
    return value


def _sensitive_values(text: str) -> frozenset[str]:
    """Extract values masked by message scrubbing for structured-field reuse."""
    return frozenset(match.group(1) for pattern in _SENSITIVE_VALUE_PATTERNS for match in pattern.finditer(text))
