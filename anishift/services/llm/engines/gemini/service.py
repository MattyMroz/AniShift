"""Native synchronous Google Gemini provider."""

from __future__ import annotations

import importlib
import time
from http import HTTPStatus
from types import ModuleType
from typing import Any, Final, Never, Protocol, cast

import httpx

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.llm.config import LlmConfig
from anishift.services.llm.engines._sdk_helpers import (
    error_with_context,
    raise_request_error,
    status_code,
    transient_error_with_context,
)
from anishift.services.llm.engines._sdk_helpers import (
    normalize_finish_reason as _normalize_finish_reason,
)
from anishift.services.llm.engines._sdk_helpers import (
    optional_int as _optional_int,
)
from anishift.services.llm.engines._sdk_helpers import (
    retry_after_seconds as _retry_after_seconds,
)
from anishift.services.llm.engines._sdk_helpers import (
    structured_markers as _structured_markers,
)
from anishift.services.llm.errors import (
    LlmAuthError,
    LlmConfigError,
    LlmContextLengthError,
    LlmError,
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

__all__ = ["ClientFactory", "GeminiService"]

_PAYMENT_FRAGMENTS: Final[tuple[str, ...]] = ("billing", "credit", "payment")
"""Structured Gemini marker fragments representing payment failures."""

_QUOTA_FRAGMENTS: Final[tuple[str, ...]] = ("daily", "per_day", "perday")
"""Structured Gemini marker fragments representing exhausted quota."""

_TIMEOUT_FRAGMENTS: Final[tuple[str, ...]] = ("deadline",)
"""Structured Gemini marker fragments representing request timeouts."""

_CONTEXT_LENGTH_FRAGMENTS: Final[tuple[str, ...]] = (
    "context_length",
    "context window",
    "input token",
    "maximum context",
    "request too large",
    "too many tokens",
)
"""Structured Gemini marker fragments representing an oversized input."""

_BLOCKED_REASONS: Final[frozenset[str]] = frozenset(
    (
        "blocklist",
        "blocked",
        "image_safety",
        "prohibited_content",
        "recitation",
        "safety",
        "spii",
    )
)
"""Normalized Gemini finish and prompt-feedback safety reasons."""

_PROMPT_BLOCK_REASONS: Final[frozenset[str]] = _BLOCKED_REASONS | frozenset(("jailbreak", "model_armor", "other"))
"""Additional installed-SDK reasons that only occur in prompt feedback."""


class _Models(Protocol):
    def generate_content(self, **kwargs: Any) -> Any:
        """Generate one Gemini response."""
        ...


class _GeminiClient(Protocol):
    @property
    def models(self) -> _Models:
        """Expose the synchronous Models resource."""
        ...

    def close(self) -> None:
        """Close the SDK client."""
        ...


class ClientFactory(Protocol):
    """Construct a synchronous Google Gen AI client."""

    def __call__(
        self,
        *,
        api_key: str,
        http_options: object,
    ) -> _GeminiClient:
        """Return a configured Gemini client."""
        ...


class GeminiService:
    """Execute provider-neutral completions through Google Gemini."""

    __slots__ = ("_client", "_client_factory", "_closed", "_config")

    def __init__(
        self,
        config: LlmConfig,
        *,
        _client_factory: ClientFactory | None = None,
    ) -> None:
        """Store configuration while deferring SDK and client creation."""
        if config.engine_id != "gemini":
            context: ErrorContext = ErrorContext(
                code=ErrorCode.LLM_CONFIG_INVALID,
                message=f"LLM config engine {config.engine_id!r} does not match 'gemini'",
                suggestion="Create the provider selected in the LLM settings.",
                details={"engine_id": config.engine_id},
            )
            raise LlmConfigError(context=context)
        self._config: LlmConfig = config
        self._client_factory: ClientFactory | None = _client_factory
        self._client: _GeminiClient | None = None
        self._closed: bool = False

    @property
    def engine_id(self) -> str:
        """Return the stable provider registry id."""
        return "gemini"

    @property
    def is_available(self) -> bool:
        """Return whether a Gemini API key is configured."""
        return not self._closed and bool(self._config.api_key.strip())

    def complete(self, request: LlmRequest) -> LlmResponse:
        """Run one synchronous Gemini completion."""
        if self._closed:
            _raise_request_error(
                "Gemini provider is already closed",
                suggestion="Create a new provider instance before sending another request.",
            )
        client: _GeminiClient = self._ensure_client()
        contents, generate_config = self._build_request(request)
        started_at: float = time.perf_counter()
        try:
            response: Any = client.models.generate_content(
                model=self._config.provider_model_id,
                contents=contents,
                config=generate_config,
            )
        except (self._sdk_api_error_type(), httpx.TimeoutException, httpx.NetworkError) as error:
            raise _map_sdk_error(error) from error
        latency_ms: float = (time.perf_counter() - started_at) * 1000
        return self._normalize_response(response, latency_ms=latency_ms)

    def close(self) -> None:
        """Close an existing Gemini client exactly once."""
        if self._closed:
            return
        self._closed = True
        client: _GeminiClient | None = self._client
        self._client = None
        if client is not None:
            client.close()

    def _ensure_client(self) -> _GeminiClient:
        if self._client is not None:
            return self._client
        api_key: str = self._config.api_key.strip()
        if not api_key:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.LLM_AUTH_FAILED,
                message="Gemini API key is not configured",
                suggestion="Set ANISHIFT_GEMINI_API_KEY in the environment or .env file.",
                details={"engine_id": self.engine_id},
            )
            raise LlmAuthError(context=context)
        types_module: ModuleType = _load_google_types()
        retry_options: object = types_module.HttpRetryOptions(attempts=1)
        http_options: object = types_module.HttpOptions(
            timeout=int(self._config.timeout_s * 1000),
            retry_options=retry_options,
        )
        factory: ClientFactory = self._client_factory or _default_client_factory
        self._client = factory(api_key=api_key, http_options=http_options)
        return self._client

    def _build_request(self, request: LlmRequest) -> tuple[list[object], object]:
        types_module: ModuleType = _load_google_types()
        system_parts: list[object] = []
        contents: list[object] = []
        for message in request.messages:
            parts: list[object] = _google_text_parts(message.parts, types_module=types_module)
            if message.role.value == "system":
                system_parts.extend(parts)
                continue
            role: str = "model" if message.role.value == "assistant" else "user"
            contents.append(types_module.Content(role=role, parts=parts))

        config_kwargs: dict[str, object] = {}
        if system_parts:
            config_kwargs["system_instruction"] = system_parts
        if self._config.temperature is not None:
            config_kwargs["temperature"] = self._config.temperature
        if self._config.top_p is not None:
            config_kwargs["top_p"] = self._config.top_p
        if self._config.max_output_tokens is not None:
            config_kwargs["max_output_tokens"] = self._config.max_output_tokens
        generate_config: object = types_module.GenerateContentConfig(**config_kwargs)
        return contents, generate_config

    def _normalize_response(self, response: Any, *, latency_ms: float) -> LlmResponse:
        candidates_value: object = getattr(response, "candidates", ())
        candidates: list[Any] | tuple[Any, ...] = (
            candidates_value if isinstance(candidates_value, (list, tuple)) else ()
        )
        candidate: Any | None = candidates[0] if candidates else None
        finish_reason: str = _normalize_finish_reason(getattr(candidate, "finish_reason", None))
        prompt_feedback: object = getattr(response, "prompt_feedback", None)
        block_reason: str = _normalize_finish_reason(getattr(prompt_feedback, "block_reason", None))
        text: str = _candidate_text(candidate)
        if finish_reason in _BLOCKED_REASONS or block_reason in _PROMPT_BLOCK_REASONS:
            context = ErrorContext(
                code=ErrorCode.LLM_OUTPUT_BLOCKED,
                message="Gemini blocked the completion",
                suggestion="Review the subtitle content or choose another provider.",
                details={
                    "engine_id": self.engine_id,
                    "finish_reason": finish_reason,
                    "block_reason": block_reason,
                },
            )
            raise LlmOutputBlockedError(context=context)
        if not text.strip():
            _raise_request_error(
                "Gemini returned an empty text completion",
                suggestion=f"Check finish reason {finish_reason!r} and the selected model.",
            )
        model: object = getattr(response, "model_version", None)
        provider_model_id: str = (
            model.strip() if isinstance(model, str) and model.strip() else self._config.provider_model_id
        )
        return LlmResponse(
            text=text,
            engine_id=self.engine_id,
            provider_model_id=provider_model_id,
            finish_reason=finish_reason,
            latency_ms=max(0.0, latency_ms),
            usage=_normalize_usage(getattr(response, "usage_metadata", None)),
        )

    @staticmethod
    def _sdk_api_error_type() -> type[BaseException]:
        errors_module: ModuleType = _load_google_errors()
        return cast("type[BaseException]", errors_module.APIError)


