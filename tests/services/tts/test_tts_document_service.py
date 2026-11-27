from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.tts import (
    AudioFormat,
    AvailabilityProbeKind,
    AvailabilitySource,
    AvailabilityStatus,
    CancellationToken,
    ClipExpectation,
    ClipSpan,
    ClipValidation,
    DocumentPart,
    DocumentSynthesisRequest,
    DocumentTtsEngine,
    EngineAvailability,
    EngineCapabilities,
    EngineClipResult,
    EngineDocumentResult,
    EngineLocality,
    PartTiming,
    SpeechBatch,
    SpeechBatchProgress,
    SpeechBatchResult,
    SpeechBatchStatus,
    SpeechRequest,
    SpeechRequestProgress,
    SpeechRetryProgress,
    SplitResult,
    SynthesisProfile,
    SynthesisRequest,
    SynthesisStatus,
    TtsCancelledError,
    TtsClipValidationError,
    TtsConfig,
    TtsError,
    TtsInputError,
    TtsQuotaError,
    TtsService,
    TtsUnsupportedError,
    VoiceInfo,
)

pytestmark = pytest.mark.unit

_RECORDING: bytes = b"\xff\xfb\x90\x00" + bytes(413)
_NO_AUDIO: bytes = b"recording"


class _Validator:
    def validate_clip(self, path: Path, expectation: ClipExpectation) -> ClipValidation | None:
        if path.is_file() and path.read_bytes() == b"valid":
            return ClipValidation(format=expectation.format, sample_rate=48000, channels=1, duration_ms=500)
        return None


class _Progress:
    def __init__(self) -> None:
        self.batches: list[SpeechBatchProgress] = []
        self.requests: list[SpeechRequestProgress] = []
        self.retries: list[SpeechRetryProgress] = []

    def on_batch_state(self, state: SpeechBatchProgress) -> None:
        self.batches.append(state)

    def on_request_committed(self, update: SpeechRequestProgress) -> None:
        self.requests.append(update)

    def on_request_retry(self, update: SpeechRetryProgress) -> None:
        self.retries.append(update)


