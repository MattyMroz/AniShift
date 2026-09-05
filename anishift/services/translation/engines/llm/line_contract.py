"""Numbered-line contract for LLM translation requests and responses."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

# ── Constants ────────────────────────────────────────────────────────────────

LINE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\[(\d+)\] ?(.*)$")
"""One contract line: the number in brackets, an optional space, then the text."""

_FENCE_PREFIX: Final[str] = "```"
"""Markdown fence opening, ignorable because it cannot hide translation text."""

_WIRE_ESCAPES: Final[tuple[tuple[str, str], ...]] = (
    ("\\", "\\\\"),
    ("\r", "\\r"),
    ("\n", "\\n"),
)
"""Plain-to-wire replacements applied in order, the backslash necessarily first."""

_UNESCAPE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\\\\|\\r|\\n")
"""Wire escape alternatives, matched left to right so ``\\\\n`` stays a backslash."""

_WIRE_TO_PLAIN: Final[dict[str, str]] = {"\\\\": "\\", "\\r": "\r", "\\n": "\n"}
"""Reverse map of :data:`_WIRE_ESCAPES` used by the single-pass unescape."""

_MAX_LISTED_NUMBERS: Final[int] = 20
"""Numbers named in one diagnosis before it falls back to a count."""


class ViolationKind(Enum):
    """Response contract violations the parser tells apart."""

    EMPTY_RESPONSE = "empty_response"
    MALFORMED_LINE = "malformed_line"
    UNKNOWN_NUMBER = "unknown_number"
    DUPLICATE_NUMBER = "duplicate_number"
    EMPTY_TRANSLATION = "empty_translation"
    WRONG_ORDER = "wrong_order"
    MISSING_NUMBER = "missing_number"


_MESSAGES: Final[dict[ViolationKind, str]] = {
    ViolationKind.EMPTY_RESPONSE: "Odpowiedź nie zawiera żadnej numerowanej linii.",
    ViolationKind.MALFORMED_LINE: "Odpowiedź zawiera linię bez numeru w formacie [N].",
    ViolationKind.UNKNOWN_NUMBER: "Odpowiedź zawiera numer, o który nie proszono.",
    ViolationKind.DUPLICATE_NUMBER: "Odpowiedź powtarza ten sam numer.",
    ViolationKind.EMPTY_TRANSLATION: "Odpowiedź zawiera numer bez tłumaczenia.",
    ViolationKind.WRONG_ORDER: "Numery w odpowiedzi nie rosną zgodnie z kolejnością wejścia.",
    ViolationKind.MISSING_NUMBER: "Odpowiedź nie zawiera wszystkich żądanych numerów.",
}
"""Safe Polish diagnosis per violation kind, free of subtitle content."""


@dataclass(frozen=True, slots=True)
class ContractViolation:
    """Safe description of why part of a response was not trusted."""

    kind: ViolationKind
    numbers: tuple[int, ...]
    message: str


@dataclass(frozen=True, slots=True)
class ParsedResponse:
    """Outcome of one response scan."""

    entries: Mapping[int, str]
    violation: ContractViolation | None


def serialize_request(items: Sequence[tuple[int, str]]) -> str:
    """Serialize numbered subtitles to the exact model input contract."""
    return "\n".join(f"[{number}] {_escape(text)}" for number, text in items)


def parse_response(text: str, expected: Sequence[int]) -> ParsedResponse:
    """Scan a numbered-line response into trusted entries and one violation."""
    order: tuple[int, ...] = tuple(dict.fromkeys(expected))
    lines: list[str] = _significant_lines(text)
    if not lines:
        return ParsedResponse(entries={}, violation=_whole_batch(ViolationKind.EMPTY_RESPONSE))
    scan = _Scan(order)
    for line in lines:
        scan.consume(line)
    return scan.verdict(order)


class _Scan:
    """Accumulator walking response lines once, in order."""

    __slots__ = ("_batch_wide", "_entries", "_invalid", "_kinds", "_last", "_position", "_positions")

    def __init__(self, order: Sequence[int]) -> None:
        """Start an empty scan bound to the requested numbers and their order."""
        self._positions: dict[int, int] = {number: index for index, number in enumerate(order)}
        self._entries: dict[int, str] = {}
        self._invalid: set[int] = set()
        self._kinds: list[ViolationKind] = []
        self._batch_wide = False
        self._last: int | None = None
        self._position: int = -1

    def consume(self, line: str) -> None:
        """Fold one significant response line into the scan."""
        match = LINE_PATTERN.match(line)
        if match is None:
            self._blame_previous(ViolationKind.MALFORMED_LINE)
            return
        self._consume_numbered(int(match.group(1)), match.group(2))

    def verdict(self, order: Sequence[int]) -> ParsedResponse:
        """Turn the scan into trusted entries plus at most one violation."""
        if self._batch_wide:
            return ParsedResponse(entries={}, violation=_whole_batch(self._kinds[0]))
        missing: tuple[int, ...] = tuple(number for number in order if number not in self._entries)
        if not self._kinds and not missing:
            return ParsedResponse(entries=dict(self._entries), violation=None)
        kind = self._kinds[0] if self._kinds else ViolationKind.MISSING_NUMBER
        return ParsedResponse(
            entries=dict(self._entries),
            violation=ContractViolation(kind=kind, numbers=missing, message=_describe(kind, missing)),
        )

    def _consume_numbered(self, number: int, body: str) -> None:
        """Fold one well-formed ``[N] text`` line into the scan."""
        position = self._positions.get(number)
        if position is None:
            self._blame_previous(ViolationKind.UNKNOWN_NUMBER)
            return
        if number in self._entries or number in self._invalid:
            self._reject(number, ViolationKind.DUPLICATE_NUMBER)
            return
        if position < self._position:
            self._kinds.append(ViolationKind.WRONG_ORDER)
            self._batch_wide = True
            return
        self._position = position
        translation: str = _unescape(body.strip())
        if not translation.strip():
            self._reject(number, ViolationKind.EMPTY_TRANSLATION)
            return
        self._entries[number] = translation
        self._last = number

    def _blame_previous(self, kind: ViolationKind) -> None:
        """Distrust the number a stray line follows, since it may be its tail."""
        self._kinds.append(kind)
        if self._last is None:
            self._batch_wide = True
            return
        self._invalid.add(self._last)
        self._entries.pop(self._last, None)

    def _reject(self, number: int, kind: ViolationKind) -> None:
        """Drop one number from the trusted set and remember why."""
        self._kinds.append(kind)
        self._invalid.add(number)
        self._entries.pop(number, None)
        self._last = number


def _significant_lines(text: str) -> list[str]:
    """Return trimmed response lines that could carry a translation."""
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(_FENCE_PREFIX):
            continue
        lines.append(line)
    return lines


def _whole_batch(kind: ViolationKind) -> ContractViolation:
    """Build a violation covering every number of the batch."""
    return ContractViolation(kind=kind, numbers=(), message=_describe(kind, ()))


def _describe(kind: ViolationKind, numbers: Sequence[int]) -> str:
    """Compose a safe diagnosis naming the numbers that need another try."""
    base = _MESSAGES[kind]
    if not numbers:
        return f"{base} Popraw całą partię."
    if len(numbers) > _MAX_LISTED_NUMBERS:
        return f"{base} Liczba numerów do poprawienia: {len(numbers)}."
    listed = ", ".join(str(number) for number in numbers)
    return f"{base} Numery do poprawienia: {listed}."


def _escape(text: str) -> str:
    """Replace characters that would break the one-line-per-subtitle rule."""
    escaped = text
    for plain, wire in _WIRE_ESCAPES:
        escaped = escaped.replace(plain, wire)
    return escaped


def _unescape(text: str) -> str:
    """Restore escaped characters in one left-to-right pass."""
    return _UNESCAPE_PATTERN.sub(lambda match: _WIRE_TO_PLAIN[match.group(0)], text)


__all__ = [
    "LINE_PATTERN",
    "ContractViolation",
    "ParsedResponse",
    "ViolationKind",
    "parse_response",
    "serialize_request",
]
