"""ElevenBytes engine adapter for the provider-neutral TTS contract."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from anishift.errors import ErrorCode, ErrorContext
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

from .api_backend import ElevenBytesApiBackend
from .config import ElevenBytesConfig, resolve_voice_id
from .constants import DALLIN_LABEL, DALLIN_VOICE_ID, MAX_TEXT_CHARS

__all__ = ["ElevenBytesTtsEngine"]


class ElevenBytesTtsEngine:
    """One-attempt adapter for the public ElevenBytes proxy."""

    engine_id = "elevenbytes"
    capabilities = EngineCapabilities(
        locality=EngineLocality.REMOTE,
        native_output_formats=(AudioFormat.MP3,),
        supports_concurrency=True,
        supports_native_rate=False,
        supports_native_volume=False,
        supports_pitch=False,
        supports_voice_settings=True,
        requires_api_key=False,
        min_text_chars=1,
        max_text_chars=MAX_TEXT_CHARS,
        max_text_bytes=None,
        availability_probe=AvailabilityProbeKind.REMOTE,
    )

    def __init__(
        self,
        config: TtsConfig,
        *,
        backend: ElevenBytesApiBackend | None = None,
    ) -> None:
        """Resolve provider configuration without performing network I/O."""
        self._config: ElevenBytesConfig = ElevenBytesConfig.from_tts_config(config)
        self._backend: ElevenBytesApiBackend = backend or ElevenBytesApiBackend(self._config)
        self._synthesis_profile: SynthesisProfile = SynthesisProfile(
            engine_id=self.engine_id,
            endpoint_id=f"teamsp-elevenbytes-{self._config.endpoint_variant}",
            provider_model_id=self._config.endpoint_variant,
            resolved_voice_id=self._config.voice_id,
            provider_output_id="mp3",
            provider_source_format=AudioFormat.MP3,
            adapter_version="elevenbytes-v1",
            voice_settings=self._request_options,
        )
        self._availability: EngineAvailability = self._build_availability(
            AvailabilityStatus.READY,
            "ElevenBytes configured",
            source=AvailabilitySource.CONFIG,
        )

    @property
    def is_available(self) -> bool:
        """Return the cached cheap projection of detailed availability."""
        return self._availability.status is AvailabilityStatus.READY and not self._backend.is_closed

    @property
    def synthesis_profile(self) -> SynthesisProfile:
        """Return the fully resolved native MP3 synthesis identity."""
        return self._synthesis_profile

    async def availability(self, *, live: bool = False) -> EngineAvailability:
        """Return cached state or perform a lightweight reachability probe."""
        if not live:
            return self._availability
        try:
            await self._backend.probe()
        except TtsTimeoutError:
            status: AvailabilityStatus = AvailabilityStatus.OFFLINE
            message: str = "ElevenBytes availability probe timed out"
        except TtsNetworkError:
            status = AvailabilityStatus.OFFLINE
            message = "ElevenBytes network is unavailable"
        except TtsProviderUnavailableError, TtsRateLimitError:
            status = AvailabilityStatus.SERVICE_UNAVAILABLE
            message = "ElevenBytes service is unavailable"
        else:
            status = AvailabilityStatus.READY
            message = "ElevenBytes is ready"
        self._availability = self._build_availability(
            status,
            message,
            source=AvailabilitySource.LIVE,
        )
        return self._availability

    async def list_voices(self) -> tuple[VoiceInfo, ...]:
        """Return the built-in voice for the selected endpoint variant."""
        return (
            VoiceInfo(
                id=DALLIN_VOICE_ID,
                label=DALLIN_LABEL,
                engine_id=self.engine_id,
                language="pl",
                experimental=self._config.is_experimental,
            ),
        )

    async def synthesize(
        self,
        request: SynthesisRequest,
        *,
        cancel: CancellationToken,
    ) -> EngineClipResult:
        """Synthesize one request without retry or shared lifecycle work."""
        self._validate_request(request)
        if cancel.is_cancelled:
            message: str = "ElevenBytes synthesis cancelled before request"
            raise TtsCancelledError(message)
        voice_id: str = resolve_voice_id(request.voice_id)
        response = await self._backend.synthesize_once(
            request.text,
            voice_id,
            deadline_s=request.deadline_s,
        )
        if cancel.is_cancelled:
            message = "ElevenBytes synthesis cancelled before write"
            raise TtsCancelledError(message)
        _write_audio(request.destination, response.audio)
        return EngineClipResult(
            request_id=request.request_id,
            path=request.destination,
            format=response.format,
            engine_id=self.engine_id,
            provider_model_id=self._config.endpoint_variant,
            voice_id=voice_id,
            request_time_ms=response.request_time_ms,
        )

    async def close(self) -> None:
        """Release the shared HTTP client."""
        await self._backend.close()
        self._availability = self._build_availability(
            AvailabilityStatus.SERVICE_UNAVAILABLE,
            "ElevenBytes engine is closed",
            source=AvailabilitySource.CACHED,
        )

    def _validate_request(self, request: SynthesisRequest) -> None:
        if not request.text or len(request.text) > MAX_TEXT_CHARS:
            text_context: ErrorContext = ErrorContext(
                code=ErrorCode.TTS_INPUT_INVALID,
                message=f"ElevenBytes text must contain 1 to {MAX_TEXT_CHARS} characters",
                suggestion="Validate and chunk neutral speech text before engine dispatch.",
            )
            raise TtsInputError(context=text_context)
        if request.provider_model_id.casefold() != self._config.endpoint_variant:
            model_context: ErrorContext = ErrorContext(
                code=ErrorCode.TTS_INPUT_INVALID,
                message="ElevenBytes request variant differs from engine configuration",
                suggestion="Use one configured endpoint variant for the service lifecycle.",
            )
            raise TtsInputError(context=model_context)
        if any(value is not None for value in (request.native_rate, request.native_volume, request.native_pitch)):
            message: str = "ElevenBytes does not support native rate, volume, or pitch"
            raise TtsUnsupportedError(message)
        if request.options and dict(request.options) != self._request_options:
            message = "ElevenBytes request options differ from engine configuration"
            raise TtsUnsupportedError(message)

    @property
    def _request_options(self) -> dict[str, str | float | bool]:
        if self._config.run7_settings is None:
            return {}
        settings = self._config.run7_settings
        return {
            "similarity_boost": settings.similarity_boost,
            "stability": settings.stability,
            "style": settings.style,
            "use_speaker_boost": settings.use_speaker_boost,
        }

    def _build_availability(
        self,
        status: AvailabilityStatus,
        message: str,
        *,
        source: AvailabilitySource,
    ) -> EngineAvailability:
        return EngineAvailability(
            status=status,
            message=message,
            checked_at=datetime.now(UTC),
            source=source,
            voices=(
                VoiceInfo(
                    id=DALLIN_VOICE_ID,
                    label=DALLIN_LABEL,
                    engine_id=self.engine_id,
                    language="pl",
                    experimental=self._config.is_experimental,
                ),
            ),
        )


def _write_audio(destination: Path, audio: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(audio)
