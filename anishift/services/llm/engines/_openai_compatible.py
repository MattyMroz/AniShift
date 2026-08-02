"""Shared synchronous transport for OpenAI-compatible chat completions."""

from __future__ import annotations

import importlib
import time
from collections.abc import Mapping
from dataclasses import dataclass
from http import HTTPStatus
from types import ModuleType, TracebackType
from typing import Any, Final, Literal, Protocol, Self, cast

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines._sdk_helpers import (
    error_with_context as _error_with_context,
)
from anishift.services.llm.engines._sdk_helpers import (
    normalize_finish_reason as _normalize_finish_reason,
)
from anishift.services.llm.engines._sdk_helpers import (
    optional_int as _optional_int,
)
from anishift.services.llm.engines._sdk_helpers import (
    raise_request_error as _raise_request_error,
)
from anishift.services.llm.engines._sdk_helpers import (
    retry_after_seconds as _retry_after_seconds,
)
from anishift.services.llm.engines._sdk_helpers import (
    status_code as _status_code,
)
from anishift.services.llm.engines._sdk_helpers import (
    transient_error_with_context as _transient_error_with_context,
)
from anishift.services.llm.errors import (
    LlmAuthError,
    LlmConfigError,
    LlmContextLengthError,
    LlmModelError,
    LlmOutputBlockedError,
    LlmPaymentError,
    LlmProviderUnavailableError,
    LlmQuotaError,
    LlmRateLimitError,
    LlmRequestError,
    LlmTimeoutError,
)
from anishift.services.llm.types import LlmRequest, LlmResponse, LlmUsage, TextPart

__all__ = [
    "ClientFactory",
    "OpenAiCompatibleProvider",
    "OpenAiCompatibleTransport",
]

type MaxTokensParameter = Literal["max_completion_tokens", "max_tokens"]
"""Supported OpenAI-compatible output limit keyword."""

_LOCAL_API_KEY_PLACEHOLDER: Final[str] = "local-no-api-key"
"""Internal SDK placeholder for an unauthenticated local endpoint."""

_QUOTA_CODES: Final[frozenset[str]] = frozenset(
    {
        "daily_limit_exceeded",
        "insufficient_quota",
        "quota_exceeded",
    }
)
"""Structured provider codes representing exhausted non-retryable quota."""

_PAYMENT_CODES: Final[frozenset[str]] = frozenset(
    {
        "billing_error",
        "billing_hard_limit_reached",
        "insufficient_credits",
        "payment_required",
    }
)
"""Structured provider codes representing a payment or credit failure."""

_MODEL_CODES: Final[frozenset[str]] = frozenset(
    {
        "invalid_model",
        "model_decommissioned",
        "model_not_found",
    }
)
"""Structured provider codes representing an unavailable model."""

_CONTEXT_CODES: Final[frozenset[str]] = frozenset(
    {
        "context_length_exceeded",
        "max_tokens_exceeded",
        "request_too_large",
    }
)
"""Structured provider codes representing an exceeded context window."""


class _ChatCompletions(Protocol):
    def create(self, **kwargs: Any) -> Any:
        """Create one chat completion."""
        ...


class _Chat(Protocol):
    completions: _ChatCompletions


class _OpenAiClient(Protocol):
    chat: _Chat

    def close(self) -> None:
        """Close the SDK client."""
        ...


class ClientFactory(Protocol):
    """Construct an OpenAI-compatible SDK client."""

    def __call__(
        self,
        *,
        api_key: str,
        base_url: str | None,
        timeout: float,
        max_retries: int,
    ) -> Any:
        """Return a configured synchronous SDK client."""
        ...


@dataclass(frozen=True, slots=True)
class OpenAiCompatibleProvider:
    """Provider-specific settings consumed by the shared transport."""

    engine_id: str
    default_base_url: str | None
    requires_api_key: bool
    api_key_env_var: str | None
    max_tokens_parameter: MaxTokensParameter
    unavailable_finish_reasons: frozenset[str] = frozenset()


