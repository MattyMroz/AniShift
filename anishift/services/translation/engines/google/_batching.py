"""Index-preserving batched translation for the Google engine.

Free Google Translate mangles structure, so this guarantees input[i] maps to
output[i] by construction: join lines with a zero-width separator; on a
segment-count mismatch fall back to newline-join, then to per-line, then pad
with the source text. Multi-line cells survive via a distinct newline marker.
Sequential, no gather - that is what avoids Google rate limits.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from anishift.services.translation.engines.google.constants import (
    LINE_SEPARATOR,
    NEWLINE_MARKER,
    ZERO_WIDTH,
)
from anishift.services.translation.types import BatchedLine

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


def _chunks(texts: list[str], batch_size: int, max_chars: int) -> list[list[str]]:
    """Split lines (newline-escaped) into chunks bounded by count and chars."""
    chunks: list[list[str]] = []
    current: list[str] = []
    current_chars = 0
    for text in texts:
        prepared = text.replace("\n", NEWLINE_MARKER)
        line_chars = len(prepared) + len(LINE_SEPARATOR)
        too_many = len(current) >= batch_size
        too_long = bool(current) and current_chars + line_chars > max_chars
        if too_many or too_long:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(prepared)
        current_chars += line_chars
    if current:
        chunks.append(current)
    return chunks


def _restore(text: str) -> str:
    """Undo markers and strip separators from a translated segment."""
    cleaned = text.replace(NEWLINE_MARKER, "\n").replace(ZERO_WIDTH, "")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n[ \t]+", "\n", cleaned)
    return cleaned.strip()


async def _per_line(
    prepared: list[str],
    translate_joined: Callable[[str], Awaitable[tuple[str, str | None]]],
) -> list[BatchedLine]:
    """Translate each line in its own call; pad source on failure."""
    out: list[BatchedLine] = []
    for line in prepared:
        try:
            translated, detected = await translate_joined(line)
        except Exception:  # noqa: BLE001 - googletrans has no stable exception hierarchy
            out.append(BatchedLine(text=line.replace(NEWLINE_MARKER, "\n"), ok=False))
            continue
        out.append(BatchedLine(text=_restore(translated), detected_lang=detected, ok=True))
    return out


async def _translate_chunk(
    prepared: list[str],
    translate_joined: Callable[[str], Awaitable[tuple[str, str | None]]],
) -> list[BatchedLine]:
    """Translate one chunk via separator -> newline -> per-line ladder."""
    try:
        joined = LINE_SEPARATOR.join(prepared)
        result, detected = await translate_joined(joined)
        parts = result.split(LINE_SEPARATOR)
        if len(parts) == len(prepared):
            return _map_parts(prepared, parts, detected)

        joined_nl = "\n".join(prepared)
        result_nl, detected_nl = await translate_joined(joined_nl)
        parts_nl = result_nl.split("\n")
        if len(parts_nl) == len(prepared):
            return _map_parts(prepared, parts_nl, detected_nl)
    except Exception:  # noqa: BLE001, S110 - ladder fallback: retry per-line on any batch failure
        pass
    return await _per_line(prepared, translate_joined)


def _map_parts(prepared: list[str], parts: list[str], detected: str | None) -> list[BatchedLine]:
    """Map translated parts to lines; empty output for non-empty input pads source.

    ``detected`` is the chunk-level source language (Google reports one per
    request); it is applied to every successfully translated line in the chunk.
    """
    out: list[BatchedLine] = []
    for source, part in zip(prepared, parts, strict=True):
        restored = _restore(part)
        if not restored and source.strip():
            out.append(BatchedLine(text=source.replace(NEWLINE_MARKER, "\n"), ok=False))
        else:
            out.append(BatchedLine(text=restored, detected_lang=detected, ok=True))
    return out


async def translate_lines(
    texts: list[str],
    *,
    batch_size: int,
    max_chars: int,
    translate_joined: Callable[[str], Awaitable[tuple[str, str | None]]],
) -> list[BatchedLine]:
    """Translate lines with index<->index mapping guaranteed by construction.

    Args:
        texts: Lines to translate, in order.
        batch_size: Max lines per request.
        max_chars: Max characters per request (chunking budget).
        translate_joined: Async callback translating one already-joined string;
            returns ``(translated, detected_lang)`` where detected is the
            chunk-level source language (``None`` if not reported).

    Returns:
        One ``BatchedLine`` per input line, same order; failed lines carry the
        source text with ``ok=False``.
    """
    if not texts:
        return []
    out: list[BatchedLine] = []
    for chunk in _chunks(texts, batch_size, max_chars):
        out.extend(await _translate_chunk(chunk, translate_joined))
    return out


__all__ = ["translate_lines"]
