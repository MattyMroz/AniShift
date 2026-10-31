from __future__ import annotations

import asyncio
import errno
import io
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest
from elevenreader_fakes import (
    ADAM_ID,
    BREAK,
    FRONCZEWSKI_ID,
    READ_ID,
    READS_URL,
    TOKEN,
    FakePage,
    FakeSession,
    FakeSite,
    audio_frame,
    fake_engine,
    stream_frames,
    tts_config,
)
from loguru import logger as loguru_logger

from anishift.services.tts import (
    AudioFormat,
    AvailabilityStatus,
    DocumentPart,
    DocumentSynthesisRequest,
    DocumentTtsEngine,
    EngineDocumentResult,
    SynthesisRequest,
    TtsAuthError,
    TtsCancellation,
    TtsCancelledError,
    TtsClipValidationError,
    TtsError,
    TtsInputError,
    TtsProviderUnavailableError,
    TtsTimeoutError,
    TtsUnsupportedError,
    TtsVoiceError,
)
from anishift.services.tts.engines.elevenreader import CLEANUP_WARNING, ElevenReaderTtsEngine, read_session, service
from anishift.services.tts.engines.elevenreader import browser as browser_module
from anishift.services.tts.engines.elevenreader.api_backend import write_session
from anishift.services.tts.engines.elevenreader.recorder import StreamRecorder
from anishift.services.tts.engines.elevenreader.service import document_text, part_spans
from anishift.services.tts.engines.elevenreader.types import AccountSettings, AlignmentChunk, LibraryState

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from pathlib import Path

    from loguru import Message

pytestmark = pytest.mark.unit

TEXTS = ("Pierwsza kwestia.", "Druga [kwestia].")
UNREADABLE_PARTS = ("", "   ", "…", " … ", 'Raz <break time="1s"/> dwa', "Raz <BREAK/>", "Raz <break dwa")


@pytest.fixture(autouse=True)
def _fast_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "POLL_S", 0.001)
    monkeypatch.setattr(service, "END_IDLE_S", 0.0)
    monkeypatch.setattr(service, "START_TIMEOUT_S", 0.02)
    monkeypatch.setattr(service, "STALL_S", 0.1)
    monkeypatch.setattr(service, "SPEED_CHECK_S", 0.0)


def _run[T](work: Coroutine[object, object, T]) -> T:
    return asyncio.run(work)


def _request(
    tmp_path: Path, *, texts: tuple[str, ...] = TEXTS, voice_id: str = "fronczewski", deadline_s: float = 60.0
) -> DocumentSynthesisRequest:
    return DocumentSynthesisRequest(
        request_id="episode:document:0",
        parts=tuple(DocumentPart(request_id=f"line-{index}", text=text) for index, text in enumerate(texts)),
        voice_id=voice_id,
        provider_model_id="eleven_v4",
        options={},
        recording=tmp_path / "rec" / "recording.mp3",
        deadline_s=deadline_s,
    )


async def _record(engine: ElevenReaderTtsEngine, request: DocumentSynthesisRequest) -> EngineDocumentResult:
    return await engine.synthesize_document(request, cancel=TtsCancellation())


def _assert_cleaned(site: FakeSite) -> None:
    assert site.account["default_voice_id"] == "previous-voice"
    assert site.account["playback_speed_rate"] == 1.5
    assert site.account["theme"] == "dark"
    assert site.deleted == [f"https://api.elevenlabs.io/v1/reader/reads/{READ_ID}"]


def test_engine_satisfies_document_protocol_with_document_limit(tmp_path: Path) -> None:
    engine = fake_engine(tmp_path, FakeSite())

    assert isinstance(engine, DocumentTtsEngine)
    assert engine.capabilities.max_document_chars == 50_000
    assert engine.capabilities.native_output_formats == (AudioFormat.MP3,)
    assert engine.synthesis_profile.provider_source_format is AudioFormat.WAV
    assert engine.synthesis_profile.resolved_voice_id == FRONCZEWSKI_ID


