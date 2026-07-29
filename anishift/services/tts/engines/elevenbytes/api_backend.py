"""Single-attempt HTTP boundary for the ElevenBytes proxy."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Final

import httpx

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.errors import (
    TtsClipValidationError,
    TtsInputError,
    TtsNetworkError,
    TtsProviderUnavailableError,
    TtsRateLimitError,
    TtsTimeoutError,
)
from anishift.services.tts.types import AudioFormat

from .config import ElevenBytesConfig
from .constants import MIN_AUDIO_BYTES, PUBLIC_PROXY_TOKEN, REQUEST_HEADERS
from .types import ElevenBytesResponse

__all__ = ["ElevenBytesApiBackend"]

_MP3_CONTENT_TYPES: Final[frozenset[str]] = frozenset(
    {"application/octet-stream", "audio/mp3", "audio/mpeg", "audio/x-mpeg"},
)
"""Content types compatible with the proxy's native MP3 response."""

_PROXY_BLOCK_STATUSES: Final[frozenset[int]] = frozenset(
    {httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN},
)
"""Statuses indicating a proxy-wide block rather than missing user credentials."""

_MP3_ID3_HEADER_BYTES: Final[int] = 10
"""Byte length of an ID3v2 header before its declared payload."""

_MP3_SYNC_FIRST_BYTE: Final[int] = 0xFF
"""First byte of an MPEG audio frame sync word."""

_MP3_SYNC_MASK: Final[int] = 0xE0
"""Mask selecting the high MPEG frame sync bits in the second byte."""

_MP3_VERSION_RESERVED: Final[int] = 1
"""Reserved MPEG audio version bit pattern."""

_MP3_LAYER_RESERVED: Final[int] = 0
"""Reserved MPEG audio layer bit pattern."""

_MP3_BITRATE_INVALID: Final[frozenset[int]] = frozenset({0, 0xF})
"""Free and invalid bitrate indices rejected at the provider boundary."""

_MP3_SAMPLE_RATE_RESERVED: Final[int] = 3
"""Reserved MPEG audio sample-rate bit pattern."""


