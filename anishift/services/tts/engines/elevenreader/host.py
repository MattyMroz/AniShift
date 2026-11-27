"""What AniShift gives the ElevenReader engine: errors, texts, platform, MP3 decoding and the TTS engine surface."""

from __future__ import annotations

import errno
import subprocess
from array import array
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.platform.binaries import Binary, BinaryNotFoundError, require_binary
from anishift.platform.child_processes import independent_child_flags
from anishift.platform.installed import find_installed
from anishift.platform.private_dir import PrivateDirectoryError, restrict_directory
from anishift.platform.process_lock import ProcessLock
from anishift.services.tts.artifacts import atomic_json_snapshot
from anishift.services.tts.cancellation import TtsCancellation as Cancellation
from anishift.services.tts.errors import (
    TtsAuthError,
    TtsCancelledError,
    TtsClipValidationError,
    TtsConfigError,
    TtsError,
    TtsInputError,
    TtsProviderUnavailableError,
    TtsQuotaError,
    TtsRateLimitError,
    TtsTimeoutError,
    TtsUnsupportedError,
    TtsVoiceError,
)
from anishift.services.tts.fingerprint import SynthesisProfile
from anishift.services.tts.types import (
    AudioFormat,
    AvailabilityProbeKind,
    AvailabilitySource,
    AvailabilityStatus,
    DocumentPart,
    DocumentSynthesisRequest,
    EngineAvailability,
    EngineCapabilities,
    EngineDocumentResult,
    EngineLocality,
    PartTiming,
    VoiceInfo,
)
from anishift.utils.logger import get_logger
from anishift.utils.mp3_frames import FrameHeader, cut_before_ms, frames_duration_ms, iter_frames, splice_times
from anishift.utils.pauses import (
    ENVELOPE_RATE,
    FRAME_MS,
    NOISE_DBFS,
    LineSpan,
    best_pause,
    frame_levels,
    server_frame_times,
    silent_cut,
)

from .constants import MAX_PARALLEL_DOCUMENTS, PROVIDER_MODEL_ID, UNAVAILABLE_RETRY_S, VOICES
from .types import Redo

if TYPE_CHECKING:
    from pathlib import Path

    from anishift.services.tts.config import TtsConfig
    from anishift.services.tts.protocols import CancellationToken
    from anishift.services.tts.types import EngineClipResult, SynthesisRequest

    from .config import ElevenReaderConfig
    from .types import AlignmentChunk, SessionRecord

__all__ = [
    "ACCOUNT_BLOCKED_HINT",
    "CHROME_MISSING_HINT",
    "CLEANUP_WARNING",
    "ENVELOPE_RATE",
    "FALLBACK_HINT",
    "FRAME_MS",
    "INPUT_HINT",
    "NAME",
    "NOISE_DBFS",
    "PART_HINT",
    "PROFILE_BUSY_HINT",
    "PROFILE_HINT",
    "QUOTA_HINT",
    "REFUSED_HINT",
    "REFUSED_MESSAGE",
    "SIGN_IN_HINT",
    "UNKNOWN_VOICE_HINT",
    "VOICE_HINT",
    "WRITE_HINT",
    "Cancellation",
    "CancellationToken",
    "ChromeBusyError",
    "ChromeMissingError",
    "DocumentPart",
    "DocumentResult",
    "DocumentSynthesisRequest",
    "EngineSettings",
    "EngineSurface",
    "ErrorCode",
    "ErrorContext",
    "FrameHeader",
    "LineSpan",
    "PartTiming",
    "PrivateDirectoryError",
    "ProcessLock",
    "TtsAuthError",
    "TtsCancelledError",
    "TtsClipValidationError",
    "TtsConfigError",
    "TtsError",
    "TtsInputError",
    "TtsProviderUnavailableError",
    "TtsQuotaError",
    "TtsRateLimitError",
    "TtsTimeoutError",
    "TtsVoiceError",
    "atomic_json_snapshot",
    "best_pause",
    "busy_error",
    "check_request",
    "cut_before_ms",
    "document_result",
    "engine_config",
    "find_installed",
    "frame_levels",
    "frames_duration_ms",
    "get_logger",
    "independent_child_flags",
    "iter_frames",
    "keeps_tags",
    "mono_pcm",
    "restrict_directory",
    "server_frame_times",
    "silent_cut",
    "splice_times",
]