class OpenAiCompatibleTransport:
    """Execute one provider-neutral request through Chat Completions."""

    __slots__ = ("_client", "_client_factory", "_closed", "_config", "_provider")

    def __init__(
        self,
        config: LlmConfig,
        provider: OpenAiCompatibleProvider,
        *,
        client_factory: ClientFactory | None = None,
    ) -> None:
        """Store configuration while deferring SDK and client creation."""
        if config.engine_id != provider.engine_id:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.LLM_CONFIG_INVALID,
                message=f"LLM config engine {config.engine_id!r} does not match {provider.engine_id!r}",
                suggestion="Create the provider selected in the LLM settings.",
                details={"engine_id": config.engine_id},
            )
            raise LlmConfigError(context=context)
        self._config: LlmConfig = config
        self._provider: OpenAiCompatibleProvider = provider
        self._client_factory: ClientFactory | None = client_factory
        self._client: _OpenAiClient | None = None
        self._closed: bool = False

    @property
    def engine_id(self) -> str:
        """Return the stable provider registry id."""
        return self._provider.engine_id

    @property
    def is_available(self) -> bool:
        """Return whether required connection settings are present."""
        if self._closed:
            return False
        if self._provider.requires_api_key:
            return bool(self._config.api_key.strip())
        return bool(self._resolved_base_url())

    def __enter__(self) -> Self:
        """Enter the provider lifecycle without creating its client."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the provider lifecycle."""
        del exc_type, exc, traceback
        self.close()

    def complete(self, request: LlmRequest) -> LlmResponse:
        """Run one synchronous completion and normalize its response."""
        if self._closed:
            _raise_request_error(
                "LLM provider is already closed",
                suggestion="Create a new provider instance before sending another request.",
            )
        client: _OpenAiClient = self._ensure_client()
        kwargs: dict[str, object] = self._build_completion_kwargs(request)
        started_at: float = time.perf_counter()
        try:
            response: Any = client.chat.completions.create(**kwargs)
        except self._sdk_api_error_type() as error:
            raise _map_sdk_error(error, engine_id=self.engine_id) from error
        latency_ms: float = (time.perf_counter() - started_at) * 1000
        return self._normalize_response(response, latency_ms=latency_ms)

    def close(self) -> None:
        """Close an existing SDK client exactly once."""
        if self._closed:
            return
        self._closed = True
        client: _OpenAiClient | None = self._client
        self._client = None
        if client is not None:
            client.close()

    def _ensure_client(self) -> _OpenAiClient:
        if self._client is not None:
            return self._client
        api_key: str = self._resolved_api_key()
        base_url: str | None = self._resolved_base_url()
        if base_url is None and not self._provider.requires_api_key:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.LLM_CONFIG_INVALID,
                message="OpenAI-compatible base URL is not configured",
                suggestion="Set the complete base URL for the custom OpenAI-compatible endpoint.",
                details={"engine_id": self.engine_id},
            )
            raise LlmConfigError(context=context)
        factory: ClientFactory = self._client_factory or _default_client_factory
        self._client = factory(
            api_key=api_key,
            base_url=base_url,
            timeout=self._config.timeout_s,
            max_retries=0,
        )
        return self._client

    def _resolved_api_key(self) -> str:
        api_key: str = self._config.api_key.strip()
        if api_key:
            return api_key
        if not self._provider.requires_api_key:
            return _LOCAL_API_KEY_PLACEHOLDER
        env_var: str = self._provider.api_key_env_var or "provider-specific API key"
        context: ErrorContext = ErrorContext(
            code=ErrorCode.LLM_AUTH_FAILED,
            message=f"{self.engine_id} API key is not configured",
            suggestion=f"Set {env_var} in the environment or .env file.",
            details={"engine_id": self.engine_id},
        )
        raise LlmAuthError(context=context)

    def _resolved_base_url(self) -> str | None:
        configured: str = (self._config.base_url or "").strip()
        return configured or self._provider.default_base_url

    def _build_completion_kwargs(self, request: LlmRequest) -> dict[str, object]:
        messages: list[dict[str, str]] = []
        for message in request.messages:
            content_parts: list[str] = []
            for part in message.parts:
                if not isinstance(part, TextPart):
                    _raise_request_error(
                        "OpenAI-compatible provider received an unsupported content part",
                        suggestion="Use text content parts for this provider.",
                    )
                content_parts.append(part.text)
            if not content_parts:
                _raise_request_error(
                    "OpenAI-compatible message must contain at least one text part",
                    suggestion="Add text content to every LLM message.",
                )
            messages.append({"role": message.role.value, "content": "\n".join(content_parts)})

        kwargs: dict[str, object] = {
            "messages": messages,
            "model": self._config.provider_model_id,
        }
        if self._config.temperature is not None:
            kwargs["temperature"] = self._config.temperature
        if self._config.top_p is not None:
            kwargs["top_p"] = self._config.top_p
        if self._config.max_output_tokens is not None:
            kwargs[self._provider.max_tokens_parameter] = self._config.max_output_tokens
        return kwargs

    def _normalize_response(self, response: Any, *, latency_ms: float) -> LlmResponse:
        choices: object = getattr(response, "choices", ())
        if not isinstance(choices, (list, tuple)) or not choices:
            _raise_request_error(
                "OpenAI-compatible provider returned no completion choice",
                suggestion="Retry with a supported model or inspect the provider status.",
            )
        choice: Any = choices[0]
        finish_reason: str = _normalize_finish_reason(getattr(choice, "finish_reason", None))
        if finish_reason in self._provider.unavailable_finish_reasons:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.LLM_PROVIDER_UNAVAILABLE,
                message=f"{self.engine_id} could not allocate resources for the completion",
                suggestion="Retry later or choose another model.",
                details={"engine_id": self.engine_id, "finish_reason": finish_reason},
            )
            raise LlmProviderUnavailableError(context=context)

        message: object = getattr(choice, "message", None)
        text: object = getattr(message, "content", None)
        refusal: object = getattr(message, "refusal", None)
        if finish_reason in {"blocked", "content_filter", "refusal", "safety"} or (
            isinstance(refusal, str) and refusal.strip()
        ):
            context = ErrorContext(
                code=ErrorCode.LLM_OUTPUT_BLOCKED,
                message=f"{self.engine_id} blocked the completion",
                suggestion="Review the subtitle content or choose another provider.",
                details={"engine_id": self.engine_id, "finish_reason": finish_reason},
            )
            raise LlmOutputBlockedError(context=context)
        if not isinstance(text, str) or not text.strip():
            _raise_request_error(
                f"{self.engine_id} returned an empty text completion",
                suggestion=f"Check finish reason {finish_reason!r} and the selected model.",
            )
        provider_model: object = getattr(response, "model", None)
        provider_model_id: str = self._config.provider_model_id
        if isinstance(provider_model, str) and provider_model.strip():
            provider_model_id = provider_model.strip()
        return LlmResponse(
            text=text,
            engine_id=self.engine_id,
            provider_model_id=provider_model_id,
            finish_reason=finish_reason,
            latency_ms=max(0.0, latency_ms),
            usage=_normalize_usage(getattr(response, "usage", None)),
        )

    @staticmethod
    def _sdk_api_error_type() -> type[BaseException]:
        sdk: ModuleType = _load_openai_sdk()
        return cast("type[BaseException]", sdk.APIError)


