from __future__ import annotations

import json
import threading
import wave
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.cancellation import EventCancellationToken, NeverCancelledToken
from anishift.application.events import WorkerNotification
from anishift.application.intents import NarrationTimeline
from anishift.application.planning import ExecutionPlan, PlanTask, ProcessingOrderPolicy, RunSettingsSnapshot, TaskKind
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.application.runtime import ProductionHandlerFactory
from anishift.application.sign_narration import write_sign_candidates
from anishift.application.tts_clips import FfmpegClipService
from anishift.application.tts_handler import (
    NarrationTiming,
    TtsProgressObserver,
    TtsTaskHandler,
    build_narration_manifest,
    load_narration_manifest,
)
from anishift.config.settings import Settings
from anishift.errors import ErrorCode, ErrorContext, ExecutionError
from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.audio.commands import CommandResult
from anishift.services.audio.errors import AudioProcessError
from anishift.services.audio.types import NormalizedClip, PcmStorage, TimedClip
from anishift.services.subtitles import SignCandidate
from anishift.services.tts import (
    AudioFormat,
    ClipExpectation,
    SpeechBatch,
    SpeechBatchProgress,
    SpeechBatchResult,
    SpeechBatchStats,
    SpeechBatchStatus,
    SpeechClip,
    SpeechRequest,
    SynthesisStatus,
    SynthesizedRequest,
)

_SPOKEN_PARAMETERS: tuple[tuple[str, str | int | bool], ...] = (
    ("narration_timeline", "source_times"),
    ("script_kind", "spoken_pl"),
)


class _Progress:
    def __init__(self) -> None:
        self.notifications: list[WorkerNotification] = []

    def emit(self, notification: WorkerNotification) -> None:
        self.notifications.append(notification)


class _Tts:
    def __init__(self, root: Path) -> None:
        self.root: Path = root
        self.batches: list[SpeechBatch] = []
        self.close_calls: int = 0

    def synthesize(self, batch: SpeechBatch, *, callbacks: TtsProgressObserver) -> SpeechBatchResult:
        del callbacks
        self.batches.append(batch)
        executions: list[SynthesizedRequest] = []
        for request in batch.requests:
            path = self.root / f"{request.request_id}.mp3"
            path.write_bytes(b"audio")
            clip = SpeechClip(
                request.request_id,
                path,
                AudioFormat.MP3,
                24_000,
                1,
                500,
                "edge",
                "edge-default",
                "voice",
                1,
                10.0,
                False,
            )
            executions.append(SynthesizedRequest(request, SynthesisStatus.SYNTHESIZED, clip, "", 0))
        stats = SpeechBatchStats(
            len(executions), len(executions), 0, 0, 0, len(executions), 0, 10.0, "edge", "edge-default", "voice"
        )
        return SpeechBatchResult(batch.scope_id, SpeechBatchStatus.COMPLETED, tuple(executions), stats, None)

    def cancel(self) -> None:
        raise AssertionError

    def close(self) -> None:
        self.close_calls += 1


class _ProgressTts(_Tts):
    def synthesize(self, batch: SpeechBatch, *, callbacks: TtsProgressObserver) -> SpeechBatchResult:
        callbacks.on_batch_state(SpeechBatchProgress(batch.scope_id, 0, 4, 0, 4, SpeechBatchStatus.PARTIAL, 1))
        callbacks.on_batch_state(SpeechBatchProgress(batch.scope_id, 1, 4, 1, 4, SpeechBatchStatus.PARTIAL, 3))
        callbacks.on_batch_state(SpeechBatchProgress(batch.scope_id, 1, 4, 1, 4, SpeechBatchStatus.PARTIAL, 2))
        callbacks.on_batch_state(SpeechBatchProgress(batch.scope_id, 4, 4, 4, 4, SpeechBatchStatus.COMPLETED, 4))
        return super().synthesize(batch, callbacks=callbacks)