# ── Constants ─────────────────────────────────────────────────────────────────

NAME: Final[str] = "anishift"
"""Program name in the uploaded file name, temporary folders and the host thread."""

FALLBACK_HINT: Final[str] = "Albo przełącz silnik na ElevenBytes w Ustawienia → Lektor."
"""Closing sentence of the permanent-failure suggestions, except the browser refusal."""

SIGN_IN_HINT: Final[str] = f"Zaloguj się w oknie z Ustawienia → Lektor → Zaloguj (otwórz okno Chrome). {FALLBACK_HINT}"
"""Suggestion for a signed-out or rejected session."""

ACCOUNT_BLOCKED_HINT: Final[str] = f"Konto ElevenReader mogło zostać zablokowane. {FALLBACK_HINT}"
"""Suggestion when the account refuses access."""

QUOTA_HINT: Final[str] = f"Poczekaj na odnowienie kredytów ElevenReader. {FALLBACK_HINT}"
"""Suggestion when the account has no credits left."""

REFUSED_MESSAGE: Final[str] = "ElevenReader odrzucił przeglądarkę AniShift"
"""Message of the permanent App Check refusal; the panel shows it, so it is Polish."""

REFUSED_HINT: Final[str] = (
    "Blokada trwa dobę. W Ustawienia → Lektor użyj Wyloguj (usuń ciasteczka ElevenReadera), potem "
    "Zaloguj (otwórz okno Chrome) i zaloguj się w otwartym oknie; albo spróbuj ponownie po dobie, albo "
    "wybierz inny silnik lektora."
)
"""Suggestion after the App Check refusal."""

VOICE_HINT: Final[str] = f"Wybierz głos Piotr Fronczewski albo Adam w Ustawienia → Lektor. {FALLBACK_HINT}"
"""Suggestion when the account did not take the voice or reading speed."""

UNKNOWN_VOICE_HINT: Final[str] = "Wybierz głos Piotr Fronczewski albo Adam w Ustawienia → Lektor."
"""Suggestion for an unknown voice."""

CHROME_MISSING_HINT: Final[str] = f"Zainstaluj Google Chrome (winget install Google.Chrome). {FALLBACK_HINT}"
"""Suggestion when Google Chrome is not installed."""

PROFILE_BUSY_HINT: Final[str] = "Zamknij okno ElevenReadera w Chrome i spróbuj ponownie."
"""Suggestion when another browser uses the profile."""

PROFILE_HINT: Final[str] = f"Sprawdź uprawnienia katalogu config/elevenreader. {FALLBACK_HINT}"
"""Suggestion when the profile directory cannot be prepared."""

WRITE_HINT: Final[str] = "Sprawdź wolne miejsce i uprawnienia dysku z workspace."
"""Suggestion when a recording cannot be written."""

INPUT_HINT: Final[str] = "Use one configured ElevenReader voice and model for the service lifecycle."
"""Suggestion for a document the engine refuses."""

PART_HINT: Final[str] = "Kwestia nie może być pusta, samym „…” ani zawierać znacznika <break>."
"""Suggestion for a part that cannot be its own paragraph."""

CLEANUP_WARNING: Final[str] = (
    "ElevenReader: nie udało się posprzątać konta — usuń z biblioteki ostatni dokument wgrany przez AniShift "
    "(jego tytuł to pierwsze zdanie odcinka) i sprawdź głos w aplikacji"
)
"""Owner-facing warning left when account cleanup failed for good."""

_DECODE_TIMEOUT_S: Final[float] = 300.0
"""Longest decode of one take; the same limit as the clip splitter's whole-recording decode in the runtime."""

type DocumentResult = EngineDocumentResult
"""Result type of one document in the TTS service."""

type EngineSettings = TtsConfig
"""What the engine is built from: the TTS configuration."""


class ChromeMissingError(TtsConfigError):
    """Google Chrome is not installed in a standard location or on ``PATH``."""


class ChromeBusyError(TtsProviderUnavailableError):
    """Another browser already uses the ElevenReader profile."""


