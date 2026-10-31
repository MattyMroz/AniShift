"""ElevenReader engine: one attempt reads a whole document in Chrome and returns the recording with part timings."""

from __future__ import annotations

import asyncio
import re
import tempfile
import time
from dataclasses import replace
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.errors import TtsClipValidationError, TtsInputError, TtsUnsupportedError
from anishift.services.tts.fingerprint import SynthesisProfile
from anishift.services.tts.types import (
    AudioFormat,
    AvailabilityProbeKind,
    AvailabilitySource,
    AvailabilityStatus,
    EngineAvailability,
    EngineCapabilities,
    EngineDocumentResult,
    EngineLocality,
    PartTiming,
    VoiceInfo,
)
from anishift.utils.logger import get_logger

from .api_backend import prepare_account, read_session, unavailable_error, voice_error
from .config import ElevenReaderConfig, find_chrome, resolve_voice
from .constants import (
    DOCUMENT_NAME,
    END_IDLE_S,
    END_SLACK_CHARS,
    LINE_SEPARATOR,
    MAX_DOCUMENT_CHARS,
    PAGE_SPEED,
    PLAY_ATTEMPTS,
    POLL_S,
    PROVIDER_MODEL_ID,
    READING_SPEED,
    SPEED_CHECK_S,
    STALL_S,
    START_TIMEOUT_S,
    VOICES,
)
from .hub import ReaderHub, cancelled_error, headless_session, timeout_error, unless_cancelled
from .recorder import StreamRecorder

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from anishift.services.tts.config import TtsConfig
    from anishift.services.tts.protocols import CancellationToken
    from anishift.services.tts.types import DocumentPart, DocumentSynthesisRequest, EngineClipResult, SynthesisRequest

    from .api_backend import ReaderPage
    from .browser import ChromeSession
    from .hub import ReaderAttempt
    from .types import AlignmentChunk, ElevenReaderVoice, PlayerState, SessionRecord, UploadedRead

