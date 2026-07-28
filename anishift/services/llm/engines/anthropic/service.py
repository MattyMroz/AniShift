"""Native synchronous Anthropic Messages provider."""

from __future__ import annotations

import importlib
import time
from collections.abc import Mapping
from http import HTTPStatus
from types import ModuleType
from typing import Any, Final, Never, Protocol, cast

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines.anthropic.constants import DEFAULT_MAX_OUTPUT_TOKENS
from anishift.services.llm.errors import (
    LlmAuthError,
    LlmConfigError,
    LlmContextLengthError,
    LlmError,
    LlmModelError,
    LlmOutputBlockedError,
    LlmPaymentError,
    LlmProviderUnavailableError,
    LlmRateLimitError,
    LlmRequestError,
    LlmTimeoutError,
)
from anishift.services.llm.types import LlmRequest, LlmResponse, LlmUsage, TextPart

__all__ = ["AnthropicService", "ClientFactory"]

_PAYMENT_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "billing_error",
        "billing_hard_limit_reached",
        "insufficient_credits",
        "payment_required",
    }
)
"""Structured Anthropic markers representing payment failures."""


class _Messages(Protocol):
    def create(self, **kwargs: Any) -> Any:
        """Create one Anthropic message."""
        ...


class _AnthropicClient(Protocol):
    @property
    def messages(self) -> _Messages:
        """Expose the synchronous Messages resource."""
        ...

    def close(self) -> None:
        """Close the SDK client."""
        ...


class ClientFactory(Protocol):
    """Construct a synchronous Anthropic SDK client."""

    def __call__(
        self,
        *,
        api_key: str,
        timeout: float,
        max_retries: int,
    ) -> _AnthropicClient:
        """Return a configured Anthropic client."""
        ...


class AnthropicService:
    """Execute provider-neutral completions through Anthropic Messages."""

    __slots__ = ("_client", "_client_factory", "_closed", "_config")

    def __init__(
        self,
        config: LlmConfig,
        *,
        _client_factory: ClientFactory | None = None,
    ) -> None:
        """Store configuration while deferring SDK and client creation."""
        if config.engine_id != "anthropic":
            context: ErrorContext = ErrorContext(
                code=ErrorCode.LLM_CONFIG_INVALID,
                message=f"LLM config engine {config.engine_id!r} does not match 'anthropic'",
                suggestion="Create the provider selected in the LLM settings.",
                details={"engine_id": config.engine_id},
            )
            raise LlmConfigError(context=context)
        self._config: LlmConfig = config
        self._client_factory: ClientFactory | None = _client_factory
        self._client: _AnthropicClient | None = None
        self._closed: bool = False

    @property
    def engine_id(self) -> str:
        """Return the stable provider registry id."""
        return "anthropic"

    @property
    def is_available(self) -> bool:
        """Return whether an Anthropic API key is configured."""
        return not self._closed and bool(self._config.api_key.strip())

    def complete(self, request: LlmRequest) -> LlmResponse:
        """Run one synchronous Anthropic completion."""
        if self._closed:
            _raise_request_error(
                "Anthropic provider is already closed",
                suggestion="Create a new provider instance before sending another request.",
            )
        client: _AnthropicClient = self._ensure_client()
        kwargs: dict[str, object] = self._build_completion_kwargs(request)
        started_at: float = time.perf_counter()
        try:
            response: Any = client.messages.create(**kwargs)
        except self._sdk_api_error_type() as error:
            raise _map_sdk_error(error) from error
        latency_ms: float = (time.perf_counter() - started_at) * 1000
        return self._normalize_response(response, latency_ms=latency_ms)

    def close(self) -> None:
        """Close an existing Anthropic client exactly once."""
        if self._closed:
            return
        self._closed = True
        client: _AnthropicClient | None = self._client
        self._client = None
        if client is not None:
            client.close()

    def _ensure_client(self) -> _AnthropicClient:
        if self._client is not None:
            return self._client
        api_key: str = self._config.api_key.strip()
        if not api_key:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.LLM_AUTH_FAILED,
                message="Anthropic API key is not configured",
                suggestion="Set ANISHIFT_ANTHROPIC_API_KEY in the environment or .env file.",
                details={"engine_id": self.engine_id},
            )
            raise LlmAuthError(context=context)
        factory: ClientFactory = self._client_factory or _default_client_factory
        self._client = factory(
            api_key=api_key,
            timeout=self._config.timeout_s,
            max_retries=0,
        )
        return self._client

    def _build_completion_kwargs(self, request: LlmRequest) -> dict[str, object]:
        system_parts: list[dict[str, str]] = []
        messages: list[dict[str, object]] = []
        for message in request.messages:
            content: list[dict[str, str]] = _text_blocks(message.parts)
            if message.role.value == "system":
                system_parts.extend(content)
                continue
            messages.append({"role": message.role.value, "content": content})
        kwargs: dict[str, object] = {
            "max_tokens": self._config.max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS,
            "messages": messages,
            "model": self._config.provider_model_id,
        }
        if system_parts:
            kwargs["system"] = system_parts
        if self._config.temperature is not None:
            kwargs["temperature"] = self._config.temperature
        if self._config.top_p is not None:
            kwargs["top_p"] = self._config.top_p
        return kwargs

    def _normalize_response(self, response: Any, *, latency_ms: float) -> LlmResponse:
        content: object = getattr(response, "content", ())
        blocks: list[Any] | tuple[Any, ...] = content if isinstance(content, (list, tuple)) else ()
        text_parts: list[str] = []
        for block in blocks:
            if getattr(block, "type", None) != "text":
                continue
            text: object = getattr(block, "text", None)
            if isinstance(text, str) and text:
                text_parts.append(text)
        text = "".join(text_parts)
        finish_reason: str = _normalize_finish_reason(getattr(response, "stop_reason", None))
        if finish_reason == "refusal":
            context = ErrorContext(
                code=ErrorCode.LLM_OUTPUT_BLOCKED,
                message="Anthropic blocked the completion",
                suggestion="Review the subtitle content or choose another provider.",
                details={"engine_id": self.engine_id, "finish_reason": finish_reason},
            )
            raise LlmOutputBlockedError(context=context)
        if not text.strip():
            _raise_request_error(
                "Anthropic returned an empty text completion",
                suggestion=f"Check finish reason {finish_reason!r} and the selected model.",
            )
        model: object = getattr(response, "model", None)
        provider_model_id: str = (
            model.strip() if isinstance(model, str) and model.strip() else self._config.provider_model_id
        )
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
        sdk: ModuleType = _load_anthropic_sdk()
        return cast("type[BaseException]", sdk.APIError)


