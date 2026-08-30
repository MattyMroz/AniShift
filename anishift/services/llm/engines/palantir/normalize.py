"""Normalization of the four Foundry proxy responses into ``LlmResponse``.

Each supported protocol returns a different response shape, so this module
extracts the completion text, the finish reason and the token usage from the
already decoded body and folds them into the single neutral ``LlmResponse``. No
provider structure, no raw body fragment and no header ever crosses this
boundary: a shape that does not match the protocol becomes a safe
``PalantirResponseDefect`` label, and a completion the provider policy blocked
becomes a typed blocked error carrying only a normalized finish reason.

A blocked completion wins over a text-shape defect. Every protocol withholds the
text when its policy blocks — OpenAI sends ``content: null``, Google omits the
candidate content and Anthropic sends an empty block list — so each protocol
probes the blocking signal on a tolerant read before any field is required.
Reading the text first would report those bodies as malformed and send the user
to debug the provider route instead of the content. The probe recognizes only
blocking reasons, so a body that is genuinely malformed still yields its typed
defect.

The body is always a fully read mapping here; this module never touches the
network and never reassembles a stream. A chunked or event-stream body has
already failed to decode into a mapping before reaching this module and is
reported as an unreadable body.

Public API:
    normalize_palantir_response: Map one decoded proxy body onto an
        ``LlmResponse`` or raise a typed failure.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Final

from anishift.services.llm.engines._sdk_helpers import normalize_finish_reason, optional_int
from anishift.services.llm.engines.palantir.errors import (
    PalantirResponseDefect,
    palantir_blocked_error,
    palantir_response_error,
    raise_palantir_config_error,
)
from anishift.services.llm.types import LlmResponse, LlmUsage
from anishift.services.llm.wire_protocol import ModelProtocol
from anishift.utils.logger import get_logger

__all__ = ["normalize_palantir_response"]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _Extracted:
    """Protocol-neutral fields pulled from one decoded response body."""

    text: str
    finish_reason: str
    usage: LlmUsage


type _Extractor = Callable[[Mapping[str, Any], str], _Extracted]
"""Signature of one protocol-specific response reader."""

type _BlockSignalReader = Callable[[Mapping[str, Any]], str]
"""Signature of one protocol-specific blocking probe, ``""`` when nothing blocks."""


@dataclass(frozen=True, slots=True)
class _ProtocolReader:
    """The two readers one protocol needs, in the order they must run.

    Attributes:
        block_signal: Tolerant probe returning the normalized blocking reason of
            a withheld completion, or ``""`` when the body is not blocked.
        extract: Strict reader that requires a well-formed body and rejects
            anything else as a typed defect.
    """

    block_signal: _BlockSignalReader
    extract: _Extractor


# ── Constants ────────────────────────────────────────────────────────────────

_BLOCKED_FINISH_REASONS: Final[frozenset[str]] = frozenset(
    {
        "blocked",
        "blocklist",
        "content_filter",
        "prohibited_content",
        "recitation",
        "refusal",
        "safety",
    },
)
"""Normalized finish reasons that mean the provider withheld the completion."""


def normalize_palantir_response(  # noqa: PLR0913 - one explicit argument per response coordinate
    protocol: ModelProtocol,
    payload: object,
    *,
    alias: str,
    engine_id: str,
    provider_model_id: str,
    latency_ms: float,
) -> LlmResponse:
    """Fold one decoded proxy body into the neutral ``LlmResponse``.

    Args:
        protocol: Wire protocol whose response shape the body follows.
        payload: Decoded response body of one completion.
        alias: Catalog alias used only in safe error diagnostics.
        engine_id: Registry id stamped on the response.
        provider_model_id: Configured model id stamped on the response.
        latency_ms: Measured round trip of the request.

    Returns:
        The normalized completion with text, usage and finish reason.

    Raises:
        LlmConfigError: The protocol has no normalizer, keeping an unsupported
            protocol a visible configuration failure.
        LlmOutputBlockedError: The provider policy blocked the completion, which
            is decided before any text field is required.
        LlmRequestError: The body does not match the protocol or is empty.
    """
    reader: _ProtocolReader | None = _READERS.get(protocol)
    if reader is None:
        raise_palantir_config_error(
            "Palantir provider declares an unsupported protocol",
            field_name="protocol",
            suggestion=f"Use one of: {', '.join(item.value for item in ModelProtocol)}.",
        )
    if not isinstance(payload, Mapping):
        raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNEXPECTED_SHAPE)
    blocked_reason: str = reader.block_signal(payload)
    if blocked_reason:
        raise palantir_blocked_error(alias=alias, finish_reason=blocked_reason)
    extracted: _Extracted = reader.extract(payload, alias)
    if not extracted.text.strip():
        raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.EMPTY_TEXT)
    logger.debug(
        "Palantir response normalized",
        alias=alias,
        protocol=protocol.value,
        finish_reason=extracted.finish_reason,
    )
    return LlmResponse(
        text=extracted.text,
        engine_id=engine_id,
        provider_model_id=provider_model_id,
        finish_reason=extracted.finish_reason,
        latency_ms=max(0.0, latency_ms),
        usage=extracted.usage,
    )


def _chat_block_signal(payload: Mapping[str, Any]) -> str:
    """Probe a Chat Completions body for a refusal or a blocking finish reason."""
    choice: Mapping[str, Any] | None = _optional_first(payload, key="choices")
    if choice is None:
        return ""
    message: object = choice.get("message")
    if isinstance(message, Mapping) and _is_visible_text(message.get("refusal")):
        return "refusal"
    return _blocking_reason(choice.get("finish_reason"))


def _anthropic_block_signal(payload: Mapping[str, Any]) -> str:
    """Probe an Anthropic Messages body for a blocking stop reason."""
    return _blocking_reason(payload.get("stop_reason"))


def _google_block_signal(payload: Mapping[str, Any]) -> str:
    """Probe a generateContent body for a prompt-level or candidate-level block."""
    prompt_block: str = _prompt_block_reason(payload)
    if prompt_block:
        return prompt_block
    candidate: Mapping[str, Any] | None = _optional_first(payload, key="candidates")
    if candidate is None:
        return ""
    return _blocking_reason(candidate.get("finishReason"))


def _responses_block_signal(payload: Mapping[str, Any]) -> str:
    """Probe a Responses body for an incomplete or explicit refusal result."""
    incomplete_details: object = payload.get("incomplete_details")
    if isinstance(incomplete_details, Mapping):
        reason: str = _blocking_reason(incomplete_details.get("reason"))
        if reason:
            return reason
    output: object = payload.get("output")
    if not isinstance(output, (list, tuple)):
        return ""
    for item in output:
        if _responses_item_refuses(item):
            return "refusal"
    return ""


def _responses_item_refuses(item: object) -> bool:
    if not isinstance(item, Mapping) or item.get("type") != "message":
        return False
    content: object = item.get("content")
    if not isinstance(content, (list, tuple)):
        return False
    return any(
        isinstance(part, Mapping)
        and part.get("type") == "refusal"
        and (_is_visible_text(part.get("refusal")) or _is_visible_text(part.get("text")))
        for part in content
    )


def _prompt_block_reason(payload: Mapping[str, Any]) -> str:
    """Return the Google prompt-level block reason, whatever value it carries.

    Google reports ``promptFeedback.blockReason`` only when it withheld the
    completion, so any visible value blocks, unlike a candidate finish reason
    that also carries the ordinary stop values.
    """
    feedback: object = payload.get("promptFeedback")
    if not isinstance(feedback, Mapping):
        return ""
    block_reason: object = feedback.get("blockReason")
    if not _is_visible_text(block_reason):
        return ""
    return normalize_finish_reason(block_reason)


def _blocking_reason(value: object) -> str:
    """Return the normalized finish reason only when it means a withheld answer."""
    reason: str = normalize_finish_reason(value)
    return reason if reason in _BLOCKED_FINISH_REASONS else ""


def _optional_first(payload: Mapping[str, Any], *, key: str) -> Mapping[str, Any] | None:
    """Return the first candidate mapping, or ``None`` for any other shape."""
    candidates: object = payload.get(key)
    if not isinstance(candidates, (list, tuple)) or not candidates:
        return None
    first: object = candidates[0]
    return first if isinstance(first, Mapping) else None


def _is_visible_text(value: object) -> bool:
    """Return whether the value is a string carrying visible characters."""
    return isinstance(value, str) and bool(value.strip())


def _extract_chat_completions(payload: Mapping[str, Any], alias: str) -> _Extracted:
    """Read text, finish reason and usage from a Chat Completions body."""
    choice: Mapping[str, Any] = _first_choice(payload, alias, key="choices")
    message: object = choice.get("message")
    if not isinstance(message, Mapping):
        raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNEXPECTED_SHAPE)
    return _Extracted(
        text=_string_field(message.get("content"), alias),
        finish_reason=normalize_finish_reason(choice.get("finish_reason")),
        usage=_chat_usage(payload.get("usage")),
    )


def _extract_anthropic_messages(payload: Mapping[str, Any], alias: str) -> _Extracted:
    """Read text, finish reason and usage from an Anthropic Messages body."""
    blocks: object = payload.get("content")
    if not isinstance(blocks, (list, tuple)) or not blocks:
        raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.MISSING_CHOICE)
    return _Extracted(
        text=_joined_text_blocks(blocks, alias),
        finish_reason=normalize_finish_reason(payload.get("stop_reason")),
        usage=_anthropic_usage(payload.get("usage")),
    )


def _extract_google_generate(payload: Mapping[str, Any], alias: str) -> _Extracted:
    """Read text, finish reason and usage from a generateContent body."""
    candidate: Mapping[str, Any] = _first_choice(payload, alias, key="candidates")
    content: object = candidate.get("content")
    if not isinstance(content, Mapping):
        raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNEXPECTED_SHAPE)
    parts: object = content.get("parts")
    if not isinstance(parts, (list, tuple)):
        raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNEXPECTED_SHAPE)
    return _Extracted(
        text=_joined_text_parts(parts, alias),
        finish_reason=normalize_finish_reason(candidate.get("finishReason")),
        usage=_google_usage(payload.get("usageMetadata")),
    )


def _extract_xai_responses(payload: Mapping[str, Any], alias: str) -> _Extracted:
    """Read message text, status and usage from an xAI Responses body."""
    output: object = payload.get("output")
    if not isinstance(output, (list, tuple)) or not output:
        raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.MISSING_CHOICE)
    texts: list[str] = []
    for item in output:
        if not isinstance(item, Mapping):
            raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNEXPECTED_SHAPE)
        if item.get("type") != "message":
            continue
        content: object = item.get("content")
        if not isinstance(content, (list, tuple)):
            raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNEXPECTED_SHAPE)
        texts.extend(_responses_text_parts(content, alias))
    return _Extracted(
        text="".join(texts),
        finish_reason=normalize_finish_reason(payload.get("status")),
        usage=_responses_usage(payload.get("usage")),
    )


def _first_choice(payload: Mapping[str, Any], alias: str, *, key: str) -> Mapping[str, Any]:
    """Return the first completion candidate, or a typed defect when absent."""
    choices: object = payload.get(key)
    if not isinstance(choices, (list, tuple)) or not choices:
        raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.MISSING_CHOICE)
    choice: object = choices[0]
    if not isinstance(choice, Mapping):
        raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNEXPECTED_SHAPE)
    return choice


def _string_field(value: object, alias: str) -> str:
    """Return a string completion field, rejecting a non-string shape."""
    if not isinstance(value, str):
        raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNEXPECTED_SHAPE)
    return value


def _joined_text_blocks(blocks: list[Any] | tuple[Any, ...], alias: str) -> str:
    """Join the text of every Anthropic ``text`` block into one string."""
    texts: list[str] = []
    for block in blocks:
        if not isinstance(block, Mapping):
            raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNEXPECTED_SHAPE)
        if block.get("type") != "text":
            continue
        texts.append(_string_field(block.get("text"), alias))
    return "".join(texts)


def _joined_text_parts(parts: list[Any] | tuple[Any, ...], alias: str) -> str:
    """Join the text of every Google content part into one string."""
    texts: list[str] = []
    for part in parts:
        if not isinstance(part, Mapping):
            raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNEXPECTED_SHAPE)
        if "text" not in part:
            continue
        texts.append(_string_field(part.get("text"), alias))
    return "".join(texts)


def _responses_text_parts(parts: list[Any] | tuple[Any, ...], alias: str) -> list[str]:
    texts: list[str] = []
    for part in parts:
        if not isinstance(part, Mapping):
            raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNEXPECTED_SHAPE)
        if part.get("type") != "output_text":
            continue
        texts.append(_string_field(part.get("text"), alias))
    return texts


def _chat_usage(usage: object) -> LlmUsage:
    """Read Chat Completions usage counters, tolerating a missing block."""
    if not isinstance(usage, Mapping):
        return LlmUsage()
    return LlmUsage(
        input_tokens=optional_int(usage.get("prompt_tokens")),
        output_tokens=optional_int(usage.get("completion_tokens")),
        total_tokens=optional_int(usage.get("total_tokens")),
    )


def _anthropic_usage(usage: object) -> LlmUsage:
    """Read Anthropic usage counters, tolerating a missing block."""
    if not isinstance(usage, Mapping):
        return LlmUsage()
    return LlmUsage(
        input_tokens=optional_int(usage.get("input_tokens")),
        output_tokens=optional_int(usage.get("output_tokens")),
    )


def _google_usage(usage: object) -> LlmUsage:
    """Read Google usage counters, tolerating a missing block."""
    if not isinstance(usage, Mapping):
        return LlmUsage()
    return LlmUsage(
        input_tokens=optional_int(usage.get("promptTokenCount")),
        output_tokens=optional_int(usage.get("candidatesTokenCount")),
        total_tokens=optional_int(usage.get("totalTokenCount")),
    )


def _responses_usage(usage: object) -> LlmUsage:
    if not isinstance(usage, Mapping):
        return LlmUsage()
    return LlmUsage(
        input_tokens=optional_int(usage.get("input_tokens")),
        output_tokens=optional_int(usage.get("output_tokens")),
        total_tokens=optional_int(usage.get("total_tokens")),
    )


# ── Constants ────────────────────────────────────────────────────────────────

_READERS: Final[Mapping[ModelProtocol, _ProtocolReader]] = MappingProxyType(
    {
        ModelProtocol.OPENAI_CHAT: _ProtocolReader(_chat_block_signal, _extract_chat_completions),
        ModelProtocol.XAI_RESPONSES: _ProtocolReader(_responses_block_signal, _extract_xai_responses),
        ModelProtocol.ANTHROPIC_MESSAGES: _ProtocolReader(_anthropic_block_signal, _extract_anthropic_messages),
        ModelProtocol.GOOGLE_GENERATE: _ProtocolReader(_google_block_signal, _extract_google_generate),
    },
)
"""Blocking probe and response reader of every supported protocol.

A protocol missing here has no response shape and cannot borrow another
provider's normalizer.
"""
