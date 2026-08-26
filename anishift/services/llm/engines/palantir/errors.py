"""Mapping of Palantir proxy failures onto the existing typed LLM taxonomy.

This module defines no error class of its own. The LLM domain already carries
the full vocabulary in ``anishift.services.llm.errors`` — auth, model, context,
blocked output, quota, payment, request, rate limit, timeout and provider
unavailable — so every Palantir condition is translated into one of those
classes and keeps its retry semantics (``TransientError`` versus
``FatalError``).

Redaction is the second responsibility. A response body, a request payload, an
``Authorization`` header and a signed URL never reach a message, a suggestion
or ``details``: a malformed response is reported through the safe
``PalantirResponseDefect`` label, and a provider payload is only ever matched
against small allowlists of structured markers used for classification.

The split between the two fail-fast raisers is deliberate and follows the four
existing engines: anything about the token — absent, blank, or a value that
cannot be sent in a header — is an authentication failure, while a defective
URL, protocol, alias, provider ID or model ID is a configuration failure. Both
are fatal and both fire before any network access.

Public API:
    PALANTIR_ENGINE_ID: Registry ID shared by the Palantir modules.
    PalantirResponseDefect: Safe labels describing a malformed response.
    raise_palantir_auth_error: Raise a typed token failure.
    raise_palantir_config_error: Raise a typed configuration failure.
    palantir_status_error: Classify one HTTP status into the LLM taxonomy.
    palantir_timeout_error, palantir_unavailable_error: Transport failures.
    palantir_response_error, palantir_blocked_error: Response-level failures.
"""

from __future__ import annotations

from enum import StrEnum
from http import HTTPStatus
from typing import Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.llm.engines._sdk_helpers import normalize_finish_reason, structured_markers
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
from anishift.utils.logger import get_logger

__all__ = [
    "PALANTIR_ENGINE_ID",
    "PalantirResponseDefect",
    "palantir_blocked_error",
    "palantir_response_error",
    "palantir_status_error",
    "palantir_timeout_error",
    "palantir_unavailable_error",
    "raise_palantir_auth_error",
    "raise_palantir_config_error",
]

logger = get_logger(__name__)


class PalantirResponseDefect(StrEnum):
    """Safe label naming why a response was unusable, instead of its content."""

    UNREADABLE_BODY = "unreadable_body"
    UNEXPECTED_SHAPE = "unexpected_shape"
    MISSING_CHOICE = "missing_choice"
    EMPTY_TEXT = "empty_text"


# ── Constants ────────────────────────────────────────────────────────────────

PALANTIR_ENGINE_ID: Final[str] = "palantir"
"""Registry ID of the single Palantir engine every module of this package tags."""

_AUTH_STATUSES: Final[frozenset[int]] = frozenset({HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN})
"""Statuses that mean the enrollment rejected the configured token."""

_QUOTA_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "daily_limit_exceeded",
        "insufficient_quota",
        "quota_exceeded",
        "quota_exhausted",
    },
)
"""Structured markers proving a 429 is an exhausted quota rather than pacing.

A bare 429 — and the generic ``resource_exhausted`` status Google-style
providers return for pacing — stays a retryable rate limit.
"""

_PAYMENT_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "billing_error",
        "billing_hard_limit_reached",
        "insufficient_credits",
        "payment_required",
    },
)
"""Structured markers of a billing or credit failure."""

_MODEL_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "invalid_model",
        "model_decommissioned",
        "model_not_found",
        "unknown_model",
    },
)
"""Structured markers of an unknown, retired or unusable model identifier."""

_CONTEXT_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "context_length_exceeded",
        "max_tokens_exceeded",
        "request_too_large",
    },
)
"""Structured markers of an exceeded context window."""

_BLOCKED_MARKERS: Final[frozenset[str]] = frozenset(
    {
        "blocked",
        "content_filter",
        "content_policy_violation",
        "prohibited_content",
        "safety",
    },
)
"""Structured markers of a safety policy blocking the completion."""


