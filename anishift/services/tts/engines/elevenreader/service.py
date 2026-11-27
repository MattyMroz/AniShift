"""ElevenReader engine: a document is read in Chrome, parts the server left unread are read again and cut in."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import time
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Final, Never

from .api_backend import prepare_account, unavailable_error, voice_error
from .config import resolve_voice
from .constants import (
    END_IDLE_S,
    END_SLACK_CHARS,
    LINE_SEPARATOR,
    PAGE_SPEED,
    PLAY_ATTEMPTS,
    POLL_S,
    READING_SPEED,
    SPEED_CHECK_S,
    STALL_S,
    START_TIMEOUT_S,
)
from .host import (
    INPUT_HINT,
    NAME,
    PART_HINT,
    WRITE_HINT,
    EngineSurface,
    ErrorCode,
    ErrorContext,
    FatalError,
    TtsCancelledError,
    TtsClipValidationError,
    TtsError,
    TtsInputError,
    check_request,
    document_result,
    engine_config,
    get_logger,
    keeps_tags,
)
from .hub import ReaderHub, cancelled_error, headless_session, timeout_error, unless_cancelled
from .recorder import StreamRecorder
from .redo import Reading, Redone, Take, new_file, read_parts, redo_blocks, splice, timings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from .api_backend import ReaderPage
    from .browser import ChromeSession
    from .config import ElevenReaderConfig
    from .host import (
        CancellationToken,
        DocumentPart,
        DocumentResult,
        DocumentSynthesisRequest,
        EngineSettings,
        PartTiming,
    )
    from .hub import ReaderAttempt
    from .types import AlignmentChunk, ElevenReaderVoice, PlayerState, UploadedRead

__all__ = ["PART_GLUE", "ElevenReaderTtsEngine", "document_text"]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

_BRACKETS: Final[dict[int, str]] = str.maketrans({"[": "(", "]": ")"})
"""Square brackets, which ElevenReader reads as audio tags, mapped to round ones."""

PART_GLUE: Final[str] = f"\n\n{LINE_SEPARATOR}\n\n"
"""Text between parts: a separator paragraph, so the server pauses and marks breaks around it."""

_BREAK_TAG: Final[str] = "<break"
"""Start of the SSML pause the server places between paragraphs; a part may not contain one."""

_ACCOUNT_VOICE: Final[str] = ""
"""Voice-gate key of a download reading with the account's voice: it waits for, and holds off, every chosen voice."""

_DOWNLOAD_REQUEST_ID: Final[str] = "download"
"""Request id of a downloaded document; the read id stays out of results."""

_DOCUMENT_NAME: Final[str] = f"{NAME}.txt"
"""Name of the uploaded file; the library titles the document by its first sentence instead."""

_TAKE_SUFFIX: Final[str] = ".take"
"""Infix of a take file: ``<name>.take<n>.mp3``, so no attempt overwrites another."""

_MP3: Final[str] = ".mp3"
"""Suffix of every recording; a recording's name ends at it."""

_STREAM_SUFFIX: Final[str] = ".stream.txt"
"""Suffix of the text the server streamed, written next to every recording under the recording's stem."""


