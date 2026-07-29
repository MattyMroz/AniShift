"""Architecture-aware Windows SAPI engine adapter."""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Never, Protocol

from anishift.services.tts.cancellation import TtsCancellation
from anishift.services.tts.config import TtsConfig
from anishift.services.tts.errors import (
    TtsCancelledError,
    TtsClipValidationError,
    TtsInputError,
    TtsProviderUnavailableError,
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
    ProcessArchitecture,
    SynthesisRequest,
    VoiceInfo,
)

from .config import SapiConfig, resolve_voice_profile
from .constants import ADAPTER_VERSION, OUTPUT_ID, WAV_ENVELOPE_BYTES, WAV_HEADER_BYTES
from .types import SapiSynthesisResult, SapiVoiceRecord
from .worker import PowerShellSapiVoiceProbe, SapiVoiceProbe, SapiWorkerController

__all__ = ["SapiRuntime", "SapiTtsEngine"]


class SapiController(Protocol):
    """Persistent worker operations consumed by the engine adapter."""

    async def synthesize(
        self,
        request_id: str,
        text: str,
        output_path: Path,
        *,
        deadline_s: float,
        cancel: CancellationToken,
    ) -> SapiSynthesisResult:
        """Synthesize one sequential request."""
        ...

    async def close(self) -> None:
        """Release the worker process."""
        ...


@dataclass(frozen=True, slots=True)
class SapiRuntime:
    """Injected local runtime boundaries for deterministic construction."""

    platform_name: str | None = None
    windows_dir: Path | None = None
    worker_asset: Path | None = None
    controller: SapiController | None = None
    live_controller: SapiController | None = None
    voice_probe: SapiVoiceProbe | None = None


