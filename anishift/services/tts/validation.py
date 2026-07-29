"""Validation for the provider-neutral TTS boundary."""

from __future__ import annotations

import re
import unicodedata
from typing import Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.errors import TtsInputError
from anishift.services.tts.types import SpeechBatch, SpeechRequest

__all__ = ["is_speech_text", "validate_scope_id", "validate_speech_batch"]

_SAFE_SCOPE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
"""Portable opaque scope ids accepted as one path segment."""

_WINDOWS_DEVICE_NAMES: Final[frozenset[str]] = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)},
)
"""Windows device names forbidden as portable scope ids."""

_ASS_ESCAPE: Final[re.Pattern[str]] = re.compile(r"\\[Nnh]")
"""ASS layout escapes forbidden at the neutral TTS boundary."""

_ASS_TAG: Final[re.Pattern[str]] = re.compile(r"\{[^}]*\\[^}]*\}")
"""ASS override blocks containing commands."""

_HTML_TAG: Final[re.Pattern[str]] = re.compile(r"</?[A-Za-z][^<>]*>")
"""HTML-style subtitle tags forbidden at the neutral TTS boundary."""

_ASS_DRAWING_COMMAND: Final[re.Pattern[str]] = re.compile(r"[mnlbspc]\Z", re.IGNORECASE)
"""One ASS vector drawing command token."""

_ASS_DRAWING_NUMBER: Final[re.Pattern[str]] = re.compile(r"-?(?:\d+(?:\.\d*)?|\.\d+)\Z")
"""One ASS vector drawing coordinate token."""

_ASS_DRAWING_PREFIX_TOKENS: Final[int] = 3
"""Command plus the first coordinate pair in an ASS drawing."""


def validate_speech_batch(batch: SpeechBatch) -> SpeechBatch:
    """Validate one caller-built batch without modifying its text."""
    if type(batch) is not SpeechBatch:
        _raise_input_error("TTS batch must use the SpeechBatch contract", field_name="batch")
    if type(batch.scope_id) is not str:
        _raise_input_error("TTS scope id must be a string", field_name="scope_id")
    validate_scope_id(batch.scope_id)
    if type(batch.batch_rank) is not int or batch.batch_rank < 0:
        _raise_input_error(
            "TTS batch rank must be a non-negative integer",
            field_name="batch_rank",
        )
    if type(batch.requests) is not tuple:
        _raise_input_error("TTS requests must be a tuple", field_name="requests")

    request_ids: set[str] = set()
    for request in batch.requests:
        _validate_request(request)
        if request.request_id in request_ids:
            _raise_input_error(
                "TTS request ids must be unique within a batch",
                field_name="request_id",
                request_id=request.request_id,
            )
        request_ids.add(request.request_id)
    return batch


def is_speech_text(text: str) -> bool:
    """Return whether text contains at least one letter or number."""
    return any(unicodedata.category(character)[0] in {"L", "N"} for character in text)


def validate_scope_id(scope_id: str) -> str:
    """Validate and return one portable opaque resume scope id."""
    if type(scope_id) is not str:
        _raise_input_error("TTS scope id must be a string", field_name="scope_id")
    if not _is_safe_scope(scope_id):
        _raise_input_error(
            "TTS scope id must be one portable opaque path segment",
            field_name="scope_id",
        )
    return scope_id


def _is_safe_scope(scope_id: str) -> bool:
    return _SAFE_SCOPE.fullmatch(scope_id) is not None and scope_id.upper() not in _WINDOWS_DEVICE_NAMES


def _validate_request(request: SpeechRequest) -> None:
    if type(request) is not SpeechRequest:
        _raise_input_error(
            "TTS requests must use the SpeechRequest contract",
            field_name="request",
        )
    if type(request.request_id) is not str or not request.request_id.strip():
        _raise_input_error("TTS request id must be a non-empty string", field_name="request_id")
    if type(request.request_rank) is not int or request.request_rank < 0:
        _raise_input_error(
            "TTS request rank must be a non-negative integer",
            field_name="request_rank",
            request_id=request.request_id,
        )
    if type(request.text) is not str:
        _raise_input_error(
            "TTS text must be a string",
            field_name="text",
            request_id=request.request_id,
        )
    if _contains_subtitle_markup(request.text):
        _raise_input_error(
            "TTS text must not contain subtitle markup, drawings, or controls",
            field_name="text",
            request_id=request.request_id,
        )


def _contains_subtitle_markup(text: str) -> bool:
    return (
        _contains_forbidden_control(text)
        or _ASS_ESCAPE.search(text) is not None
        or _ASS_TAG.search(text) is not None
        or _HTML_TAG.search(text) is not None
        or _is_ass_drawing(text)
    )


def _is_ass_drawing(text: str) -> bool:
    tokens: list[str] = text.split()
    if len(tokens) < _ASS_DRAWING_PREFIX_TOKENS or tokens[0].casefold() not in {"m", "n"}:
        return False
    if any(_ASS_DRAWING_NUMBER.fullmatch(token) is None for token in tokens[1:_ASS_DRAWING_PREFIX_TOKENS]):
        return False
    return all(
        _ASS_DRAWING_COMMAND.fullmatch(token) is not None or _ASS_DRAWING_NUMBER.fullmatch(token) is not None
        for token in tokens[3:]
    )


def _contains_forbidden_control(text: str) -> bool:
    for character in text:
        if character in {"\u2028", "\u2029"}:
            return True
        if unicodedata.category(character) in {"Cc", "Cs"}:
            return True
    return False


def _raise_input_error(
    message: str,
    *,
    field_name: str,
    request_id: str = "",
) -> Never:
    details: dict[str, str] = {"field": field_name}
    if request_id:
        details["request_id"] = request_id
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_INPUT_INVALID,
        message=message,
        suggestion="Pass clean single-line text and opaque identifiers to TTS.",
        details=details,
    )
    raise TtsInputError(context=context)