__all__ = ["ElevenReaderTtsEngine", "document_text", "part_spans"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_BRACKETS: Final[dict[int, str]] = str.maketrans({"[": "(", "]": ")"})
"""Square brackets, which ElevenReader reads as audio tags, mapped to round ones."""

_PART_GLUE: Final[str] = f"\n\n{LINE_SEPARATOR}\n\n"
"""Text between parts: a separator paragraph, so the server pauses and marks breaks around it."""

_BREAK_TAG: Final[str] = "<break"
"""Start of the SSML pause the server places between paragraphs; a part may not contain one."""

_BREAK_RUN: Final[re.Pattern[str]] = re.compile(r"<break[^>]*(?:>|$)(?:\s*<break[^>]*(?:>|$))*")
"""Adjacent SSML pauses forming one boundary; the final tag may be cut off at the end of the text."""


class ElevenReaderTtsEngine:
    """One-attempt adapter recording ElevenReader documents in a tab of the profile's shared Chrome."""

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
        max_text_chars=MAX_DOCUMENT_CHARS,
        max_text_bytes=None,
        availability_probe=AvailabilityProbeKind.LOCAL,
        max_document_chars=MAX_DOCUMENT_CHARS,
    )

    def __init__(
        self,
        config: TtsConfig,
        *,
        browser_factory: Callable[[Path], ChromeSession] | None = None,
    ) -> None:
        """Resolve the voice and profile and join the profile's host without starting a browser."""
        self._config: ElevenReaderConfig = ElevenReaderConfig.from_tts_config(config)
        self._hub: ReaderHub = ReaderHub.acquire(self._config.profile_root, browser_factory or headless_session)
        self._closed: bool = False
        self._synthesis_profile: SynthesisProfile = SynthesisProfile(
            engine_id=self.engine_id,
            endpoint_id="elevenreader-web-stream-v2",
            provider_model_id=PROVIDER_MODEL_ID,
            resolved_voice_id=self._config.voice.voice_id,
            provider_output_id="pcm_s16le_48000_cut",
            provider_source_format=AudioFormat.WAV,
            adapter_version="elevenreader-v1",
            voice_settings={"reading_speed": "1", "document_layout": "line_separator_paragraph"},
        )
        self._availability: EngineAvailability = self._chrome_availability(AvailabilitySource.LOCAL)

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
        if not live:
            self._availability = self._chrome_availability(AvailabilitySource.LOCAL)
            return self._availability
        self._availability = self._chrome_availability(AvailabilitySource.LIVE)
        if self._availability.status is not AvailabilityStatus.READY:
            return self._availability
        record: SessionRecord | None = read_session(self._config.profile_root)
        if record is None or not record.signed_in:
            self._availability = self._build_availability(
                AvailabilityStatus.MISSING_KEY,
                "ElevenReader session is not signed in",
                source=AvailabilitySource.LIVE,
            )
        return self._availability

    async def list_voices(self) -> tuple[VoiceInfo, ...]:
        """Return the offered ElevenReader voices."""
        return _voices()

    def document_chars(self, parts: tuple[DocumentPart, ...]) -> int:
        """Return the length of the uploaded document text for *parts*."""
        return len(document_text(parts))

    def validate_part(self, part: DocumentPart) -> None:
        """Raise TtsInputError when *part* cannot be read as its own paragraph."""
        text: str = _neutralize(part.text)
        if not text or text == LINE_SEPARATOR or _BREAK_TAG in text.casefold():
            _raise_unreadable_part(part.request_id)

    async def synthesize(self, request: SynthesisRequest, *, cancel: CancellationToken) -> EngineClipResult:
        """Refuse a single request; ElevenReader reads documents only."""
        del request, cancel
        message: str = "ElevenReader reads whole documents only"
        raise TtsUnsupportedError(message)

    async def synthesize_document(
        self,
        request: DocumentSynthesisRequest,
        *,
        cancel: CancellationToken,
    ) -> EngineDocumentResult:
        """Record one document once in its own tab, always deleting it from the library afterwards."""
        voice: ElevenReaderVoice = self._validate(request)
        if cancel.is_cancelled:
            raise cancelled_error()
        if self._closed:
            message: str = "ElevenReader engine is closed"
            raise unavailable_error(message)
        return await self._hub.record(
            partial(self._read, _reported_here(request), voice),
            voice_id=voice.voice_id,
            deadline_s=request.deadline_s,
            cancel=cancel,
        )

    async def close(self) -> None:
        """Leave the profile's host; the last engine to leave cleans the account and stops Chrome."""
        if self._closed:
            return
        self._closed = True
        await self._hub.release()

    def _validate(self, request: DocumentSynthesisRequest) -> ElevenReaderVoice:
        voice: ElevenReaderVoice = resolve_voice(request.voice_id)
        if voice != self._config.voice:
            _raise_input("ElevenReader request voice differs from engine configuration")
        if request.provider_model_id.strip().casefold() != PROVIDER_MODEL_ID:
            _raise_input(f"ElevenReader reads only with {PROVIDER_MODEL_ID}")
        if request.options:
            message: str = "ElevenReader accepts no engine options"
            raise TtsUnsupportedError(message)
        if self.document_chars(request.parts) > MAX_DOCUMENT_CHARS:
            _raise_input(f"ElevenReader document exceeds {MAX_DOCUMENT_CHARS} characters")
        for part in request.parts:
            self.validate_part(part)
        return voice

    async def _read(
        self,
        request: DocumentSynthesisRequest,
        voice: ElevenReaderVoice,
        attempt: ReaderAttempt,
    ) -> EngineDocumentResult:
        page: ReaderPage = attempt.page
        cancel: CancellationToken = attempt.cancel
        text: str = document_text(request.parts)
        with tempfile.TemporaryDirectory(prefix="anishift-elevenreader-") as folder:
            document: Path = Path(folder) / DOCUMENT_NAME
            document.write_text(text, encoding="utf-8")
            uploaded: UploadedRead = await unless_cancelled(
                page.upload(document, attempt.uploads, attempt.save),
                cancel,
            )
        logger.info("ElevenReader document uploaded", parts=len(request.parts), chars=uploaded.char_count)
        await unless_cancelled(
            prepare_account(page, uploaded.token, voice.voice_id, attempt.account, attempt.save),
            cancel,
        )
        request.recording.parent.mkdir(parents=True, exist_ok=True)
        stream_voices: list[bool] = []
        with request.recording.open("wb") as output:
            recorder: StreamRecorder = StreamRecorder(output)
            page.watch_stream(recorder, lambda url: stream_voices.append(voice.voice_id in url))
            try:
                await unless_cancelled(page.open_document(uploaded.read_id), cancel)
                await unless_cancelled(page.set_page_speed(PAGE_SPEED), cancel)
                await unless_cancelled(page.press_play(), cancel)
                played_at: float = time.monotonic()
                await _stream_opened(recorder, stream_voices, played_at, cancel)
                attempt.started()
                await self._record(page, recorder, request, uploaded.char_count, cancel, played_at=played_at)
            finally:
                page.unwatch_stream()
                recorder.stop()
        if not any(stream_voices):
            message: str = "ElevenReader stream address did not carry the selected voice"
            raise voice_error(message)
        elapsed_ms: float = (time.monotonic() - attempt.entered_at) * 1000
        return self._result(request, voice, recorder, uploaded.char_count, elapsed_ms)

    async def _record(  # noqa: PLR0913 - one recording loop needs its tab, stream, request and Play moment
        self,
        page: ReaderPage,
        recorder: StreamRecorder,
        request: DocumentSynthesisRequest,
        char_count: int,
        cancel: CancellationToken,
        *,
        played_at: float,
    ) -> None:
        now: float = time.monotonic()
        last_progress: float = now
        last_speed_check: float = now
        last_bytes: int = 0
        plays: int = 1
        while True:
            await unless_cancelled(asyncio.sleep(POLL_S), cancel)
            if recorder.write_error is not None:
                raise _write_error(recorder.write_error)
            if recorder.listening_speed not in (None, READING_SPEED):
                message: str = "ElevenReader streamed with Eleven v2 instead of v4"
                raise unavailable_error(message)
            now = time.monotonic()
            if now - last_speed_check >= SPEED_CHECK_S:
                last_speed_check = now
                await unless_cancelled(page.check_page_speed(PAGE_SPEED), cancel)
            if not recorder.audio_bytes:
                if now - played_at < START_TIMEOUT_S:
                    continue
                if plays >= PLAY_ATTEMPTS:
                    reason: str = "ElevenReader sent no audio after Play"
                    raise timeout_error(reason)
                await unless_cancelled(page.press_play(), cancel)
                plays, played_at = plays + 1, now
                continue
            if recorder.audio_bytes != last_bytes:
                last_bytes, last_progress = recorder.audio_bytes, now
                if request.progress is not None:
                    await request.progress(min(recorder.chars, char_count), char_count)
            if await self._finished(page, recorder, char_count, cancel) and now - last_progress >= END_IDLE_S:
                return
            if now - last_progress >= STALL_S:
                reason = "ElevenReader recording stalled"
                raise timeout_error(reason)

    async def _finished(
        self, page: ReaderPage, recorder: StreamRecorder, char_count: int, cancel: CancellationToken
    ) -> bool:
        if recorder.chars >= char_count:
            return True
        state: PlayerState = await unless_cancelled(page.player_state(), cancel)
        return state.length > 0 and state.length - state.value <= END_SLACK_CHARS

    def _result(
        self,
        request: DocumentSynthesisRequest,
        voice: ElevenReaderVoice,
        recorder: StreamRecorder,
        char_count: int,
        elapsed_ms: float,
    ) -> EngineDocumentResult:
        if recorder.chars < char_count:
            _raise_clip("ElevenReader recording is incomplete", received=recorder.chars, expected=char_count)
        if recorder.chars > char_count:
            logger.warning(
                "ElevenReader received more text than uploaded", received=recorder.chars, expected=char_count
            )
        timings: tuple[PartTiming, ...] = part_spans(recorder.chunks, request.parts)
        logger.info("ElevenReader document recorded", parts=len(timings), chars=recorder.chars, elapsed_ms=elapsed_ms)
        return EngineDocumentResult(
            request_id=request.request_id,
            recording=request.recording,
            format=AudioFormat.MP3,
            engine_id=self.engine_id,
            provider_model_id=PROVIDER_MODEL_ID,
            voice_id=voice.voice_id,
            request_time_ms=elapsed_ms,
            parts=timings,
        )

    def _chrome_availability(self, source: AvailabilitySource) -> EngineAvailability:
        if find_chrome() is None:
            return self._build_availability(
                AvailabilityStatus.MISSING_BINARY,
                "Google Chrome is not installed",
                source=source,
            )
        return self._build_availability(AvailabilityStatus.READY, "ElevenReader is ready", source=source)

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
            voices=_voices(),
        )