def test_tts_handler_writes_timed_clip_manifest(tmp_path: Path) -> None:
    source_path = tmp_path / "episode.spoken.pl.srt"
    source_path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nCześć\n\n2\n00:00:03,000 --> 00:00:04,000\n...\n",
        encoding="utf-8",
    )
    source = Artifact(
        "spoken",
        "group-1",
        ArtifactKind.SPOKEN_PL,
        source_path,
        ArtifactState.READY,
        ArtifactLifetime.SOURCE,
        source_path,
    )
    output = Artifact(
        "manifest", "group-1", ArtifactKind.TTS_MANIFEST, None, ArtifactState.MISSING, ArtifactLifetime.INTERMEDIATE
    )
    task = PlanTask(
        "tts",
        "group-1",
        TaskKind.SYNTHESIZE_SPEECH,
        ("spoken",),
        ("manifest",),
        (),
        "tts:edge",
        _SPOKEN_PARAMETERS,
    )

    service = _Tts(tmp_path)
    result: TaskResult = TtsTaskHandler(
        service,
        run_root=tmp_path / "run",
        group_ranks={"group-1": 0},
    ).execute(
        task,
        ArtifactSnapshot({"spoken": source}, {"manifest": output}),
        NeverCancelledToken(),
        _Progress(),
    )

    manifest = load_narration_manifest(result.outputs[0].path)
    assert manifest.scope_id == "group-1"
    assert manifest.clips[0].start_ms == 1000
    assert manifest.clips[0].end_ms == 2000
    assert manifest.clips[0].path.read_bytes() == b"audio"
    assert service.batches[0].batch_rank == 0
    assert len(service.batches[0].requests) == 1


def test_a_subtitle_without_duration_still_gets_a_placement_window(tmp_path: Path) -> None:
    source_path = tmp_path / "episode.spoken.pl.srt"
    source_path.write_text(
        "1\n00:11:18,240 --> 00:11:18,240\nSzybko!\n",
        encoding="utf-8",
    )
    source = Artifact(
        "spoken",
        "group-1",
        ArtifactKind.SPOKEN_PL,
        source_path,
        ArtifactState.READY,
        ArtifactLifetime.SOURCE,
        source_path,
    )
    output = Artifact(
        "manifest", "group-1", ArtifactKind.TTS_MANIFEST, None, ArtifactState.MISSING, ArtifactLifetime.INTERMEDIATE
    )
    task = PlanTask(
        "tts",
        "group-1",
        TaskKind.SYNTHESIZE_SPEECH,
        ("spoken",),
        ("manifest",),
        (),
        "tts:edge",
        _SPOKEN_PARAMETERS,
    )

    result: TaskResult = TtsTaskHandler(
        _Tts(tmp_path),
        run_root=tmp_path / "run",
        group_ranks={"group-1": 0},
    ).execute(
        task,
        ArtifactSnapshot({"spoken": source}, {"manifest": output}),
        NeverCancelledToken(),
        _Progress(),
    )

    manifest = load_narration_manifest(result.outputs[0].path)
    assert manifest.clips[0].start_ms == 678240
    assert manifest.clips[0].end_ms == 678241


class _Preparer:
    def __init__(self) -> None:
        self.roots: set[Path] = set()

    def prepare_clip(self, clip: TimedClip, *, tmp_root: Path, cancel: threading.Event | None) -> NormalizedClip:
        del cancel
        self.roots.add(tmp_root)
        return NormalizedClip(clip, tmp_root / f"{clip.request_id}.pcm", 1000, 2, 1, 500, PcmStorage.RAW, False)


def _signed_synthesis(tmp_path: Path) -> tuple[PlanTask, ArtifactSnapshot]:
    script_path = tmp_path / "episode.spoken.pl.srt"
    script_path.write_text("1\n00:00:05,000 --> 00:00:05,500\nCześć\n", encoding="utf-8")
    signs_path: Path = write_sign_candidates(
        (
            SignCandidate(3, 1000, 4000, "Brama szkoły", "brama szkoły", 0.9, 0.0),
            SignCandidate(7, 5000, 5400, "Napis", "napis", 0.3, 0.0),
        ),
        tmp_path / "signs.json",
    )
    spoken = Artifact(
        "spoken", "group-1", ArtifactKind.SPOKEN_PL, script_path, ArtifactState.READY, ArtifactLifetime.INTERMEDIATE
    )
    signs = Artifact(
        "signs", "group-1", ArtifactKind.SIGN_CANDIDATES, signs_path, ArtifactState.READY, ArtifactLifetime.INTERMEDIATE
    )
    output = Artifact(
        "manifest", "group-1", ArtifactKind.TTS_MANIFEST, None, ArtifactState.MISSING, ArtifactLifetime.INTERMEDIATE
    )
    task = PlanTask(
        "tts",
        "group-1",
        TaskKind.SYNTHESIZE_SPEECH,
        ("spoken", "signs"),
        ("manifest",),
        (),
        "tts:edge",
        (*_SPOKEN_PARAMETERS, ("sign_narration", "smart")),
    )
    return task, ArtifactSnapshot({"spoken": spoken, "signs": signs}, {"manifest": output})