def test_synthesize_document_success_returns_ordered_timings_and_cleans_account(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS)
    engine = fake_engine(tmp_path, site)
    request = _request(tmp_path)

    result = _run(_record(engine, request))

    assert [timing.request_id for timing in result.parts] == ["line-0", "line-1"]
    assert result.parts[0].end_ms <= result.parts[1].start_ms
    assert result.recording == request.recording
    assert request.recording.stat().st_size > 0
    assert result.format is AudioFormat.MP3
    assert result.voice_id == FRONCZEWSKI_ID
    assert result.provider_model_id == "eleven_v4"
    assert site.uploaded == ["Pierwsza kwestia.\n\n…\n\nDruga (kwestia).\n"]
    assert "set_page_speed" in site.events
    _assert_cleaned(site)
    assert site.pages[0].closed
    assert not site.pages[0].watching
    assert site.sessions[0].alive


def test_synthesize_document_sets_voice_and_speed_before_opening_document(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS)
    engine = fake_engine(tmp_path, site, voice_id="adam")

    _run(_record(engine, _request(tmp_path, voice_id="adam")))

    assert site.events.index("set_account") < site.events.index("open_document")
    assert site.events.index("upload") < site.events.index("set_account")


def test_synthesize_document_signed_in_records_session(tmp_path: Path) -> None:
    _run(_record(fake_engine(tmp_path, FakeSite(texts=TEXTS)), _request(tmp_path)))

    record = read_session(tmp_path)
    assert record is not None
    assert record.signed_in


def test_synthesize_document_signed_out_raises_auth_error_and_records_session(tmp_path: Path) -> None:
    site = FakeSite(library=LibraryState.SIGNED_OUT)

    with pytest.raises(TtsAuthError) as error:
        _run(_record(fake_engine(tmp_path, site), _request(tmp_path)))

    assert "Zaloguj / sprawdź sesję" in error.value.context.suggestion
    assert "upload" not in site.events
    record = read_session(tmp_path)
    assert record is not None
    assert not record.signed_in