class EngineSurface:
    """The TTS engine protocol around the ElevenReader engine: identity, capabilities, availability and voices."""

    engine_id = "elevenreader"
    capabilities = EngineCapabilities(
        locality=EngineLocality.REMOTE,
        native_output_formats=(AudioFormat.MP3,),
        supports_concurrency=True,
        supports_native_rate=False,
        supports_native_volume=False,
        supports_pitch=False,
        supports_voice_settings=False,
        requires_api_key=False,
        min_text_chars=1,
        max_text_chars=None,
        max_text_bytes=None,
        availability_probe=AvailabilityProbeKind.LOCAL,
        reads_documents=True,
    )
    _config: ElevenReaderConfig
    _closed: bool
    _synthesis_profile: SynthesisProfile
    _availability: EngineAvailability

    @property
    def is_available(self) -> bool:
        """Return the cached cheap projection of detailed availability."""
        return self._availability.status is AvailabilityStatus.READY and not self._closed

    @property
    def synthesis_profile(self) -> SynthesisProfile:
        """Return the resolved identity of the cut WAV clips."""
        return self._synthesis_profile

    async def availability(self, *, live: bool = False) -> EngineAvailability:
        """Report whether Chrome is installed; *live* also reads the last saved session check."""
        from .api_backend import read_session  # noqa: PLC0415 - api_backend imports this module

        self._availability = self._chrome_availability(AvailabilitySource.LIVE if live else AvailabilitySource.LOCAL)
        if not live or self._availability.status is not AvailabilityStatus.READY:
            return self._availability
        record: SessionRecord | None = read_session(self._config.profile_root)
        if record is None or not record.signed_in:
            self._availability = _availability(
                AvailabilityStatus.MISSING_KEY, "ElevenReader session is not signed in", AvailabilitySource.LIVE
            )
        return self._availability

    async def list_voices(self) -> tuple[VoiceInfo, ...]:
        """Return the offered ElevenReader voices."""
        return _voices()

    async def synthesize(self, request: SynthesisRequest, *, cancel: CancellationToken) -> EngineClipResult:
        """Refuse a single request; ElevenReader reads documents only."""
        del request, cancel
        message: str = "ElevenReader reads whole documents only"
        raise TtsUnsupportedError(message)

    def _attach_host(self) -> None:
        """Resolve the synthesis profile and the first availability check."""
        self._synthesis_profile = SynthesisProfile(
            engine_id=self.engine_id,
            endpoint_id="elevenreader-web-stream-v2",
            provider_model_id=PROVIDER_MODEL_ID,
            resolved_voice_id=self._config.voice.voice_id,
            provider_output_id="pcm_s16le_48000_cut",
            provider_source_format=AudioFormat.WAV,
            adapter_version="elevenreader-v1",
            voice_settings={"reading_speed": "1", "document_layout": "line_separator_paragraph"},
        )
        self._availability = self._chrome_availability(AvailabilitySource.LOCAL)

    def _chrome_availability(self, source: AvailabilitySource) -> EngineAvailability:
        from .config import find_chrome  # noqa: PLC0415 - config imports this module

        if find_chrome() is None:
            return _availability(AvailabilityStatus.MISSING_BINARY, "Google Chrome is not installed", source)
        return _availability(AvailabilityStatus.READY, "ElevenReader is ready", source)


def engine_config(settings: EngineSettings) -> ElevenReaderConfig:
    """Resolve voice and profile from the TTS configuration, refusing what ElevenReader cannot honour; redo by line."""
    from .config import ElevenReaderConfig, resolve_voice  # noqa: PLC0415 - config imports this module

    if settings.provider_model_id.strip().casefold() != PROVIDER_MODEL_ID:
        _raise_config_error(f"ElevenReader reads only with {PROVIDER_MODEL_ID}", field_name="provider_model_id")
    if not 1 <= settings.max_concurrency <= MAX_PARALLEL_DOCUMENTS:
        _raise_config_error(
            f"ElevenReader records 1 to {MAX_PARALLEL_DOCUMENTS} documents at a time", field_name="max_concurrency"
        )
    if settings.engine_options:
        _raise_config_error("ElevenReader accepts no engine options", field_name="engine_options")
    if settings.elevenreader_profile_root is None:
        _raise_config_error("ElevenReader needs a browser profile directory", field_name="elevenreader_profile_root")
    return ElevenReaderConfig(
        voice=resolve_voice(settings.voice_id), profile_root=settings.elevenreader_profile_root, redo=Redo.LINE
    )