def _text_blocks(parts: tuple[TextPart, ...]) -> list[dict[str, str]]:
    if not parts:
        _raise_request_error(
            "Anthropic messages must contain at least one text part",
            suggestion="Add text content to every LLM message.",
        )
    blocks: list[dict[str, str]] = []
    for part in parts:
        if not isinstance(part, TextPart):
            _raise_request_error(
                "Anthropic received an unsupported content part",
                suggestion="Use text content parts for this provider.",
            )
        blocks.append({"type": "text", "text": part.text})
    return blocks


def _default_client_factory(
    *,
    api_key: str,
    timeout: float,
    max_retries: int,
) -> _AnthropicClient:
    sdk: ModuleType = _load_anthropic_sdk()
    client_type: ClientFactory = cast("ClientFactory", sdk.Anthropic)
    return client_type(
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
    )


def _load_anthropic_sdk() -> ModuleType:
    try:
        return importlib.import_module("anthropic")
    except ImportError as error:
        if error.name != "anthropic":
            raise
        context: ErrorContext = ErrorContext(
            code=ErrorCode.LLM_PROVIDER_UNAVAILABLE,
            message="Anthropic SDK is not installed",
            suggestion="Install the AniShift LLM dependencies and retry.",
            details={"engine_id": "anthropic"},
        )
        raise LlmProviderUnavailableError(context=context) from error