def test_synthesize_document_default_browser_starts_chrome_headless(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = FakeSite(library=LibraryState.SIGNED_OUT)
    modes: list[bool] = []

    def session(root: Path, *, headless: bool) -> FakeSession:
        modes.append(headless)
        created: FakeSession = FakeSession(site)
        site.sessions.append(created)
        return created

    monkeypatch.setattr(browser_module, "ChromeSession", session)

    with pytest.raises(TtsAuthError):
        _run(_record(ElevenReaderTtsEngine(tts_config(tmp_path)), _request(tmp_path)))

    assert modes == [True]


def test_synthesize_document_unavailable_library_raises_transient_error_and_closes_browser(tmp_path: Path) -> None:
    site = FakeSite(library=LibraryState.UNAVAILABLE)

    with pytest.raises(TtsProviderUnavailableError) as error:
        _run(_record(fake_engine(tmp_path, site), _request(tmp_path)))

    assert error.value.retry_after_s == 60.0
    assert site.sessions[0].closed


def test_synthesize_document_account_ignoring_voice_raises_voice_error_and_cleans(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, ignore_voice=True)

    with pytest.raises(TtsVoiceError):
        _run(_record(fake_engine(tmp_path, site), _request(tmp_path)))

    _assert_cleaned(site)
    assert "open_document" not in site.events


def test_synthesize_document_stream_without_voice_raises_voice_error(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, voice_in_url=False)

    with pytest.raises(TtsVoiceError):
        _run(_record(fake_engine(tmp_path, site), _request(tmp_path)))

    _assert_cleaned(site)


def test_synthesize_document_v2_stream_raises_transient_error_and_closes_browser(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, listening_speed=3.0)

    with pytest.raises(TtsProviderUnavailableError, match="Eleven v2"):
        _run(_record(fake_engine(tmp_path, site), _request(tmp_path)))

    _assert_cleaned(site)
    assert site.sessions[0].closed


def test_synthesize_document_incomplete_recording_raises_clip_error(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, char_count=10_000, player_done=True)

    with pytest.raises(TtsClipValidationError, match="incomplete"):
        _run(_record(fake_engine(tmp_path, site), _request(tmp_path)))

    _assert_cleaned(site)


def test_synthesize_document_line_count_mismatch_raises_clip_error(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, frames=stream_frames(("Pierwsza kwestia. Druga (kwestia).",)))

    with pytest.raises(TtsClipValidationError, match="line count mismatch"):
        _run(_record(fake_engine(tmp_path, site), _request(tmp_path)))


def test_synthesize_document_without_audio_presses_play_three_times_then_times_out(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, send_audio=False)

    with pytest.raises(TtsTimeoutError, match="no audio"):
        _run(_record(fake_engine(tmp_path, site), _request(tmp_path)))

    assert site.plays == 3
    _assert_cleaned(site)
    assert site.sessions[0].closed


def test_synthesize_document_stalled_stream_times_out(tmp_path: Path) -> None:
    frames: list[str] = [audio_frame("Pierwsza kwestia. " + BREAK, frames=3)]
    site = FakeSite(texts=TEXTS, frames=frames, char_count=10_000)

    with pytest.raises(TtsTimeoutError, match="stalled"):
        _run(_record(fake_engine(tmp_path, site), _request(tmp_path)))


def test_synthesize_document_progress_reports_received_characters(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS)
    seen: list[tuple[int, int]] = []

    async def observe(received: int, total: int) -> None:
        seen.append((received, total))

    request = _request(tmp_path)
    request = DocumentSynthesisRequest(
        request_id=request.request_id,
        parts=request.parts,
        voice_id=request.voice_id,
        provider_model_id=request.provider_model_id,
        options=request.options,
        recording=request.recording,
        deadline_s=request.deadline_s,
        progress=observe,
    )

    _run(_record(fake_engine(tmp_path, site), request))

    assert seen
    assert seen[-1] == (site.count(), site.count())


def test_synthesize_document_cancel_while_waiting_stops_quickly_and_cleans(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, hang_on="open_document")
    engine = fake_engine(tmp_path, site)
    cancel = TtsCancellation()

    async def scenario() -> float:
        started: float = time.monotonic()
        task = asyncio.create_task(engine.synthesize_document(_request(tmp_path), cancel=cancel))
        await site.hung.wait()
        cancel.cancel()
        with pytest.raises(TtsCancelledError):
            await task
        return time.monotonic() - started

    elapsed: float = _run(scenario())

    assert elapsed < 2.0
    _assert_cleaned(site)
    assert site.sessions[0].closed


@pytest.mark.parametrize("hung", ["set_page_speed", "press_play", "check_page_speed", "player_state"])
def test_synthesize_document_cancel_while_page_hangs_stops_quickly_and_cleans(tmp_path: Path, hung: str) -> None:
    site = FakeSite(texts=TEXTS, char_count=10_000, hang_on=hung)
    engine = fake_engine(tmp_path, site)
    cancel = TtsCancellation()

    async def scenario() -> None:
        async with asyncio.timeout(5.0):
            task = asyncio.create_task(engine.synthesize_document(_request(tmp_path), cancel=cancel))
            await site.hung.wait()
            cancel.cancel()
            with pytest.raises(TtsCancelledError):
                await task

    _run(scenario())

    _assert_cleaned(site)
    assert site.sessions[0].closed


def test_synthesize_document_hung_page_times_out_at_deadline_and_cleans(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, char_count=10_000, hang_on="player_state")
    engine = fake_engine(tmp_path, site)

    async def scenario() -> None:
        async with asyncio.timeout(5.0):
            await _record(engine, _request(tmp_path, deadline_s=0.2))

    with pytest.raises(TtsTimeoutError, match="deadline"):
        _run(scenario())

    _assert_cleaned(site)
    assert site.sessions[0].closed


def test_synthesize_document_task_cancelled_still_cleans_and_closes_browser(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, hang_on="open_document")
    engine = fake_engine(tmp_path, site)

    async def scenario() -> None:
        task = asyncio.create_task(_record(engine, _request(tmp_path)))
        await site.hung.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    _run(scenario())

    _assert_cleaned(site)
    assert site.sessions[0].closed


def test_synthesize_document_cancel_during_upload_deletes_document_found_by_title(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, hang_on="upload")
    engine = fake_engine(tmp_path, site)
    cancel = TtsCancellation()

    async def scenario() -> None:
        task = asyncio.create_task(engine.synthesize_document(_request(tmp_path), cancel=cancel))
        await site.hung.wait()
        cancel.cancel()
        with pytest.raises(TtsCancelledError):
            await task

    _run(scenario())

    assert site.deleted == [f"{READS_URL}/{READ_ID}"]
    assert site.reads == []
    record = read_session(tmp_path)
    assert record is not None
    assert not record.cleanup_pending
    assert site.sessions[0].closed


def test_synthesize_document_task_cancelled_during_upload_deletes_document_found_by_title(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, hang_on="upload")
    engine = fake_engine(tmp_path, site)

    async def scenario() -> None:
        task = asyncio.create_task(_record(engine, _request(tmp_path)))
        await site.hung.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    _run(scenario())

    assert site.deleted == [f"{READS_URL}/{READ_ID}"]
    assert site.sessions[0].closed


def test_synthesize_document_cancel_during_upload_before_document_appears_keeps_saved_trace(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, hang_on="upload")
    engine = fake_engine(tmp_path, site)
    cancel = TtsCancellation()

    async def scenario() -> None:
        task = asyncio.create_task(engine.synthesize_document(_request(tmp_path), cancel=cancel))
        await site.hung.wait()
        site.reads.clear()
        cancel.cancel()
        with pytest.raises(TtsCancelledError):
            await task
        await engine.close()

    _run(scenario())

    record = read_session(tmp_path)
    assert record is not None
    assert record.delete_document
    assert READ_ID not in (tmp_path / "session.json").read_text(encoding="utf-8")


def test_saved_document_trace_is_cleaned_by_next_engine_before_upload(tmp_path: Path) -> None:
    first = FakeSite(texts=TEXTS, hang_on="upload", failing={"list_reads"})
    engine = fake_engine(tmp_path, first)
    cancel = TtsCancellation()

    async def interrupted() -> None:
        task = asyncio.create_task(engine.synthesize_document(_request(tmp_path), cancel=cancel))
        await first.hung.wait()
        cancel.cancel()
        with pytest.raises(TtsCancelledError):
            await task
        await engine.close()

    _run(interrupted())
    saved = read_session(tmp_path)
    assert saved is not None
    assert saved.delete_document
    second = FakeSite(texts=TEXTS, reads=[READ_ID])

    _run(_record(fake_engine(tmp_path, second), _request(tmp_path)))

    assert second.events.index("list_reads") < second.events.index("upload")
    assert second.deleted == [f"{READS_URL}/{READ_ID}", f"{READS_URL}/{READ_ID}"]
    record = read_session(tmp_path)
    assert record is not None
    assert not record.cleanup_pending


def test_failed_restore_is_saved_and_run_by_next_engine(tmp_path: Path) -> None:
    first = FakeSite(texts=TEXTS, failing={"restore_account"})
    _run(_record(fake_engine(tmp_path, first), _request(tmp_path)))
    saved = read_session(tmp_path)
    assert saved is not None
    assert saved.restore == AccountSettings(voice_id="previous-voice", speed=1.5)
    assert not saved.delete_document
    second = FakeSite(texts=TEXTS, account={"default_voice_id": FRONCZEWSKI_ID, "playback_speed_rate": 1.0})

    _run(_record(fake_engine(tmp_path, second), _request(tmp_path)))

    assert second.events.index("restore_account") < second.events.index("upload")
    assert second.account["default_voice_id"] == "previous-voice"
    record = read_session(tmp_path)
    assert record is not None
    assert not record.cleanup_pending


def test_synthesize_document_unwritable_recording_raises_clip_error_without_waiting_for_stall(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "STALL_S", 300.0)
    monkeypatch.setattr(service, "StreamRecorder", lambda output: StreamRecorder(_FullDisk()))
    site = FakeSite(texts=TEXTS)
    started: float = time.monotonic()

    with pytest.raises(TtsClipValidationError) as error:
        _run(_record(fake_engine(tmp_path, site), _request(tmp_path)))

    assert time.monotonic() - started < 2.0
    assert error.value.context.details == {"error_class": "OSError", "errno": errno.ENOSPC}
    _assert_cleaned(site)


class _FullDisk(io.BytesIO):
    def write(self, data: object) -> int:
        raise OSError(errno.ENOSPC, "No space left on device")


@pytest.mark.parametrize("text", UNREADABLE_PARTS)
def test_synthesize_document_part_unreadable_as_paragraph_is_refused_without_browser(tmp_path: Path, text: str) -> None:
    site = FakeSite()

    with pytest.raises(TtsInputError) as error:
        _run(_record(fake_engine(tmp_path, site), _request(tmp_path, texts=("Dobrze.", text))))

    assert error.value.context.details == {"request_id": "line-1"}
    assert site.sessions == []
    assert site.uploaded == []


@pytest.mark.parametrize("text", UNREADABLE_PARTS)
def test_validate_part_unreadable_as_paragraph_raises_input_error(tmp_path: Path, text: str) -> None:
    site = FakeSite()

    with pytest.raises(TtsInputError) as error:
        fake_engine(tmp_path, site).validate_part(DocumentPart(request_id="line-7", text=text))

    assert error.value.context.details == {"request_id": "line-7"}
    assert site.sessions == []


@pytest.mark.parametrize("text", ["Zobacz filmik…", "Raz [dwa].", "  Trzy\ncztery.  "])
def test_validate_part_readable_paragraph_accepts_part(tmp_path: Path, text: str) -> None:
    fake_engine(tmp_path, FakeSite()).validate_part(DocumentPart(request_id="line-0", text=text))


def test_synthesize_document_cancelled_before_start_opens_no_browser(tmp_path: Path) -> None:
    site = FakeSite()
    cancel = TtsCancellation()
    cancel.cancel()

    with pytest.raises(TtsCancelledError):
        _run(fake_engine(tmp_path, site).synthesize_document(_request(tmp_path), cancel=cancel))

    assert site.sessions == []


def test_failed_delete_stays_pending_and_runs_before_next_upload(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, failing={"delete_read"})
    engine = fake_engine(tmp_path, site)

    async def scenario() -> None:
        await _record(engine, _request(tmp_path))
        site.failing.clear()
        site.events.clear()
        await _record(engine, _request(tmp_path))

    _run(scenario())

    assert site.events.index("delete_read") < site.events.index("upload")
    assert len(site.deleted) == 2


def test_close_runs_pending_cleanup_while_browser_lives(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, failing={"delete_read"})
    engine = fake_engine(tmp_path, site)

    async def scenario() -> None:
        await _record(engine, _request(tmp_path))
        site.failing.clear()
        await engine.close()

    _run(scenario())

    assert len(site.deleted) == 1
    assert site.sessions[0].closed


def test_close_with_cleanup_failing_for_good_warns_owner(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, failing={"delete_read", "restore_account"})
    engine = fake_engine(tmp_path, site)
    captured: list[Message] = []
    handler_id: int = loguru_logger.add(captured.append, format="{message} {extra}", level="DEBUG")

    async def scenario() -> None:
        await _record(engine, _request(tmp_path))
        await engine.close()

    try:
        _run(scenario())
    finally:
        loguru_logger.remove(handler_id)

    warnings: list[str] = [str(message) for message in captured if CLEANUP_WARNING in str(message)]
    assert len(warnings) == 1
    assert "restore_settings" in warnings[0]
    assert "delete_read" in warnings[0]
    assert site.sessions[0].closed
    record = read_session(tmp_path)
    assert record is not None
    assert record.restore == AccountSettings(voice_id="previous-voice", speed=1.5)
    assert record.delete_document


class _BrokenTabPage(FakePage):
    async def close(self) -> None:
        await super().close()
        message: str = "tab gone"
        raise RuntimeError(message)


def test_synthesize_document_tab_close_breaking_still_closes_browser(tmp_path: Path) -> None:
    site = FakeSite(texts=TEXTS, listening_speed=3.0, page_type=_BrokenTabPage)

    with pytest.raises(RuntimeError, match="tab gone"):
        _run(_record(fake_engine(tmp_path, site), _request(tmp_path)))

    _assert_cleaned(site)
    assert site.events[-2:] == ["close_page", "close_browser"]
    assert site.sessions[0].closed


def test_synthesize_document_cleanup_breaking_unexpectedly_still_closes_tab_and_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken(page: object, cleanup: object) -> None:
        message: str = "cleanup bug"
        raise RuntimeError(message)

    monkeypatch.setattr(service, "clean_account", broken)
    site = FakeSite(texts=TEXTS, listening_speed=3.0)

    with pytest.raises(RuntimeError, match="cleanup bug"):
        _run(_record(fake_engine(tmp_path, site), _request(tmp_path)))

    assert site.pages[0].closed
    assert site.sessions[0].closed


def test_logs_never_contain_token_read_id_or_stream_address(tmp_path: Path) -> None:
    captured: list[Message] = []
    handler_id: int = loguru_logger.add(captured.append, format="{message} {extra}", level="DEBUG")

    async def scenario() -> None:
        engine = fake_engine(tmp_path, FakeSite(texts=TEXTS))
        await _record(engine, _request(tmp_path))
        failing = fake_engine(tmp_path, FakeSite(texts=TEXTS, failing={"delete_read", "restore_account"}))
        await _record(failing, _request(tmp_path))
        await failing.close()

    try:
        _run(scenario())
    finally:
        loguru_logger.remove(handler_id)

    text: str = "\n".join(str(message) for message in captured)
    assert captured
    assert TOKEN not in text
    assert READ_ID not in text
    assert "wss://" not in text
    assert str(tmp_path) not in text


def test_synthesize_single_request_is_unsupported(tmp_path: Path) -> None:
    request = SynthesisRequest(
        request_id="line-0",
        text="Tekst.",
        voice_id="fronczewski",
        provider_model_id="eleven_v4",
        native_rate=None,
        native_volume=None,
        native_pitch=None,
        options={},
        destination=tmp_path / "clip.mp3",
        deadline_s=1.0,
    )

    with pytest.raises(TtsUnsupportedError):
        _run(fake_engine(tmp_path, FakeSite()).synthesize(request, cancel=TtsCancellation()))


@pytest.mark.parametrize(
    ("change", "error_type"),
    [
        ({"voice_id": ADAM_ID}, TtsInputError),
        ({"voice_id": "dallin"}, TtsVoiceError),
        ({"provider_model_id": "eleven_v2"}, TtsInputError),
        ({"options": {"stability": 0.5}}, TtsUnsupportedError),
        ({"parts": (DocumentPart(request_id="line-0", text="x" * 50_001),)}, TtsInputError),
    ],
)
def test_synthesize_document_invalid_request_is_refused_without_browser(
    tmp_path: Path,
    change: dict[str, object],
    error_type: type[TtsError],
) -> None:
    site = FakeSite()
    base = _request(tmp_path)
    values: dict[str, object] = {
        "request_id": base.request_id,
        "parts": base.parts,
        "voice_id": base.voice_id,
        "provider_model_id": base.provider_model_id,
        "options": base.options,
        "recording": base.recording,
        "deadline_s": base.deadline_s,
    }
    values.update(change)
    request = DocumentSynthesisRequest(**values)  # type: ignore[arg-type]

    with pytest.raises(error_type):
        _run(_record(fake_engine(tmp_path, site), request))

    assert site.sessions == []


def test_availability_without_chrome_reports_missing_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "find_chrome", lambda: None)

    availability = _run(fake_engine(tmp_path, FakeSite()).availability())

    assert availability.status is AvailabilityStatus.MISSING_BINARY