def raise_palantir_auth_error(message: str, *, field_name: str, suggestion: str) -> Never:
    """Raise a typed token failure before any network access happens.

    Used for an absent, blank or unsendable token, matching what the four
    existing engines raise for a missing key, so a UI can route every credential
    problem to the same place.

    Args:
        message: Safe description naming the defective field, never its value.
        field_name: Environment variable or configuration field at fault.
        suggestion: Actionable fix shown to the user.

    Raises:
        LlmAuthError: Always; the caller has no usable token.
    """
    context: ErrorContext = ErrorContext(
        code=ErrorCode.LLM_AUTH_FAILED,
        message=message,
        suggestion=suggestion,
        details={"engine_id": PALANTIR_ENGINE_ID, "field": field_name},
    )
    raise LlmAuthError(context=context)


def raise_palantir_config_error(message: str, *, field_name: str, suggestion: str) -> Never:
    """Raise a typed configuration failure before any network access happens.

    Used for a defective URL, protocol, alias, provider ID or model ID. A token
    problem goes through ``raise_palantir_auth_error`` instead.

    Args:
        message: Safe description naming the defective field, never its value.
        field_name: Configuration field or environment variable at fault.
        suggestion: Actionable fix shown to the user.

    Raises:
        LlmConfigError: Always; the caller found an unusable configuration.
    """
    context: ErrorContext = ErrorContext(
        code=ErrorCode.LLM_CONFIG_INVALID,
        message=message,
        suggestion=suggestion,
        details={"engine_id": PALANTIR_ENGINE_ID, "field": field_name},
    )
    raise LlmConfigError(context=context)


def palantir_status_error(
    status_code: int,
    *,
    alias: str,
    payload: object = None,
    retry_after_s: float | None = None,
) -> LlmError:
    """Classify one proxy HTTP status into the existing LLM taxonomy.

    Args:
        status_code: HTTP status the proxy returned.
        alias: Catalog alias whose request failed.
        payload: Decoded error body used only to match structured markers; its
            content never reaches the message, the suggestion or ``details``.
        retry_after_s: Retry hint parsed from the response headers.

    Returns:
        One instance of the existing typed LLM error classes, transient for
        pacing and availability failures and fatal for everything else.
    """
    markers: frozenset[str] = structured_markers(payload)
    error: LlmError = _classify_status(
        status_code,
        alias=alias,
        markers=markers,
        retry_after_s=retry_after_s,
    )
    logger.debug(
        "Palantir response classified",
        alias=alias,
        status=status_code,
        error_code=str(error.context.code),
    )
    return error


def palantir_timeout_error(*, alias: str) -> LlmError:
    """Build the transient error of a proxy request that exceeded its timeout."""
    return LlmTimeoutError(
        context=_context(
            ErrorCode.TIMEOUT,
            alias=alias,
            message="Palantir proxy request timed out",
            suggestion="Retry after checking the network connection to the enrollment.",
        ),
    )


def palantir_unavailable_error(*, alias: str, retry_after_s: float | None = None) -> LlmError:
    """Build the transient error of an unreachable or failing enrollment."""
    return LlmProviderUnavailableError(
        context=_context(
            ErrorCode.LLM_PROVIDER_UNAVAILABLE,
            alias=alias,
            message="Palantir enrollment is temporarily unavailable",
            suggestion="Retry later or check the enrollment status.",
        ),
        retry_after_s=retry_after_s,
    )


def palantir_response_error(*, alias: str, defect: PalantirResponseDefect) -> LlmError:
    """Build the fatal error of a response that does not match the protocol.

    Args:
        alias: Catalog alias whose response was unusable.
        defect: Safe label of the defect, used instead of the response body.

    Returns:
        A fatal ``LlmRequestError`` naming only the defect label.
    """
    return LlmRequestError(
        context=_context(
            ErrorCode.LLM_REQUEST_FAILED,
            alias=alias,
            message=f"Palantir proxy returned an unusable response: {defect.value}",
            suggestion="Check that the provider route matches the protocol declared in the catalog.",
            defect=defect.value,
        ),
    )


def palantir_blocked_error(*, alias: str, finish_reason: object = None) -> LlmError:
    """Build the fatal error of a completion the provider policy blocked."""
    return LlmOutputBlockedError(
        context=_context(
            ErrorCode.LLM_OUTPUT_BLOCKED,
            alias=alias,
            message="Palantir provider blocked the completion",
            suggestion="Review the subtitle content or select another model.",
            finish_reason=normalize_finish_reason(finish_reason),
        ),
    )