class SapiTtsEngine:
    """Local SAPI adapter with passive voice discovery and one worker."""

    engine_id = "sapi"
    capabilities = EngineCapabilities(
        locality=EngineLocality.SYSTEM,
        native_output_formats=(AudioFormat.WAV,),
        supports_concurrency=False,
        supports_native_rate=True,
        supports_native_volume=True,
        supports_pitch=False,
        supports_voice_settings=False,
        requires_api_key=False,
        min_text_chars=1,
        max_text_chars=None,
        max_text_bytes=None,
        availability_probe=AvailabilityProbeKind.LOCAL,
    )

    def __init__(
        self,
        config: TtsConfig,
        *,
        runtime: SapiRuntime | None = None,
    ) -> None:
        """Resolve hosts and profiles without starting COM or PowerShell."""
        resolved_runtime: SapiRuntime = runtime or SapiRuntime()
        self._config: SapiConfig = SapiConfig.from_tts_config(
            config,
            platform_name=resolved_runtime.platform_name,
            windows_dir=resolved_runtime.windows_dir,
            worker_asset=resolved_runtime.worker_asset,
        )
        self._controller: SapiController | None = resolved_runtime.controller
        self._live_controller: SapiController | None = resolved_runtime.live_controller
        self._voice_probe: SapiVoiceProbe = resolved_runtime.voice_probe or PowerShellSapiVoiceProbe()
        self._voices: tuple[VoiceInfo, ...] | None = None
        self._probe_lock: asyncio.Lock = asyncio.Lock()
        self._closed: bool = False
        self._synthesis_profile: SynthesisProfile = SynthesisProfile(
            engine_id=self.engine_id,
            endpoint_id=f"windows-sapi5-{self._config.profile.architecture.value}",
            provider_model_id=self._config.provider_model_id,
            resolved_voice_id=self._config.profile.resolved_voice_id,
            provider_output_id=OUTPUT_ID,
            provider_source_format=AudioFormat.WAV,
            adapter_version=ADAPTER_VERSION,
            native_rate=float(self._config.native_rate),
            native_volume=float(self._config.native_volume),
        )
        self._availability: EngineAvailability = self._initial_availability()

    @property
    def is_available(self) -> bool:
        """Return the cached cheap projection of detailed availability."""
        return self._availability.status is AvailabilityStatus.READY and not self._closed

    @property
    def synthesis_profile(self) -> SynthesisProfile:
        """Return the resolved architecture-specific synthesis identity."""
        return self._synthesis_profile

    async def availability(self, *, live: bool = False) -> EngineAvailability:
        """Enumerate voices and optionally run one isolated synthesis probe."""
        if self._closed or not self._can_probe:
            return self._availability
        async with self._probe_lock:
            if self._voices is None:
                passive: EngineAvailability = await self._probe_voices()
                if passive.status is not AvailabilityStatus.READY:
                    return passive
            if not live:
                return self._availability
            try:
                await self._run_live_probe()
            except TtsTimeoutError:
                return self._set_availability(
                    AvailabilityStatus.SERVICE_UNAVAILABLE,
                    "SAPI live synthesis probe timed out",
                    source=AvailabilitySource.LIVE,
                )
            except TtsProviderUnavailableError, TtsClipValidationError:
                return self._set_availability(
                    AvailabilityStatus.SERVICE_UNAVAILABLE,
                    "SAPI live synthesis probe failed",
                    source=AvailabilitySource.LIVE,
                )
            return self._set_availability(
                AvailabilityStatus.READY,
                "SAPI live synthesis probe succeeded",
                source=AvailabilitySource.LIVE,
            )

    async def list_voices(self) -> tuple[VoiceInfo, ...]:
        """Return voices enumerated independently by x64 and x86 hosts."""
        if self._closed:
            _raise_unavailable("SAPI engine is closed")
        if not self._can_probe:
            _raise_unavailable(self._availability.message)
        availability: EngineAvailability = await self.availability()
        if availability.status is AvailabilityStatus.SERVICE_UNAVAILABLE:
            raise TtsProviderUnavailableError(availability.message)
        return availability.voices

    async def synthesize(
        self,
        request: SynthesisRequest,
        *,
        cancel: CancellationToken,
    ) -> EngineClipResult:
        """Synthesize one request through the persistent sequential worker."""
        self._validate_request(request)
        destination: Path = _validate_destination(request.destination)
        if cancel.is_cancelled:
            _raise_cancelled("SAPI synthesis cancelled before request")
        availability: EngineAvailability = await self.availability()
        if availability.status is not AvailabilityStatus.READY:
            raise TtsProviderUnavailableError(availability.message)
        controller: SapiController = self._require_controller()
        result: SapiSynthesisResult = await controller.synthesize(
            request.request_id,
            request.text,
            destination,
            deadline_s=request.deadline_s,
            cancel=cancel,
        )
        if cancel.is_cancelled:
            _raise_cancelled("SAPI synthesis cancelled before validation")
        _validate_wav_envelope(result.output_path)
        return EngineClipResult(
            request_id=request.request_id,
            path=result.output_path,
            format=AudioFormat.WAV,
            engine_id=self.engine_id,
            provider_model_id=self._config.provider_model_id,
            voice_id=self._config.profile.resolved_voice_id,
            request_time_ms=result.request_time_ms,
        )

    async def close(self) -> None:
        """Close the persistent worker once."""
        if self._closed:
            return
        self._closed = True
        if self._controller is not None:
            await self._controller.close()
        self._set_availability(
            AvailabilityStatus.SERVICE_UNAVAILABLE,
            "SAPI engine is closed",
            source=AvailabilitySource.CACHED,
        )

    @property
    def _can_probe(self) -> bool:
        return (
            self._config.platform_supported
            and bool(self._config.hosts)
            and self._config.host is not None
            and self._config.worker_asset.is_file()
        )

    async def _enumerate_voices(self) -> tuple[VoiceInfo, ...]:
        records: list[SapiVoiceRecord] = []
        for host in self._config.hosts:
            host_records: tuple[SapiVoiceRecord, ...] = await self._voice_probe.list_voices(
                host,
                self._config.worker_asset,
                timeout_s=self._config.request_timeout_s,
            )
            records.extend(host_records)
        return tuple(
            VoiceInfo(
                id=f"{record.name}@{record.architecture.value}",
                label=record.name,
                engine_id=self.engine_id,
                language="pl-PL",
                architecture=record.architecture,
            )
            for record in records
        )

    async def _probe_voices(self) -> EngineAvailability:
        try:
            voices: tuple[VoiceInfo, ...] = await self._enumerate_voices()
        except TtsTimeoutError:
            return self._set_availability(
                AvailabilityStatus.SERVICE_UNAVAILABLE,
                "SAPI passive voice probe timed out",
            )
        except TtsProviderUnavailableError:
            return self._set_availability(
                AvailabilityStatus.SERVICE_UNAVAILABLE,
                "SAPI passive voice probe failed",
            )
        self._voices = voices
        expected_name: str = self._config.profile.voice_name
        expected_architecture: ProcessArchitecture = self._config.profile.architecture
        if any(
            voice.label.casefold() == expected_name.casefold() and voice.architecture is expected_architecture
            for voice in voices
        ):
            return self._set_availability(
                AvailabilityStatus.READY,
                "SAPI is ready",
                voices=voices,
            )
        wrong_architecture: bool = any(
            voice.label.casefold() == expected_name.casefold() and voice.architecture is not expected_architecture
            for voice in voices
        )
        detail: str = " in the wrong process architecture" if wrong_architecture else ""
        return self._set_availability(
            AvailabilityStatus.MISSING_VOICE,
            f"SAPI voice is unavailable{detail}: {expected_name}",
            voices=voices,
        )

    async def _run_live_probe(self) -> None:
        controller: SapiController = self._live_controller or SapiWorkerController(
            self._config,
        )
        cancellation = TtsCancellation()
        try:
            with tempfile.TemporaryDirectory(prefix="anishift-sapi-live-") as directory:
                output_path: Path = Path(directory) / "probe.wav"
                result: SapiSynthesisResult = await controller.synthesize(
                    "sapi-live-probe",
                    "Test.",
                    output_path,
                    deadline_s=self._config.request_timeout_s,
                    cancel=cancellation,
                )
                _validate_wav_envelope(result.output_path)
        finally:
            await controller.close()

    def _validate_request(self, request: SynthesisRequest) -> None:
        if not request.text:
            _raise_input("SAPI text cannot be empty")
        if request.provider_model_id.casefold() != self._config.provider_model_id.casefold():
            _raise_unsupported("SAPI request model differs from engine configuration")
        requested_profile = resolve_voice_profile(request.voice_id)
        if requested_profile is not self._config.profile:
            _raise_unsupported("SAPI request voice differs from engine configuration")
        if request.native_pitch is not None or request.options:
            _raise_unsupported("SAPI does not accept pitch or provider-specific options")
        if request.native_rate is not None and request.native_rate != self._config.native_rate:
            _raise_unsupported("SAPI request rate differs from engine configuration")
        if request.native_volume is not None and request.native_volume != self._config.native_volume:
            _raise_unsupported("SAPI request volume differs from engine configuration")

    def _require_controller(self) -> SapiController:
        if self._closed:
            _raise_unavailable("SAPI engine is closed")
        if self._controller is None:
            self._controller = SapiWorkerController(self._config)
        return self._controller

    def _initial_availability(self) -> EngineAvailability:
        if not self._config.platform_supported:
            status: AvailabilityStatus = AvailabilityStatus.UNSUPPORTED_PLATFORM
            message: str = "SAPI is available only on Windows"
        elif not self._config.worker_asset.is_file():
            status = AvailabilityStatus.MISSING_BINARY
            message = "Packaged SAPI worker asset is missing"
        elif self._config.host is None:
            status = AvailabilityStatus.MISSING_BINARY
            architecture: str = self._config.profile.architecture.value
            message = f"SAPI {architecture} PowerShell host is missing"
        else:
            status = AvailabilityStatus.READY
            message = "SAPI configured; passive voice probe pending"
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
        source: AvailabilitySource = AvailabilitySource.LOCAL,
        voices: tuple[VoiceInfo, ...] | None = None,
    ) -> EngineAvailability:
        self._availability = EngineAvailability(
            status=status,
            message=message,
            checked_at=datetime.now(UTC),
            source=source,
            voices=voices if voices is not None else self._voices or (),
        )
        return self._availability


