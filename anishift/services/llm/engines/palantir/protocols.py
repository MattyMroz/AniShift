"""Router mapping one neutral request onto the four Foundry proxy protocols.

The catalog declares exactly one protocol per provider, and the router turns it
into the builder that shapes the request: the route appended to the configured
base URL, the headers and the JSON body. There is no fallback — an unsupported
protocol raises a configuration error instead of silently borrowing another
provider's shape.

``LlmMessage`` and its text parts are the only source of content. A content part
the protocol cannot express is rejected instead of being dropped, so nothing
disappears from a prompt on the way to the wire.

Nothing here performs I/O: a builder returns a ``PalantirHttpRequest``
description, and sending it is the job of the engine added later.

Public API:
    PalantirHttpRequest: Frozen description of one request; headers and body
        stay out of ``repr``.
    PalantirRequestBuilder: Signature every protocol builder implements.
    request_builder: Return the builder declared by one protocol.
    build_palantir_request: Build the request for one configuration.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Final
from urllib.parse import quote

from anishift.services.llm.engines._sdk_helpers import raise_request_error
from anishift.services.llm.engines.palantir.auth import authorization_headers
from anishift.services.llm.engines.palantir.config import PalantirGenerationOptions, PalantirModelConfig
from anishift.services.llm.engines.palantir.errors import PALANTIR_ENGINE_ID, raise_palantir_config_error
from anishift.services.llm.types import LlmMessage, LlmRequest, LlmRole, TextPart
from anishift.services.llm.wire_protocol import ModelProtocol
from anishift.utils.logger import get_logger

__all__ = [
    "PalantirHttpRequest",
    "PalantirRequestBuilder",
    "build_palantir_request",
    "request_builder",
]

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class PalantirHttpRequest:
    """One protocol-shaped request, described without being sent.

    Attributes:
        method: HTTP method of the proxy route.
        url: Absolute endpoint assembled from the configured base URL.
        headers: Allowlisted headers, kept out of ``repr`` because they carry
            the bearer token.
        body: JSON body, kept out of ``repr`` because it carries the prompt.
    """

    method: str
    url: str
    headers: Mapping[str, str] = field(repr=False)
    body: Mapping[str, Any] = field(repr=False)


type PalantirRequestBuilder = Callable[
    [PalantirModelConfig, LlmRequest, PalantirGenerationOptions],
    PalantirHttpRequest,
]
"""Signature shared by the builder of every supported protocol."""

# ── Constants ────────────────────────────────────────────────────────────────

_HTTP_METHOD: Final[str] = "POST"
"""Only method the four completion protocols use."""

_CHAT_COMPLETIONS_ROUTE: Final[str] = "/chat/completions"
"""Route of the OpenAI Chat Completions protocol."""

_RESPONSES_ROUTE: Final[str] = "/responses"
"""Route used by the Foundry xAI proxy for Grok models."""

_MESSAGES_ROUTE: Final[str] = "/messages"
"""Route of the Anthropic Messages protocol."""

_GENERATE_CONTENT_ROUTE: Final[str] = "/models/{model}:generateContent"
"""Route template of the Google generateContent protocol."""

_STREAM_GENERATE_CONTENT_ROUTE: Final[str] = "/models/{model}:streamGenerateContent?alt=sse"
"""SSE route template of the Google streaming generateContent protocol."""

_ANTHROPIC_VERSION_HEADER: Final[str] = "anthropic-version"
"""Header the Anthropic Messages API requires on every request."""

_ANTHROPIC_VERSION: Final[str] = "2023-06-01"
"""Anthropic Messages API version this mapper writes."""

_ANTHROPIC_DEFAULT_MAX_TOKENS: Final[int] = 8192
"""Output limit written when the caller configured none.

The Anthropic Messages protocol rejects a request without ``max_tokens``, so a
value is mandatory here. What to send through the proxy is a Palantir decision,
which is why this default is local instead of borrowed from the native Anthropic
engine: importing that package would load its SDK on a plain import of this one.
"""

_OPENAI_MAX_TOKENS_KEY: Final[str] = "max_completion_tokens"
"""Output limit keyword of the OpenAI Chat Completions endpoint."""

_COMPATIBLE_MAX_TOKENS_KEY: Final[str] = "max_tokens"
"""Output limit keyword every other Chat Completions endpoint accepts."""

_GOOGLE_ROLES: Final[Mapping[LlmRole, str]] = MappingProxyType(
    {
        LlmRole.USER: "user",
        LlmRole.ASSISTANT: "model",
    },
)
"""Google role names of the neutral conversation roles.