@pytest.mark.parametrize(
    ("signed_in", "status"), [(True, AvailabilityStatus.READY), (False, AvailabilityStatus.MISSING_KEY)]
)
def test_availability_live_reads_saved_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    signed_in: bool,
    status: AvailabilityStatus,
) -> None:
    monkeypatch.setattr(service, "find_chrome", lambda: tmp_path / "chrome.exe")
    write_session(tmp_path, signed_in=signed_in)

    availability = _run(fake_engine(tmp_path, FakeSite()).availability(live=True))

    assert availability.status is status
    assert [voice.id for voice in availability.voices] == [FRONCZEWSKI_ID, ADAM_ID]


def test_availability_live_without_saved_session_reports_missing_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "find_chrome", lambda: tmp_path / "chrome.exe")

    availability = _run(fake_engine(tmp_path, FakeSite()).availability(live=True))

    assert availability.status is AvailabilityStatus.MISSING_KEY


def test_package_import_does_not_load_playwright() -> None:
    script = (
        "import sys\n"
        "import anishift.services.tts.engines.elevenreader\n"
        "loaded = [name for name in sys.modules if name.startswith('playwright')]\n"
        "if loaded:\n"
        "    raise SystemExit(','.join(loaded))\n"
    )

    completed = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[śmiech] No [tak]", "(śmiech) No (tak)"),
        ("Dwie\n linie\t i  spacje ", "Dwie linie i spacje"),
        ("Bez zmian: „cudzysłów”…", "Bez zmian: „cudzysłów”…"),
    ],
)
def test_document_text_part_returns_round_brackets_and_single_spaces(text: str, expected: str) -> None:
    assert document_text((DocumentPart(request_id="a", text=text),)) == expected + "\n"


