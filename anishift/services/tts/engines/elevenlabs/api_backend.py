"""Lazy one-attempt boundary around the official ElevenLabs SDK."""

from __future__ import annotations

import importlib
import math
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from typing import Never, Protocol, cast

import httpx

from anishift.services.tts.errors import (
    TtsClipValidationError,
    TtsNetworkError,
    TtsProviderUnavailableError,
    TtsTimeoutError,
)
from anishift.services.tts.types import VoiceInfo

from .config import ElevenLabsConfig
from .options import ElevenLabsAttempt

__all__ = [
    "ElevenLabsApiError",
    "ElevenLabsBackend",
    "ElevenLabsSdkBackend",
]


@dataclass(frozen=True, slots=True)
class ElevenLabsApiError(Exception):
    """Safe HTTP metadata from one failed official SDK request."""

    status_code: int | None
    headers: Mapping[str, str]


class _TextToSpeechClient(Protocol):
    def convert(
        self,
        voice_id: str,
        **kwargs: object,
    ) -> AsyncIterator[bytes]: ...


class _VoicesClient(Protocol):
    async def search(self, **kwargs: object) -> object: ...


class _SdkClient(Protocol):
    text_to_speech: _TextToSpeechClient
    voices: _VoicesClient


@dataclass(slots=True)
class _SdkRuntime:
    client: _SdkClient
    voice_settings_factory: Callable[..., object]
    api_error_type: type[Exception]
    http_client: httpx.AsyncClient | None


type _RuntimeFactory = Callable[[ElevenLabsConfig], _SdkRuntime]


class ElevenLabsBackend(Protocol):
    """One-attempt official ElevenLabs SDK boundary."""

    async def synthesize_once(self, attempt: ElevenLabsAttempt) -> bytes:
        """Submit one paid payload without retry."""
        ...

    async def list_voices_once(self, *, deadline_s: float) -> tuple[VoiceInfo, ...]:
        """Fetch all voice pages without retry."""
        ...

    async def close(self) -> None:
        """Release provider resources."""
        ...


class ElevenLabsSdkBackend:
    """Lazy official SDK transport with every automatic retry disabled."""

    def __init__(
        self,
        config: ElevenLabsConfig,
        *,
        runtime_factory: _RuntimeFactory | None = None,
    ) -> None:
        """Store configuration without importing or initializing the SDK."""
        self._config: ElevenLabsConfig = config
        self._runtime_factory: _RuntimeFactory = runtime_factory or _load_sdk_runtime
        self._runtime: _SdkRuntime | None = None

    async def synthesize_once(self, attempt: ElevenLabsAttempt) -> bytes:
        """Submit one payload with SDK retry explicitly disabled."""
        runtime: _SdkRuntime = self._get_runtime()
        voice_settings: object = runtime.voice_settings_factory(
            stability=attempt.voice_settings.stability,
            similarity_boost=attempt.voice_settings.similarity_boost,
            style=attempt.voice_settings.style,
            use_speaker_boost=attempt.voice_settings.use_speaker_boost,
            speed=attempt.voice_settings.speed,
        )
        request_options: dict[str, int] = {
            "max_retries": 0,
            "timeout_in_seconds": math.ceil(attempt.deadline_s),
        }
        try:
            response: AsyncIterator[bytes] = runtime.client.text_to_speech.convert(
                attempt.voice_id,
                text=attempt.text,
                model_id=attempt.model_id,
                output_format=attempt.output_format,
                voice_settings=voice_settings,
                request_options=request_options,
            )
            chunks: list[bytes] = []
            async for chunk in response:
                if not isinstance(chunk, bytes):
                    message: str = "ElevenLabs returned a non-audio response chunk"
                    raise TtsClipValidationError(message)
                if chunk:
                    chunks.append(chunk)
        except runtime.api_error_type as error:
            _raise_safe_api_error(error)
        except httpx.TimeoutException as error:
            message = "ElevenLabs request timed out"
            raise TtsTimeoutError(message) from error
        except httpx.NetworkError as error:
            message = "ElevenLabs network request failed"
            raise TtsNetworkError(message) from error
        if not chunks:
            message = "ElevenLabs returned no audio"
            raise TtsClipValidationError(message)
        return b"".join(chunks)

    async def list_voices_once(self, *, deadline_s: float) -> tuple[VoiceInfo, ...]:
        """Fetch all voice pages without SDK retry."""
        runtime: _SdkRuntime = self._get_runtime()
        request_options: dict[str, int] = {
            "max_retries": 0,
            "timeout_in_seconds": math.ceil(deadline_s),
        }
        voices: list[VoiceInfo] = []
        next_page_token: str | None = None
        seen_page_tokens: set[str] = set()
        while True:
            response: object = await self._request_voice_page(
                runtime,
                request_options=request_options,
                next_page_token=next_page_token,
            )
            voices.extend(_normalize_voice_page(response))
            has_more: object = getattr(response, "has_more", False)
            if has_more is not True:
                return tuple(voices)
            raw_next_token: object = getattr(response, "next_page_token", None)
            if not isinstance(raw_next_token, str) or not raw_next_token or raw_next_token in seen_page_tokens:
                message: str = "ElevenLabs returned invalid voice pagination"
                raise TtsProviderUnavailableError(message)
            seen_page_tokens.add(raw_next_token)
            next_page_token = raw_next_token

    async def close(self) -> None:
        """Close the SDK transport if it was initialized."""
        if self._runtime is None or self._runtime.http_client is None:
            return
        await self._runtime.http_client.aclose()

    async def _request_voice_page(
        self,
        runtime: _SdkRuntime,
        *,
        request_options: dict[str, int],
        next_page_token: str | None,
    ) -> object:
        try:
            return await runtime.client.voices.search(
                next_page_token=next_page_token,
                page_size=100,
                request_options=request_options,
            )
        except runtime.api_error_type as error:
            _raise_safe_api_error(error)
        except httpx.TimeoutException as error:
            message: str = "ElevenLabs voice request timed out"
            raise TtsTimeoutError(message) from error
        except httpx.NetworkError as error:
            message = "ElevenLabs voice request failed"
            raise TtsNetworkError(message) from error

    def _get_runtime(self) -> _SdkRuntime:
        if self._runtime is not None:
            return self._runtime
        try:
            self._runtime = self._runtime_factory(self._config)
        except ModuleNotFoundError as error:
            message: str = "Official ElevenLabs SDK is not installed"
            raise TtsProviderUnavailableError(message) from error
        return self._runtime


