"""Single synchronous Palantir engine over the four Foundry proxy protocols.

The engine ties the T-013 configuration, authorization and routing to the wire:
it resolves one catalog alias into an immutable ``PalantirModelConfig``, builds
the protocol-shaped request, sends it through the owned ``httpx`` client and
folds the response into the neutral ``LlmResponse``. The token arrives in
``LlmConfig.api_key`` — the composition root fills it from
``Settings.palantir_token``, which already folds the process environment, the
``.env`` file and the compatibility variable into one resolved value — so the
engine has a single source of truth and never reads the environment itself. It
carries no retry of its own — that stays in the LLM domain retry policy — and no
cancellation, which the retry policy checks between attempts.

Google generateContent calls use the provider SSE route when invoked through
``LlmService``; the other proxy protocols retain their ordinary completion path.

Laziness is deliberate and structural: ``palantir/__init__.py`` imports neither
this module nor its HTTP module, and the registry names this submodule instead
of the package, so an HTTP client is loaded only when an engine is created. The
client itself is then built on the first completion. ``httpx`` appears here only
in annotations, which is why it stays behind ``TYPE_CHECKING`` — an eager import
would put an HTTP client back on the path of anything that merely reaches the
Palantir configuration or routing.

Public API:
    PalantirService: The lazy engine implementing the synchronous LLM contract.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

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
from anishift.services.llm.engines.palantir.normalize import merge_google_stream, normalize_palantir_response
from anishift.services.llm.engines.palantir.protocols import PalantirHttpRequest, build_palantir_request
from anishift.services.llm.types import LlmRequest, LlmResponse
from anishift.services.llm.wire_protocol import ModelProtocol
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    import httpx

__all__ = ["PalantirService"]

logger = get_logger(__name__)


class PalantirService:
    """Synchronous engine for one catalog alias served by a Foundry proxy."""

    __slots__ = ("_client", "_closed", "_config", "_model_config")

    def __init__(self, config: LlmConfig, *, client: httpx.Client | None = None) -> None:
        """Resolve the immutable model configuration without opening a socket.

        Args:
            config: Provider-neutral configuration carrying the resolved alias,
                provider id, wire protocol, joined base URL, model id and the
                token in ``api_key``.
            client: Injected synchronous client, created lazily when absent.

        Raises:
            LlmAuthError: The token in ``api_key`` is absent or unsendable.
            LlmConfigError: The alias, provider, protocol or base URL is invalid.
        """
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
        """Run one completion and normalize its response.

        Args:
            request: Provider-neutral ordered messages of one completion.

        Returns:
            The normalized provider response.

        Raises:
            LlmRequestError: The engine is closed, or the response is unusable.
            LlmError: A transport or status failure mapped by the taxonomy.
        """
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

    def complete_stream(self, request: LlmRequest) -> LlmResponse:
        """Stream Google completions and use the normal path for other protocols."""
        if self._model_config.protocol is not ModelProtocol.GOOGLE_GENERATE:
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
        )
        latency_ms: float = (time.perf_counter() - started_at) * 1000
        return normalize_palantir_response(
            self._model_config.protocol,
            merge_google_stream(events),
            alias=self._model_config.alias,
            engine_id=PALANTIR_ENGINE_ID,
            provider_model_id=self._model_config.provider_model_id,
            latency_ms=latency_ms,
        )

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
    """Build the immutable model configuration from the neutral config.

    The catalog alias has already been resolved to a provider, a wire protocol
    and a joined base URL before ``LlmConfig`` was built, and the token was
    folded from the environment and ``.env`` into ``LlmConfig.api_key`` by
    ``Settings.palantir_token``; a blank value is rejected as an authentication
    failure by ``PalantirModelConfig``, naming the canonical variable.
    """
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