def document_text(parts: tuple[DocumentPart, ...]) -> str:
    """Return the uploaded document: neutralized parts as paragraphs split by separator paragraphs, newline-ended."""
    return _PART_GLUE.join(_neutralize(part.text) for part in parts) + "\n"


def part_spans(chunks: tuple[AlignmentChunk, ...], parts: tuple[DocumentPart, ...]) -> tuple[PartTiming, ...]:
    """Return the server timing of every part from the text runs between break tags, skipping separators."""
    text: str = "".join(char for chunk in chunks for char in chunk.chars)
    starts: list[float] = [chunk.offset_ms + start for chunk in chunks for start in chunk.starts_ms]
    ends: list[float] = [
        chunk.offset_ms + start + duration
        for chunk in chunks
        for start, duration in zip(chunk.starts_ms, chunk.durations_ms, strict=True)
    ]
    bounds: list[tuple[int, int]] = []
    cursor: int = 0
    for match in (*_BREAK_RUN.finditer(text), None):
        stop: int = len(text) if match is None else match.start()
        bound: tuple[int, int] | None = _segment(text, cursor, stop)
        if bound is not None:
            bounds.append(bound)
        cursor = len(text) if match is None else match.end()
    if len(bounds) != len(parts):
        _raise_clip("ElevenReader line count mismatch", received=len(bounds), expected=len(parts))
    timings: list[PartTiming] = []
    for index, (part, (first, last)) in enumerate(zip(parts, bounds, strict=True)):
        if text[first : last + 1] != _neutralize(part.text):
            _raise_clip("ElevenReader line text mismatch", line=index)
        if ends[last] < starts[first]:
            _raise_clip("ElevenReader part timing is reversed", line=index)
        timings.append(PartTiming(request_id=part.request_id, start_ms=starts[first], end_ms=ends[last]))
    return tuple(timings)


