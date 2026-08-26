"""Synchronous HTTP send for the Palantir proxy, with typed failure mapping.

This module creates the client, and only the engine imports it. What keeps the
Palantir package free of ``httpx`` is not this split but ``__init__.py``, which
imports neither this module nor ``service``; the registry reaches the engine
through the ``.service`` submodule, so an HTTP client is loaded only once an
engine is actually created. One request is sent, its full body is read before
anything is parsed — the engine never consumes a stream — and the outcome is
either a decoded mapping or a typed LLM error.

The failure mapping mirrors the taxonomy the four native engines use: a timeout
becomes a transient timeout, an unreachable enrollment becomes a transient
availability error, an HTTP error status is classified through the shared status
mapper, and a body that is not a JSON object becomes a safe response defect. No
body fragment, header or signed URL reaches an error message.

Public API:
    build_palantir_client: Create the synchronous client the engine owns.
    send_palantir_request: Send one described request and return its decoded
        body or raise a typed failure.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

import httpx

from anishift.services.llm.engines.palantir.errors import (
    PalantirResponseDefect,
    palantir_response_error,
    palantir_status_error,
    palantir_timeout_error,
    palantir_unavailable_error,
)
from anishift.services.llm.engines.palantir.protocols import PalantirHttpRequest
from anishift.utils.logger import get_logger

__all__ = ["build_palantir_client", "send_palantir_request"]

logger = get_logger(__name__)


def build_palantir_client(timeout_s: float) -> httpx.Client:
    """Create the synchronous client the engine owns for its lifetime.

    Args:
        timeout_s: Per-request timeout applied to every proxy call.

    Returns:
        A client with SDK-side retries disabled, since retry belongs to the
        LLM domain retry policy alone.
    """
    return httpx.Client(timeout=timeout_s)


def send_palantir_request(
    client: httpx.Client,
    built: PalantirHttpRequest,
    *,
    alias: str,
) -> Mapping[str, Any]:
    """Send one described request and return its decoded JSON body.

    Args:
        client: Synchronous client owned by the engine.
        built: Described request carrying the method, URL, headers and body.
        alias: Catalog alias used only in safe error diagnostics.

    Returns:
        The decoded response body as a mapping.

    Raises:
        LlmTimeoutError: The request exceeded its timeout.
        LlmProviderUnavailableError: The enrollment could not be reached.
        LlmError: The proxy returned an error status, mapped by the taxonomy.
        LlmRequestError: The success body was not a readable JSON object.
    """
    response: httpx.Response = _send(client, built, alias=alias)
    payload: dict[str, Any] | None = _decode(response.text)
    if response.status_code >= HTTPStatus.BAD_REQUEST:
        logger.debug("Palantir proxy returned an error status", alias=alias, status=response.status_code)
        raise palantir_status_error(
            response.status_code,
            alias=alias,
            payload=payload,
            retry_after_s=_retry_after(response.headers),
        )
    if payload is None:
        raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNREADABLE_BODY)
    return payload


def _send(client: httpx.Client, built: PalantirHttpRequest, *, alias: str) -> httpx.Response:
    """Send the request, mapping transport failures onto transient errors."""
    try:
        return client.request(
            built.method,
            built.url,
            headers=dict(built.headers),
            content=json.dumps(dict(built.body)).encode("utf-8"),
        )
    except httpx.TimeoutException as error:
        raise palantir_timeout_error(alias=alias) from error
    except httpx.TransportError as error:
        raise palantir_unavailable_error(alias=alias) from error


def _decode(body: str) -> dict[str, Any] | None:
    """Return the body as a JSON object, or ``None`` when it is not one."""
    try:
        parsed: object = json.loads(body)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _retry_after(headers: Mapping[str, str]) -> float | None:
    """Return the non-negative ``retry-after`` header value, when present."""
    value: str | None = headers.get("retry-after")
    if value is None:
        return None
    try:
        parsed: float = float(value)
    except ValueError:
        return None
    return max(0.0, parsed)