def _classify_status(
    status_code: int,
    *,
    alias: str,
    markers: frozenset[str],
    retry_after_s: float | None,
) -> LlmError:
    """Map one status onto the taxonomy, keeping pacing distinct from quota."""
    if status_code in _AUTH_STATUSES:
        return LlmAuthError(
            context=_context(
                ErrorCode.LLM_AUTH_FAILED,
                alias=alias,
                message="Palantir enrollment rejected the configured token",
                suggestion="Refresh the token and confirm the enrollment grants access to this model.",
                status=status_code,
            ),
        )
    if status_code == HTTPStatus.REQUEST_TIMEOUT:
        return palantir_timeout_error(alias=alias)
    if status_code == HTTPStatus.TOO_MANY_REQUESTS:
        return _pacing_error(alias=alias, markers=markers, retry_after_s=retry_after_s)
    if status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        return palantir_unavailable_error(alias=alias, retry_after_s=retry_after_s)
    return _client_error(status_code, alias=alias, markers=markers)


def _pacing_error(*, alias: str, markers: frozenset[str], retry_after_s: float | None) -> LlmError:
    """Separate an exhausted quota from a retryable rate limit."""
    if markers & _QUOTA_MARKERS:
        return LlmQuotaError(
            context=_context(
                ErrorCode.LLM_QUOTA_EXHAUSTED,
                alias=alias,
                message="Palantir provider quota is exhausted",
                suggestion="Wait for the quota reset or select another model.",
                status=int(HTTPStatus.TOO_MANY_REQUESTS),
            ),
        )
    return LlmRateLimitError(
        context=_context(
            ErrorCode.LLM_RATE_LIMITED,
            alias=alias,
            message="Palantir provider rate limit was reached",
            suggestion="Wait for the provider retry window.",
            status=int(HTTPStatus.TOO_MANY_REQUESTS),
        ),
        retry_after_s=retry_after_s,
    )


def _client_error(status_code: int, *, alias: str, markers: frozenset[str]) -> LlmError:
    """Map a request-level failure using allowlisted structured markers only."""
    if status_code == HTTPStatus.PAYMENT_REQUIRED or markers & _PAYMENT_MARKERS:
        return LlmPaymentError(
            context=_context(
                ErrorCode.LLM_PAYMENT_REQUIRED,
                alias=alias,
                message="Palantir provider requires payment or sufficient credit",
                suggestion="Check the provider billing state for this enrollment.",
                status=status_code,
            ),
        )
    if markers & _BLOCKED_MARKERS:
        return palantir_blocked_error(alias=alias)
    if status_code == HTTPStatus.CONTENT_TOO_LARGE or markers & _CONTEXT_MARKERS:
        return LlmContextLengthError(
            context=_context(
                ErrorCode.LLM_CONTEXT_EXCEEDED,
                alias=alias,
                message="Palantir provider context window was exceeded",
                suggestion="Split the completion into smaller batches.",
                status=status_code,
            ),
        )
    if status_code == HTTPStatus.NOT_FOUND or markers & _MODEL_MARKERS:
        return LlmModelError(
            context=_context(
                ErrorCode.LLM_MODEL_INVALID,
                alias=alias,
                message="Palantir enrollment does not serve the selected model",
                suggestion="Check the catalog model ID or RID and the provider proxy route.",
                status=status_code,
            ),
        )
    return LlmRequestError(
        context=_context(
            ErrorCode.LLM_REQUEST_FAILED,
            alias=alias,
            message="Palantir proxy rejected the completion request",
            suggestion="Check the selected model, the provider route and the generation settings.",
            status=status_code,
        ),
    )


def _context(
    code: ErrorCode,
    *,
    alias: str,
    message: str,
    suggestion: str,
    **diagnostics: object,
) -> ErrorContext:
    """Build a context carrying the alias plus only safe diagnostic values.

    Args:
        code: Stable error code of the mapped failure.
        alias: Catalog alias the failure belongs to.
        message: Safe UI message without body, headers or token.
        suggestion: Actionable fix shown to the user.
        **diagnostics: Extra safe values such as the HTTP status, the response
            defect label or the finish reason.

    Returns:
        The structured context attached to the mapped error.
    """
    details: dict[str, object] = {"engine_id": PALANTIR_ENGINE_ID, "alias": alias, **diagnostics}
    return ErrorContext(code=code, message=message, suggestion=suggestion, details=details)