def _google_text_parts(parts: tuple[TextPart, ...], *, types_module: ModuleType) -> list[object]:
    if not parts:
        _raise_request_error(
            "Gemini messages must contain at least one text part",
            suggestion="Add text content to every LLM message.",
        )
    mapped_parts: list[object] = []
    for part in parts:
        if not isinstance(part, TextPart):
            _raise_request_error(
                "Gemini received an unsupported content part",
                suggestion="Use text content parts for this provider.",
            )
        mapped_parts.append(types_module.Part(text=part.text))
    return mapped_parts


def _candidate_text(candidate: object) -> str:
    content: object = getattr(candidate, "content", None)
    parts_value: object = getattr(content, "parts", ())
    parts: list[Any] | tuple[Any, ...] = parts_value if isinstance(parts_value, (list, tuple)) else ()
    text_parts: list[str] = []
    for part in parts:
        text: object = getattr(part, "text", None)
        if isinstance(text, str) and text:
            text_parts.append(text)
    return "".join(text_parts)


def _default_client_factory(
    *,
    api_key: str,
    http_options: object,
) -> _GeminiClient:
    sdk: ModuleType = _load_google_sdk()
    client_type: ClientFactory = cast("ClientFactory", sdk.Client)
    return client_type(api_key=api_key, http_options=http_options)