def _default_client_factory(
    *,
    api_key: str,
    base_url: str | None,
    timeout: float,
    max_retries: int,
) -> _OpenAiClient:
    sdk: ModuleType = _load_openai_sdk()
    client_type: ClientFactory = cast("ClientFactory", sdk.OpenAI)
    return cast(
        "_OpenAiClient",
        client_type(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        ),
    )


def _load_openai_sdk() -> ModuleType:
    try:
        return importlib.import_module("openai")
    except ImportError as error:
        if error.name != "openai":
            raise
        context: ErrorContext = ErrorContext(
            code=ErrorCode.LLM_PROVIDER_UNAVAILABLE,
            message="OpenAI SDK is not installed",
            suggestion="Install the AniShift LLM dependencies and retry.",
        )
        raise LlmProviderUnavailableError(context=context) from error


def _map_sdk_error(error: BaseException, *, engine_id: str) -> Exception:
    sdk: ModuleType = _load_openai_sdk()
    status_code: int | None = _status_code(error)
    structured_codes: frozenset[str] = _structured_codes(getattr(error, "body", None))
    retry_after_s: float | None = _retry_after_seconds(error)

    mapped_error: Exception
    if isinstance(error, sdk.APITimeoutError) or status_code == HTTPStatus.REQUEST_TIMEOUT:
        mapped_error = _error_with_context(
            LlmTimeoutError,
            engine_id=engine_id,
            message=f"{engine_id} request timed out",
            suggestion="Retry after checking the network connection.",
        )
    elif isinstance(error, sdk.AuthenticationError) or status_code in {
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN,
    }:
        mapped_error = _error_with_context(
            LlmAuthError,
            engine_id=engine_id,
            message=f"{engine_id} rejected the configured credentials",
            suggestion=f"Check the {engine_id} API key and account permissions.",
        )
    elif status_code == HTTPStatus.PAYMENT_REQUIRED or structured_codes & _PAYMENT_CODES:
        mapped_error = _error_with_context(
            LlmPaymentError,
            engine_id=engine_id,
            message=f"{engine_id} requires payment or sufficient account credit",
            suggestion="Check provider billing and available account credit.",
        )
    elif status_code == HTTPStatus.TOO_MANY_REQUESTS and structured_codes & _QUOTA_CODES:
        mapped_error = _error_with_context(
            LlmQuotaError,
            engine_id=engine_id,
            message=f"{engine_id} quota is exhausted",
            suggestion="Wait for the quota reset or select another provider.",
        )
    elif isinstance(error, sdk.RateLimitError) or status_code == HTTPStatus.TOO_MANY_REQUESTS:
        mapped_error = _transient_error_with_context(
            LlmRateLimitError,
            engine_id=engine_id,
            message=f"{engine_id} rate limit was reached",
            suggestion="Wait for the provider retry window.",
            retry_after_s=retry_after_s,
        )
    elif status_code == HTTPStatus.NOT_FOUND and structured_codes & _MODEL_CODES:
        mapped_error = _error_with_context(
            LlmModelError,
            engine_id=engine_id,
            message=f"{engine_id} could not find the selected model",
            suggestion="Check the provider model ID in settings.",
        )
    elif status_code == HTTPStatus.NOT_FOUND:
        mapped_error = _error_with_context(
            LlmRequestError,
            engine_id=engine_id,
            message=f"{engine_id} endpoint was not found",
            suggestion="Check the configured base URL and its API version path.",
        )
    elif status_code == HTTPStatus.BAD_REQUEST and structured_codes & _CONTEXT_CODES:
        mapped_error = _error_with_context(
            LlmContextLengthError,
            engine_id=engine_id,
            message=f"{engine_id} context window was exceeded",
            suggestion="Split the completion into smaller batches.",
        )
    elif isinstance(error, sdk.APIConnectionError):
        mapped_error = _transient_error_with_context(
            LlmProviderUnavailableError,
            engine_id=engine_id,
            message=f"{engine_id} could not be reached",
            suggestion="Check the network connection and provider status.",
            retry_after_s=retry_after_s,
        )
    elif status_code is not None and status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        mapped_error = _transient_error_with_context(
            LlmProviderUnavailableError,
            engine_id=engine_id,
            message=f"{engine_id} is temporarily unavailable",
            suggestion="Retry after checking the provider status.",
            retry_after_s=retry_after_s,
        )
    else:
        mapped_error = _error_with_context(
            LlmRequestError,
            engine_id=engine_id,
            message=f"{engine_id} rejected the completion request",
            suggestion="Check the provider model, endpoint, and generation settings.",
        )
    return mapped_error


def _normalize_usage(usage: object) -> LlmUsage:
    if usage is None:
        return LlmUsage()
    input_tokens: int | None = _optional_int(getattr(usage, "prompt_tokens", None))
    output_tokens: int | None = _optional_int(getattr(usage, "completion_tokens", None))
    total_tokens: int | None = _optional_int(getattr(usage, "total_tokens", None))
    reported_cost: float | None = _optional_float(getattr(usage, "cost", None))
    return LlmUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        reported_cost=reported_cost,
    )


def _structured_codes(body: object) -> frozenset[str]:
    codes: set[str] = set()
    if isinstance(body, Mapping):
        for key, value in body.items():
            if key in {"code", "status", "type"} and isinstance(value, str) and value.strip():
                codes.add(value.strip().lower())
            elif isinstance(value, (Mapping, list, tuple)):
                codes.update(_structured_codes(value))
    elif isinstance(body, (list, tuple)):
        for value in body:
            codes.update(_structured_codes(value))
    return frozenset(codes)


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
