from __future__ import annotations

import json
import threading
import wave
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.cancellation import EventCancellationToken, NeverCancelledToken
from anishift.application.events import WorkerNotification
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.application.tts_clips import FfmpegClipService
from anishift.application.tts_handler import (
    NarrationTiming,
    TtsProgressObserver,
    TtsTaskHandler,
    build_narration_manifest,
    load_narration_manifest,
)
from anishift.errors import ErrorCode, ErrorContext, ExecutionError
from anishift.services.audio.commands import CommandResult
from anishift.services.audio.errors import AudioProcessError
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
    task = PlanTask("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH, ("spoken",), ("manifest",), (), "tts:edge")

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
    task = PlanTask("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH, ("spoken",), ("manifest",), (), "tts:edge")

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


def test_a_stored_manifest_window_without_duration_is_repaired_on_load(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "scope_id": "group-1",
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
    task = PlanTask("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH, ("spoken",), ("manifest",), (), "tts:edge")
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
    task = PlanTask("tts", "group-1", TaskKind.SYNTHESIZE_SPEECH, ("spoken",), ("manifest",), (), "tts:edge")

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
