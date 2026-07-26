"""LLM domain value types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.llm.errors import LlmRequestError

__all__ = [
    "LlmContentPart",
    "LlmMessage",
    "LlmRequest",
    "LlmResponse",
    "LlmRole",
    "LlmUsage",
    "TextPart",
]


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


type LlmContentPart = TextPart
"""Supported provider-neutral content parts."""


@dataclass(frozen=True, slots=True)
class LlmMessage:
    """One ordered LLM message."""

    role: LlmRole
    parts: tuple[LlmContentPart, ...]


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


def _raise_request_error(message: str, *, field_name: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.LLM_REQUEST_FAILED,
        message=message,
        suggestion="Check the LLM request messages and text content.",
        details={"field": field_name},
    )
    raise LlmRequestError(context=context)