def test_document_text_parts_returns_separator_paragraph_between_parts() -> None:
    parts = (DocumentPart(request_id="a", text="Raz [dwa]."), DocumentPart(request_id="b", text="Trzy\ncztery."))

    assert document_text(parts) == "Raz (dwa).\n\n…\n\nTrzy cztery.\n"


def test_document_chars_parts_returns_uploaded_text_length(tmp_path: Path) -> None:
    parts = (DocumentPart(request_id="a", text="Raz."), DocumentPart(request_id="b", text="Dwa."))

    assert fake_engine(tmp_path, FakeSite()).document_chars(parts) == len("Raz.\n\n…\n\nDwa.\n")


def test_document_text_single_part_returns_one_paragraph() -> None:
    assert document_text((DocumentPart(request_id="a", text="Tylko."),)) == "Tylko.\n"


def _chunk(text: str, *, offset_ms: float = 0.0, step_ms: float = 10.0) -> AlignmentChunk:
    return AlignmentChunk(
        offset_ms=offset_ms,
        chars=tuple(text),
        starts_ms=tuple(index * step_ms for index in range(len(text))),
        durations_ms=(step_ms,) * len(text),
    )


def _parts(*texts: str) -> tuple[DocumentPart, ...]:
    return tuple(DocumentPart(request_id=f"line-{index}", text=text) for index, text in enumerate(texts))


