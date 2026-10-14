"""Synchronous HTTP send for the Palantir proxy, with typed failure mapping."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing, contextmanager
from http import HTTPStatus
from typing import Any

import httpx

from anishift.services.llm.engines.palantir.accounts import (
    PalantirAccount,
    account_order,
    account_request,
    clear_cooldown,
    start_cooldown,
)
from anishift.services.llm.engines.palantir.errors import (
    PalantirResponseDefect,
    palantir_generation_error,
    palantir_response_error,
    palantir_status_error,
    palantir_timeout_error,
    palantir_unavailable_error,
)
from anishift.services.llm.engines.palantir.protocols import PalantirHttpRequest
from anishift.services.llm.errors import LlmError
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
    accounts: tuple[PalantirAccount, ...],
) -> Mapping[str, Any]:
    """Send one described request and return its decoded JSON body."""
    with _open_response(client, built, alias=alias, accounts=accounts) as response:
        response.read()
        if response.status_code >= HTTPStatus.BAD_REQUEST:
            raise _status_failure(response, alias=alias)
        payload: dict[str, Any] | None = _decode(response.text)
    if payload is None:
        raise palantir_response_error(alias=alias, defect=PalantirResponseDefect.UNREADABLE_BODY)
    return payload


def stream_palantir_request(
    client: httpx.Client,
    built: PalantirHttpRequest,
    *,
    alias: str,
    accounts: tuple[PalantirAccount, ...],
    on_event: Callable[[Mapping[str, Any]], None] | None = None,
) -> tuple[Mapping[str, Any], ...]:
    """Consume one SSE response and return its decoded JSON events."""
    with _open_response(client, built, alias=alias, accounts=accounts) as response:
        if response.status_code >= HTTPStatus.BAD_REQUEST:
            response.read()
            raise _status_failure(response, alias=alias)
        events: tuple[Mapping[str, Any], ...] = _collect_events(response, alias=alias, on_event=on_event)
    if not events:
        raise palantir_unavailable_error(alias=alias)
    return events


def _collect_events(
    response: httpx.Response,
    *,
    alias: str,
    on_event: Callable[[Mapping[str, Any]], None] | None,
) -> tuple[Mapping[str, Any], ...]:
    collected: list[Mapping[str, Any]] = []
    for event in _sse_events(response.iter_lines(), alias=alias):
        if event.get("type") == "error":
            raise palantir_generation_error(event.get("code"), alias=alias)
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
    return tuple(collected)


@contextmanager
def _open_response(
    client: httpx.Client,
    built: PalantirHttpRequest,
    *,
    alias: str,
    accounts: tuple[PalantirAccount, ...],
) -> Iterator[httpx.Response]:
    try:
        with closing(_send(client, built, alias=alias, accounts=accounts)) as response:
            yield response
    except httpx.TimeoutException as error:
        raise palantir_timeout_error(alias=alias) from error
    except httpx.TransportError as error:
        raise palantir_unavailable_error(alias=alias) from error


def _send(
    client: httpx.Client,
    built: PalantirHttpRequest,
    *,
    alias: str,
    accounts: tuple[PalantirAccount, ...],
) -> httpx.Response:
    pool: tuple[PalantirAccount, ...] = account_order(accounts)
    for index, account in enumerate(pool):
        selected: PalantirHttpRequest = account_request(built, account)
        request: httpx.Request = client.build_request(
            selected.method,
            selected.url,
            headers=dict(selected.headers),
            content=json.dumps(dict(selected.body)).encode("utf-8"),
        )
        response: httpx.Response = client.send(request, stream=True)
        if (
            response.status_code != HTTPStatus.TOO_MANY_REQUESTS
            and response.status_code < HTTPStatus.INTERNAL_SERVER_ERROR
        ):
            clear_cooldown(account)
            return response
        start_cooldown(account)
        if index == len(pool) - 1:
            break
        response.close()
        logger.debug(
            "Palantir request switching account", alias=alias, account=account.number, status=response.status_code
        )
    return response


def _status_failure(response: httpx.Response, *, alias: str) -> LlmError:
    logger.debug("Palantir proxy returned an error status", alias=alias, status=response.status_code)
    return palantir_status_error(
        response.status_code,
        alias=alias,
        payload=_decode(response.text),
        retry_after_s=_retry_after(response.headers),
    )


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
        if not line:
            yield from _decode_sse_data(data_lines, alias=alias)
            data_lines.clear()
            continue
        if line.startswith("data:"):
            data_lines.append(line.removeprefix("data:").lstrip())
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
