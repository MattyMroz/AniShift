"""Provider-neutral adapter for Microsoft Edge speech synthesis."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from anishift.services.tts.config import TtsConfig
from anishift.services.tts.errors import (
    TtsCancelledError,
    TtsInputError,
    TtsNetworkError,
    TtsProviderUnavailableError,
    TtsRateLimitError,
    TtsTimeoutError,
    TtsUnsupportedError,
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

from .api_backend import EdgeApiBackend, EdgeBackend
from .config import EdgeConfig
from .constants import (
    ADAPTER_VERSION,
    MAREK_VOICE_ID,
    MAX_TEXT_BYTES,
    OUTPUT_FORMAT,
    ZOFIA_VOICE_ID,
)
from .patch import ensure_edge_quality_patch
from .types import (
    EdgeAttempt,
    EdgeAudioResponse,
    EdgePatchResult,
    EdgePatchStatus,
    EdgeVoiceList,
)

__all__ = ["EdgeTtsEngine"]

type _PatchFactory = Callable[[], EdgePatchResult]
"""Callable preparing edge-tts before its runtime import."""

type _BackendFactory = Callable[[], EdgeBackend]
"""Callable loading the already-patched Edge runtime."""


class EdgeTtsEngine:
    """One-attempt adapter for the patched Microsoft Edge speech service."""

    engine_id = "edge"
    capabilities = EngineCapabilities(
        locality=EngineLocality.REMOTE,
        native_output_formats=(AudioFormat.MP3,),
        supports_concurrency=True,
        supports_native_rate=True,
        supports_native_volume=True,
        supports_pitch=True,
        supports_voice_settings=False,
        requires_api_key=False,
        min_text_chars=1,
        max_text_chars=None,
        max_text_bytes=MAX_TEXT_BYTES,
        availability_probe=AvailabilityProbeKind.REMOTE,
    )

    def __init__(
        self,
        config: TtsConfig,
        *,
        patcher: _PatchFactory = ensure_edge_quality_patch,
        backend_factory: _BackendFactory = EdgeApiBackend,
    ) -> None:
        """Resolve configuration, enforce the patch, then load the runtime."""
        self._config: EdgeConfig = EdgeConfig.from_tts_config(config)
        self._patch_result: EdgePatchResult = patcher()
        self._backend: EdgeBackend | None = backend_factory() if self._patch_result.is_ready else None
        self._closed: bool = False
        self._synthesis_profile: SynthesisProfile = SynthesisProfile(
            engine_id=self.engine_id,
            endpoint_id="microsoft-edge-readaloud-consumer",
            provider_model_id=self._config.provider_model_id,
            resolved_voice_id=self._config.voice_id,
            provider_output_id=OUTPUT_FORMAT,
            provider_source_format=AudioFormat.MP3,
            adapter_version=ADAPTER_VERSION,
            voice_settings={
                "pitch": self._config.pitch,
                "rate": self._config.rate,
                "volume": self._config.volume,
            },
        )
        self._availability: EngineAvailability = self._availability_from_patch()

    @property
    def is_available(self) -> bool:
        """Return the cached cheap projection of detailed availability."""
        return self._availability.status is AvailabilityStatus.READY and not self._closed

    @property
    def synthesis_profile(self) -> SynthesisProfile:
        """Return the fully resolved native Edge synthesis identity."""
        return self._synthesis_profile

    async def availability(self, *, live: bool = False) -> EngineAvailability:
        """Return cached patch state or probe the live voice service."""
        if not live or self._backend is None or self._closed:
            return self._availability
        try:
            voices: EdgeVoiceList = await self._backend.list_voices()
        except TtsTimeoutError:
            return self._set_availability(
                AvailabilityStatus.OFFLINE,
                "Edge availability probe timed out",
                source=AvailabilitySource.LIVE,
            )
        except TtsNetworkError:
            return self._set_availability(
                AvailabilityStatus.OFFLINE,
                "Edge network is unavailable",
                source=AvailabilitySource.LIVE,
            )
        except TtsProviderUnavailableError, TtsRateLimitError:
            return self._set_availability(
                AvailabilityStatus.SERVICE_UNAVAILABLE,
                "Edge service is unavailable",
                source=AvailabilitySource.LIVE,
            )
        if not any(voice.id == self._config.voice_id for voice in voices):
            return self._set_availability(
                AvailabilityStatus.MISSING_VOICE,
                f"Edge voice is unavailable: {self._config.voice_id}",
                source=AvailabilitySource.LIVE,
                voices=voices,
            )
        return self._set_availability(
            AvailabilityStatus.READY,
            "Edge is ready",
            source=AvailabilitySource.LIVE,
            voices=voices,
        )

    async def list_voices(self) -> tuple[VoiceInfo, ...]:
        """Return the current provider voice list."""
        backend: EdgeBackend = self._require_backend()
        voices: EdgeVoiceList = await backend.list_voices()
        return voices

    async def synthesize(
        self,
        request: SynthesisRequest,
        *,
        cancel: CancellationToken,
    ) -> EngineClipResult:
        """Synthesize one request without retry or shared lifecycle work."""
        self._validate_request(request)
        if cancel.is_cancelled:
            message: str = "Edge synthesis cancelled before request"
            raise TtsCancelledError(message)
        backend: EdgeBackend = self._require_backend()
        response: EdgeAudioResponse = await backend.synthesize_once(
            EdgeAttempt(
                text=request.text,
                voice_id=request.voice_id,
                rate=self._config.rate,
                volume=self._config.volume,
                pitch=self._config.pitch,
                deadline_s=request.deadline_s,
            ),
        )
        if cancel.is_cancelled:
            message = "Edge synthesis cancelled before write"
            raise TtsCancelledError(message)
        _write_audio(request.destination, response.audio)
        return EngineClipResult(
            request_id=request.request_id,
            path=request.destination,
            format=response.format,
            engine_id=self.engine_id,
            provider_model_id=self._config.provider_model_id,
            voice_id=request.voice_id,
            request_time_ms=response.request_time_ms,
        )

    async def close(self) -> None:
        """Close the Edge runtime boundary once."""
        if self._closed:
            return
        if self._backend is not None:
            await self._backend.close()
        self._closed = True
        self._set_availability(
            AvailabilityStatus.SERVICE_UNAVAILABLE,
            "Edge engine is closed",
            source=AvailabilitySource.CACHED,
        )

    def _validate_request(self, request: SynthesisRequest) -> None:
        if not request.text or len(request.text.encode("utf-8")) > MAX_TEXT_BYTES:
            message: str = f"Edge text must contain 1 to {MAX_TEXT_BYTES} UTF-8 bytes"
            raise TtsInputError(message)
        if request.provider_model_id.casefold() != self._config.provider_model_id:
            message = "Edge request model differs from engine configuration"
            raise TtsUnsupportedError(message)
        if request.voice_id != self._config.voice_id:
            message = "Edge request voice differs from engine configuration"
            raise TtsUnsupportedError(message)
        expected_native: tuple[str | float | None, ...] = (
            request.native_rate,
            request.native_volume,
            request.native_pitch,
        )
        configured_native: tuple[str, ...] = (
            self._config.rate,
            self._config.volume,
            self._config.pitch,
        )
        if any(value is not None for value in expected_native) and expected_native != configured_native:
            message = "Edge request native settings differ from engine configuration"
            raise TtsUnsupportedError(message)
        if request.options:
            message = "Edge request options must use dedicated native fields"
            raise TtsUnsupportedError(message)

    def _require_backend(self) -> EdgeBackend:
        if self._backend is not None and not self._closed:
            return self._backend
        raise TtsProviderUnavailableError(self._patch_result.message)

    def _availability_from_patch(self) -> EngineAvailability:
        if self._patch_result.status is EdgePatchStatus.PACKAGE_MISSING:
            status: AvailabilityStatus = AvailabilityStatus.MISSING_BINARY
        elif self._patch_result.is_ready:
            status = AvailabilityStatus.READY
        else:
            status = AvailabilityStatus.SERVICE_UNAVAILABLE
        return EngineAvailability(
            status=status,
            message=self._patch_result.message,
            checked_at=datetime.now(UTC),
            source=AvailabilitySource.LOCAL,
            voices=_builtin_polish_voices(),
        )

    def _set_availability(
        self,
        status: AvailabilityStatus,
        message: str,
        *,
        source: AvailabilitySource,
        voices: tuple[VoiceInfo, ...] | None = None,
    ) -> EngineAvailability:
        self._availability = EngineAvailability(
            status=status,
            message=message,
            checked_at=datetime.now(UTC),
            source=source,
            voices=voices if voices is not None else _builtin_polish_voices(),
        )
        return self._availability


def _builtin_polish_voices() -> tuple[VoiceInfo, ...]:
    return (
        VoiceInfo(
            id=MAREK_VOICE_ID,
            label="Marek",
            engine_id="edge",
            language="pl-PL",
            gender="Male",
        ),
        VoiceInfo(
            id=ZOFIA_VOICE_ID,
            label="Zofia",
            engine_id="edge",
            language="pl-PL",
            gender="Female",
        ),
    )


def _write_audio(destination: Path, audio: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(audio)