def test_signs_are_read_in_free_pauses_and_rejected_signs_stay_out_of_the_manifest(tmp_path: Path) -> None:
    task, snapshot = _signed_synthesis(tmp_path)
    service = _Tts(tmp_path)
    preparer = _Preparer()
    handler = TtsTaskHandler(service, run_root=tmp_path / "run", group_ranks={"group-1": 0}, audio=preparer)

    first: TaskResult = handler.execute(task, snapshot, NeverCancelledToken(), _Progress())
    second: TaskResult = handler.execute(task, snapshot, NeverCancelledToken(), _Progress())

    manifest = load_narration_manifest(first.outputs[0].path)
    assert [(clip.request_id, clip.start_ms, clip.end_ms) for clip in manifest.clips] == [
        ("group-1-0", 5000, 5500),
        ("group-1-sign-3", 1000, 1500),
    ]
    assert [request.request_id for request in service.batches[1].requests] == ["group-1-sign-3", "group-1-sign-7"]
    assert first.outputs[0].metadata == {
        "sign_decisions": "3:read,7:weight",
        "sign_chars_synthesized": len("Brama szkoły") + len("Napis"),
        "signs_read": 1,
        "clip_count": 2,
    }
    assert second.outputs[0].metadata == first.outputs[0].metadata
    assert load_narration_manifest(second.outputs[0].path) == manifest
    assert preparer.roots == {tmp_path / "run" / "group-1" / "audio"}


class _CancellingPreparer(_Preparer):
    def __init__(self, token: EventCancellationToken) -> None:
        super().__init__()
        self.token: EventCancellationToken = token
        self.signalled: list[bool] = []

    def prepare_clip(self, clip: TimedClip, *, tmp_root: Path, cancel: threading.Event | None) -> NormalizedClip:
        self.token.cancel()
        self.signalled.append(cancel is not None and cancel.wait(5))
        return super().prepare_clip(clip, tmp_root=tmp_root, cancel=cancel)


def test_cancelling_the_task_stops_the_normalization_of_its_clips(tmp_path: Path) -> None:
    task, snapshot = _signed_synthesis(tmp_path)
    token = EventCancellationToken()
    preparer = _CancellingPreparer(token)
    handler = TtsTaskHandler(_Tts(tmp_path), run_root=tmp_path / "run", group_ranks={"group-1": 0}, audio=preparer)

    with pytest.raises(ExecutionError) as caught:
        handler.execute(task, snapshot, token, _Progress())

    assert caught.value.context.code is ErrorCode.CANCELLED
    assert preparer.signalled == [True]