def _neutralize(text: str) -> str:
    return " ".join(text.translate(_BRACKETS).split())


def _segment(text: str, first: int, stop: int) -> tuple[int, int] | None:
    last: int = stop - 1
    while first <= last and text[first].isspace():
        first += 1
    while last >= first and text[last].isspace():
        last -= 1
    if first > last or text[first : last + 1] == LINE_SEPARATOR:
        return None
    return first, last


def _voices() -> tuple[VoiceInfo, ...]:
    return tuple(
        VoiceInfo(id=voice.voice_id, label=voice.label, engine_id="elevenreader", language="pl")
        for voice in VOICES.values()
    )


def _reported_here(request: DocumentSynthesisRequest) -> DocumentSynthesisRequest:
    progress: Callable[[int, int], Awaitable[None]] | None = request.progress
    if progress is None:
        return request
    loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()

    async def notify(received: int, total: int) -> None:
        await progress(received, total)

    async def report(received: int, total: int) -> None:
        await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(notify(received, total), loop))

    return replace(request, progress=report)


async def _stream_opened(
    recorder: StreamRecorder, addresses: list[bool], played_at: float, cancel: CancellationToken
) -> None:
    while not addresses and not recorder.audio_bytes and time.monotonic() - played_at < START_TIMEOUT_S:
        await unless_cancelled(asyncio.sleep(POLL_S), cancel)


def _write_error(error: OSError) -> TtsClipValidationError:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CLIP_INVALID,
        message="ElevenReader recording could not be written",
        suggestion="Sprawdź wolne miejsce i uprawnienia dysku z workspace.",
        details={"error_class": type(error).__name__, "errno": error.errno},
    )
    return TtsClipValidationError(context=context)


def _raise_input(message: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_INPUT_INVALID,
        message=message,
        suggestion="Use one configured ElevenReader voice and model for the service lifecycle.",
    )
    raise TtsInputError(context=context)


def _raise_unreadable_part(request_id: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_INPUT_INVALID,
        message="ElevenReader part cannot be read as its own paragraph",
        suggestion="Kwestia nie może być pusta, samym „…” ani zawierać znacznika <break>.",
        details={"request_id": request_id},
    )
    raise TtsInputError(context=context)


def _raise_clip(message: str, **details: int) -> Never:
    context: ErrorContext = ErrorContext(code=ErrorCode.TTS_CLIP_INVALID, message=message, details=details)
    raise TtsClipValidationError(context=context)