class ElevenReaderTtsEngine(EngineSurface):
    """Engine recording ElevenReader documents in tabs of the profile's shared Chrome, redoing parts left unread."""

    def __init__(
        self,
        config: EngineSettings,
        *,
        browser_factory: Callable[[Path], ChromeSession] | None = None,
    ) -> None:
        """Resolve the configuration and join the profile's host without starting a browser."""
        self._config: ElevenReaderConfig = engine_config(config)
        self._hub: ReaderHub = ReaderHub.acquire(self._config.profile_root, browser_factory or headless_session)
        self._closed: bool = False
        self._attach_host()

    def document_chars(self, parts: tuple[DocumentPart, ...]) -> int:
        """Return the length of the uploaded document text for *parts*."""
        return len(document_text(parts))

    def validate_part(self, part: DocumentPart) -> None:
        """Raise TtsInputError when *part* cannot be read as its own paragraph."""
        text: str = _neutralize(part.text)
        if not text or text == LINE_SEPARATOR or _BREAK_TAG in text.casefold():
            _raise_unreadable_part(part.request_id)

    async def synthesize_document(
        self,
        request: DocumentSynthesisRequest,
        *,
        cancel: CancellationToken,
    ) -> DocumentResult:
        """Record one document, redo each block with a missing word once, join it in, list parts still incomplete."""
        voice: ElevenReaderVoice = self._validate(request)
        _require_new(request.recording)
        if cancel.is_cancelled:
            raise cancelled_error()
        if self._closed:
            message: str = "ElevenReader engine is closed"
            raise unavailable_error(message)
        entered_at: float = time.monotonic()
        tags: bool = keeps_tags(request)
        texts: list[str] = [part.text for part in request.parts]
        reported: DocumentSynthesisRequest = _reported_here(request)
        main: Take = await self._take(
            reported, request.parts, voice, cancel, recording=_next_take(request.recording), progress=reported.progress
        )
        reading: Reading = _read(main, texts, offset=0)
        redone: list[Redone] = []
        cause: ErrorContext | None = None
        if reading.missing:
            redone, cause = await self._redo(request, voice, reading, cancel)
        chunks: tuple[AlignmentChunk, ...] = await asyncio.to_thread(
            _joined, main, reading, redone, request.recording, len(request.parts)
        )
        final: Take = Take(request.recording, chunks)
        _write_stream_text(final)
        for take in (main, *(block.take for block in redone)):
            _discard(take.recording)
        joined: Reading = read_parts(final.text, texts)
        parts: tuple[PartTiming, ...] = timings(chunks, request.parts, joined.ranges)
        incomplete: tuple[str, ...] = tuple(request.parts[index].request_id for index in joined.missing)
        if incomplete:
            logger.warning("ElevenReader parts stay incomplete after their redo", parts=list(joined.missing))
        logger.info(
            "ElevenReader document recorded",
            parts=len(parts),
            unspoken=sum(not timing.spoken for timing in parts),
            incomplete=len(incomplete),
            chars=len(final.text),
            tags=tags,
        )
        return document_result(
            request_id=request.request_id,
            recording=request.recording,
            voice_id=voice.voice_id,
            request_time_ms=(time.monotonic() - entered_at) * 1000,
            parts=parts,
            chunks=chunks,
            ranges=joined.ranges,
            incomplete=incomplete,
            incomplete_cause=cause if incomplete else None,
        )

    async def download_document(
        self,
        read_id: str,
        recording: Path,
        *,
        voice_id: str | None,
        deadline_s: float,
        cancel: CancellationToken,
    ) -> DocumentResult:
        """Record a library document from its start into *recording* with the voice or the account's; it stays there."""
        voice: ElevenReaderVoice | None = None if voice_id is None else resolve_voice(voice_id)
        _require_new(recording)
        if cancel.is_cancelled:
            raise cancelled_error()
        if self._closed:
            message: str = "ElevenReader engine is closed"
            raise unavailable_error(message)
        entered_at: float = time.monotonic()
        take_file: Path = _next_take(recording)
        take: Take = await self._hub.record(
            partial(self._download, read_id, take_file, voice),
            voice_id=_ACCOUNT_VOICE if voice is None else voice.voice_id,
            deadline_s=deadline_s,
            cancel=cancel,
        )
        await asyncio.to_thread(_copy_new, take.recording, recording)
        _write_stream_text(Take(recording, take.chunks))
        _discard(take.recording)
        return document_result(
            request_id=_DOWNLOAD_REQUEST_ID,
            recording=recording,
            voice_id=None if voice is None else voice.voice_id,
            request_time_ms=(time.monotonic() - entered_at) * 1000,
            parts=(),
            chunks=take.chunks,
            ranges=(),
            incomplete=(),
            incomplete_cause=None,
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
        check_request(request)
        for part in request.parts:
            self.validate_part(part)
        return voice

    async def _redo(
        self, request: DocumentSynthesisRequest, voice: ElevenReaderVoice, reading: Reading, cancel: CancellationToken
    ) -> tuple[list[Redone], ErrorContext | None]:
        """Record every block with a missing word once more; return the complete blocks and what stopped the rest."""
        redone: list[Redone] = []
        for first, last in redo_blocks(reading.missing, len(request.parts), self._config.redo):
            parts: tuple[DocumentPart, ...] = request.parts[first : last + 1]
            logger.info("ElevenReader block is read again", first=first, last=last, mode=self._config.redo.value)
            recording: Path = _next_take(request.recording)
            try:
                take: Take = await self._take(request, parts, voice, cancel, recording=recording, progress=None)
            except TtsCancelledError:
                raise
            except FatalError as error:
                _discard(recording)
                logger.warning(
                    "ElevenReader redo stopped; the blocks left stay incomplete",
                    first=first,
                    error_code=error.context.code.value,
                )
                return redone, error.context
            except (TtsError, OSError) as error:
                _discard(recording)
                logger.warning("ElevenReader redo failed", first=first, last=last, error_class=type(error).__name__)
                continue
            if _read(take, [part.text for part in parts], offset=first).missing:
                _discard(recording)
                logger.warning("ElevenReader redo still lacks words and is not joined", first=first, last=last)
                continue
            redone.append(Redone(first=first, last=last, take=take))
        return redone, None

    async def _take(  # noqa: PLR0913 - one take needs its request, parts, voice, cancel, file and progress
        self,
        request: DocumentSynthesisRequest,
        parts: tuple[DocumentPart, ...],
        voice: ElevenReaderVoice,
        cancel: CancellationToken,
        *,
        recording: Path,
        progress: Callable[[int, int], Awaitable[None]] | None,
    ) -> Take:
        logger.info("ElevenReader take started", take=recording.name, parts=len(parts))
        return await self._hub.record(
            partial(
                self._read,
                parts,
                text=document_text(parts, tags=keeps_tags(request)),
                voice=voice,
                recording=recording,
                progress=progress,
            ),
            voice_id=voice.voice_id,
            deadline_s=request.deadline_s,
            cancel=cancel,
        )

    async def _read(  # noqa: PLR0913 - one take needs its parts, text, voice, file, progress and tab
        self,
        parts: tuple[DocumentPart, ...],
        attempt: ReaderAttempt,
        *,
        text: str,
        voice: ElevenReaderVoice,
        recording: Path,
        progress: Callable[[int, int], Awaitable[None]] | None,
    ) -> Take:
        page: ReaderPage = attempt.page
        cancel: CancellationToken = attempt.cancel
        with tempfile.TemporaryDirectory(prefix=f"{NAME}-elevenreader-") as folder:
            document: Path = Path(folder) / _DOCUMENT_NAME
            document.write_text(text, encoding="utf-8")
            uploaded: UploadedRead = await unless_cancelled(
                page.upload(document, attempt.uploads, attempt.save),
                cancel,
            )
        logger.info("ElevenReader document uploaded", parts=len(parts), chars=uploaded.char_count)
        await unless_cancelled(
            prepare_account(page, uploaded.token, voice.voice_id, attempt.account, attempt.save),
            cancel,
        )
        recorder: StreamRecorder = await self._stream(
            attempt, uploaded.read_id, recording, voice, char_count=uploaded.char_count, progress=progress
        )
        if recorder.chars != uploaded.char_count:
            logger.warning(
                "ElevenReader streamed another length than uploaded",
                received=recorder.chars,
                expected=uploaded.char_count,
            )
        return Take(recording, recorder.chunks)

    async def _download(
        self,
        read_id: str,
        recording: Path,
        voice: ElevenReaderVoice | None,
        attempt: ReaderAttempt,
    ) -> Take:
        token: str | None = attempt.page.token
        if not token:
            message: str = "ElevenReader library gave no account token"
            raise unavailable_error(message)
        await unless_cancelled(
            prepare_account(
                attempt.page, token, None if voice is None else voice.voice_id, attempt.account, attempt.save
            ),
            attempt.cancel,
        )
        recorder: StreamRecorder = await self._stream(
            attempt, read_id, recording, voice, char_count=None, progress=None
        )
        logger.info("ElevenReader document downloaded", chars=recorder.chars)
        return Take(recording, recorder.chunks)

    async def _stream(  # noqa: PLR0913 - one stream needs its tab, document, file, voice, length and progress
        self,
        attempt: ReaderAttempt,
        read_id: str,
        recording: Path,
        voice: ElevenReaderVoice | None,
        *,
        char_count: int | None,
        progress: Callable[[int, int], Awaitable[None]] | None,
    ) -> StreamRecorder:
        page: ReaderPage = attempt.page
        cancel: CancellationToken = attempt.cancel
        recording.parent.mkdir(parents=True, exist_ok=True)
        stream_voices: list[bool] = []
        with recording.open("xb") as output:
            recorder: StreamRecorder = StreamRecorder(output)
            page.watch_stream(recorder, lambda url: stream_voices.append(voice is None or voice.voice_id in url))
            try:
                await unless_cancelled(page.open_document(read_id), cancel)
                await unless_cancelled(page.set_page_speed(PAGE_SPEED), cancel)
                await unless_cancelled(page.press_play(), cancel)
                played_at: float = time.monotonic()
                await _stream_opened(page, recorder, stream_voices, played_at, cancel)
                attempt.started()
                try:
                    async with asyncio.timeout_at(attempt.deadline_at - POLL_S):
                        await self._record(
                            attempt, recorder, char_count, progress, read_id=read_id, played_at=played_at
                        )
                except TimeoutError:
                    reason: str = "ElevenReader document reached the end of its deadline"
                    raise timeout_error(reason) from None
            except (TtsError, OSError) as error:
                if not _keeps(recorder, char_count, error):
                    raise
                _broken_off(recorder, type(error).__name__)
            finally:
                page.unwatch_stream()
                recorder.stop()
                _write_stream_text(Take(recording, recorder.chunks))
        if voice is not None and not any(stream_voices):
            message: str = "ElevenReader stream address did not carry the selected voice"
            raise voice_error(message)
        return recorder

    async def _record(  # noqa: PLR0913 - one recording loop needs its tab, stream, length, progress, read and Play moment
        self,
        attempt: ReaderAttempt,
        recorder: StreamRecorder,
        char_count: int | None,
        progress: Callable[[int, int], Awaitable[None]] | None,
        *,
        read_id: str,
        played_at: float,
    ) -> None:
        page: ReaderPage = attempt.page
        cancel: CancellationToken = attempt.cancel
        now: float = time.monotonic()
        last_progress: float = now
        last_speed_check: float = now
        last_bytes: int = 0
        plays: int = 1
        while True:
            await unless_cancelled(asyncio.sleep(POLL_S), cancel)
            _check(page, recorder, char_count)
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
                logger.warning("ElevenReader sent no audio; the document is opened again", attempt=plays + 1)
                await unless_cancelled(page.open_document(read_id), cancel)
                await unless_cancelled(page.set_page_speed(PAGE_SPEED), cancel)
                await unless_cancelled(page.press_play(), cancel)
                plays, played_at = plays + 1, time.monotonic()
                continue
            if recorder.audio_bytes != last_bytes:
                last_bytes, last_progress = recorder.audio_bytes, now
                if progress is not None and char_count is not None:
                    await progress(min(recorder.chars, char_count), char_count)
            if await self._finished(page, recorder, char_count, cancel) and now - last_progress >= END_IDLE_S:
                return
            if now - last_progress >= STALL_S:
                reason = "ElevenReader recording stalled"
                raise timeout_error(reason)

    async def _finished(
        self, page: ReaderPage, recorder: StreamRecorder, char_count: int | None, cancel: CancellationToken
    ) -> bool:
        if char_count is not None and recorder.chars >= char_count:
            return True
        state: PlayerState = await unless_cancelled(page.player_state(), cancel)
        return state.length > 0 and state.length - state.value <= END_SLACK_CHARS


def document_text(parts: tuple[DocumentPart, ...], *, tags: bool = False) -> str:
    """Return the uploaded document: parts split by separator paragraphs; *tags* keeps square brackets as audio tags."""
    return PART_GLUE.join(_neutralize(part.text, tags=tags) for part in parts) + "\n"


def _neutralize(text: str, *, tags: bool = False) -> str:
    return " ".join((text if tags else text.translate(_BRACKETS)).split())


def _read(take: Take, texts: Sequence[str], *, offset: int) -> Reading:
    """Compare *take* with the parts it read and log every difference with the part's number in the document."""
    reading: Reading = read_parts(take.text, texts)
    for difference in reading.differences:
        logger.warning(
            "ElevenReader streamed other words than the parts",
            take=take.recording.name,
            part=offset + difference.part,
            expected=difference.expected,
            received=difference.received,
        )
    return reading


def _next_take(recording: Path) -> Path:
    """Return the first ``<name>.take<n>.mp3`` next to *recording* that does not exist yet."""
    number: int = 1
    while (take := recording.with_name(f"{_head(recording)}{_TAKE_SUFFIX}{number}{_MP3}")).exists():
        number += 1
    return take


def _head(recording: Path) -> str:
    """Return the file name of *recording* without ``.mp3`` and whatever follows it."""
    return recording.name.partition(_MP3)[0] or recording.stem


def _joined(main: Take, reading: Reading, redone: list[Redone], output: Path, count: int) -> tuple[AlignmentChunk, ...]:
    """Write *main* with the redone blocks cut in to *output*, or *main* alone when they cannot be joined."""
    if redone:
        try:
            chunks, _ = splice(main, reading, redone, output, count)
        except OSError as error:
            logger.warning("ElevenReader redo is not joined; the recording stays", error_class=type(error).__name__)
        else:
            return chunks
    _copy_new(main.recording, output)
    return main.chunks


def _require_new(recording: Path) -> None:
    """Refuse a recording file that holds data already, before anything is recorded, so none is ever overwritten."""
    if recording.is_file() and recording.stat().st_size:
        _raise_input("ElevenReader recording file exists already")


def _copy_new(source: Path, destination: Path) -> None:
    """Copy *source* to *destination*, which must be missing or an empty placeholder, so no recording is overwritten."""
    with source.open("rb") as reader, new_file(destination) as writer:
        shutil.copyfileobj(reader, writer)


def _write_stream_text(take: Take) -> None:
    """Write the text the server streamed next to the recording; a failure only reaches the log."""
    try:
        _stream_file(take.recording).write_text(take.text, encoding="utf-8")
    except OSError as error:
        logger.warning("ElevenReader streamed text could not be written", error_class=type(error).__name__)


def _stream_file(recording: Path) -> Path:
    return recording.with_name(f"{_head(recording)}{_STREAM_SUFFIX}")


def _discard(take: Path) -> None:
    """Delete a take and its streamed text, which no result needs; a failure only reaches the log."""
    try:
        take.unlink(missing_ok=True)
        _stream_file(take).unlink(missing_ok=True)
    except OSError as error:
        logger.warning("ElevenReader take could not be deleted", error_class=type(error).__name__)


def _check(page: ReaderPage, recorder: StreamRecorder, char_count: int | None) -> None:
    """Raise what ends the attempt: a refused browser, a failed write, a resumed download or Eleven v2."""
    page.raise_if_refused()
    if recorder.write_error is not None:
        raise _write_error(recorder.write_error)
    if char_count is None and recorder.start_position:
        raise _resumed_error(recorder.start_position)
    if recorder.listening_speed not in (None, READING_SPEED):
        message: str = "ElevenReader streamed with Eleven v2 instead of v4"
        raise unavailable_error(message)


def _keeps(recorder: StreamRecorder, char_count: int | None, error: TtsError | OSError) -> bool:
    """Tell whether a failed take of an uploaded document keeps the speech that came instead of failing."""
    if isinstance(error, TtsCancelledError) or char_count is None or not recorder.audio_bytes:
        return False
    return recorder.listening_speed in (None, READING_SPEED) or recorder.off_speed_after_speech


def _broken_off(recorder: StreamRecorder, reason: str) -> None:
    logger.warning(
        "ElevenReader stream broke off; the recording keeps what came and the missing parts are read again",
        reason=reason,
        chars=recorder.chars,
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
    page: ReaderPage, recorder: StreamRecorder, addresses: list[bool], played_at: float, cancel: CancellationToken
) -> None:
    while not addresses and not recorder.audio_bytes and time.monotonic() - played_at < START_TIMEOUT_S:
        page.raise_if_refused()
        await unless_cancelled(asyncio.sleep(POLL_S), cancel)


def _resumed_error(position: float) -> TtsInputError:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_INPUT_INVALID,
        message=f"The document resumes at character {position:.0f}, not at its beginning",
        suggestion="Rewind the document to its beginning in ElevenReader and run the command again.",
        details={"position": position},
    )
    return TtsInputError(context=context)


def _write_error(error: OSError) -> TtsClipValidationError:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_CLIP_INVALID,
        message="ElevenReader recording could not be written",
        suggestion=WRITE_HINT,
        details={"error_class": type(error).__name__, "errno": error.errno},
    )
    return TtsClipValidationError(context=context)


def _raise_input(message: str) -> Never:
    context: ErrorContext = ErrorContext(code=ErrorCode.TTS_INPUT_INVALID, message=message, suggestion=INPUT_HINT)
    raise TtsInputError(context=context)


def _raise_unreadable_part(request_id: str) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.TTS_INPUT_INVALID,
        message="ElevenReader part cannot be read as its own paragraph",
        suggestion=PART_HINT,
        details={"request_id": request_id},
    )
    raise TtsInputError(context=context)
