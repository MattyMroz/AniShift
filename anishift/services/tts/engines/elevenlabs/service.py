"""Official ElevenLabs SDK adapter for provider-neutral speech synthesis."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Final, cast

from anishift.services.tts.artifacts import atomic_json_snapshot
from anishift.services.tts.config import TtsConfig
from anishift.services.tts.errors import (
    TtsAuthError,
    TtsCancelledError,
    TtsClipValidationError,
    TtsInputError,
    TtsNetworkError,
    TtsProviderUnavailableError,
    TtsRateLimitError,
    TtsTimeoutError,
    TtsUnsupportedError,
    TtsVoiceError,
)
from anishift.services.tts.fingerprint import SynthesisProfile
from anishift.services.tts.protocols import CancellationToken
from anishift.services.tts.types import (
    AudioFormat,
    AvailabilityProbeKind,
    AvailabilitySource,
    AvailabilityStatus,
    EngineAvailability,
    EngineCapabilities,
    EngineClipResult,
    EngineLocality,
    SynthesisRequest,
    VoiceInfo,
)

from .api_backend import (
    ElevenLabsApiError,
    ElevenLabsBackend,
    ElevenLabsSdkBackend,
)
from .config import ElevenLabsConfig
from .constants import (
    ADAPTER_VERSION,
    ELEVENLABS_ENDPOINT_ID,
    MAX_TEXT_CHARS,
    VOICES_CACHE_TTL_S,
)
from .options import ElevenLabsAttempt, resolve_elevenlabs_options

__all__ = ["ElevenLabsTtsEngine"]

_HTTP_BAD_REQUEST: Final[int] = 400
"""HTTP status used for invalid ElevenLabs payloads."""

_HTTP_UNAUTHORIZED: Final[int] = 401
"""HTTP status used for rejected ElevenLabs credentials."""

_HTTP_FORBIDDEN: Final[int] = 403
"""HTTP status used for rejected ElevenLabs permissions."""

_HTTP_NOT_FOUND: Final[int] = 404
"""HTTP status used for missing ElevenLabs resources."""

_HTTP_RATE_LIMITED: Final[int] = 429
"""HTTP status used for ElevenLabs rate limits."""

_HTTP_SERVER_ERROR: Final[int] = 500
"""First HTTP status in the server-error range."""

_WAV_HEADER_SIZE: Final[int] = 12
"""Minimum byte length of a RIFF/WAVE header."""

_VOICE_CACHE_SCHEMA: Final[int] = 1
"""Schema version for the non-secret voice metadata cache."""


type _SdkProbe = Callable[[], bool]
type _Clock = Callable[[], float]


class ElevenLabsTtsEngine:
    """One-attempt adapter for the official ElevenLabs API."""

    engine_id = "elevenlabs"
    capabilities = EngineCapabilities(
        locality=EngineLocality.REMOTE,
        native_output_formats=(AudioFormat.MP3, AudioFormat.OPUS, AudioFormat.WAV),
        supports_concurrency=True,
        supports_native_rate=False,
        supports_native_volume=False,
        supports_pitch=False,
        supports_voice_settings=True,
        requires_api_key=True,
        min_text_chars=1,
        max_text_chars=MAX_TEXT_CHARS,
        max_text_bytes=None,
        availability_probe=AvailabilityProbeKind.REMOTE,
    )

    def __init__(
        self,
        config: TtsConfig,
        *,
        backend: ElevenLabsBackend | None = None,
        sdk_probe: _SdkProbe | None = None,
        clock: _Clock = time.monotonic,
        wall_clock: _Clock = time.time,
    ) -> None:
        """Resolve configuration without importing or calling the SDK."""
        self._config: ElevenLabsConfig = ElevenLabsConfig.from_tts_config(config)
        self._backend: ElevenLabsBackend = backend or ElevenLabsSdkBackend(self._config)
        self._sdk_probe: _SdkProbe = sdk_probe or _sdk_installed
        self._clock: _Clock = clock
        self._wall_clock: _Clock = wall_clock
        self._closed: bool = False
        self._voices_lock: asyncio.Lock = asyncio.Lock()
        self._voices_cache: tuple[VoiceInfo, ...] = ()
        self._voices_cached_at: float = 0.0
        self._voices_cache_path: Path | None = (
            config.metadata_cache_root / "elevenlabs-voices.json" if config.metadata_cache_root is not None else None
        )
        self._availability: EngineAvailability = self._initial_availability()
        self._load_voice_cache()
        if self._voices_cache:
            self._availability = EngineAvailability(
                status=self._availability.status,
                message=self._availability.message,
                checked_at=self._availability.checked_at,
                source=AvailabilitySource.CACHED,
                voices=self._voices_cache,
            )
        self._synthesis_profile: SynthesisProfile = SynthesisProfile(
            engine_id=self.engine_id,
            endpoint_id=ELEVENLABS_ENDPOINT_ID,
            provider_model_id=self._config.provider_model_id,
            resolved_voice_id=self._config.voice_id,
            provider_output_id=self._config.options.output.token,
            provider_source_format=self._config.options.output.format,
            adapter_version=ADAPTER_VERSION,
            voice_settings=self._config.options.as_engine_options(),
        )

    @property
    def is_available(self) -> bool:
        """Return the cached cheap projection of detailed availability."""
        return self._availability.status is AvailabilityStatus.READY and not self._closed

    @property
    def synthesis_profile(self) -> SynthesisProfile:
        """Return the fully resolved official ElevenLabs synthesis identity."""
        return self._synthesis_profile

    async def availability(self, *, live: bool = False) -> EngineAvailability:
        """Return configuration state or perform one live voice-list probe."""
        if not live or self._closed:
            return self._availability
        if self._availability.status in {
            AvailabilityStatus.MISSING_BINARY,
            AvailabilityStatus.MISSING_KEY,
        }:
            return self._availability
        return await self._live_availability()

    async def _live_availability(self) -> EngineAvailability:
        try:
            voices: tuple[VoiceInfo, ...] = await self._fetch_voices(force=True)
        except TtsAuthError:
            return self._set_availability(
                AvailabilityStatus.SERVICE_UNAVAILABLE,
                "ElevenLabs authentication failed",
                source=AvailabilitySource.LIVE,
            )
        except TtsTimeoutError, TtsNetworkError:
            return self._set_availability(
                AvailabilityStatus.OFFLINE,
                "ElevenLabs network is unavailable",
                source=AvailabilitySource.LIVE,
            )
        except TtsProviderUnavailableError, TtsRateLimitError:
            return self._set_availability(
                AvailabilityStatus.SERVICE_UNAVAILABLE,
                "ElevenLabs service is unavailable",
                source=AvailabilitySource.LIVE,
            )
        if not any(voice.id == self._config.voice_id for voice in voices):
            return self._set_availability(
                AvailabilityStatus.MISSING_VOICE,
                f"ElevenLabs voice is unavailable: {self._config.voice_id}",
                source=AvailabilitySource.LIVE,
                voices=voices,
            )
        return self._set_availability(
            AvailabilityStatus.READY,
            "ElevenLabs is ready",
            source=AvailabilitySource.LIVE,
            voices=voices,
        )

    async def list_voices(self) -> tuple[VoiceInfo, ...]:
        """Return the cached provider voice list or refresh it once."""
        self._require_ready()
        return await self._fetch_voices()

    async def synthesize(
        self,
        request: SynthesisRequest,
        *,
        cancel: CancellationToken,
    ) -> EngineClipResult:
        """Synthesize one request without shared retry or lifecycle work."""
        self._validate_request(request)
        self._require_ready()
        if cancel.is_cancelled:
            message: str = "ElevenLabs synthesis cancelled before request"
            raise TtsCancelledError(message)
        started_at: float = time.perf_counter()
        try:
            audio: bytes = await self._backend.synthesize_once(
                ElevenLabsAttempt(
                    text=request.text,
                    voice_id=request.voice_id,
                    model_id=request.provider_model_id,
                    output_format=self._config.options.output.token,
                    voice_settings=self._config.options.voice_settings,
                    deadline_s=request.deadline_s,
                ),
            )
        except ElevenLabsApiError as error:
            _raise_mapped_api_error(error)
        _validate_audio(audio, self._config.options.output.format)
        if cancel.is_cancelled:
            message = "ElevenLabs synthesis cancelled before write"
            raise TtsCancelledError(message)
        _write_audio(request.destination, audio)
        return EngineClipResult(
            request_id=request.request_id,
            path=request.destination,
            format=self._config.options.output.format,
            engine_id=self.engine_id,
            provider_model_id=self._config.provider_model_id,
            voice_id=self._config.voice_id,
            request_time_ms=(time.perf_counter() - started_at) * 1000.0,
        )

    async def close(self) -> None:
        """Release the SDK transport once."""
        if self._closed:
            return
        await self._backend.close()
        self._closed = True
        self._set_availability(
            AvailabilityStatus.SERVICE_UNAVAILABLE,
            "ElevenLabs engine is closed",
            source=AvailabilitySource.CACHED,
        )

    async def _fetch_voices(self, *, force: bool = False) -> tuple[VoiceInfo, ...]:
        self._require_ready()
        async with self._voices_lock:
            if not force and self._cache_is_fresh():
                return self._voices_cache
            try:
                voices: tuple[VoiceInfo, ...] = await self._backend.list_voices_once(
                    deadline_s=self._config.timeout_s,
                )
            except ElevenLabsApiError as error:
                _raise_mapped_api_error(error)
            self._voices_cache = voices
            self._voices_cached_at = self._clock()
            self._write_voice_cache(voices)
            return voices

    def _validate_request(self, request: SynthesisRequest) -> None:
        if not request.text or len(request.text) > MAX_TEXT_CHARS:
            message: str = f"ElevenLabs text must contain 1 to {MAX_TEXT_CHARS} characters"
            raise TtsInputError(message)
        if request.provider_model_id != self._config.provider_model_id:
            message = "ElevenLabs request model differs from engine configuration"
            raise TtsUnsupportedError(message)
        if request.voice_id != self._config.voice_id:
            message = "ElevenLabs request voice differs from engine configuration"
            raise TtsUnsupportedError(message)
        if any(value is not None for value in (request.native_rate, request.native_volume, request.native_pitch)):
            message = "ElevenLabs native controls must use engine options"
            raise TtsUnsupportedError(message)
        request_options = resolve_elevenlabs_options(request.options)
        if request_options != self._config.options:
            message = "ElevenLabs request options differ from engine configuration"
            raise TtsUnsupportedError(message)

    def _require_ready(self) -> None:
        if self._closed:
            message: str = "ElevenLabs engine is closed"
            raise TtsProviderUnavailableError(message)
        if not self._config.api_key:
            message = "ElevenLabs API key is missing"
            raise TtsAuthError(message)
        if not self._sdk_probe():
            message = "Official ElevenLabs SDK is not installed"
            raise TtsProviderUnavailableError(message)

    def _initial_availability(self) -> EngineAvailability:
        if not self._config.api_key:
            status: AvailabilityStatus = AvailabilityStatus.MISSING_KEY
            message: str = "ElevenLabs API key is missing"
        elif not self._sdk_probe():
            status = AvailabilityStatus.MISSING_BINARY
            message = "Official ElevenLabs SDK is not installed"
        else:
            status = AvailabilityStatus.READY
            message = "ElevenLabs configured; network unchecked"
        return EngineAvailability(
            status=status,
            message=message,
            checked_at=datetime.now(UTC),
            source=AvailabilitySource.CONFIG,
        )

    def _set_availability(
        self,
        status: AvailabilityStatus,
        message: str,
        *,
        source: AvailabilitySource,
        voices: tuple[VoiceInfo, ...] = (),
    ) -> EngineAvailability:
        self._availability = EngineAvailability(
            status=status,
            message=message,
            checked_at=datetime.now(UTC),
            source=source,
            voices=voices,
        )
        return self._availability

    def _cache_is_fresh(self) -> bool:
        return bool(self._voices_cache) and self._clock() - self._voices_cached_at < VOICES_CACHE_TTL_S

    def _load_voice_cache(self) -> None:
        path: Path | None = self._voices_cache_path
        if path is None or not path.is_file():
            return
        try:
            payload: object = json.loads(path.read_text(encoding="utf-8"))
            voices, cached_at = _parse_voice_cache(
                payload,
                account_fingerprint=_account_fingerprint(self._config.api_key),
            )
        except OSError, json.JSONDecodeError, TypeError, ValueError:
            return
        age_s: float = self._wall_clock() - cached_at
        if not 0.0 <= age_s < VOICES_CACHE_TTL_S:
            return
        self._voices_cache = voices
        self._voices_cached_at = self._clock() - age_s

    def _write_voice_cache(self, voices: tuple[VoiceInfo, ...]) -> None:
        path: Path | None = self._voices_cache_path
        if path is None:
            return
        payload: dict[str, object] = {
            "schema_version": _VOICE_CACHE_SCHEMA,
            "account_fingerprint": _account_fingerprint(self._config.api_key),
            "cached_at": self._wall_clock(),
            "voices": [
                {
                    "id": voice.id,
                    "label": voice.label,
                    "language": voice.language,
                    "gender": voice.gender,
                    "experimental": voice.experimental,
                }
                for voice in voices
            ],
        }
        try:
            atomic_json_snapshot(path, payload)
        except OSError:
            return


def _account_fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _parse_voice_cache(
    payload: object,
    *,
    account_fingerprint: str,
) -> tuple[tuple[VoiceInfo, ...], float]:
    if type(payload) is not dict:
        raise TypeError
    data: dict[str, object] = cast("dict[str, object]", payload)
    if set(data) != {
        "schema_version",
        "account_fingerprint",
        "cached_at",
        "voices",
    }:
        raise ValueError
    if data["schema_version"] != _VOICE_CACHE_SCHEMA or data["account_fingerprint"] != account_fingerprint:
        raise ValueError
    cached_at_value: object = data["cached_at"]
    if isinstance(cached_at_value, bool) or not isinstance(
        cached_at_value,
        (int, float),
    ):
        raise TypeError
    raw_voices: object = data["voices"]
    if type(raw_voices) is not list:
        raise TypeError
    voices: list[VoiceInfo] = []
    for item in cast("list[object]", raw_voices):
        if type(item) is not dict:
            raise TypeError
        voice: dict[str, object] = cast("dict[str, object]", item)
        if set(voice) != {
            "id",
            "label",
            "language",
            "gender",
            "experimental",
        }:
            raise ValueError
        if (
            any(type(voice[field]) is not str for field in ("id", "label", "language", "gender"))
            or type(voice["experimental"]) is not bool
        ):
            raise TypeError
        voices.append(
            VoiceInfo(
                id=cast("str", voice["id"]),
                label=cast("str", voice["label"]),
                engine_id="elevenlabs",
                language=cast("str", voice["language"]),
                gender=cast("str", voice["gender"]),
                experimental=voice["experimental"],
            ),
        )
    return tuple(voices), float(cached_at_value)


def _sdk_installed() -> bool:
    return importlib.util.find_spec("elevenlabs") is not None


def _raise_mapped_api_error(error: ElevenLabsApiError) -> None:
    status_code: int | None = error.status_code
    retry_after_s: float | None = _parse_retry_after(error.headers)
    if status_code == _HTTP_BAD_REQUEST:
        message: str = "ElevenLabs rejected the synthesis request"
        raise TtsInputError(message)
    if status_code in {_HTTP_UNAUTHORIZED, _HTTP_FORBIDDEN}:
        message = "ElevenLabs rejected the configured credentials or permissions"
        raise TtsAuthError(message)
    if status_code == _HTTP_NOT_FOUND:
        message = "ElevenLabs voice or model was not found"
        raise TtsVoiceError(message)
    if status_code == _HTTP_RATE_LIMITED:
        message = "ElevenLabs rate limit reached"
        raise TtsRateLimitError(message, retry_after_s=retry_after_s)
    if status_code is not None and status_code >= _HTTP_SERVER_ERROR:
        message = "ElevenLabs service is unavailable"
        raise TtsProviderUnavailableError(
            message,
            retry_after_s=retry_after_s,
        )
    if status_code is not None and _HTTP_BAD_REQUEST <= status_code < _HTTP_SERVER_ERROR:
        message = f"ElevenLabs rejected the request with HTTP {status_code}"
        raise TtsInputError(message)
    message = "ElevenLabs request failed without an HTTP status"
    raise TtsProviderUnavailableError(message)


def _parse_retry_after(headers: Mapping[str, str]) -> float | None:
    raw_value: str | None = next(
        (value for key, value in headers.items() if key.casefold() == "retry-after"),
        None,
    )
    if raw_value is None:
        return None
    try:
        delay: float = float(raw_value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw_value)
        except TypeError, ValueError, OverflowError:
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        delay = (retry_at - datetime.now(UTC)).total_seconds()
    return max(0.0, delay)


def _validate_audio(audio: bytes, format_: AudioFormat) -> None:
    signatures: dict[AudioFormat, tuple[bytes, ...]] = {
        AudioFormat.MP3: (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),
        AudioFormat.OPUS: (b"OggS",),
        AudioFormat.WAV: (b"RIFF",),
    }
    expected: tuple[bytes, ...] = signatures[format_]
    if not audio or not any(audio.startswith(signature) for signature in expected):
        message: str = f"ElevenLabs returned invalid {format_.value} audio"
        raise TtsClipValidationError(message)
    if format_ is AudioFormat.WAV and (len(audio) < _WAV_HEADER_SIZE or audio[8:12] != b"WAVE"):
        message = "ElevenLabs returned invalid WAV audio"
        raise TtsClipValidationError(message)


def _write_audio(destination: Path, audio: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(audio)
