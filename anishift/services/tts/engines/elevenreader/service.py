"""ElevenReader engine: one attempt reads a whole document in Chrome and returns the recording with part timings."""

from __future__ import annotations

import asyncio
import re
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts.errors import (
    TtsAuthError,
    TtsCancelledError,
    TtsClipValidationError,
    TtsError,
    TtsInputError,
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
    EngineAvailability,
    EngineCapabilities,
    EngineDocumentResult,
    EngineLocality,
    PartTiming,
    VoiceInfo,
)
from anishift.utils.logger import get_logger

from .api_backend import (
    clean_account,
    load_cleanup,
    prepare_account,
    read_session,
    require_signed_in,
    save_cleanup,
    unavailable_error,
    voice_error,
)
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
from .recorder import StreamRecorder

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from anishift.services.tts.config import TtsConfig
    from anishift.services.tts.protocols import CancellationToken
    from anishift.services.tts.types import DocumentPart, DocumentSynthesisRequest, EngineClipResult, SynthesisRequest

    from .api_backend import ReaderPage
    from .browser import ChromeSession
    from .types import (
        AccountCleanup,
        AccountSettings,
        AlignmentChunk,
        DocumentTrace,
        ElevenReaderVoice,
        PlayerState,
        SessionRecord,
        UploadedRead,
    )