class _DocumentEngine:
    engine_id = "document"
    is_available = True
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
        max_text_chars=40,
        max_text_bytes=None,
        availability_probe=AvailabilityProbeKind.CONFIG,
        reads_documents=True,
    )
    synthesis_profile = SynthesisProfile(
        engine_id="document",
        endpoint_id="document-v1",
        provider_model_id="document-model",
        resolved_voice_id="document-voice",
        provider_output_id="pcm-cut",
        provider_source_format=AudioFormat.WAV,
        adapter_version="document:v1",
    )

    def __init__(  # noqa: PLR0913
        self,
        *,
        failures: tuple[TtsError, ...] = (),
        drop_timing_once: bool = False,
        wrong_voice_once: bool = False,
        speaks_up_to: dict[str, int] | None = None,
        incomplete: frozenset[str] = frozenset(),
        incomplete_cause: ErrorContext | None = None,
        recording: bytes = _RECORDING,
        fault: Exception | None = None,
    ) -> None:
        self.recording: bytes = recording
        self.fault: Exception | None = fault
        self.on_recorded: Callable[[], None] | None = None
        self.speaks_up_to: dict[str, int] = speaks_up_to or {}
        self.incomplete: frozenset[str] = incomplete
        self.incomplete_cause: ErrorContext | None = incomplete_cause
        self.documents: list[tuple[str, ...]] = []
        self.document_ids: list[str] = []
        self.recordings: list[Path] = []
        self.stale_files: list[list[str]] = []
        self.failures: list[TtsError] = list(failures)
        self.drop_timing_once: bool = drop_timing_once
        self.wrong_voice_once: bool = wrong_voice_once
        self.closed: int = 0

    async def availability(self, *, live: bool = False) -> EngineAvailability:
        del live
        return EngineAvailability(
            status=AvailabilityStatus.READY,
            message="ready",
            checked_at=datetime.now(UTC),
            source=AvailabilitySource.CONFIG,
        )

    async def list_voices(self) -> tuple[VoiceInfo, ...]:
        return ()

    async def synthesize(self, request: SynthesisRequest, *, cancel: CancellationToken) -> EngineClipResult:
        del request, cancel
        raise TtsUnsupportedError("document engine")

    def validate_part(self, part: DocumentPart) -> None:
        if "<break" in part.text:
            raise TtsInputError(part.request_id)

    async def synthesize_document(
        self,
        request: DocumentSynthesisRequest,
        *,
        cancel: CancellationToken,
    ) -> EngineDocumentResult:
        assert not cancel.is_cancelled
        for part in request.parts:
            self.validate_part(part)
        self.documents.append(tuple(part.request_id for part in request.parts))
        self.document_ids.append(request.request_id)
        self.recordings.append(request.recording)
        self.stale_files.append(
            sorted(path.name for path in request.recording.parent.glob(".clip-*") if path != request.recording)
        )
        head: str = request.recording.name.partition(".mp3")[0]
        request.recording.with_name(f"{head}.take1.mp3").write_bytes(b"take")
        request.recording.with_name(f"{head}.take1.stream.txt").write_text("take", encoding="utf-8")
        if self.failures:
            raise self.failures.pop(0)
        request.recording.write_bytes(self.recording)
        request.recording.with_name(f"{head}.stream.txt").write_text("result", encoding="utf-8")
        if self.fault is not None:
            raise self.fault
        if self.on_recorded is not None:
            self.on_recorded()
        total: int = sum(len(part.text) for part in request.parts)
        if request.progress is not None:
            await request.progress(total // 2, total)
            await request.progress(total, total)
        timings: tuple[PartTiming, ...] = tuple(
            PartTiming(
                request_id=part.request_id,
                start_ms=index * 1000.0,
                end_ms=index * 1000.0
                + (500.0 if len(request.parts) <= self.speaks_up_to.get(part.text, len(request.parts)) else 0.0),
            )
            for index, part in enumerate(request.parts)
        )
        if self.drop_timing_once:
            self.drop_timing_once = False
            timings = timings[:-1]
        voice_id: str = "other-voice" if self.wrong_voice_once else "document-voice"
        self.wrong_voice_once = False
        return EngineDocumentResult(
            request_id=request.request_id,
            recording=request.recording,
            format=AudioFormat.MP3,
            engine_id=self.engine_id,
            provider_model_id="document-model",
            voice_id=voice_id,
            request_time_ms=5.0,
            parts=timings,
            incomplete=tuple(part.request_id for part in request.parts if part.text in self.incomplete),
            incomplete_cause=self.incomplete_cause,
        )

    async def close(self) -> None:
        self.closed += 1


class _Splitter:
    def __init__(
        self,
        *,
        failures: tuple[Exception, ...] = (),
        invalid_clip: str = "",
        missing_clip_once: bool = False,
        uncertain_boundaries: int = 0,
    ) -> None:
        self.calls: list[tuple[ClipSpan, ...]] = []
        self.sources: list[Path] = []
        self.failures: list[Exception] = list(failures)
        self.invalid_clip: str = invalid_clip
        self.missing_clip_once: bool = missing_clip_once
        self.uncertain_boundaries: int = uncertain_boundaries
        self.service: TtsService | None = None
        self.cancel_after_split: bool = False

    def split_clip(self, source: Path, spans: tuple[ClipSpan, ...], expectation: ClipExpectation) -> SplitResult:
        assert source.read_bytes() in {_RECORDING, _NO_AUDIO}
        assert expectation.format is AudioFormat.WAV
        self.calls.append(spans)
        self.sources.append(source)
        if self.failures:
            raise self.failures.pop(0)
        for span in spans:
            span.destination.write_bytes(b"invalid" if span.request_id == self.invalid_clip else b"valid")
        if self.cancel_after_split and self.service is not None:
            self.service.cancel()
        written: tuple[str, ...] = tuple(span.request_id for span in spans)
        if self.missing_clip_once:
            self.missing_clip_once = False
            written = written[:-1]
        return SplitResult(written=written, uncertain_boundaries=self.uncertain_boundaries)


def _config() -> TtsConfig:
    return TtsConfig(
        engine_id="document",
        provider_model_id="document-model",
        voice_id="document-voice",
        max_concurrency=1,
        queue_capacity=2,
        retry_backoff_seconds=(0.0,),
        request_timeout_s=5.0,
        shutdown_deadline_s=1.0,
    )


def _batch(*texts: str, scope_id: str = "episode") -> SpeechBatch:
    return SpeechBatch(
        scope_id=scope_id,
        batch_rank=0,
        requests=tuple(
            SpeechRequest(request_id=f"line-{index}", text=text, request_rank=index) for index, text in enumerate(texts)
        ),
    )


def _service(
    tmp_path: Path,
    engine: _DocumentEngine,
    splitter: _Splitter | None,
) -> TtsService:
    service = TtsService(
        _config(),
        resume_root=tmp_path,
        validator=_Validator(),
        splitter=splitter,
        engine_factory=lambda config: engine,
    )
    if splitter is not None:
        splitter.service = service
    return service


def _run(
    tmp_path: Path,
    engine: _DocumentEngine,
    splitter: _Splitter | None,
    *batches: SpeechBatch,
) -> list[SpeechBatchResult]:
    with _service(tmp_path, engine, splitter) as service:
        return [service.synthesize(batch, callbacks=_Progress()) for batch in batches]


def _statuses(result: SpeechBatchResult) -> list[SynthesisStatus]:
    return [item.status for item in result.requests]


def test_document_tts_engine_fake_engine_satisfies_protocol() -> None:
    assert isinstance(_DocumentEngine(), DocumentTtsEngine)


def test_document_batch_mixed_lines_commits_speech_and_skips_non_speech(tmp_path: Path) -> None:
    engine = _DocumentEngine()
    splitter = _Splitter()

    (result,) = _run(tmp_path, engine, splitter, _batch("Raz dwa.", "♪", "Trzy cztery."))

    assert result.status is SpeechBatchStatus.COMPLETED
    assert _statuses(result) == [SynthesisStatus.SYNTHESIZED, SynthesisStatus.SKIPPED, SynthesisStatus.SYNTHESIZED]
    assert engine.documents == [("line-0", "line-2")]
    clips = [item.speech_clip for item in result.requests if item.speech_clip is not None]
    assert [clip.format for clip in clips] == [AudioFormat.WAV, AudioFormat.WAV]
    assert all(clip.path.read_bytes() == b"valid" for clip in clips)
    assert result.stats.provider_calls == 1
    assert engine.closed == 1


def test_document_batch_success_discards_recording_and_temporary_clips(tmp_path: Path) -> None:
    engine = _DocumentEngine()

    _run(tmp_path, engine, _Splitter(), _batch("Raz dwa.", "Trzy cztery."))

    assert engine.recordings
    assert not any(path.exists() for path in engine.recordings)
    assert list((tmp_path / "episode").rglob("*.tmp")) == []
    assert list((tmp_path / "episode").rglob(".clip-*")) == []


def test_document_batch_failed_and_retried_recording_leaves_no_engine_file(tmp_path: Path) -> None:
    engine = _DocumentEngine(failures=(TtsClipValidationError("cut"), TtsQuotaError("no credits")))

    _run(tmp_path, engine, _Splitter(), _batch("Raz dwa."))

    assert len(engine.documents) == 2
    assert engine.stale_files == [[], []]
    assert list((tmp_path / "episode").rglob(".clip-*")) == []


def test_document_batch_all_lines_resumed_makes_no_engine_call(tmp_path: Path) -> None:
    engine = _DocumentEngine()
    batch = _batch("Raz dwa.", "Trzy cztery.")

    first, second = _run(tmp_path, engine, _Splitter(), batch, batch)

    assert _statuses(first) == [SynthesisStatus.SYNTHESIZED, SynthesisStatus.SYNTHESIZED]
    assert _statuses(second) == [SynthesisStatus.RESUME_HIT, SynthesisStatus.RESUME_HIT]
    assert engine.documents == [("line-0", "line-1")]
    assert second.stats.provider_calls == 0


def test_document_batch_partial_resume_reads_only_missing_lines(tmp_path: Path) -> None:
    engine = _DocumentEngine()

    _first, second = _run(
        tmp_path,
        engine,
        _Splitter(),
        _batch("Raz dwa.", "Trzy cztery."),
        _batch("Raz dwa.", "Trzy cztery.", "Pięć sześć."),
    )

    assert engine.documents == [("line-0", "line-1"), ("line-2",)]
    assert _statuses(second) == [
        SynthesisStatus.RESUME_HIT,
        SynthesisStatus.RESUME_HIT,
        SynthesisStatus.SYNTHESIZED,
    ]


def test_document_batch_lines_far_over_the_old_document_limit_are_one_document(tmp_path: Path) -> None:
    engine = _DocumentEngine()
    lines: list[str] = [f"Kwestia {number} ma dość znaków." for number in range(2_000)]

    (result,) = _run(tmp_path, engine, _Splitter(), _batch(*lines))

    assert sum(len(line) for line in lines) > 50_000
    assert engine.documents == [tuple(f"line-{number}" for number in range(2_000))]
    assert result.status is SpeechBatchStatus.COMPLETED


def test_document_batch_same_scope_documents_in_one_run_get_distinct_ids(tmp_path: Path) -> None:
    engine = _DocumentEngine()

    _run(tmp_path, engine, _Splitter(), _batch("Raz dwa.", "Trzy."), _batch("Cztery pięć."))

    assert engine.document_ids == ["episode:document:0", "episode:document:1"]


def test_document_batch_line_over_text_limit_fails_only_that_line(tmp_path: Path) -> None:
    engine = _DocumentEngine()
    too_long: str = " ".join(["słowo"] * 10) + "."

    (result,) = _run(tmp_path, engine, _Splitter(), _batch("Raz dwa.", too_long))

    assert _statuses(result) == [SynthesisStatus.SYNTHESIZED, SynthesisStatus.FAILED]
    assert result.requests[1].error_code == "TTS_INPUT_INVALID"
    assert engine.documents == [("line-0",)]
    assert result.status is SpeechBatchStatus.PARTIAL


def test_document_batch_part_refused_by_engine_fails_only_that_line(tmp_path: Path) -> None:
    engine = _DocumentEngine()

    (result,) = _run(tmp_path, engine, _Splitter(), _batch("Raz dwa.", "Trzy <break cztery.", "Pięć."))

    assert _statuses(result) == [SynthesisStatus.SYNTHESIZED, SynthesisStatus.FAILED, SynthesisStatus.SYNTHESIZED]
    assert result.requests[1].error_code == "TTS_INPUT_INVALID"
    assert engine.documents == [("line-0", "line-2")]
    assert result.stats.provider_calls == 1
    assert result.status is SpeechBatchStatus.PARTIAL


def test_document_batch_part_the_server_did_not_speak_fails_only_that_line(tmp_path: Path) -> None:
    engine = _DocumentEngine(speaks_up_to={"j g": 0})
    splitter = _Splitter()

    (result,) = _run(tmp_path, engine, splitter, _batch("Raz dwa.", "j g", "Pięć."))

    assert _statuses(result) == [SynthesisStatus.SYNTHESIZED, SynthesisStatus.FAILED, SynthesisStatus.SYNTHESIZED]
    assert result.requests[1].error_code == "TTS_INPUT_INVALID"
    assert engine.documents == [("line-0", "line-1", "line-2"), ("line-1",)]
    assert [[span.request_id for span in spans] for spans in splitter.calls] == [["line-0", "line-2"]]
    assert result.stats.provider_calls == 2
    assert result.status is SpeechBatchStatus.PARTIAL


def test_document_batch_line_still_missing_words_after_redo_fails_alone_without_another_read(tmp_path: Path) -> None:
    engine = _DocumentEngine(incomplete=frozenset({"Trzy cztery."}))
    splitter = _Splitter()

    (result,) = _run(tmp_path, engine, splitter, _batch("Raz dwa.", "Trzy cztery.", "Pięć."))

    assert _statuses(result) == [SynthesisStatus.SYNTHESIZED, SynthesisStatus.FAILED, SynthesisStatus.SYNTHESIZED]
    assert result.requests[1].error_code == "TTS_INPUT_INVALID"
    assert engine.documents == [("line-0", "line-1", "line-2")]
    assert [[span.request_id for span in spans] for spans in splitter.calls] == [["line-0", "line-1", "line-2"]]
    assert result.requests[1].speech_clip is None
    assert result.status is SpeechBatchStatus.PARTIAL


def test_document_batch_incomplete_line_fails_with_the_cause_that_stopped_its_redo(tmp_path: Path) -> None:
    cause = ErrorContext(code=ErrorCode.TTS_AUTH_FAILED, message="refused", suggestion="sign in again")
    engine = _DocumentEngine(incomplete=frozenset({"Trzy cztery."}), incomplete_cause=cause)

    (result,) = _run(tmp_path, engine, _Splitter(), _batch("Raz dwa.", "Trzy cztery."))

    assert _statuses(result) == [SynthesisStatus.SYNTHESIZED, SynthesisStatus.FAILED]
    assert result.requests[1].error_code == "TTS_AUTH_FAILED"
    assert result.failure == cause
    assert len(engine.documents) == 1


def test_document_batch_lines_silent_in_large_document_are_spoken_after_reading_them_together(
    tmp_path: Path,
) -> None:
    engine = _DocumentEngine(speaks_up_to={"Dwa.": 2, "Pięć.": 2})
    splitter = _Splitter()

    (result,) = _run(tmp_path, engine, splitter, _batch("Raz.", "Dwa.", "Trzy.", "Pięć."))

    assert result.status is SpeechBatchStatus.COMPLETED
    assert _statuses(result) == [SynthesisStatus.SYNTHESIZED] * 4
    assert engine.documents == [("line-0", "line-1", "line-2", "line-3"), ("line-1", "line-3")]
    assert [[span.request_id for span in spans] for spans in splitter.calls] == [
        ["line-0", "line-2"],
        ["line-1", "line-3"],
    ]
    assert result.stats.provider_calls == 2


def test_document_batch_lines_silent_with_other_lines_are_spoken_when_read_alone(tmp_path: Path) -> None:
    engine = _DocumentEngine(speaks_up_to={"Dwa.": 1, "Pięć.": 1})

    (result,) = _run(tmp_path, engine, _Splitter(), _batch("Raz.", "Dwa.", "Trzy.", "Pięć."))

    assert result.status is SpeechBatchStatus.COMPLETED
    assert _statuses(result) == [SynthesisStatus.SYNTHESIZED] * 4
    assert engine.documents == [
        ("line-0", "line-1", "line-2", "line-3"),
        ("line-1", "line-3"),
        ("line-1",),
        ("line-3",),
    ]
    assert result.stats.provider_calls == 4


def test_document_batch_line_silent_even_alone_fails_alone_after_bounded_rereads(tmp_path: Path) -> None:
    engine = _DocumentEngine(speaks_up_to={"Dwa.": 0, "Pięć.": 1})
    progress = _Progress()

    with _service(tmp_path, engine, _Splitter()) as service:
        result = service.synthesize(_batch("Raz.", "Dwa.", "Trzy.", "Pięć."), callbacks=progress)

    assert _statuses(result) == [
        SynthesisStatus.SYNTHESIZED,
        SynthesisStatus.FAILED,
        SynthesisStatus.SYNTHESIZED,
        SynthesisStatus.SYNTHESIZED,
    ]
    assert result.requests[1].error_code == "TTS_INPUT_INVALID"
    assert result.failure is not None
    assert "own document" in result.failure.message
    assert result.status is SpeechBatchStatus.PARTIAL
    assert engine.documents == [
        ("line-0", "line-1", "line-2", "line-3"),
        ("line-1", "line-3"),
        ("line-1",),
        ("line-3",),
    ]
    assert result.stats.provider_calls == 4
    assert sorted(update.request_id for update in progress.requests) == ["line-0", "line-1", "line-2", "line-3"]


def test_document_batch_every_line_silent_reads_each_alone_once(tmp_path: Path) -> None:
    engine = _DocumentEngine(speaks_up_to={"Raz.": 0, "Dwa.": 0})

    (result,) = _run(tmp_path, engine, _Splitter(), _batch("Raz.", "Dwa."))

    assert _statuses(result) == [SynthesisStatus.FAILED, SynthesisStatus.FAILED]
    assert engine.documents == [("line-0", "line-1"), ("line-0",), ("line-1",)]
    assert result.stats.provider_calls == 3
    assert result.status is SpeechBatchStatus.FAILED


def test_document_batch_without_any_spoken_part_fails_its_lines_without_split(tmp_path: Path) -> None:
    engine = _DocumentEngine(speaks_up_to={"j g": 0})
    splitter = _Splitter()

    (result,) = _run(tmp_path, engine, splitter, _batch("j g"))

    assert _statuses(result) == [SynthesisStatus.FAILED]
    assert result.requests[0].error_code == "TTS_INPUT_INVALID"
    assert engine.documents == [("line-0",)]
    assert splitter.calls == []


@pytest.mark.parametrize(
    ("splitter", "cuts"),
    [
        (_Splitter(failures=(RuntimeError("cut failed"), RuntimeError("cut failed"))), 2),
        (_Splitter(failures=(ValueError("no frames"),)), 1),
        (_Splitter(missing_clip_once=True), 1),
    ],
    ids=["split_failure_twice", "unreadable_recording", "missing_clip"],
)
def test_document_batch_recording_that_cannot_be_cut_fails_its_lines_without_recording_again(
    tmp_path: Path, splitter: _Splitter, cuts: int
) -> None:
    engine = _DocumentEngine()

    (result,) = _run(tmp_path, engine, splitter, _batch("Raz dwa.", "Trzy cztery."))

    assert _statuses(result) == [SynthesisStatus.FAILED, SynthesisStatus.FAILED]
    assert [item.error_code for item in result.requests] == ["TTS_CLIP_INVALID", "TTS_CLIP_INVALID"]
    assert len(engine.documents) == 1
    assert len(splitter.calls) == cuts
    assert not any(span.destination.exists() for span in splitter.calls[0])


def test_document_batch_splitter_fault_fails_its_lines_without_recording_again(tmp_path: Path) -> None:
    engine = _DocumentEngine()
    splitter = _Splitter(failures=(IndexError("bug"),) * 6)

    (result,) = _run(tmp_path, engine, splitter, _batch("Raz dwa.", "Trzy cztery."))

    assert [item.error_code for item in result.requests] == ["TTS_CLIP_INVALID", "TTS_CLIP_INVALID"]
    assert len(engine.documents) == 1
    assert len(splitter.calls) == 1


def test_document_batch_engine_fault_after_recording_fails_its_lines_without_recording_again(tmp_path: Path) -> None:
    engine = _DocumentEngine(fault=OSError("disk"))
    splitter = _Splitter()

    (result,) = _run(tmp_path, engine, splitter, _batch("Raz dwa.", "Trzy cztery."))

    assert [item.error_code for item in result.requests] == ["TTS_CLIP_INVALID", "TTS_CLIP_INVALID"]
    assert len(engine.documents) == 1
    assert splitter.calls == []
    assert list((tmp_path / "episode").rglob(".clip-*")) == []


@pytest.mark.parametrize(
    "failures",
    [(RuntimeError("cut failed"), RuntimeError("cut failed")), (IndexError("bug"),)],
    ids=["split_failure_twice", "splitter_fault"],
)
def test_document_batch_recording_that_cannot_be_cut_is_kept_and_cut_on_retry_without_recording_again(
    tmp_path: Path, failures: tuple[Exception, ...]
) -> None:
    engine = _DocumentEngine()
    batch: SpeechBatch = _batch("Raz dwa.", "Trzy cztery.")

    (failed,) = _run(tmp_path, engine, _Splitter(failures=failures), batch)
    kept: list[Path] = sorted((tmp_path / "episode").rglob("document-*"))
    splitter = _Splitter()
    (retried,) = _run(tmp_path, engine, splitter, batch)

    assert _statuses(failed) == [SynthesisStatus.FAILED, SynthesisStatus.FAILED]
    assert failed.failure is not None
    assert "without recording" in failed.failure.suggestion
    assert [path.suffix for path in kept] == [".json", ".mp3"]
    assert _statuses(retried) == [SynthesisStatus.SYNTHESIZED, SynthesisStatus.SYNTHESIZED]
    assert len(engine.documents) == 1
    assert splitter.sources == [kept[1]]
    assert list((tmp_path / "episode").rglob("document-*")) == []
    assert list((tmp_path / "episode").rglob(".clip-*")) == []


def test_document_batch_cancelled_during_redo_keeps_the_recording_and_the_retry_cuts_it(tmp_path: Path) -> None:
    engine = _DocumentEngine(incomplete=frozenset({"Trzy cztery."}))
    batch: SpeechBatch = _batch("Raz dwa.", "Trzy cztery.")

    with _service(tmp_path, engine, _Splitter()) as service:
        engine.on_recorded = service.cancel
        cancelled: SpeechBatchResult = service.synthesize(batch, callbacks=_Progress())
    kept: list[Path] = sorted((tmp_path / "episode").rglob("document-*"))
    engine.on_recorded = None
    engine.incomplete = frozenset()
    splitter = _Splitter()
    (retried,) = _run(tmp_path, engine, splitter, batch)
    leftover: list[Path] = list((tmp_path / "episode").rglob("document-*"))
    (redone,) = _run(tmp_path, engine, _Splitter(), batch)

    assert cancelled.status is SpeechBatchStatus.CANCELLED
    assert _statuses(cancelled) == [SynthesisStatus.CANCELLED, SynthesisStatus.CANCELLED]
    assert [path.suffix for path in kept] == [".json", ".mp3"]
    assert _statuses(retried) == [SynthesisStatus.SYNTHESIZED, SynthesisStatus.FAILED]
    assert splitter.sources == [kept[1]]
    assert leftover == []
    assert list((tmp_path / "episode").rglob(".clip-*")) == []
    assert _statuses(redone) == [SynthesisStatus.RESUME_HIT, SynthesisStatus.SYNTHESIZED]
    assert engine.documents == [("line-0", "line-1"), ("line-1",)]


def test_document_batch_recording_without_audio_is_not_kept_and_is_recorded_on_retry(tmp_path: Path) -> None:
    engine = _DocumentEngine(recording=_NO_AUDIO)
    batch: SpeechBatch = _batch("Raz dwa.", "Trzy cztery.")

    (failed,) = _run(tmp_path, engine, _Splitter(failures=(ValueError("no frames"),)), batch)
    kept: list[Path] = list((tmp_path / "episode").rglob("document-*"))
    _run(tmp_path, engine, _Splitter(failures=(ValueError("no frames"),)), batch)

    assert failed.failure is not None
    assert "recorded again" in failed.failure.suggestion
    assert kept == []
    assert len(engine.documents) == 2
    assert list((tmp_path / "episode").rglob("document-*")) == []


def test_document_batch_invalid_clip_fails_only_its_line_without_recording_again(tmp_path: Path) -> None:
    engine = _DocumentEngine()

    (result,) = _run(tmp_path, engine, _Splitter(invalid_clip="line-0"), _batch("Raz dwa.", "Trzy cztery."))

    assert _statuses(result) == [SynthesisStatus.FAILED, SynthesisStatus.SYNTHESIZED]
    assert result.requests[0].error_code == "TTS_CLIP_INVALID"
    assert result.requests[1].speech_clip is not None
    assert result.requests[1].speech_clip.path.read_bytes() == b"valid"
    assert len(engine.documents) == 1


def test_document_batch_split_cancelled_by_decoder_ends_as_cancellation(tmp_path: Path) -> None:
    engine = _DocumentEngine()
    splitter = _Splitter(failures=(TtsCancelledError("decode cancelled"),))

    (result,) = _run(tmp_path, engine, splitter, _batch("Raz dwa.", "Trzy cztery."))

    assert [item.error_code for item in result.requests] == ["CANCELLED", "CANCELLED"]
    assert len(engine.documents) == 1


def test_document_batch_split_failing_once_is_cut_again_without_recording_again(tmp_path: Path) -> None:
    engine = _DocumentEngine()
    splitter = _Splitter(failures=(RuntimeError("decode timed out"),))

    (result,) = _run(tmp_path, engine, splitter, _batch("Raz dwa.", "Trzy cztery."))

    assert result.status is SpeechBatchStatus.COMPLETED
    assert len(engine.documents) == 1
    assert len(splitter.calls) == 2


def test_document_batch_uncertain_boundaries_commits_every_line(tmp_path: Path) -> None:
    engine = _DocumentEngine()

    (result,) = _run(tmp_path, engine, _Splitter(uncertain_boundaries=1), _batch("Raz dwa", "Trzy cztery."))

    assert _statuses(result) == [SynthesisStatus.SYNTHESIZED, SynthesisStatus.SYNTHESIZED]
    assert len(engine.documents) == 1


@pytest.mark.parametrize(
    "engine",
    [_DocumentEngine(wrong_voice_once=True), _DocumentEngine(drop_timing_once=True)],
    ids=["unowned_result", "timing_count_mismatch"],
)
def test_document_batch_result_breaking_the_contract_fails_its_lines_without_recording_again(
    tmp_path: Path, engine: _DocumentEngine
) -> None:
    splitter = _Splitter()

    (result,) = _run(tmp_path, engine, splitter, _batch("Raz dwa.", "Trzy cztery."))

    assert _statuses(result) == [SynthesisStatus.FAILED, SynthesisStatus.FAILED]
    assert [item.error_code for item in result.requests] == ["TTS_CLIP_INVALID", "TTS_CLIP_INVALID"]
    assert len(engine.documents) == 1
    assert splitter.calls == []
    assert list((tmp_path / "episode").rglob(".clip-*")) == []


def test_document_batch_quota_error_opens_circuit_for_next_document(tmp_path: Path) -> None:
    engine = _DocumentEngine(failures=(TtsQuotaError("no credits"),))
    line: str = "Piętnaście zn."

    result, _ = _run(tmp_path, engine, _Splitter(), _batch(line, line, line), _batch("Cztery pięć."))

    assert result.status is SpeechBatchStatus.FAILED
    assert [item.error_code for item in result.requests] == ["TTS_QUOTA_EXHAUSTED"] * 3
    assert engine.documents == [("line-0", "line-1", "line-2")]
    assert result.failure is not None
    assert result.failure.code.value == "TTS_QUOTA_EXHAUSTED"


def test_document_batch_engine_progress_reports_received_lines(tmp_path: Path) -> None:
    engine = _DocumentEngine()
    progress = _Progress()

    with _service(tmp_path, engine, _Splitter()) as service:
        service.synthesize(_batch("Raz dwa.", "Trzy cztery."), callbacks=progress)

    received: list[int] = [
        state.received_required_requests for state in progress.batches if state.committed_required_requests == 0
    ]
    assert received[-2:] == [1, 2]
    assert progress.batches[-1].committed_required_requests == 2
    assert progress.batches[-1].status is SpeechBatchStatus.COMPLETED


def test_document_batch_without_splitter_fails_speech_lines_as_unsupported(tmp_path: Path) -> None:
    engine = _DocumentEngine()

    (result,) = _run(tmp_path, engine, None, _batch("Raz dwa.", "♪"))

    assert _statuses(result) == [SynthesisStatus.FAILED, SynthesisStatus.SKIPPED]
    assert result.requests[0].error_code == "TTS_UNSUPPORTED"
    assert engine.documents == []


def test_document_batch_line_endings_set_open_end(tmp_path: Path) -> None:
    splitter = _Splitter()

    _run(tmp_path, _DocumentEngine(), splitter, _batch("Kiedy wrócisz", "Jutro.", "Naprawdę?”"))

    assert [span.open_end for span in splitter.calls[0]] == [True, False, False]
    assert [(span.start_ms, span.end_ms) for span in splitter.calls[0]] == [
        (0.0, 500.0),
        (1000.0, 1500.0),
        (2000.0, 2500.0),
    ]


def test_document_batch_cancel_before_commit_keeps_no_clip(tmp_path: Path) -> None:
    splitter = _Splitter()
    splitter.cancel_after_split = True

    (result,) = _run(tmp_path, _DocumentEngine(), splitter, _batch("Raz dwa.", "Trzy cztery."))

    assert result.status is SpeechBatchStatus.CANCELLED
    assert _statuses(result) == [SynthesisStatus.CANCELLED, SynthesisStatus.CANCELLED]
    assert list((tmp_path / "episode").rglob("clip-*")) == []
    assert list((tmp_path / "episode").rglob("*.tmp")) == []


def test_document_batch_cancel_during_retry_delay_ends_at_once_without_another_attempt(tmp_path: Path) -> None:
    engine = _DocumentEngine(failures=(TtsClipValidationError("cut"),))
    progress = _Progress()
    results: list[SpeechBatchResult] = []
    with TtsService(
        replace(_config(), retry_backoff_seconds=(600.0,)),
        resume_root=tmp_path,
        validator=_Validator(),
        splitter=_Splitter(),
        engine_factory=lambda config: engine,
    ) as service:
        worker = threading.Thread(
            target=lambda: results.append(service.synthesize(_batch("Raz dwa."), callbacks=progress))
        )
        worker.start()
        deadline: float = time.monotonic() + 5.0
        while not progress.retries and time.monotonic() < deadline:
            time.sleep(0.01)
        cancelled_at: float = time.monotonic()
        service.cancel()
        worker.join(timeout=5.0)
        ended_after: float = time.monotonic() - cancelled_at

    assert progress.retries
    assert not worker.is_alive()
    assert ended_after < 2.0
    assert results[0].status is SpeechBatchStatus.CANCELLED
    assert engine.documents == [("line-0",)]


def test_document_batch_line_engine_with_splitter_uses_line_path(tmp_path: Path) -> None:
    class _LineEngine(_DocumentEngine):
        capabilities = replace(_DocumentEngine.capabilities, reads_documents=False)

    engine = _LineEngine()

    (result,) = _run(tmp_path, engine, _Splitter(), _batch("Raz dwa."))

    assert engine.documents == []
    assert result.requests[0].error_code == "TTS_UNSUPPORTED"
