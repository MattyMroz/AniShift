"""Synchronous HTTP send for the Palantir proxy, with typed failure mapping."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
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

__all__ = ["build_palantir_client", "send_palantir_request", "stream_palantir_request"]

logger = get_logger(__name__)


def build_palantir_client(timeout_s: float) -> httpx.Client:
    """Create the synchronous client the engine owns for its lifetime."""
    return httpx.Client(timeout=timeout_s)


def send_palantir_request(
    client: httpx.Client,
    built: PalantirHttpRequest,
    *,
    alias: str,
) -> Mapping[str, Any]:
    """Send one described request and return its decoded JSON body."""
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


def stream_palantir_request(
    client: httpx.Client,
    built: PalantirHttpRequest,
    *,
    alias: str,
    on_event: Callable[[Mapping[str, Any]], None] | None = None,
) -> tuple[Mapping[str, Any], ...]:
    """Consume one SSE response and return its decoded JSON events."""
    try:
        with client.stream(
            built.method,
            built.url,
            headers=dict(built.headers),
            content=json.dumps(dict(built.body)).encode("utf-8"),
        ) as response:
            if response.status_code >= HTTPStatus.BAD_REQUEST:
                response.read()
                payload: dict[str, Any] | None = _decode(response.text)
                logger.debug("Palantir proxy returned an error status", alias=alias, status=response.status_code)
                raise palantir_status_error(
                    response.status_code,
                    alias=alias,
                    payload=payload,
                    retry_after_s=_retry_after(response.headers),
                )
            collected: list[Mapping[str, Any]] = []
            for event in _sse_events(response.iter_lines(), alias=alias):
                if event.get("error") is not None:
                    error_payload: object = event["error"]
                    code: object = error_payload.get("code") if isinstance(error_payload, Mapping) else None
                    status: int = (
                        code
                        if isinstance(code, int) and code in HTTPStatus and code >= HTTPStatus.BAD_REQUEST
                        else HTTPStatus.BAD_REQUEST
                    )
                    raise palantir_status_error(status, alias=alias, payload=event)
                collected.append(event)
                if on_event is not None:
                    on_event(event)
            events: tuple[Mapping[str, Any], ...] = tuple(collected)
    except httpx.TimeoutException as error:
        raise palantir_timeout_error(alias=alias) from error
    except httpx.TransportError as error:
        raise palantir_unavailable_error(alias=alias) from error
    if not events:
        raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNREADABLE_BODY)
    return events


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


def _sse_events(lines: Iterator[str], *, alias: str) -> Iterator[Mapping[str, Any]]:
    """Yield JSON objects carried by SSE data fields."""
    data_lines: list[str] = []
    for line in lines:
        if line:
            if line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").lstrip())
            continue
        yield from _decode_sse_data(data_lines, alias=alias)
        data_lines.clear()
    yield from _decode_sse_data(data_lines, alias=alias)


def _decode_sse_data(data_lines: list[str], *, alias: str) -> Iterator[Mapping[str, Any]]:
    if not data_lines:
        return
    data: str = "\n".join(data_lines)
    if data == "[DONE]":
        return
    payload: dict[str, Any] | None = _decode(data)
    if payload is None:
        raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNREADABLE_BODY)
    yield payload


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
