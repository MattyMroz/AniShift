"""Router mapping one neutral request onto the four Foundry proxy protocols."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Final, cast
from urllib.parse import quote

from anishift.services.llm.engines._sdk_helpers import (
    DEFAULT_PDF_NAME,
    anthropic_content_block,
    group_adjacent_text_parts,
    joined_text,
    require_file_modalities,
)
from anishift.services.llm.engines.palantir.auth import authorization_headers
from anishift.services.llm.engines.palantir.config import PalantirGenerationOptions, PalantirModelConfig
from anishift.services.llm.engines.palantir.errors import PALANTIR_ENGINE_ID, raise_palantir_config_error
from anishift.services.llm.types import FilePart, LlmContentPart, LlmMessage, LlmRequest, LlmRole, TextPart
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
    """One protocol-shaped request, described without being sent."""

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

_RESPONSES_ROUTE: Final[str] = "/responses"
"""Route used by the Foundry OpenAI and xAI proxies."""

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
"""Output limit written when the caller configured none."""

_GOOGLE_ROLES: Final[Mapping[LlmRole, str]] = MappingProxyType(
    {
        LlmRole.USER: "user",
        LlmRole.ASSISTANT: "model",
    },
)
"""Google role names of the neutral conversation roles."""


def request_builder(protocol: ModelProtocol) -> PalantirRequestBuilder:
    """Return the request builder the given protocol declares."""
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
    """Build the request one configuration and one neutral prompt describe."""
    require_file_modalities(request, accepted=config.file_modalities, engine_id=PALANTIR_ENGINE_ID)
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
    """Turn one built request into the server-sent-events variant of its protocol."""
    if config.protocol is ModelProtocol.OPENAI_RESPONSES:
        return replace(built, body={**dict(built.body), "stream": True})
    if config.protocol is not ModelProtocol.GOOGLE_GENERATE:
        raise_palantir_config_error(
            "Palantir streaming is not available for this provider protocol",
            field_name="protocol",
            suggestion="Use the normal completion path for this provider protocol.",
        )
    route: str = _STREAM_GENERATE_CONTENT_ROUTE.format(model=quote(config.provider_model_id, safe=""))
    return replace(built, url=f"{config.base_url}{route}")


def _build_responses(
    config: PalantirModelConfig,
    request: LlmRequest,
    options: PalantirGenerationOptions,
) -> PalantirHttpRequest:
    body: dict[str, Any] = {
        **options.request_options,
        "model": config.provider_model_id,
        "input": [_responses_item(message) for message in request.messages],
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


def _responses_item(message: LlmMessage) -> dict[str, Any]:
    if message.role is not LlmRole.USER:
        return {"role": message.role.value, "content": joined_text(message.parts)}
    blocks: list[dict[str, Any]] = [
        {"type": "input_text", "text": part.text} if isinstance(part, TextPart) else _responses_file(part)
        for part in group_adjacent_text_parts(message.parts)
    ]
    return {"role": message.role.value, "content": blocks}


def _responses_file(part: FilePart) -> dict[str, Any]:
    if part.modality == "image":
        return {"type": "input_image", "image_url": part.data_url}
    return {"type": "input_file", "filename": part.name or DEFAULT_PDF_NAME, "file_data": part.data_url}


def _google_part(part: LlmContentPart) -> dict[str, Any]:
    if isinstance(part, TextPart):
        return {"text": part.text}
    return {"inlineData": {"mimeType": part.media_type, "data": part.base64}}


def _build_anthropic_messages(
    config: PalantirModelConfig,
    request: LlmRequest,
    options: PalantirGenerationOptions,
) -> PalantirHttpRequest:
    """Shape one Anthropic Messages request, hoisting system content."""
    system_blocks: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    for message in request.messages:
        blocks: list[dict[str, object]] = [anthropic_content_block(part) for part in message.parts]
        if message.role is LlmRole.SYSTEM:
            system_blocks.extend(blocks)
            continue
        messages.append({"role": message.role.value, "content": blocks})
    body: dict[str, Any] = {
        **options.request_options,
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
    system_parts: list[dict[str, Any]] = []
    contents: list[dict[str, Any]] = []
    for message in request.messages:
        parts: list[dict[str, Any]] = [_google_part(part) for part in message.parts]
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
    generation: dict[str, Any] = dict(cast("Mapping[str, object]", options.request_options.get("generationConfig", {})))
    if options.temperature is not None:
        generation["temperature"] = options.temperature
    if options.top_p is not None:
        generation["topP"] = options.top_p
    if options.max_output_tokens is not None:
        generation["maxOutputTokens"] = options.max_output_tokens
    return generation


# ── Constants ────────────────────────────────────────────────────────────────

_BUILDERS: Final[Mapping[ModelProtocol, PalantirRequestBuilder]] = MappingProxyType(
    {
        ModelProtocol.OPENAI_RESPONSES: _build_responses,
        ModelProtocol.ANTHROPIC_MESSAGES: _build_anthropic_messages,
        ModelProtocol.GOOGLE_GENERATE: _build_google_generate,
        ModelProtocol.XAI_RESPONSES: _build_responses,
    },
)
"""Builder of every supported protocol, defined after the builders it names."""