def _validate_destination(destination: Path) -> Path:
    lexical: Path = destination.absolute()
    parent: Path = lexical.parent
    if (
        parent.name != "clips"
        or not lexical.name.startswith(".clip-")
        or not lexical.name.endswith(".wav.tmp")
        or not lexical.exists()
        or not lexical.is_file()
        or lexical.is_symlink()
        or parent.is_symlink()
        or parent.is_junction()
    ):
        _raise_input("SAPI destination is not an owned WAV temporary clip")
    resolved_parent: Path = parent.resolve()
    resolved: Path = lexical.resolve()
    try:
        resolved.relative_to(resolved_parent)
    except ValueError as error:
        message: str = "SAPI destination escapes the owned clips directory"
        raise TtsInputError(message) from error
    if resolved.stat().st_size != 0:
        _raise_input("SAPI destination must be an empty reserved temporary clip")
    return resolved


def _validate_wav_envelope(path: Path) -> None:
    try:
        size: int = path.stat().st_size
        with path.open("rb") as stream:
            header: bytes = stream.read(WAV_ENVELOPE_BYTES)
    except OSError as error:
        message: str = "SAPI WAV output cannot be read"
        raise TtsClipValidationError(message) from error
    if size <= WAV_HEADER_BYTES or len(header) < WAV_ENVELOPE_BYTES or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        _raise_invalid_clip("SAPI returned an empty or invalid WAV envelope")


def _raise_cancelled(message: str) -> Never:
    raise TtsCancelledError(message)


def _raise_input(message: str) -> Never:
    raise TtsInputError(message)


def _raise_invalid_clip(message: str) -> Never:
    raise TtsClipValidationError(message)


def _raise_unavailable(message: str) -> Never:
    raise TtsProviderUnavailableError(message)


def _raise_unsupported(message: str) -> Never:
    raise TtsUnsupportedError(message)
