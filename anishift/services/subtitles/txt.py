"""Convert UTF-8 plain text into narrator lines."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.subtitles.errors import SubtitleError
from anishift.services.subtitles.types import SpokenLine

__all__ = ["read_txt", "txt_to_spoken"]

_RE_SPACES: Final[re.Pattern[str]] = re.compile(r"\s+")
"""Whitespace normalisation pattern."""

_RE_SENTENCE_END: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?…])\s+")
"""Sentence boundary pattern."""

_MAX_CHUNK_CHARS: Final[int] = 750
"""Maximum preferred narrator line length."""


def _fail(message: str, suggestion: str = "") -> SubtitleError:
    """Build a subtitle error with structured context."""
    return SubtitleError(
        context=ErrorContext(code=ErrorCode.SUBTITLE_PARSE_FAILED, message=message, suggestion=suggestion),
    )


def read_txt(path: Path) -> str:
    """Read a UTF-8 text file.

    Raises:
        SubtitleError: The file is missing, unreadable or not UTF-8.
    """
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        msg = f"Text file not found: {path}"
        raise _fail(msg, "Check that the file still exists") from exc
    except UnicodeDecodeError as exc:
        msg = f"Text file is not valid UTF-8: {path}"
        raise _fail(msg, "Save the file as UTF-8 and retry") from exc
    except OSError as exc:
        msg = f"Text file could not be read: {path}"
        raise _fail(msg, "Check file permissions") from exc


def txt_to_spoken(path: Path, *, max_chars: int = _MAX_CHUNK_CHARS) -> tuple[SpokenLine, ...]:
    """Read UTF-8 text and split it into narrator lines."""
    text = _RE_SPACES.sub(" ", read_txt(path)).strip()
    if not text:
        return ()
    chunks: list[str] = []
    current = ""
    for sentence in _RE_SENTENCE_END.split(text):
        for piece in _word_pieces(sentence, max_chars):
            if not current:
                current = piece
                continue
            if len(current) + 1 + len(piece) <= max_chars:
                current = f"{current} {piece}"
                continue
            chunks.append(current)
            current = piece
    if current:
        chunks.append(current)
    return tuple(SpokenLine(0, 0, chunk, "") for chunk in chunks)


def _word_pieces(sentence: str, max_chars: int) -> list[str]:
    """Split an oversized sentence at word boundaries."""
    if len(sentence) <= max_chars:
        return [sentence]
    pieces: list[str] = []
    current = ""
    for word in sentence.split():
        if not current:
            current = word
            continue
        if len(current) + 1 + len(word) <= max_chars:
            current = f"{current} {word}"
            continue
        pieces.append(current)
        current = word
    if current:
        pieces.append(current)
    return pieces