def _spans(chunks: tuple[AlignmentChunk, ...], *texts: str) -> list[tuple[float, float]]:
    return [(timing.start_ms, timing.end_ms) for timing in part_spans(chunks, _parts(*texts))]


def test_part_spans_break_tags_split_parts_in_server_time() -> None:
    chunks = (_chunk('Ab. <break time="0.6s"/> Cd.'),)

    assert _spans(chunks, "Ab.", "Cd.") == [(0.0, 30.0), (250.0, 280.0)]


def test_part_spans_separator_paragraph_is_not_a_part() -> None:
    chunks = (_chunk('Ab. <break time="0.6s"/> … <break time="0.6s"/> Cd.'),)

    assert _spans(chunks, "Ab.", "Cd.") == [(0.0, 30.0), (480.0, 510.0)]


def test_part_spans_adjacent_break_tags_form_one_boundary() -> None:
    chunks = (_chunk('Ab.<break time="0.6s"/> <break time="0.6s"/>Cd.'),)

    assert _spans(chunks, "Ab.", "Cd.") == [(0.0, 30.0), (440.0, 470.0)]


def test_part_spans_ellipsis_ending_a_part_stays_in_its_text() -> None:
    chunks = (_chunk('Zobacz filmik… <break time="0.6s"/> … <break time="0.6s"/> Cd.'),)

    timings = part_spans(chunks, _parts("Zobacz filmik…", "Cd."))

    assert [(timing.start_ms, timing.end_ms) for timing in timings] == [(0.0, 140.0), (590.0, 620.0)]