def _load_google_sdk() -> ModuleType:
    return _load_google_module("google.genai")


def _load_google_types() -> ModuleType:
    return _load_google_module("google.genai.types")


def _load_google_errors() -> ModuleType:
    return _load_google_module("google.genai.errors")


def _load_google_module(module_name: str) -> ModuleType:
    try:
        return importlib.import_module(module_name)
    except ImportError as error:
        if error.name not in {"google", "google.genai", module_name}:
            raise
        context: ErrorContext = ErrorContext(
            code=ErrorCode.LLM_PROVIDER_UNAVAILABLE,
            message="Google Gen AI SDK is not installed",
            suggestion="Install the AniShift LLM dependencies and retry.",
            details={"engine_id": "gemini"},
        )
        raise LlmProviderUnavailableError(context=context) from error


def _map_sdk_error(error: BaseException) -> Exception:
    errors_module: ModuleType = _load_google_errors()
    status_code: int | None = _status_code(error)
    markers: frozenset[str] = _structured_markers(
        (
            getattr(error, "details", None),
            getattr(error, "message", None),
            getattr(error, "status", None),
        )
    )
    retry_after_s: float | None = _retry_after_seconds(error)

    mapped_error: Exception
    if (
        isinstance(error, httpx.TimeoutException)
        or status_code == HTTPStatus.REQUEST_TIMEOUT
        or _has_fragment(markers, _TIMEOUT_FRAGMENTS)
    ):
        mapped_error = _error_with_context(
            LlmTimeoutError,
            message="Gemini request timed out",
            suggestion="Retry after checking the network connection.",
        )
    elif status_code == HTTPStatus.BAD_REQUEST and _has_fragment(markers, _CONTEXT_LENGTH_FRAGMENTS):
        mapped_error = _error_with_context(
            LlmContextLengthError,
            message="Gemini context window was exceeded",
            suggestion="Split the completion into smaller batches.",
        )
    elif isinstance(error, httpx.NetworkError):
        mapped_error = _transient_error_with_context(
            LlmProviderUnavailableError,
            message="Gemini could not be reached",
            suggestion="Check the network connection and Gemini status.",
            retry_after_s=retry_after_s,
        )
    elif status_code in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
        mapped_error = _error_with_context(
            LlmAuthError,
            message="Gemini rejected the configured credentials",
            suggestion="Check the Gemini API key and account permissions.",
        )
    elif status_code == HTTPStatus.TOO_MANY_REQUESTS and _has_fragment(markers, _QUOTA_FRAGMENTS):
        mapped_error = _error_with_context(
            LlmQuotaError,
            message="Gemini quota is exhausted",
            suggestion="Wait for the quota reset or select another provider.",
        )
    elif status_code == HTTPStatus.TOO_MANY_REQUESTS:
        # Gemini 429 bodies mention "billing" ("check your plan and billing
        # details"), so rate limits must be classified before the payment
        # fragments or a per-minute limit becomes a fatal payment error.
        mapped_error = _transient_error_with_context(
            LlmRateLimitError,
            message="Gemini rate limit was reached",
            suggestion="Wait for the Gemini retry window.",
            retry_after_s=retry_after_s,
        )
    elif _has_fragment(markers, _PAYMENT_FRAGMENTS) or status_code == HTTPStatus.PAYMENT_REQUIRED:
        mapped_error = _error_with_context(
            LlmPaymentError,
            message="Gemini requires payment or sufficient account credit",
            suggestion="Check Gemini billing and available account credit.",
        )
    elif status_code == HTTPStatus.NOT_FOUND:
        mapped_error = _error_with_context(
            LlmModelError,
            message="Gemini could not find the selected model",
            suggestion="Check the Gemini model ID in settings.",
        )
    elif isinstance(error, errors_module.ServerError) or (
        status_code is not None and status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
    ):
        mapped_error = _transient_error_with_context(
            LlmProviderUnavailableError,
            message="Gemini is temporarily unavailable",
            suggestion="Retry after checking Gemini status.",
            retry_after_s=retry_after_s,
        )
    else:
        mapped_error = _error_with_context(
            LlmRequestError,
            message="Gemini rejected the completion request",
            suggestion="Check the Gemini model and generation settings.",
        )
    return mapped_error


