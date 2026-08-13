from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.cancellation import EventCancellationToken, NeverCancelledToken
from anishift.application.events import WorkerNotification
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.application.tts_handler import (
    NarrationTiming,
    TtsProgressObserver,
    TtsTaskHandler,
    build_narration_manifest,
    load_narration_manifest,
)
from anishift.errors import ErrorCode, ExecutionError
from anishift.services.tts import (
    AudioFormat,
    SpeechBatch,
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