def test_without_sign_narration_the_manifest_holds_only_the_spoken_lines_in_their_times(tmp_path: Path) -> None:
    script_path = tmp_path / "episode.spoken.pl.srt"
    script_path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nCześć\n\n2\n00:00:05,000 --> 00:00:06,500\nNa razie\n", encoding="utf-8"
    )
    spoken = Artifact(
        "spoken", "group-1", ArtifactKind.SPOKEN_PL, script_path, ArtifactState.READY, ArtifactLifetime.INTERMEDIATE
    )
    output = Artifact(
        "manifest", "group-1", ArtifactKind.TTS_MANIFEST, None, ArtifactState.MISSING, ArtifactLifetime.INTERMEDIATE
    )
    task = PlanTask(
        "tts", "group-1", TaskKind.SYNTHESIZE_SPEECH, ("spoken",), ("manifest",), (), "tts:edge", _SPOKEN_PARAMETERS
    )
    service = _Tts(tmp_path)
    preparer = _Preparer()
    handler = TtsTaskHandler(service, run_root=tmp_path / "run", group_ranks={"group-1": 0}, audio=preparer)

    result: TaskResult = handler.execute(
        task, ArtifactSnapshot({"spoken": spoken}, {"manifest": output}), NeverCancelledToken(), _Progress()
    )

    manifest = load_narration_manifest(result.outputs[0].path)
    assert [(clip.request_id, clip.start_ms, clip.end_ms, clip.source_order) for clip in manifest.clips] == [
        ("group-1-0", 1000, 2000, 0),
        ("group-1-1", 5000, 6500, 1),
    ]
    assert result.outputs[0].metadata == {"clip_count": 2}
    assert len(service.batches) == 1
    assert preparer.roots == set()


def test_sign_narration_without_the_run_audio_service_is_refused(tmp_path: Path) -> None:
    task, snapshot = _signed_synthesis(tmp_path)
    handler = TtsTaskHandler(_Tts(tmp_path), run_root=tmp_path / "run", group_ranks={"group-1": 0})

    with pytest.raises(ExecutionError):
        handler.execute(task, snapshot, NeverCancelledToken(), _Progress())