def _normalize_usage(usage: object) -> LlmUsage:
    if usage is None:
        return LlmUsage()
    return LlmUsage(
        input_tokens=_optional_int(getattr(usage, "prompt_token_count", None)),
        output_tokens=_optional_int(getattr(usage, "candidates_token_count", None)),
        total_tokens=_optional_int(getattr(usage, "total_token_count", None)),
    )


def _has_fragment(markers: frozenset[str], fragments: tuple[str, ...]) -> bool:
    return any(fragment in marker for marker in markers for fragment in fragments)


def _status_code(error: BaseException) -> int | None:
    return status_code(error, attributes=("code", "status_code"))


def _error_with_context(
    error_type: type[LlmError],
    *,
    message: str,
    suggestion: str,
) -> Exception:
    return error_with_context(error_type, engine_id="gemini", message=message, suggestion=suggestion)


def _transient_error_with_context(
    error_type: type[LlmRateLimitError] | type[LlmProviderUnavailableError],
    *,
    message: str,
    suggestion: str,
    retry_after_s: float | None,
) -> Exception:
    return transient_error_with_context(
        error_type,
        engine_id="gemini",
        message=message,
        suggestion=suggestion,
        retry_after_s=retry_after_s,
    )


def _raise_request_error(message: str, *, suggestion: str) -> Never:
    raise_request_error(message, suggestion=suggestion, engine_id="gemini")
