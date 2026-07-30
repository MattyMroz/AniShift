"""Limit-aware speech chunking on Unicode grapheme boundaries."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterator
from typing import Final

import regex

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.errors import TtsUnsupportedError
from anishift.services.tts.validation import is_speech_text

__all__ = ["chunk_speech_text"]

_GRAPHEME_PATTERN: Final[regex.Pattern[str]] = regex.compile(r"\X")
"""Unicode extended grapheme cluster pattern."""

_SENTENCE_ENDINGS: Final[frozenset[str]] = frozenset(
    (".", "!", "?", "\u2026", "\u3002", "\uff01", "\uff1f"),
)
"""Characters preferred as sentence chunk boundaries."""

_PHRASE_ENDINGS: Final[frozenset[str]] = frozenset(
    (",", ";", ":", "\u2014", "\u2013", "\uff0c", "\uff1b"),
)
"""Characters preferred as phrase chunk boundaries."""

_CLOSING_PUNCTUATION: Final[frozenset[str]] = frozenset(
    ('"', "'", "\u201d", "\u2019", "\u00bb", ")", "]", "}"),
)
"""Punctuation retained with a preceding sentence or phrase."""

_COMMON_ABBREVIATIONS: Final[frozenset[str]] = frozenset(
    {"dr", "itd", "itp", "mgr", "mr", "mrs", "ms", "np", "nr", "prof", "św", "tj", "tzn", "ul"},
)
"""Common abbreviations whose full stop does not end a sentence."""


def chunk_speech_text(
    text: str,
    *,
    max_chars: int | None,
    max_bytes: int | None,
) -> tuple[str, ...]:
    """Split text by sentence, phrase, word, then grapheme boundaries."""
    _validate_limit(max_chars)
    _validate_limit(max_bytes)
    if not text:
        return ()
    if _fits_limits(text, max_chars=max_chars, max_bytes=max_bytes):
        if not is_speech_text(text):
            _raise_unsupported_limit(text)
        return (text,)

    graphemes: tuple[str, ...] = tuple(_GRAPHEME_PATTERN.findall(text))
    speech_prefix: tuple[int, ...] = _speech_prefix(graphemes)
    character_prefix: tuple[int, ...] = _length_prefix(graphemes, encoded=False)
    byte_prefix: tuple[int, ...] = _length_prefix(graphemes, encoded=True)
    next_boundary: list[int | None] = [None] * (len(graphemes) + 1)
    next_boundary[-1] = len(graphemes)
    for cursor in range(len(graphemes) - 1, -1, -1):
        fitting_end: int = _largest_fitting_end(
            cursor,
            character_prefix=character_prefix,
            byte_prefix=byte_prefix,
            max_chars=max_chars,
            max_bytes=max_bytes,
        )
        if fitting_end == cursor:
            continue
        for boundary in _candidate_boundaries(graphemes, cursor, fitting_end):
            if speech_prefix[boundary] > speech_prefix[cursor] and next_boundary[boundary] is not None:
                next_boundary[cursor] = boundary
                break

    if next_boundary[0] is None:
        _raise_unsupported_limit(text)

    chunks: list[str] = []
    cursor = 0
    while cursor < len(graphemes):
        resolved_boundary: int | None = next_boundary[cursor]
        if resolved_boundary is None:
            incomplete_message: str = "Speech chunk plan is incomplete"
            raise RuntimeError(incomplete_message)
        chunks.append("".join(graphemes[cursor:resolved_boundary]))
        cursor = resolved_boundary

    if "".join(chunks) != text:
        changed_message: str = "Speech chunking changed the source text"
        raise RuntimeError(changed_message)
    return tuple(chunks)


def _largest_fitting_end(
    start: int,
    *,
    character_prefix: tuple[int, ...],
    byte_prefix: tuple[int, ...],
    max_chars: int | None,
    max_bytes: int | None,
) -> int:
    last_index: int = len(character_prefix) - 1
    character_end: int = last_index
    byte_end: int = last_index
    if max_chars is not None:
        character_end = (
            bisect_right(
                character_prefix,
                character_prefix[start] + max_chars,
                lo=start + 1,
            )
            - 1
        )
    if max_bytes is not None:
        byte_end = (
            bisect_right(
                byte_prefix,
                byte_prefix[start] + max_bytes,
                lo=start + 1,
            )
            - 1
        )
    return min(character_end, byte_end)


def _speech_prefix(graphemes: tuple[str, ...]) -> tuple[int, ...]:
    counts: list[int] = [0]
    for grapheme in graphemes:
        counts.append(counts[-1] + int(is_speech_text(grapheme)))
    return tuple(counts)


def _length_prefix(
    graphemes: tuple[str, ...],
    *,
    encoded: bool,
) -> tuple[int, ...]:
    counts: list[int] = [0]
    for grapheme in graphemes:
        length: int = len(grapheme.encode("utf-8")) if encoded else len(grapheme)
        counts.append(counts[-1] + length)
    return tuple(counts)


def _candidate_boundaries(
    graphemes: tuple[str, ...],
    start: int,
    fitting_end: int,
) -> Iterator[int]:
    if fitting_end == len(graphemes):
        yield fitting_end
        return

    seen: set[int] = set()
    for endings, sentence_only in (
        (_SENTENCE_ENDINGS, True),
        (_PHRASE_ENDINGS, False),
    ):
        for index in range(fitting_end - 1, start - 1, -1):
            if graphemes[index] not in endings:
                continue
            if sentence_only and not _is_sentence_ending(graphemes, index):
                continue
            boundary: int = _extend_boundary(graphemes, index + 1, fitting_end)
            if boundary not in seen:
                seen.add(boundary)
                yield boundary
    for index in range(fitting_end - 1, start - 1, -1):
        if graphemes[index].isspace():
            boundary = _extend_boundary(graphemes, index + 1, fitting_end)
            if boundary not in seen:
                seen.add(boundary)
                yield boundary
    for boundary in range(fitting_end, start, -1):
        if boundary not in seen:
            seen.add(boundary)
            yield boundary


def _fits_limits(
    text: str,
    *,
    max_chars: int | None,
    max_bytes: int | None,
) -> bool:
    return (max_chars is None or len(text) <= max_chars) and (
        max_bytes is None or len(text.encode("utf-8")) <= max_bytes
    )


def _is_sentence_ending(graphemes: tuple[str, ...], index: int) -> bool:
    if graphemes[index] != ".":
        return True
    previous: str = graphemes[index - 1] if index > 0 else ""
    immediate_following: str = graphemes[index + 1] if index + 1 < len(graphemes) else ""
    if previous.isdigit() and immediate_following.isdigit():
        return False

    token_start: int = index - 1
    while token_start >= 0 and graphemes[token_start].isalpha():
        token_start -= 1
    token: str = "".join(graphemes[token_start + 1 : index]).casefold()
    if token in _COMMON_ABBREVIATIONS:
        return False
    following: str = _next_non_space(graphemes, index + 1)
    if len(token) == 1 and token.isalpha() and following.isupper():
        return False
    return not following.islower()


def _next_non_space(graphemes: tuple[str, ...], start: int) -> str:
    for grapheme in graphemes[start:]:
        if not grapheme.isspace() and grapheme not in _CLOSING_PUNCTUATION:
            return grapheme
    return ""


def _extend_boundary(
    graphemes: tuple[str, ...],
    boundary: int,
    fitting_end: int,
) -> int:
    while boundary < fitting_end:
        grapheme: str = graphemes[boundary]
        if not grapheme.isspace() and grapheme not in _CLOSING_PUNCTUATION:
            break
        boundary += 1
    return boundary


def _validate_limit(limit: int | None) -> None:
    if limit is not None and (type(limit) is not int or limit <= 0):
        message: str = "Speech chunk limits must be positive integers"
        raise ValueError(message)


def _raise_unsupported_limit(text: str) -> None:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_UNSUPPORTED,
        message="Speech cannot be split into pronounceable chunks within the engine limit",
        suggestion="Select an engine with a larger input limit.",
        details={
            "text_chars": len(text),
            "text_bytes": len(text.encode("utf-8")),
        },
    )
    raise TtsUnsupportedError(context=context)
