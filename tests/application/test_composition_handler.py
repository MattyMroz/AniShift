from __future__ import annotations

import threading
from pathlib import Path

import pytest

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.cancellation import EventCancellationToken, NeverCancelledToken
from anishift.application.composition_handler import CompositionTaskHandler
from anishift.application.events import WorkerNotification
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.errors import ErrorCode, ExecutionError
from anishift.services.composition import ContainerCompositionRequest, ContainerCompositionResult


class _Progress:
    def __init__(self) -> None:
        self.notifications: list[WorkerNotification] = []

    def emit(self, notification: WorkerNotification) -> None:
        self.notifications.append(notification)


class _Composer:
    def __init__(self) -> None:
        self.requests: list[ContainerCompositionRequest] = []

    def compose_container(
        self,
        request: ContainerCompositionRequest,
        *,
        cancel: threading.Event | None = None,
    ) -> ContainerCompositionResult:
        assert cancel is not None
        assert cancel.is_set() is False
        self.requests.append(request)
        request.destination.write_bytes(b"container")
        return ContainerCompositionResult(
            request.source_video,
            request.target,
            request.destination,
            request.destination.stat().st_size,
            request.source_video.stat().st_size,
            10.0,
        )


def _snapshot(tmp_path: Path) -> tuple[PlanTask, ArtifactSnapshot, Path]:
    source_path = tmp_path / "Episode.mkv"
    source_path.write_bytes(b"source")
    destination = tmp_path / "Episode.pl.mp4"
    destination.write_bytes(b"previous")
    source = Artifact(
        "video",
        "group-1",
        ArtifactKind.VIDEO_MKV,
        source_path,
        ArtifactState.READY,
        ArtifactLifetime.SOURCE,
        source_path,
    )
    output = Artifact(
        "mp4",
        "group-1",
        ArtifactKind.FINAL_MP4,
        None,
        ArtifactState.MISSING,
        ArtifactLifetime.DURABLE,
        destination,
    )
    task = PlanTask(
        "compose-mp4",
        "group-1",
        TaskKind.COMPOSE_MP4,
        (source.artifact_id,),
        (output.artifact_id,),
        (),
        "composition:balanced",
        (("audio_source", "original"), ("burn_subtitles", "none")),
    )
    return task, ArtifactSnapshot({source.artifact_id: source}, {output.artifact_id: output}), destination


def test_composition_handler_keeps_final_destination_private_from_worker(tmp_path: Path) -> None:
    task, snapshot, destination = _snapshot(tmp_path)
    service = _Composer()
    progress = _Progress()

    result: TaskResult = CompositionTaskHandler(service, run_root=tmp_path / "run").execute(
        task,
        snapshot,
        NeverCancelledToken(),
        progress,
    )

    assert destination.read_bytes() == b"previous"
    assert service.requests[0].destination == tmp_path / "run" / "group-1" / "mp4.mp4"
    assert result.outputs[0].path.read_bytes() == b"container"
    assert result.outputs[0].metadata["validated"] is True
    assert progress.notifications[-1].progress_percent == 100


def test_composition_handler_rejects_cancelled_task_before_service_call(tmp_path: Path) -> None:
    task, snapshot, _ = _snapshot(tmp_path)
    service = _Composer()
    token = EventCancellationToken()
    token.cancel()

    with pytest.raises(ExecutionError) as raised:
        CompositionTaskHandler(service, run_root=tmp_path / "run").execute(task, snapshot, token, _Progress())

    assert raised.value.context.code is ErrorCode.CANCELLED
    assert service.requests == []