def test_part_spans_final_break_adds_no_empty_part() -> None:
    chunks = (_chunk('Ab. <break time="0.6s"/> Cd. <break time="2s"/>'),)

    assert len(_spans(chunks, "Ab.", "Cd.")) == 2


def test_part_spans_tag_cut_between_chunks_still_splits() -> None:
    chunks = (_chunk("Ab. <break ti"), _chunk('me="0.6s"/> Cd.', offset_ms=1000.0))

    assert _spans(chunks, "Ab.", "Cd.") == [(0.0, 30.0), (1120.0, 1150.0)]


def test_part_spans_unclosed_tag_at_end_is_dropped() -> None:
    chunks = (_chunk('Ab. <break time="2'),)

    assert _spans(chunks, "Ab.") == [(0.0, 30.0)]


def test_part_spans_surrounding_whitespace_is_trimmed() -> None:
    chunks = (_chunk("  Ab  "),)

    assert _spans(chunks, "Ab") == [(20.0, 40.0)]


def test_part_spans_bracketed_part_matches_round_brackets_in_server_text() -> None:
    chunks = (_chunk("(Ab)"),)

    assert _spans(chunks, "[Ab]") == [(0.0, 40.0)]


def test_part_spans_count_mismatch_raises_clip_error() -> None:
    chunks = (_chunk('Ab. <break time="0.6s"/> Cd.'),)

    with pytest.raises(TtsClipValidationError, match="line count mismatch"):
        part_spans(chunks, _parts("Ab. Cd."))


def test_part_spans_text_mismatch_raises_clip_error() -> None:
    chunks = (_chunk('Ab. <break time="0.6s"/> Cd.'),)

    with pytest.raises(TtsClipValidationError, match="line text mismatch"):
        part_spans(chunks, _parts("Ab.", "Ef."))


def test_part_spans_no_chunks_and_no_parts_returns_nothing() -> None:
    assert part_spans((), ()) == ()
