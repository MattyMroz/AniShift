"""Shared SDK-neutral helpers for LLM provider adapters."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from itertools import groupby
from typing import Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.llm.errors import (
    LlmError,
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmRequestError,
)
from anishift.services.llm.types import FilePart, LlmContentPart, LlmRequest, Modality, TextPart

__all__ = [
    "DEFAULT_PDF_NAME",
    "anthropic_content_block",
    "error_with_context",
    "group_adjacent_text_parts",
    "joined_text",
    "normalize_finish_reason",
    "optional_int",
    "raise_request_error",
    "require_file_modalities",
    "retry_after_seconds",
    "status_code",
    "structured_markers",
    "transient_error_with_context",
]

# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_PDF_NAME: Final[str] = "document.pdf"
"""Filename sent for a PDF without a caller-supplied name."""


def require_file_modalities(request: LlmRequest, *, accepted: frozenset[Modality], engine_id: str) -> None:
    """Reject unsupported files across the request before serializing any content."""
    files: Iterator[FilePart] = (
        part for message in request.messages for part in message.parts if isinstance(part, FilePart)
    )
    for part in files:
        if part.modality not in accepted:
            raise_request_error(
                f"{engine_id} does not support {part.modality} files ({part.media_type})",
                suggestion="Choose a provider that accepts this file type.",
                engine_id=engine_id,
            )


def anthropic_content_block(part: LlmContentPart) -> dict[str, object]:
    """Shape a validated text, image or PDF part for Anthropic Messages."""
    if isinstance(part, TextPart):
        return {"type": "text", "text": part.text}
    return {
        "type": "image" if part.modality == "image" else "document",
        "source": {"type": "base64", "media_type": part.media_type, "data": part.base64},
    }


def joined_text(parts: Iterable[LlmContentPart]) -> str:
    """Join text parts with newlines in their original order."""
    return "\n".join(part.text for part in parts if isinstance(part, TextPart))


def group_adjacent_text_parts(parts: tuple[LlmContentPart, ...]) -> Iterator[LlmContentPart]:
    """Join adjacent text parts with newlines while preserving file positions."""
    for is_text, group in groupby(parts, key=lambda part: isinstance(part, TextPart)):
        if is_text:
            yield TextPart(joined_text(group))
        else:
            yield from group


def normalize_finish_reason(value: object) -> str:
    """Return a lowercase finish reason, or ``unknown`` for missing values."""
    enum_value: object = getattr(value, "value", value)
    if not isinstance(enum_value, str) or not enum_value.strip():
        return "unknown"
    return enum_value.strip().lower()


def structured_markers(value: object) -> frozenset[str]:
    """Collect every lowercase string nested inside an SDK error payload."""
    markers: set[str] = set()
    if isinstance(value, Mapping):
        for nested in value.values():
            markers.update(structured_markers(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            markers.update(structured_markers(nested))
    elif isinstance(value, str) and value.strip():
        markers.add(value.strip().lower())
    return frozenset(markers)


def status_code(error: BaseException, *, attributes: tuple[str, ...] = ("status_code",)) -> int | None:
    """Return the first integer HTTP status found on the given attributes."""
    for attribute_name in attributes:
        status: object = getattr(error, attribute_name, None)
        if isinstance(status, int) and not isinstance(status, bool):
            return status
    return None


def retry_after_seconds(error: BaseException) -> float | None:
    """Return the non-negative ``retry-after`` header value, when present."""
    response: object = getattr(error, "response", None)
    headers: object = getattr(response, "headers", None)
    if not isinstance(headers, Mapping):
        return None
    value: object = headers.get("retry-after")
    if not isinstance(value, str):
        return None
    try:
        parsed: float = float(value)
    except ValueError:
        return None
    return max(0.0, parsed)


def optional_int(value: object) -> int | None:
    """Return the value only when it is a real integer (bool excluded)."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def error_with_context(
    error_type: type[LlmError],
    *,
    engine_id: str,
    message: str,
    suggestion: str,
) -> Exception:
    """Build a typed provider error tagged with the engine id."""
    context: ErrorContext = ErrorContext(
        code=error_type.error_code,
        message=message,
        suggestion=suggestion,
        details={"engine_id": engine_id},
    )
    return error_type(context=context)


def transient_error_with_context(
    error_type: type[LlmRateLimitError] | type[LlmProviderUnavailableError],
    *,
    engine_id: str,
    message: str,
    suggestion: str,
    retry_after_s: float | None,
) -> Exception:
    """Build a transient provider error carrying the retry-after hint."""
    context: ErrorContext = ErrorContext(
        code=error_type.error_code,
        message=message,
        suggestion=suggestion,
        details={"engine_id": engine_id},
    )
    return error_type(context=context, retry_after_s=retry_after_s)


def raise_request_error(message: str, *, suggestion: str, engine_id: str | None = None) -> Never:
    """Raise a request failure, tagging the engine id when one is given."""
    context: ErrorContext = ErrorContext(
        code=ErrorCode.LLM_REQUEST_FAILED,
        message=message,
        suggestion=suggestion,
        details={"engine_id": engine_id} if engine_id is not None else {},
    )
    raise LlmRequestError(context=context)