A system message has no role of its own there and becomes ``systemInstruction``.
"""


def request_builder(protocol: ModelProtocol) -> PalantirRequestBuilder:
    """Return the request builder the given protocol declares.

    Args:
        protocol: Wire protocol taken from a validated provider entry.

    Returns:
        The builder that shapes a request for that protocol.

    Raises:
        LlmConfigError: The value is outside the four supported protocols, so
            the failure stays visible instead of falling back to a provider the
            user did not choose.
    """
    builder: PalantirRequestBuilder | None = _BUILDERS.get(protocol)
    if builder is None:
        raise_palantir_config_error(
            "Palantir provider declares an unsupported protocol",
            field_name="protocol",
            suggestion=f"Use one of: {', '.join(item.value for item in ModelProtocol)}.",
        )
    return builder


def build_palantir_request(
    config: PalantirModelConfig,
    request: LlmRequest,
    options: PalantirGenerationOptions | None = None,
    *,
    stream: bool = False,
) -> PalantirHttpRequest:
    """Build the request one configuration and one neutral prompt describe.

    Args:
        config: Configuration whose protocol selects the builder.
        request: Neutral ordered messages of one completion.
        options: Already validated generation limits, none by default.
        stream: Whether to select Google's SSE endpoint.

    Returns:
        The described request, ready for an engine to send.

    Raises:
        LlmConfigError: The configured protocol is unsupported.
        LlmRequestError: A message carries no text or an unsupported part.
    """
    builder: PalantirRequestBuilder = request_builder(config.protocol)
    built: PalantirHttpRequest = builder(config, request, options or PalantirGenerationOptions())
    if stream:
        built = _streaming_variant(config, built)
    logger.debug(
        "Palantir request built",
        alias=config.alias,
        protocol=config.protocol.value,
        messages=len(request.messages),
    )
    return built


def _streaming_variant(config: PalantirModelConfig, built: PalantirHttpRequest) -> PalantirHttpRequest:
    """Turn one built request into the server-sent-events variant of its protocol.

    Google exposes a dedicated SSE route, while Chat Completions keeps its route
    and asks for a stream in the body.
    """
    if config.protocol is ModelProtocol.OPENAI_CHAT:
        return replace(built, body={**dict(built.body), "stream": True})
    if config.protocol is not ModelProtocol.GOOGLE_GENERATE:
        raise_palantir_config_error(
            "Palantir streaming is not available for this provider protocol",
            field_name="protocol",
            suggestion="Use the normal completion path for this provider protocol.",
        )
    route: str = _STREAM_GENERATE_CONTENT_ROUTE.format(model=quote(config.provider_model_id, safe=""))
    return replace(built, url=f"{config.base_url}{route}")


def _build_openai_chat(
    config: PalantirModelConfig,
    request: LlmRequest,
    options: PalantirGenerationOptions,
) -> PalantirHttpRequest:
    """Shape one OpenAI-compatible Chat Completions request."""
    return _chat_completions_request(
        config,
        request,
        options,
        max_tokens_key=_OPENAI_MAX_TOKENS_KEY,
    )


def _build_xai_responses(
    config: PalantirModelConfig,
    request: LlmRequest,
    options: PalantirGenerationOptions,
) -> PalantirHttpRequest:
    """Shape one non-streaming xAI Responses request."""
    input_items: list[dict[str, str]] = [
        {"role": message.role.value, "content": _joined_text(message)} for message in request.messages
    ]
    body: dict[str, Any] = {
        "model": config.provider_model_id,
        "input": input_items,
        "stream": False,
    }
    if options.temperature is not None:
        body["temperature"] = options.temperature
    if options.top_p is not None:
        body["top_p"] = options.top_p
    if options.max_output_tokens is not None:
        body["max_output_tokens"] = options.max_output_tokens
    return PalantirHttpRequest(
        method=_HTTP_METHOD,
        url=f"{config.base_url}{_RESPONSES_ROUTE}",
        headers=authorization_headers(config.token),
        body=body,
    )


def _chat_completions_request(
    config: PalantirModelConfig,
    request: LlmRequest,
    options: PalantirGenerationOptions,
    *,
    max_tokens_key: str,
) -> PalantirHttpRequest:
    """Shape a Chat Completions body, differing only in the output limit key."""
    messages: list[dict[str, str]] = [
        {"role": message.role.value, "content": _joined_text(message)} for message in request.messages
    ]
    body: dict[str, Any] = {"model": config.provider_model_id, "messages": messages}
    if options.temperature is not None:
        body["temperature"] = options.temperature
    if options.top_p is not None:
        body["top_p"] = options.top_p
    if options.max_output_tokens is not None:
        body[max_tokens_key] = options.max_output_tokens
    return PalantirHttpRequest(
        method=_HTTP_METHOD,
        url=f"{config.base_url}{_CHAT_COMPLETIONS_ROUTE}",
        headers=authorization_headers(config.token),
        body=body,
    )


def _build_anthropic_messages(
    config: PalantirModelConfig,
    request: LlmRequest,
    options: PalantirGenerationOptions,
) -> PalantirHttpRequest:
    """Shape one Anthropic Messages request, hoisting system content."""
    system_blocks: list[dict[str, str]] = []
    messages: list[dict[str, Any]] = []
    for message in request.messages:
        blocks: list[dict[str, str]] = [{"type": "text", "text": text} for text in _texts(message)]
        if message.role is LlmRole.SYSTEM:
            system_blocks.extend(blocks)
            continue
        messages.append({"role": message.role.value, "content": blocks})
    body: dict[str, Any] = {
        "model": config.provider_model_id,
        "max_tokens": options.max_output_tokens or _ANTHROPIC_DEFAULT_MAX_TOKENS,
        "messages": messages,
    }
    if system_blocks:
        body["system"] = system_blocks
    if options.temperature is not None:
        body["temperature"] = options.temperature
    if options.top_p is not None:
        body["top_p"] = options.top_p
    headers: dict[str, str] = authorization_headers(config.token)
    headers[_ANTHROPIC_VERSION_HEADER] = _ANTHROPIC_VERSION
    return PalantirHttpRequest(
        method=_HTTP_METHOD,
        url=f"{config.base_url}{_MESSAGES_ROUTE}",
        headers=headers,
        body=body,
    )


def _build_google_generate(
    config: PalantirModelConfig,
    request: LlmRequest,
    options: PalantirGenerationOptions,
) -> PalantirHttpRequest:
    """Shape one Google generateContent request, hoisting system content."""
    system_parts: list[dict[str, str]] = []
    contents: list[dict[str, Any]] = []
    for message in request.messages:
        parts: list[dict[str, str]] = [{"text": text} for text in _texts(message)]
        if message.role is LlmRole.SYSTEM:
            system_parts.extend(parts)
            continue
        contents.append({"role": _GOOGLE_ROLES[message.role], "parts": parts})
    body: dict[str, Any] = {"contents": contents}
    if system_parts:
        body["systemInstruction"] = {"parts": system_parts}
    generation: dict[str, Any] = _generation_config(options)
    if generation:
        body["generationConfig"] = generation
    route: str = _GENERATE_CONTENT_ROUTE.format(model=quote(config.provider_model_id, safe=""))
    return PalantirHttpRequest(
        method=_HTTP_METHOD,
        url=f"{config.base_url}{route}",
        headers=authorization_headers(config.token),
        body=body,
    )


def _generation_config(options: PalantirGenerationOptions) -> dict[str, Any]:
    """Collect the Google generation limits that are actually configured."""
    generation: dict[str, Any] = {}
    if options.temperature is not None:
        generation["temperature"] = options.temperature
    if options.top_p is not None:
        generation["topP"] = options.top_p
    if options.max_output_tokens is not None:
        generation["maxOutputTokens"] = options.max_output_tokens
    return generation


def _texts(message: LlmMessage) -> list[str]:
    """Return the text of every part, rejecting a part no protocol can carry."""
    texts: list[str] = []
    for part in message.parts:
        if not isinstance(part, TextPart):
            raise_request_error(
                "Palantir received an unsupported content part",
                suggestion="Use text content parts for the Palantir proxy protocols.",
                engine_id=PALANTIR_ENGINE_ID,
            )
        texts.append(part.text)
    if not texts:
        raise_request_error(
            "Palantir message must contain at least one text part",
            suggestion="Add text content to every LLM message.",
            engine_id=PALANTIR_ENGINE_ID,
        )
    return texts


def _joined_text(message: LlmMessage) -> str:
    """Join every text part of one message into a single content string."""
    return "\n".join(_texts(message))


# ── Constants ────────────────────────────────────────────────────────────────

_BUILDERS: Final[Mapping[ModelProtocol, PalantirRequestBuilder]] = MappingProxyType(
    {
        ModelProtocol.OPENAI_CHAT: _build_openai_chat,
        ModelProtocol.ANTHROPIC_MESSAGES: _build_anthropic_messages,
        ModelProtocol.GOOGLE_GENERATE: _build_google_generate,
        ModelProtocol.XAI_RESPONSES: _build_xai_responses,
    },
)
"""Builder of every supported protocol, defined after the builders it names.

A protocol missing from this table has no request shape and cannot fall back to
another provider.
"""
