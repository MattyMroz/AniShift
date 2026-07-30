"""Single-attempt runtime boundary for edge-tts."""

from __future__ import annotations

import importlib
import time
from collections.abc import AsyncIterator, Mapping
from http import HTTPStatus
from typing import Protocol, cast

import aiohttp

from anishift.services.tts.errors import (
    TtsClipValidationError,
    TtsInputError,
    TtsNetworkError,
    TtsProviderUnavailableError,
    TtsRateLimitError,
    TtsTimeoutError,
)
from anishift.services.tts.types import AudioFormat, VoiceInfo

from .types import EdgeAttempt, EdgeAudioResponse, EdgeVoiceList

__all__ = ["EdgeApiBackend", "EdgeBackend"]


class _EdgeCommunicate(Protocol):
    def stream(self) -> AsyncIterator[Mapping[str, object]]:
        """Yield provider audio and metadata chunks."""
        ...


class _EdgeCommunicateFactory(Protocol):
    def __call__(  # noqa: PLR0913
        self,
        text: str,
        voice: str,
        *,
        rate: str,
        volume: str,
        pitch: str,
        connect_timeout: int,
        receive_timeout: int,
    ) -> _EdgeCommunicate:
        """Create one Edge synthesis stream."""
        ...


class _VoiceLister(Protocol):
    async def __call__(self) -> object:
        """Fetch raw provider voice records."""
        ...


class _EdgeRuntime(Protocol):
    Communicate: _EdgeCommunicateFactory
    list_voices: _VoiceLister
    exceptions: object


class EdgeBackend(Protocol):
    """Runtime operations used by the provider-neutral Edge engine."""

    async def synthesize_once(
        self,
        attempt: EdgeAttempt,
    ) -> EdgeAudioResponse:
        """Perform exactly one Edge synthesis attempt."""
        ...

    async def list_voices(self) -> EdgeVoiceList:
        """Return normalized voices from the Edge service."""
        ...

    async def close(self) -> None:
        """Release provider resources."""
        ...


class EdgeApiBackend:
    """Import and call edge-tts only after the quality patch succeeds."""

    def __init__(self) -> None:
        """Load the already-patched runtime API without making network calls."""
        runtime: _EdgeRuntime = cast("_EdgeRuntime", importlib.import_module("edge_tts"))
        self._communicate: _EdgeCommunicateFactory = runtime.Communicate
        self._list_voices: _VoiceLister = runtime.list_voices
        exceptions: object = runtime.exceptions
        self._runtime_errors: tuple[type[BaseException], ...] = tuple(
            cast("type[BaseException]", getattr(exceptions, name))
            for name in ("NoAudioReceived", "UnexpectedResponse", "UnknownResponse", "WebSocketError")
        )
        self._closed: bool = False

    async def synthesize_once(
        self,
        attempt: EdgeAttempt,
    ) -> EdgeAudioResponse:
        """Perform one streaming synthesis request and collect native MP3 bytes."""
        self._ensure_open()
        started_at: float = time.perf_counter()
        timeout_s: int = max(1, int(attempt.deadline_s))
        try:
            communicate: _EdgeCommunicate = self._communicate(
                attempt.text,
                attempt.voice_id,
                rate=attempt.rate,
                volume=attempt.volume,
                pitch=attempt.pitch,
                connect_timeout=timeout_s,
                receive_timeout=timeout_s,
            )
            chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk.get("type") != "audio":
                    continue
                audio: object = chunk.get("data")
                if isinstance(audio, bytes):
                    chunks.append(audio)
        except TimeoutError as exc:
            message: str = "Edge synthesis timed out"
            raise TtsTimeoutError(message) from exc
        except aiohttp.ClientResponseError as exc:
            _raise_response_error(exc)
        except aiohttp.ClientError as exc:
            message = "Edge network request failed"
            raise TtsNetworkError(message) from exc
        except (ValueError, TypeError) as exc:
            message = "Edge rejected the selected voice or native options"
            raise TtsInputError(message) from exc
        except self._runtime_errors as exc:
            message = "Edge service returned an invalid synthesis response"
            raise TtsProviderUnavailableError(message) from exc
        audio_bytes: bytes = b"".join(chunks)
        if not audio_bytes:
            message = "Edge returned no audio"
            raise TtsClipValidationError(message)
        return EdgeAudioResponse(
            audio=audio_bytes,
            format=AudioFormat.MP3,
            request_time_ms=(time.perf_counter() - started_at) * 1000.0,
        )

    async def list_voices(self) -> EdgeVoiceList:
        """Fetch and normalize the current Edge voice list."""
        self._ensure_open()
        try:
            raw_result: object = await self._list_voices()
        except TimeoutError as exc:
            message: str = "Edge voice listing timed out"
            raise TtsTimeoutError(message) from exc
        except aiohttp.ClientResponseError as exc:
            _raise_response_error(exc)
        except aiohttp.ClientError as exc:
            message = "Edge voice listing failed"
            raise TtsNetworkError(message) from exc
        voices: list[VoiceInfo] = []
        if not isinstance(raw_result, list):
            message = "Edge returned an invalid voice list"
            raise TtsProviderUnavailableError(message)
        for item in raw_result:
            voice: VoiceInfo | None = _normalize_voice(item)
            if voice is not None:
                voices.append(voice)
        if not voices:
            message = "Edge returned an empty voice list"
            raise TtsProviderUnavailableError(message)
        return tuple(voices)

    async def close(self) -> None:
        """Mark the stateless runtime boundary as closed."""
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            message: str = "Edge backend is closed"
            raise TtsProviderUnavailableError(message)


def _normalize_voice(raw: object) -> VoiceInfo | None:
    if not isinstance(raw, dict):
        return None
    short_name: object = raw.get("ShortName")
    locale: object = raw.get("Locale")
    gender: object = raw.get("Gender", "")
    if not isinstance(short_name, str) or not isinstance(locale, str):
        return None
    return VoiceInfo(
        id=short_name,
        label=short_name,
        engine_id="edge",
        language=locale,
        gender=gender if isinstance(gender, str) else "",
    )


def _raise_response_error(exc: aiohttp.ClientResponseError) -> None:
    if exc.status == HTTPStatus.TOO_MANY_REQUESTS:
        retry_after: str | None = exc.headers.get("Retry-After") if exc.headers is not None else None
        retry_after_s: float | None = _parse_retry_after(retry_after)
        message: str = "Edge rate limit reached"
        raise TtsRateLimitError(message, retry_after_s=retry_after_s) from exc
    if exc.status >= HTTPStatus.INTERNAL_SERVER_ERROR or exc.status in {
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.FORBIDDEN,
    }:
        message = f"Edge service unavailable (HTTP {exc.status})"
        raise TtsProviderUnavailableError(message) from exc
    message = f"Edge rejected the request (HTTP {exc.status})"
    raise TtsInputError(message) from exc


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