class _ApiError(Protocol):
    status_code: int | None
    headers: Mapping[str, str] | None


def _load_sdk_runtime(config: ElevenLabsConfig) -> _SdkRuntime:
    sdk_module = importlib.import_module("elevenlabs")
    api_error_module = importlib.import_module("elevenlabs.core.api_error")
    client_factory = cast("Callable[..., _SdkClient]", sdk_module.AsyncElevenLabs)
    voice_settings_factory = cast("Callable[..., object]", sdk_module.VoiceSettings)
    api_error_type = cast("type[Exception]", api_error_module.ApiError)
    http_client = httpx.AsyncClient(timeout=config.timeout_s, follow_redirects=True)
    client: _SdkClient = client_factory(
        api_key=config.api_key,
        timeout=config.timeout_s,
        httpx_client=http_client,
    )
    return _SdkRuntime(
        client=client,
        voice_settings_factory=voice_settings_factory,
        api_error_type=api_error_type,
        http_client=http_client,
    )


def _raise_safe_api_error(error: Exception) -> Never:
    failure = cast("_ApiError", error)
    raise ElevenLabsApiError(
        status_code=failure.status_code,
        headers=failure.headers or {},
    ) from error


def _voice_label(labels: object, key: str) -> str:
    if not isinstance(labels, Mapping):
        return ""
    value: object = labels.get(key)
    return value if isinstance(value, str) else ""


def _normalize_voice_page(response: object) -> list[VoiceInfo]:
    raw_voices: object = getattr(response, "voices", ())
    if not isinstance(raw_voices, (tuple, list)):
        message: str = "ElevenLabs returned an invalid voice list"
        raise TtsProviderUnavailableError(message)
    voices: list[VoiceInfo] = []
    for raw_voice in raw_voices:
        voice_id: object = getattr(raw_voice, "voice_id", "")
        if not isinstance(voice_id, str) or not voice_id:
            continue
        label: object = getattr(raw_voice, "name", "")
        labels: object = getattr(raw_voice, "labels", {})
        voices.append(
            VoiceInfo(
                id=voice_id,
                label=label if isinstance(label, str) and label else voice_id,
                engine_id="elevenlabs",
                language=_voice_label(labels, "language"),
                gender=_voice_label(labels, "gender"),
            ),
        )
    return voices
