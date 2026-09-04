"""Single synchronous Palantir engine over the four Foundry proxy protocols."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from types import TracebackType
from typing import TYPE_CHECKING, Any, Final, Self

from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines._sdk_helpers import raise_request_error
from anishift.services.llm.engines.palantir.config import (
    PalantirGenerationOptions,
    PalantirModelConfig,
)
from anishift.services.llm.engines.palantir.errors import PALANTIR_ENGINE_ID, raise_palantir_config_error
from anishift.services.llm.engines.palantir.http import (
    build_palantir_client,
    send_palantir_request,
    stream_palantir_request,
)
from anishift.services.llm.engines.palantir.normalize import (
    google_stream_delta,
    merge_google_stream,
    merge_openai_stream,
    normalize_palantir_response,
    openai_stream_delta,
)
from anishift.services.llm.engines.palantir.protocols import PalantirHttpRequest, build_palantir_request
from anishift.services.llm.types import LlmRequest, LlmResponse
from anishift.services.llm.wire_protocol import ModelProtocol
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    import httpx

__all__ = ["PalantirService"]

logger = get_logger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

_STREAM_MERGERS: Final[dict[ModelProtocol, Callable[[tuple[Mapping[str, Any], ...]], Mapping[str, Any]]]] = {
    ModelProtocol.GOOGLE_GENERATE: merge_google_stream,
    ModelProtocol.OPENAI_CHAT: merge_openai_stream,
}
"""Stream mergers per protocol; an absent protocol has no server-sent shape."""

_STREAM_TEXTS: Final[dict[ModelProtocol, Callable[[Mapping[str, Any]], str]]] = {
    ModelProtocol.GOOGLE_GENERATE: google_stream_delta,
    ModelProtocol.OPENAI_CHAT: openai_stream_delta,
}
"""Arriving-text extractors, one per protocol in :data:`_STREAM_MERGERS`."""


class PalantirService:
    """Synchronous engine for one catalog alias served by a Foundry proxy."""

    __slots__ = ("_client", "_closed", "_config", "_model_config")

    def __init__(self, config: LlmConfig, *, client: httpx.Client | None = None) -> None:
        """Resolve the immutable model configuration without opening a socket."""
        self._config: LlmConfig = config
        self._model_config: PalantirModelConfig = _resolve_model_config(config)
        self._client: httpx.Client | None = client
        self._closed: bool = False

    @property
    def engine_id(self) -> str:
        """Return the stable registry id shared by the Palantir modules."""
        return PALANTIR_ENGINE_ID

    @property
    def is_available(self) -> bool:
        """Return whether a Palantir token was resolved into the configuration."""
        if self._closed:
            return False
        return bool(self._config.api_key.strip())

    def complete(self, request: LlmRequest) -> LlmResponse:
        """Run one completion and normalize its response."""
        if self._closed:
            raise_request_error(
                "Palantir engine is already closed",
                suggestion="Create a new engine before sending another request.",
                engine_id=PALANTIR_ENGINE_ID,
            )
        built: PalantirHttpRequest = build_palantir_request(
            self._model_config,
            request,
            self._generation_options(),
        )
        started_at: float = time.perf_counter()
        payload = send_palantir_request(
            self._ensure_client(),
            built,
            alias=self._model_config.alias,
        )
        latency_ms: float = (time.perf_counter() - started_at) * 1000
        return normalize_palantir_response(
            self._model_config.protocol,
            payload,
            alias=self._model_config.alias,
            engine_id=PALANTIR_ENGINE_ID,
            provider_model_id=self._model_config.provider_model_id,
            latency_ms=latency_ms,
        )

    def complete_stream(
        self,
        request: LlmRequest,
        *,
        on_text: Callable[[str], None] | None = None,
    ) -> LlmResponse:
        """Stream one completion, handing every arriving text delta to *on_text*."""
        merge = _STREAM_MERGERS.get(self._model_config.protocol)
        if merge is None:
            return self.complete(request)
        if self._closed:
            raise_request_error(
                "Palantir engine is already closed",
                suggestion="Create a new engine before sending another request.",
                engine_id=PALANTIR_ENGINE_ID,
            )
        built: PalantirHttpRequest = build_palantir_request(
            self._model_config,
            request,
            self._generation_options(),
            stream=True,
        )
        started_at: float = time.perf_counter()
        events: tuple[Mapping[str, Any], ...] = stream_palantir_request(
            self._ensure_client(),
            built,
            alias=self._model_config.alias,
            on_event=self._text_reporter(on_text),
        )
        latency_ms: float = (time.perf_counter() - started_at) * 1000
        return normalize_palantir_response(
            self._model_config.protocol,
            merge(events),
            alias=self._model_config.alias,
            engine_id=PALANTIR_ENGINE_ID,
            provider_model_id=self._model_config.provider_model_id,
            latency_ms=latency_ms,
        )

    def _text_reporter(
        self,
        on_text: Callable[[str], None] | None,
    ) -> Callable[[Mapping[str, Any]], None] | None:
        """Adapt one protocol's stream events into plain arriving text."""
        if on_text is None:
            return None
        extract = _STREAM_TEXTS[self._model_config.protocol]

        def report(event: Mapping[str, Any]) -> None:
            delta: str = extract(event)
            if delta:
                on_text(delta)

        return report

    def close(self) -> None:
        """Close the owned client exactly once and mark the engine closed."""
        if self._closed:
            return
        self._closed = True
        client: httpx.Client | None = self._client
        self._client = None
        if client is not None:
            client.close()
        logger.debug("Palantir engine closed", alias=self._model_config.alias)

    def __enter__(self) -> Self:
        """Enter the engine lifecycle without creating its client."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the owned client when leaving the engine context."""
        del exc_type, exc_value, traceback
        self.close()

    def _ensure_client(self) -> httpx.Client:
        if self._client is None:
            self._client = build_palantir_client(self._config.timeout_s)
        return self._client

    def _generation_options(self) -> PalantirGenerationOptions:
        return PalantirGenerationOptions(
            temperature=self._config.temperature,
            top_p=self._config.top_p,
            max_output_tokens=self._config.max_output_tokens,
        )


def _resolve_model_config(config: LlmConfig) -> PalantirModelConfig:
    """Build the immutable model configuration from the neutral config."""
    if config.protocol is None:
        raise_palantir_config_error(
            "Palantir engine requires a wire protocol",
            field_name="protocol",
            suggestion="Resolve the catalog alias to a provider protocol before selecting the engine.",
        )
    return PalantirModelConfig(
        alias=config.alias,
        provider_id=config.provider_id,
        protocol=config.protocol,
        base_url=config.base_url or "",
        provider_model_id=config.provider_model_id,
        token=config.api_key,
    )