def test_a_stored_manifest_window_without_duration_is_repaired_on_load(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "scope_id": "group-1",
                "timeline": "source_times",
                "clips": [
                    {
                        "request_id": "group-1-214",
                        "start_ms": 678240,
                        "end_ms": 678240,
                        "source_order": 214,
                        "path": str(tmp_path / "clip.wav"),
                        "format": "wav",
                        "sample_rate": 24000,
                        "channels": 1,
                        "duration_ms": 900,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_narration_manifest(path)

    assert manifest.clips[0].start_ms == 678240
    assert manifest.clips[0].end_ms == 678241


def test_tts_handler_forwards_legacy_visible_required_percentages(tmp_path: Path) -> None:
    source_path = tmp_path / "episode.spoken.pl.srt"
    source_path.write_text("1\n00:00:01,000 --> 00:00:02,000\nCześć\n", encoding="utf-8")
    source = Artifact(
        "spoken",
        "group-1",
        ArtifactKind.SPOKEN_PL,
        source_path,
        ArtifactState.READY,
        ArtifactLifetime.SOURCE,
        source_path,
    )
    output = Artifact(
        "manifest", "group-1", ArtifactKind.TTS_MANIFEST, None, ArtifactState.MISSING, ArtifactLifetime.INTERMEDIATE
    )
    task = PlanTask(
        "tts",
        "group-1",
        TaskKind.SYNTHESIZE_SPEECH,
        ("spoken",),
        ("manifest",),
        (),
        "tts:edge",
        _SPOKEN_PARAMETERS,
    )
    progress = _Progress()

    TtsTaskHandler(
        _ProgressTts(tmp_path),
        run_root=tmp_path / "run",
        group_ranks={"group-1": 0},
    ).execute(
        task,
        ArtifactSnapshot({"spoken": source}, {"manifest": output}),
        NeverCancelledToken(),
        progress,
    )

    assert [notification.progress_percent for notification in progress.notifications] == [25, 75, 75, 100]


def test_tts_handler_reuses_service_and_closes_only_at_run_boundary(tmp_path: Path) -> None:
    source_path = tmp_path / "episode.spoken.pl.srt"
    source_path.write_text("1\n00:00:01,000 --> 00:00:02,000\nCześć\n", encoding="utf-8")
    service = _Tts(tmp_path)
    handler = TtsTaskHandler(
        service,
        run_root=tmp_path / "run",
        group_ranks={"group-1": 0, "group-2": 1},
    )
    for group_id in ("group-1", "group-2"):
        source = Artifact(
            f"spoken-{group_id}",
            group_id,
            ArtifactKind.SPOKEN_PL,
            source_path,
            ArtifactState.READY,
            ArtifactLifetime.SOURCE,
            source_path,
        )
        output = Artifact(
            f"manifest-{group_id}",
            group_id,
            ArtifactKind.TTS_MANIFEST,
            None,
            ArtifactState.MISSING,
            ArtifactLifetime.INTERMEDIATE,
        )
        task = PlanTask(
            f"tts-{group_id}",
            group_id,
            TaskKind.SYNTHESIZE_SPEECH,
            (source.artifact_id,),
            (output.artifact_id,),
            (),
            "tts:edge",
            _SPOKEN_PARAMETERS,
        )
        handler.execute(
            task,
            ArtifactSnapshot({source.artifact_id: source}, {output.artifact_id: output}),
            NeverCancelledToken(),
            _Progress(),
        )

    assert len(service.batches) == 2
    assert [batch.batch_rank for batch in service.batches] == [0, 1]
    assert service.close_calls == 0
    handler.close()
    assert service.close_calls == 1


def test_tts_handler_rejects_cancelled_task_before_synthesis(tmp_path: Path) -> None:
    token = EventCancellationToken()
    token.cancel()
    service = _Tts(tmp_path)
    task = PlanTask(
        "tts",
        "group-1",
        TaskKind.SYNTHESIZE_SPEECH,
        ("spoken",),
        ("manifest",),
        (),
        "tts:edge",
        _SPOKEN_PARAMETERS,
    )

    with pytest.raises(ExecutionError) as raised:
        TtsTaskHandler(service, run_root=tmp_path / "run", group_ranks={"group-1": 0}).execute(
            task,
            ArtifactSnapshot({}, {}),
            token,
            _Progress(),
        )

    assert raised.value.context.code is ErrorCode.CANCELLED
    assert service.batches == []


def test_manifest_rejects_submitted_request_without_clip(tmp_path: Path) -> None:
    request = SpeechRequest("request-1", "Cześć", 0)
    callbacks: TtsProgressObserver = cast(TtsProgressObserver, _Progress())
    result = _Tts(tmp_path).synthesize(SpeechBatch("group-1", 0, (request,)), callbacks=callbacks)
    missing_clip = replace(result.requests[0], speech_clip=None)

    with pytest.raises(ValueError, match="lacks a required clip"):
        build_narration_manifest(
            replace(result, requests=(missing_clip,)),
            (NarrationTiming("request-1", 1000, 2000, 0),),
            expected_scope_id="group-1",
            timeline=NarrationTimeline.SOURCE_TIMES,
        )


class _ClipRunner:
    def __init__(self, *, fail_decode: bool = False) -> None:
        self.operations: list[str] = []
        self.fail_decode: bool = fail_decode

    def run(
        self,
        command: tuple[str, ...],
        *,
        operation: str,
        timeout_s: float,
        cancel: threading.Event | None = None,
        on_stdout_line: Callable[[str], None] | None = None,
    ) -> CommandResult:
        del timeout_s, cancel
        self.operations.append(operation)
        if operation == "probe":
            payload: str = json.dumps(
                {
                    "streams": [
                        {
                            "codec_type": "audio",
                            "codec_name": "pcm_s16le",
                            "sample_rate": "48000",
                            "channels": 1,
                            "duration": "1",
                        },
                    ],
                    "format": {"format_name": "wav", "duration": "1"},
                },
            )
            return CommandResult(command, payload, "", 0)
        if operation == "decode" and self.fail_decode:
            raise AudioProcessError(context=ErrorContext(code=ErrorCode.AUDIO_FAILED, message="decode failed"))
        return CommandResult(command, "", "", 0)


def _write_pcm_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(48_000)
        stream.writeframes(bytes(96_000))


def _clips(runner: _ClipRunner, *, cancel: threading.Event | None = None) -> FfmpegClipService:
    return FfmpegClipService(
        cancel=cancel if cancel is not None else threading.Event(),
        runner=runner,
        ffmpeg=Path("ffmpeg"),
        ffprobe=Path("ffprobe"),
        timeout_s=1,
    )


def test_clip_validation_trusts_a_readable_pcm_wav_without_any_process(tmp_path: Path) -> None:
    path: Path = tmp_path / "voice.wav"
    _write_pcm_wav(path)
    runner = _ClipRunner()

    validation = _clips(runner).validate_clip(path, ClipExpectation(AudioFormat.WAV))

    assert validation is not None
    assert validation.sample_rate == 48_000
    assert validation.channels == 1
    assert validation.duration_ms == 1000
    assert runner.operations == []


def test_clip_validation_falls_back_to_ffmpeg_for_an_unsupported_wav(tmp_path: Path) -> None:
    path: Path = tmp_path / "voice.wav"
    _write_pcm_wav(path)
    payload: bytearray = bytearray(path.read_bytes())
    payload[20:22] = (6).to_bytes(2, byteorder="little")
    path.write_bytes(payload)
    runner = _ClipRunner()

    validation = _clips(runner).validate_clip(path, ClipExpectation(AudioFormat.WAV))

    assert validation is not None
    assert runner.operations == ["probe", "decode"]


def test_clip_validation_rejects_a_truncated_wav_that_cannot_decode_completely(tmp_path: Path) -> None:
    path: Path = tmp_path / "voice.wav"
    _write_pcm_wav(path)
    path.write_bytes(path.read_bytes()[:-2])
    runner = _ClipRunner(fail_decode=True)

    validation = _clips(runner).validate_clip(path, ClipExpectation(AudioFormat.WAV))

    assert validation is None
    assert runner.operations == ["probe", "decode"]


def test_clip_validation_starts_no_process_once_cancelled(tmp_path: Path) -> None:
    path: Path = tmp_path / "voice.wav"
    _write_pcm_wav(path)
    runner = _ClipRunner()
    cancel = threading.Event()
    cancel.set()

    validation = _clips(runner, cancel=cancel).validate_clip(path, ClipExpectation(AudioFormat.WAV))

    assert validation is None
    assert runner.operations == []


def _script(path: Path, kind: ArtifactKind) -> Artifact:
    return Artifact("script", "group-1", kind, path, ArtifactState.READY, ArtifactLifetime.SOURCE, path)


def _manifest_slot() -> Artifact:
    return Artifact(
        "manifest", "group-1", ArtifactKind.TTS_MANIFEST, None, ArtifactState.MISSING, ArtifactLifetime.INTERMEDIATE
    )


def _speech_task(timeline: str, script_kind: ArtifactKind) -> PlanTask:
    return PlanTask(
        "tts",
        "group-1",
        TaskKind.SYNTHESIZE_SPEECH,
        ("script",),
        ("manifest",),
        (),
        "tts:edge",
        (("narration_timeline", timeline), ("script_kind", script_kind.value)),
    )


def _read_aloud(
    tmp_path: Path,
    path: Path,
    kind: ArtifactKind,
    timeline: str,
    service: _Tts | None = None,
) -> TaskResult:
    return TtsTaskHandler(
        service if service is not None else _Tts(tmp_path),
        run_root=tmp_path / "run",
        group_ranks={"group-1": 0},
    ).execute(
        _speech_task(timeline, kind),
        ArtifactSnapshot({"script": _script(path, kind)}, {"manifest": _manifest_slot()}),
        NeverCancelledToken(),
        _Progress(),
    )


def _book_srt(tmp_path: Path) -> Path:
    path: Path = tmp_path / "book.pl.srt"
    path.write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nPierwsze zdanie\n\n"
        "2\n00:05:00,000 --> 00:05:04,000\nDrugie zdanie\n\n"
        "3\n00:05:03,000 --> 00:05:08,000\nTrzecie zdanie\n",
        encoding="utf-8",
    )
    return path


def test_a_continuous_reading_asks_for_no_place_in_time_at_all(tmp_path: Path) -> None:
    path: Path = _book_srt(tmp_path)

    result: TaskResult = _read_aloud(tmp_path, path, ArtifactKind.FULL_PL, "continuous")

    manifest = load_narration_manifest(result.outputs[0].path)
    assert [(clip.start_ms, clip.end_ms) for clip in manifest.clips] == [(0, 1), (0, 1), (0, 1)]
    assert [clip.source_order for clip in manifest.clips] == [0, 1, 2]


def test_a_reading_that_keeps_the_book_times_keeps_them_exactly(tmp_path: Path) -> None:
    path: Path = _book_srt(tmp_path)

    result: TaskResult = _read_aloud(tmp_path, path, ArtifactKind.FULL_PL, "source_times")

    manifest = load_narration_manifest(result.outputs[0].path)
    assert [(clip.start_ms, clip.end_ms) for clip in manifest.clips] == [
        (1_000, 2_000),
        (300_000, 304_000),
        (303_000, 308_000),
    ]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("prefix", [b"", b"\xef\xbb\xbf"])
def test_reading_a_book_never_rewrites_one_byte_of_the_book(tmp_path: Path, newline: str, prefix: bytes) -> None:
    path: Path = tmp_path / "book.pl.srt"
    lines: str = newline.join(
        (
            "1",
            "00:00:01,000 --> 00:00:02,000",
            "Pierwsze zdanie",
            "",
            "2",
            "00:05:00,000 --> 00:05:04,000",
            "Drugie zdanie",
            "",
        )
    )
    before: bytes = prefix + lines.encode("utf-8")
    path.write_bytes(before)

    result: TaskResult = _read_aloud(tmp_path, path, ArtifactKind.FULL_PL, "continuous")

    assert len(load_narration_manifest(result.outputs[0].path).clips) == 2
    assert path.read_bytes() == before


def test_a_plain_text_is_read_in_the_order_it_was_written(tmp_path: Path) -> None:
    path: Path = tmp_path / "book.txt"
    paragraphs: tuple[str, ...] = ("Alfa " * 100, "Beta " * 100, "Gamma " * 80)
    path.write_text("".join(f"{paragraph.strip()}.\n\n" for paragraph in paragraphs), encoding="utf-8")
    service = _Tts(tmp_path)

    result: TaskResult = _read_aloud(tmp_path, path, ArtifactKind.STANDALONE_TEXT, "continuous", service)

    manifest = load_narration_manifest(result.outputs[0].path)
    spoken: tuple[str, ...] = tuple(request.text for request in service.batches[0].requests)
    assert [text.split()[0] for text in spoken] == ["Alfa", "Beta", "Gamma"]
    assert [clip.source_order for clip in manifest.clips] == [0, 1, 2]
    assert [(clip.start_ms, clip.end_ms) for clip in manifest.clips] == [(0, 1), (0, 1), (0, 1)]


def test_a_plain_text_cannot_be_read_at_times_it_never_had(tmp_path: Path) -> None:
    path: Path = tmp_path / "book.txt"
    path.write_text("Pierwsze zdanie.\n", encoding="utf-8")
    service = _Tts(tmp_path)

    with pytest.raises(ExecutionError, match="times"):
        _read_aloud(tmp_path, path, ArtifactKind.STANDALONE_TEXT, "source_times", service)

    assert service.batches == []


def test_a_book_with_nothing_to_pronounce_fails_before_any_voice_is_asked(tmp_path: Path) -> None:
    path: Path = tmp_path / "book.pl.srt"
    path.write_text("1\n00:00:01,000 --> 00:00:02,000\n...\n\n2\n00:00:03,000 --> 00:00:04,000\n♪\n", encoding="utf-8")
    service = _Tts(tmp_path)

    with pytest.raises(ExecutionError, match="no pronounceable text"):
        _read_aloud(tmp_path, path, ArtifactKind.FULL_PL, "continuous", service)

    assert service.batches == []


def test_a_script_that_is_not_the_one_the_plan_promised_is_refused(tmp_path: Path) -> None:
    path: Path = _book_srt(tmp_path)
    service = _Tts(tmp_path)
    handler = TtsTaskHandler(service, run_root=tmp_path / "run", group_ranks={"group-1": 0})

    with pytest.raises(ExecutionError, match="does not match the document"):
        handler.execute(
            _speech_task("continuous", ArtifactKind.SPOKEN_PL),
            ArtifactSnapshot({"script": _script(path, ArtifactKind.FULL_PL)}, {"manifest": _manifest_slot()}),
            NeverCancelledToken(),
            _Progress(),
        )

    assert service.batches == []


def test_a_voice_the_engine_does_not_offer_is_refused_before_any_request_is_paid_for(tmp_path: Path) -> None:
    path: Path = _book_srt(tmp_path)
    service = _Tts(tmp_path)
    handler = TtsTaskHandler(
        service,
        run_root=tmp_path / "run",
        group_ranks={"group-1": 0},
        voice_id="pl-PL-SomeoneElseNeural",
        allowed_voice_ids=frozenset({"pl-PL-MarekNeural", "pl-PL-ZofiaNeural"}),
    )

    with pytest.raises(ExecutionError, match="not one the chosen TTS engine offers"):
        handler.execute(
            _speech_task("continuous", ArtifactKind.FULL_PL),
            ArtifactSnapshot({"script": _script(path, ArtifactKind.FULL_PL)}, {"manifest": _manifest_slot()}),
            NeverCancelledToken(),
            _Progress(),
        )

    assert service.batches == []


def test_a_voice_only_the_provider_can_name_is_never_refused_locally(tmp_path: Path) -> None:
    path: Path = _book_srt(tmp_path)
    service = _Tts(tmp_path)
    handler = TtsTaskHandler(
        service,
        run_root=tmp_path / "run",
        group_ranks={"group-1": 0},
        voice_id="a-provider-only-id",
    )

    handler.execute(
        _speech_task("continuous", ArtifactKind.FULL_PL),
        ArtifactSnapshot({"script": _script(path, ArtifactKind.FULL_PL)}, {"manifest": _manifest_slot()}),
        NeverCancelledToken(),
        _Progress(),
    )

    assert len(service.batches) == 1


def test_the_production_speech_handler_refuses_a_voice_its_own_engine_never_offered(tmp_path: Path) -> None:
    if resolve_binary(Binary.FFMPEG) is None or resolve_binary(Binary.FFPROBE) is None:
        pytest.skip("bundled FFmpeg is unavailable")
    settings = RunSettingsSnapshot(
        translation_profile_id="google",
        translation_max_retries=2,
        translation_concurrency=2,
        llm_profile_id="gemini",
        llm_max_concurrency=2,
        tts_profile_id="edge",
        tts_max_retries=2,
        tts_group_jobs=2,
        audio_profile_id="eac3",
        composition_profile_id="balanced",
        processing_order_policy=ProcessingOrderPolicy.READY_FIRST,
        tts_voice_id="pl-PL-SomeoneElseNeural",
        tts_allowed_voice_ids=("pl-PL-MarekNeural", "pl-PL-ZofiaNeural"),
    )
    handler: TtsTaskHandler | None = ProductionHandlerFactory._tts_handler(
        Settings(_env_file=None),
        tmp_path / "run",
        ExecutionPlan((), (), (), settings, ()),
        frozenset({TaskKind.SYNTHESIZE_SPEECH}),
        None,
    )
    path: Path = _book_srt(tmp_path)

    assert handler is not None
    with pytest.raises(ExecutionError, match="not one the chosen TTS engine offers"):
        handler.execute(
            _speech_task("continuous", ArtifactKind.FULL_PL),
            ArtifactSnapshot({"script": _script(path, ArtifactKind.FULL_PL)}, {"manifest": _manifest_slot()}),
            NeverCancelledToken(),
            _Progress(),
        )


def _ass_script(path: Path) -> Path:
    path.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1280\nPlayResY: 720\n\n"
        "[V4+ Styles]\nFormat: Name\nStyle: Default\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Cześć wszystkim.\n"
        "Dialogue: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,{\\an7}WKURZONY\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.unit
@pytest.mark.parametrize(
    ("kind", "texts"),
    [
        (ArtifactKind.SPOKEN_PL, ["Cześć wszystkim.", "WKURZONY"]),
        (ArtifactKind.FULL_PL, ["Cześć wszystkim."]),
    ],
)
def test_a_spoken_only_script_is_read_whole_while_a_full_script_is_classified(
    tmp_path: Path, kind: ArtifactKind, texts: list[str]
) -> None:
    service: _Tts = _Tts(tmp_path)

    _read_aloud(tmp_path, _ass_script(tmp_path / "episode.ass"), kind, "source_times", service)

    assert [request.text for request in service.batches[0].requests] == texts