class ElevenBytesApiBackend:
    """Send one proxy request without retry, persistence, or scheduling."""

    def __init__(
        self,
        config: ElevenBytesConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create one reusable async client for an engine lifecycle."""
        self._config: ElevenBytesConfig = config
        resolved_transport: httpx.AsyncBaseTransport = transport or httpx.AsyncHTTPTransport(retries=0)
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            headers=dict(REQUEST_HEADERS),
            timeout=httpx.Timeout(config.timeout_s),
            transport=resolved_transport,
        )
        self._closed: bool = False

    @property
    def is_closed(self) -> bool:
        """Whether this backend no longer accepts requests."""
        return self._closed

    async def synthesize_once(
        self,
        text: str,
        voice_id: str,
        *,
        deadline_s: float,
    ) -> ElevenBytesResponse:
        """Perform exactly one synthesis POST and validate its response envelope."""
        started_at: float = time.perf_counter()
        try:
            response: httpx.Response = await self._client.post(
                self._config.endpoint,
                data=self._build_payload(text, voice_id),
                timeout=httpx.Timeout(min(self._config.timeout_s, deadline_s)),
            )
        except httpx.TimeoutException as exc:
            message: str = "ElevenBytes request timed out"
            raise TtsTimeoutError(message) from exc
        except httpx.TransportError as exc:
            message = "ElevenBytes network request failed"
            raise TtsNetworkError(message) from exc

        request_time_ms: float = (time.perf_counter() - started_at) * 1000.0
        self._raise_for_status(response)
        content_type: str = _normalized_content_type(response)
        _validate_mp3_response(response.content, content_type=content_type)
        return ElevenBytesResponse(
            audio=response.content,
            format=AudioFormat.MP3,
            content_type=content_type,
            request_time_ms=request_time_ms,
        )

    async def probe(self) -> None:
        """Check endpoint reachability without submitting synthesis text."""
        if self._closed:
            closed_message: str = "ElevenBytes HTTP backend is closed"
            raise TtsProviderUnavailableError(closed_message)
        try:
            response: httpx.Response = await self._client.get(self._config.endpoint)
        except httpx.TimeoutException as exc:
            timeout_message: str = "ElevenBytes availability probe timed out"
            raise TtsTimeoutError(timeout_message) from exc
        except httpx.TransportError as exc:
            network_message: str = "ElevenBytes availability probe failed"
            raise TtsNetworkError(network_message) from exc
        if (
            response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR
            or response.status_code in _PROXY_BLOCK_STATUSES
            or response.status_code == httpx.codes.TOO_MANY_REQUESTS
        ):
            self._raise_for_status(response)

    async def close(self) -> None:
        """Close the underlying HTTP client once."""
        if self._closed:
            return
        await self._client.aclose()
        self._closed = True

    def _build_payload(self, text: str, voice_id: str) -> dict[str, str]:
        payload: dict[str, str] = {
            "key": PUBLIC_PROXY_TOKEN,
            "text": text,
            "voice": voice_id,
        }
        if self._config.run7_settings is not None:
            payload.update(self._config.run7_settings.as_form())
        return payload

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status_code: int = response.status_code
        retry_after_s: float | None = _parse_retry_after(response.headers.get("Retry-After"))
        if status_code == httpx.codes.TOO_MANY_REQUESTS:
            message: str = "ElevenBytes rate limit reached"
            raise TtsRateLimitError(
                message,
                retry_after_s=retry_after_s,
            )
        if status_code in _PROXY_BLOCK_STATUSES or status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
            message = f"ElevenBytes service unavailable (HTTP {status_code})"
            raise TtsProviderUnavailableError(
                message,
                retry_after_s=retry_after_s,
            )
        if httpx.codes.BAD_REQUEST <= status_code < httpx.codes.INTERNAL_SERVER_ERROR:
            context: ErrorContext = ErrorContext(
                code=ErrorCode.TTS_INPUT_INVALID,
                message=f"ElevenBytes rejected the request (HTTP {status_code})",
                suggestion="Check the selected endpoint, voice, and request text.",
                details={"status_code": status_code},
            )
            raise TtsInputError(context=context)
        if status_code != httpx.codes.OK:
            message = f"Unexpected ElevenBytes response (HTTP {status_code})"
            raise TtsProviderUnavailableError(message)


def _normalized_content_type(response: httpx.Response) -> str:
    raw_content_type: str = response.headers.get("Content-Type", "")
    return raw_content_type.partition(";")[0].strip().lower()


def _validate_mp3_response(audio: bytes, *, content_type: str) -> None:
    if len(audio) < MIN_AUDIO_BYTES:
        message: str = f"ElevenBytes returned too little audio data ({len(audio)} bytes)"
        raise TtsClipValidationError(message)
    if _contains_mp3_header(audio):
        return
    if content_type and content_type not in _MP3_CONTENT_TYPES:
        message = f"ElevenBytes returned non-MP3 content ({content_type})"
        raise TtsClipValidationError(message)
    message = "ElevenBytes response is not recognizable MP3 audio"
    raise TtsClipValidationError(message)


def _contains_mp3_header(audio: bytes) -> bool:
    offset: int = 0
    if audio.startswith(b"ID3") and len(audio) >= _MP3_ID3_HEADER_BYTES:
        tag_size: int = (audio[6] & 0x7F) << 21 | (audio[7] & 0x7F) << 14 | (audio[8] & 0x7F) << 7 | (audio[9] & 0x7F)
        offset = _MP3_ID3_HEADER_BYTES + tag_size
    search_end: int = min(len(audio) - 2, offset + 8192)
    for index in range(offset, search_end):
        first: int = audio[index]
        second: int = audio[index + 1]
        if _is_mp3_frame_header(first, second, audio[index + 2]):
            return True
    return False


def _is_mp3_frame_header(first: int, second: int, third: int) -> bool:
    if first != _MP3_SYNC_FIRST_BYTE or second & _MP3_SYNC_MASK != _MP3_SYNC_MASK:
        return False
    version: int = (second >> 3) & 0x03
    layer: int = (second >> 1) & 0x03
    bitrate: int = (third >> 4) & 0x0F
    sample_rate: int = (third >> 2) & 0x03
    return (
        version != _MP3_VERSION_RESERVED
        and layer != _MP3_LAYER_RESERVED
        and bitrate not in _MP3_BITRATE_INVALID
        and sample_rate != _MP3_SAMPLE_RATE_RESERVED
    )


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds: float = float(value)
    except ValueError:
        return _retry_after_from_http_date(value)
    return max(0.0, seconds)


def _retry_after_from_http_date(value: str) -> float | None:
    try:
        retry_at: datetime = parsedate_to_datetime(value)
    except TypeError, ValueError:
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
