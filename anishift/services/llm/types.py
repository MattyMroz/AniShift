"""LLM domain value types."""

from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, Literal, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.llm.errors import LlmRequestError

__all__ = [
    "FilePart",
    "LlmContentPart",
    "LlmMessage",
    "LlmRequest",
    "LlmResponse",
    "LlmRole",
    "LlmUsage",
    "Modality",
    "TextPart",
]

# ── Constants ─────────────────────────────────────────────────────────────────

type Modality = Literal["image", "pdf", "audio", "video"]
"""Supported provider-neutral file modalities."""

_IMAGE_MEDIA_TYPES: Final[frozenset[str]] = frozenset({"image/png", "image/jpeg", "image/webp"})
"""Supported image media types."""


class LlmRole(StrEnum):
    """Supported roles in an LLM conversation."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class TextPart:
    """One non-empty text content part."""

    text: str

    def __post_init__(self) -> None:
        """Validate that the content contains visible text."""
        if not self.text.strip():
            _raise_request_error(
                "LLM text content cannot be empty",
                field_name="text",
            )


@dataclass(frozen=True, slots=True)
class FilePart:
    """One non-empty file with a supported media type."""

    media_type: str
    data: bytes = field(repr=False)
    name: str = ""
    modality: Modality = field(init=False)

    def __post_init__(self) -> None:
        """Require file data and a supported media type."""
        if not self.data:
            _raise_request_error("LLM file data cannot be empty", field_name="data")
        object.__setattr__(self, "modality", _file_modality(self.media_type))

    @property
    def base64(self) -> str:
        """Return the file data encoded as base64."""
        return b64encode(self.data).decode("ascii")

    @property
    def data_url(self) -> str:
        """Return the file as a base64 data URL."""
        return f"data:{self.media_type};base64,{self.base64}"


type LlmContentPart = TextPart | FilePart
"""Supported provider-neutral content parts."""


@dataclass(frozen=True, slots=True)
class LlmMessage:
    """One ordered LLM message."""

    role: LlmRole
    parts: tuple[LlmContentPart, ...]

    def __post_init__(self) -> None:
        """Require text and allow files only in user messages."""
        if not any(isinstance(part, TextPart) for part in self.parts):
            _raise_request_error("LLM message must contain at least one text part", field_name="parts")
        if self.role is not LlmRole.USER and any(isinstance(part, FilePart) for part in self.parts):
            _raise_request_error("LLM files are allowed only in user messages", field_name="role")


@dataclass(frozen=True, slots=True)
class LlmRequest:
    """Ordered messages sent in one LLM completion."""

    messages: tuple[LlmMessage, ...]

    def __post_init__(self) -> None:
        """Require at least one user message."""
        has_user_message: bool = any(message.role is LlmRole.USER for message in self.messages)
        if not has_user_message:
            _raise_request_error(
                "LLM request must contain at least one user message",
                field_name="messages",
            )


@dataclass(frozen=True, slots=True)
class LlmUsage:
    """Usage and optional direct cost reported by an LLM provider."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reported_cost: float | None = None

    def __post_init__(self) -> None:
        """Derive total usage only when both component counts are known."""
        if self.total_tokens is not None:
            return
        if self.input_tokens is None or self.output_tokens is None:
            return
        object.__setattr__(self, "total_tokens", self.input_tokens + self.output_tokens)


@dataclass(frozen=True, slots=True)
class LlmResponse:
    """Normalized result of one provider completion."""

    text: str
    engine_id: str
    provider_model_id: str
    finish_reason: str
    latency_ms: float
    usage: LlmUsage


def _file_modality(media_type: str) -> Modality:
    if media_type in _IMAGE_MEDIA_TYPES:
        return "image"
    if media_type == "application/pdf":
        return "pdf"
    if media_type.startswith("audio/"):
        return "audio"
    if media_type.startswith("video/"):
        return "video"
    return _raise_request_error("LLM file media type is unsupported", field_name="media_type")


def _raise_request_error(message: str, *, field_name: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.LLM_REQUEST_FAILED,
        message=message,
        suggestion="Check the LLM request messages and text content.",
        details={"field": field_name},
    )
    raise LlmRequestError(context=context)