def check_request(request: DocumentSynthesisRequest) -> None:
    """Refuse a request for another model or with engine options."""
    if request.provider_model_id.strip().casefold() != PROVIDER_MODEL_ID:
        context: ErrorContext = ErrorContext(
            code=ErrorCode.TTS_INPUT_INVALID,
            message=f"ElevenReader reads only with {PROVIDER_MODEL_ID}",
            suggestion=INPUT_HINT,
        )
        raise TtsInputError(context=context)
    if request.options:
        message: str = "ElevenReader accepts no engine options"
        raise TtsUnsupportedError(message)


def keeps_tags(request: DocumentSynthesisRequest) -> bool:
    """Tell whether square brackets go to the server as audio tags; AniShift never sends them."""
    del request
    return False


def document_result(  # noqa: PLR0913 - every field of one recorded document
    *,
    request_id: str,
    recording: Path,
    voice_id: str | None,
    request_time_ms: float,
    parts: tuple[PartTiming, ...],
    chunks: tuple[AlignmentChunk, ...],
    ranges: tuple[tuple[int, int] | None, ...],
    incomplete: tuple[str, ...],
) -> EngineDocumentResult:
    """Return the result AniShift's TTS service reads: the recording, part timings and the incomplete parts."""
    del chunks, ranges
    return EngineDocumentResult(
        request_id=request_id,
        recording=recording,
        format=AudioFormat.MP3,
        engine_id=EngineSurface.engine_id,
        provider_model_id=PROVIDER_MODEL_ID,
        voice_id=voice_id or "",
        request_time_ms=request_time_ms,
        parts=parts,
        incomplete=incomplete,
    )


def busy_error() -> ChromeBusyError:
    """Return the retryable error of a profile another browser uses."""
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_ENGINE_UNAVAILABLE,
        message="ElevenReader browser profile is in use",
        suggestion=PROFILE_BUSY_HINT,
    )
    return ChromeBusyError(retry_after_s=UNAVAILABLE_RETRY_S, context=context)


def mono_pcm(recording: Path) -> array[int]:
    """Return the MP3 *recording* decoded by FFmpeg to mono PCM S16 at ``ENVELOPE_RATE``; any failure is OSError."""
    try:
        ffmpeg: str = str(require_binary(Binary.FFMPEG))
    except BinaryNotFoundError as error:
        raise OSError(errno.ENOENT, "FFmpeg is not installed") from error
    command: list[str] = [
        ffmpeg, "-v", "error", "-f", "mp3", "-i", str(recording), "-ac", "1",
        "-ar", str(ENVELOPE_RATE), "-f", "s16le", "pipe:1",
    ]  # fmt: skip
    try:
        decoded: subprocess.CompletedProcess[bytes] = subprocess.run(  # noqa: S603 - fixed arguments, no shell
            command, capture_output=True, check=True, timeout=_DECODE_TIMEOUT_S
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise OSError(errno.EIO, "FFmpeg could not decode the ElevenReader take") from error
    pcm: array[int] = array("h")
    pcm.frombytes(decoded.stdout[: len(decoded.stdout) // pcm.itemsize * pcm.itemsize])
    return pcm


def _availability(status: AvailabilityStatus, message: str, source: AvailabilitySource) -> EngineAvailability:
    return EngineAvailability(
        status=status, message=message, checked_at=datetime.now(UTC), source=source, voices=_voices()
    )


def _voices() -> tuple[VoiceInfo, ...]:
    return tuple(
        VoiceInfo(id=voice.voice_id, label=voice.label, engine_id="elevenreader", language="pl")
        for voice in VOICES.values()
    )


def _raise_config_error(message: str, *, field_name: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CONFIG_INVALID,
        message=message,
        suggestion=(
            f"Select ElevenReader with model eleven_v4, 1 to {MAX_PARALLEL_DOCUMENTS} syntheses at a time "
            "and the application profile."
        ),
        details={"field": field_name},
    )
    raise TtsConfigError(context=context)