__all__ = ["CLEANUP_WARNING", "ElevenReaderTtsEngine", "document_text", "part_spans"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

CLEANUP_WARNING: Final[str] = (
    "ElevenReader: nie udało się posprzątać konta — usuń z biblioteki ostatni dokument wgrany przez AniShift "
    "(jego tytuł to pierwsze zdanie odcinka) i sprawdź głos w aplikacji"
)
"""Owner-facing warning left when account cleanup failed for good."""

_BRACKETS: Final[dict[int, str]] = str.maketrans({"[": "(", "]": ")"})
"""Square brackets, which ElevenReader reads as audio tags, mapped to round ones."""

_PART_GLUE: Final[str] = f"\n\n{LINE_SEPARATOR}\n\n"
"""Text between parts: a separator paragraph, so the server pauses and marks breaks around it."""

_BREAK_TAG: Final[str] = "<break"
"""Start of the SSML pause the server places between paragraphs; a part may not contain one."""

_BREAK_RUN: Final[re.Pattern[str]] = re.compile(r"<break[^>]*(?:>|$)(?:\s*<break[^>]*(?:>|$))*")
"""Adjacent SSML pauses forming one boundary; the final tag may be cut off at the end of the text."""

_KEEP_BROWSER_ERRORS: Final[tuple[type[TtsError], ...]] = (
    TtsAuthError,
    TtsClipValidationError,
    TtsInputError,
    TtsQuotaError,
    TtsRateLimitError,
    TtsVoiceError,
)
"""Failures that leave the browser healthy, so it stays open for cleanup and the next attempt."""


class ElevenReaderTtsEngine:
    """One-attempt adapter recording ElevenReader documents through the owner's signed-in Chrome profile."""

    engine_id = "elevenreader"
    capabilities = EngineCapabilities(
        locality=EngineLocality.REMOTE,
        native_output_formats=(AudioFormat.MP3,),
        supports_concurrency=False,
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
        """Resolve the voice and profile without starting a browser."""
        self._config: ElevenReaderConfig = ElevenReaderConfig.from_tts_config(config)
        self._browser_factory: Callable[[Path], ChromeSession] = browser_factory or _headless_session
        self._browser: ChromeSession | None = None
        self._cleanup: AccountCleanup = load_cleanup(self._config.profile_root)
        self._saved_cleanup: tuple[AccountSettings | None, tuple[DocumentTrace, ...]] = self._cleanup_state()
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
        """Record one document once, always cleaning the account afterwards."""
        voice: ElevenReaderVoice = self._validate(request)
        if cancel.is_cancelled:
            raise _cancelled_error()
        started: float = time.monotonic()
        browser: ChromeSession = await _unless_cancelled(self._open_browser(), cancel)
        page: ReaderPage | None = None
        keep_browser: bool = False
        try:
            async with _within_deadline(request.deadline_s):
                page = await _unless_cancelled(browser.new_page(), cancel)
                result: EngineDocumentResult = await self._read(page, request, voice, cancel, started)
        except _KEEP_BROWSER_ERRORS:
            keep_browser = True
            raise
        else:
            keep_browser = True
            return result
        finally:
            await _finish_shielded(self._end_attempt(page, keep_browser=keep_browser))

    async def close(self) -> None:
        """Run pending account cleanup while the browser lives, save and warn about what is left, then stop Chrome."""
        if self._closed:
            return
        self._closed = True
        browser: ChromeSession | None = self._browser
        try:
            if self._cleanup.pending and browser is not None and browser.alive:
                await _finish_shielded(self._clean_in_new_tab(browser))
        finally:
            self._save_cleanup()
            if self._cleanup.pending:
                logger.warning(CLEANUP_WARNING, steps=list(self._cleanup.pending))
            await self._close_browser()

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

    async def _open_browser(self) -> ChromeSession:
        if self._closed:
            message: str = "ElevenReader engine is closed"
            raise unavailable_error(message)
        browser: ChromeSession | None = self._browser
        if browser is not None and browser.alive:
            return browser
        await self._close_browser()
        browser = self._browser_factory(self._config.profile_root)
        self._browser = browser
        await browser.start()
        return browser

    async def _read(
        self,
        page: ReaderPage,
        request: DocumentSynthesisRequest,
        voice: ElevenReaderVoice,
        cancel: CancellationToken,
        started: float,
    ) -> EngineDocumentResult:
        await _unless_cancelled(require_signed_in(page, self._config.profile_root), cancel)
        if self._cleanup.pending:
            await _finish_shielded(clean_account(page, self._cleanup))
            self._save_cleanup()
        text: str = document_text(request.parts)
        with tempfile.TemporaryDirectory(prefix="anishift-elevenreader-") as folder:
            document: Path = Path(folder) / DOCUMENT_NAME
            document.write_text(text, encoding="utf-8")
            uploaded: UploadedRead = await _unless_cancelled(
                page.upload(document, self._cleanup, self._save_cleanup),
                cancel,
            )
        logger.info("ElevenReader document uploaded", parts=len(request.parts), chars=uploaded.char_count)
        await _unless_cancelled(
            prepare_account(page, uploaded.token, voice.voice_id, self._cleanup, self._save_cleanup),
            cancel,
        )
        request.recording.parent.mkdir(parents=True, exist_ok=True)
        stream_voices: list[bool] = []
        with request.recording.open("wb") as output:
            recorder: StreamRecorder = StreamRecorder(output)
            page.watch_stream(recorder, lambda url: stream_voices.append(voice.voice_id in url))
            try:
                await _unless_cancelled(page.open_document(uploaded.read_id), cancel)
                await _unless_cancelled(page.set_page_speed(PAGE_SPEED), cancel)
                await _unless_cancelled(page.press_play(), cancel)
                await self._record(page, recorder, request, uploaded.char_count, cancel)
            finally:
                page.unwatch_stream()
                recorder.stop()
        if not any(stream_voices):
            message: str = "ElevenReader stream address did not carry the selected voice"
            raise voice_error(message)
        elapsed_ms: float = (time.monotonic() - started) * 1000
        return self._result(request, voice, recorder, uploaded.char_count, elapsed_ms)

    async def _record(
        self,
        page: ReaderPage,
        recorder: StreamRecorder,
        request: DocumentSynthesisRequest,
        char_count: int,
        cancel: CancellationToken,
    ) -> None:
        now: float = time.monotonic()
        played_at: float = now
        last_progress: float = now
        last_speed_check: float = now
        last_bytes: int = 0
        plays: int = 1
        while True:
            await _unless_cancelled(asyncio.sleep(POLL_S), cancel)
            if recorder.write_error is not None:
                raise _write_error(recorder.write_error)
            if recorder.listening_speed not in (None, READING_SPEED):
                message: str = "ElevenReader streamed with Eleven v2 instead of v4"
                raise unavailable_error(message)
            now = time.monotonic()
            if now - last_speed_check >= SPEED_CHECK_S:
                last_speed_check = now
                await _unless_cancelled(page.check_page_speed(PAGE_SPEED), cancel)
            if not recorder.audio_bytes:
                if now - played_at < START_TIMEOUT_S:
                    continue
                if plays >= PLAY_ATTEMPTS:
                    reason: str = "ElevenReader sent no audio after Play"
                    raise _timeout_error(reason)
                await _unless_cancelled(page.press_play(), cancel)
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
                raise _timeout_error(reason)

    async def _finished(
        self, page: ReaderPage, recorder: StreamRecorder, char_count: int, cancel: CancellationToken
    ) -> bool:
        if recorder.chars >= char_count:
            return True
        state: PlayerState = await _unless_cancelled(page.player_state(), cancel)
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

    async def _end_attempt(self, page: ReaderPage | None, *, keep_browser: bool) -> None:
        try:
            if page is not None:
                await self._end_page(page)
        finally:
            if not keep_browser:
                await self._close_browser()

    async def _end_page(self, page: ReaderPage) -> None:
        try:
            page.unwatch_stream()
            await clean_account(page, self._cleanup)
        finally:
            self._save_cleanup()
            await page.close()

    async def _clean_in_new_tab(self, browser: ChromeSession) -> None:
        try:
            page: ReaderPage = await browser.new_page()
        except TtsError as error:
            logger.warning("ElevenReader cleanup tab could not open", code=error.context.code.value)
            return
        try:
            await page.open_library()
            await clean_account(page, self._cleanup)
        finally:
            await page.close()

    def _save_cleanup(self) -> None:
        state: tuple[AccountSettings | None, tuple[DocumentTrace, ...]] = self._cleanup_state()
        if state != self._saved_cleanup and save_cleanup(self._config.profile_root, self._cleanup):
            self._saved_cleanup = state

    def _cleanup_state(self) -> tuple[AccountSettings | None, tuple[DocumentTrace, ...]]:
        return self._cleanup.restore, tuple(self._cleanup.documents)

    async def _close_browser(self) -> None:
        browser: ChromeSession | None = self._browser
        self._browser = None
        if browser is not None:
            await browser.close()

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


def _headless_session(root: Path) -> ChromeSession:
    from .browser import ChromeSession  # noqa: PLC0415 - keeps Playwright out of the package import

    return ChromeSession(root, headless=True)


def _voices() -> tuple[VoiceInfo, ...]:
    return tuple(
        VoiceInfo(id=voice.voice_id, label=voice.label, engine_id="elevenreader", language="pl")
        for voice in VOICES.values()
    )


async def _unless_cancelled[T](work: Awaitable[T], cancel: CancellationToken) -> T:
    task: asyncio.Future[T] = asyncio.ensure_future(work)
    waiter: asyncio.Future[None] = asyncio.ensure_future(cancel.wait())
    try:
        done, _ = await asyncio.wait((task, waiter), return_when=asyncio.FIRST_COMPLETED)
    except BaseException:
        task.cancel()
        waiter.cancel()
        raise
    waiter.cancel()
    if task in done:
        return task.result()
    task.cancel()
    await asyncio.wait((task,))
    raise _cancelled_error()


@asynccontextmanager
async def _within_deadline(deadline_s: float) -> AsyncIterator[None]:
    limit: asyncio.Timeout = asyncio.timeout(deadline_s)
    try:
        async with limit:
            yield
    except TimeoutError:
        if not limit.expired():
            raise
        reason: str = "ElevenReader document exceeded its deadline"
        raise _timeout_error(reason) from None


async def _finish_shielded(work: Awaitable[None]) -> None:
    task: asyncio.Future[None] = asyncio.ensure_future(work)
    interrupted: bool = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            interrupted = True
    if interrupted:
        raise asyncio.CancelledError
    task.result()


def _cancelled_error() -> TtsCancelledError:
    return TtsCancelledError("ElevenReader synthesis cancelled")


def _write_error(error: OSError) -> TtsClipValidationError:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CLIP_INVALID,
        message="ElevenReader recording could not be written",
        suggestion="Sprawdź wolne miejsce i uprawnienia dysku z workspace.",
        details={"error_class": type(error).__name__, "errno": error.errno},
    )
    return TtsClipValidationError(context=context)


def _timeout_error(message: str) -> TtsTimeoutError:
    context: ErrorContext = ErrorContext(code=ErrorCode.TTS_TIMEOUT, message=message)
    return TtsTimeoutError(context=context)


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