def _map_sdk_error(error: BaseException) -> Exception:
    sdk: ModuleType = _load_anthropic_sdk()
    status_code: int | None = _status_code(error)
    markers: frozenset[str] = _structured_markers(getattr(error, "body", None))
    retry_after_s: float | None = _retry_after_seconds(error)

    mapped_error: Exception
    if isinstance(error, sdk.APITimeoutError) or status_code == HTTPStatus.REQUEST_TIMEOUT:
        mapped_error = _error_with_context(
            LlmTimeoutError,
            message="Anthropic request timed out",
            suggestion="Retry after checking the network connection.",
        )
    elif isinstance(error, (sdk.AuthenticationError, sdk.PermissionDeniedError)) or status_code in {
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN,
    }:
        mapped_error = _error_with_context(
            LlmAuthError,
            message="Anthropic rejected the configured credentials",
            suggestion="Check the Anthropic API key and account permissions.",
        )
    elif markers & _PAYMENT_MARKERS or status_code == HTTPStatus.PAYMENT_REQUIRED:
        mapped_error = _error_with_context(
            LlmPaymentError,
            message="Anthropic requires payment or sufficient account credit",
            suggestion="Check Anthropic billing and available account credit.",
        )
    elif isinstance(error, sdk.RateLimitError) or status_code == HTTPStatus.TOO_MANY_REQUESTS:
        mapped_error = _transient_error_with_context(
            LlmRateLimitError,
            message="Anthropic rate limit was reached",
            suggestion="Wait for the Anthropic retry window.",
            retry_after_s=retry_after_s,
        )
    elif isinstance(error, sdk.RequestTooLargeError) or status_code == HTTPStatus.CONTENT_TOO_LARGE:
        mapped_error = _error_with_context(
            LlmContextLengthError,
            message="Anthropic context window was exceeded",
            suggestion="Split the completion into smaller batches.",
        )
    elif isinstance(error, sdk.NotFoundError) or status_code == HTTPStatus.NOT_FOUND:
        mapped_error = _error_with_context(
            LlmModelError,
            message="Anthropic could not find the selected model",
            suggestion="Check the Anthropic model ID in settings.",
        )
    elif isinstance(error, sdk.APIConnectionError):
        mapped_error = _transient_error_with_context(
            LlmProviderUnavailableError,
            message="Anthropic could not be reached",
            suggestion="Check the network connection and Anthropic status.",
            retry_after_s=retry_after_s,
        )
    elif isinstance(error, (sdk.InternalServerError, sdk.OverloadedError)) or (
        status_code is not None and status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
    ):
        mapped_error = _transient_error_with_context(
            LlmProviderUnavailableError,
            message="Anthropic is temporarily unavailable",
            suggestion="Retry after checking Anthropic status.",
            retry_after_s=retry_after_s,
        )
    else:
        mapped_error = _error_with_context(
            LlmRequestError,
            message="Anthropic rejected the completion request",
            suggestion="Check the Anthropic model and generation settings.",
        )
    return mapped_error


def _normalize_usage(usage: object) -> LlmUsage:
    if usage is None:
        return LlmUsage()
    return LlmUsage(
        input_tokens=_optional_int(getattr(usage, "input_tokens", None)),
        output_tokens=_optional_int(getattr(usage, "output_tokens", None)),
    )


def _normalize_finish_reason(value: object) -> str:
    enum_value: object = getattr(value, "value", value)
    if not isinstance(enum_value, str) or not enum_value.strip():
        return "unknown"
    return enum_value.strip().lower()


def _structured_markers(value: object) -> frozenset[str]:
    markers: set[str] = set()
    if isinstance(value, Mapping):
        for nested in value.values():
            markers.update(_structured_markers(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            markers.update(_structured_markers(nested))
    elif isinstance(value, str) and value.strip():
        markers.add(value.strip().lower())
    return frozenset(markers)


def _status_code(error: BaseException) -> int | None:
    status: object = getattr(error, "status_code", None)
    return status if isinstance(status, int) and not isinstance(status, bool) else None


def _retry_after_seconds(error: BaseException) -> float | None:
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


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _error_with_context(
    error_type: type[LlmError],
    *,
    message: str,
    suggestion: str,
) -> Exception:
    context: ErrorContext = ErrorContext(
        code=error_type.error_code,
        message=message,
        suggestion=suggestion,
        details={"engine_id": "anthropic"},
    )
    return error_type(context=context)


def _transient_error_with_context(
    error_type: type[LlmRateLimitError] | type[LlmProviderUnavailableError],
    *,
    message: str,
    suggestion: str,
    retry_after_s: float | None,
) -> Exception:
    context: ErrorContext = ErrorContext(
        code=error_type.error_code,
        message=message,
        suggestion=suggestion,
        details={"engine_id": "anthropic"},
    )
    return error_type(context=context, retry_after_s=retry_after_s)


def _raise_request_error(message: str, *, suggestion: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.LLM_REQUEST_FAILED,
        message=message,
        suggestion=suggestion,
        details={"engine_id": "anthropic"},
    )
    raise LlmRequestError(context=context)
