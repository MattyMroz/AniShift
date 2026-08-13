from __future__ import annotations

import threading
from pathlib import Path

import pytest

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState, SourceGroup
from anishift.application.cancellation import EventCancellationToken, NeverCancelledToken
from anishift.application.events import WorkerNotification
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.publish_handler import PublishTaskHandler
from anishift.application.publisher import PublishRequest
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.errors import ErrorCode, ErrorContext, ExecutionError


class _Progress:
    def __init__(self) -> None:
        self.notifications: list[WorkerNotification] = []

    def emit(self, notification: WorkerNotification) -> None:
        self.notifications.append(notification)


class _BlockingStager:
    def __init__(self) -> None:
        self.entered: threading.Event = threading.Event()

    def stage(self, request: PublishRequest, destination: Path, *, cancel: threading.Event) -> Path:
        del request, destination
        self.entered.set()
        cancel.wait(2.0)
        context = ErrorContext(code=ErrorCode.CANCELLED, message="staging cancelled")
        raise ExecutionError(context=context)


def _contract(
    tmp_path: Path,
    *,
    destination_directory: Path | None = None,
) -> tuple[PlanTask, ArtifactSnapshot, SourceGroup, Path]:
    source_path = tmp_path / "translated.srt"
    source_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nNowe\n", encoding="utf-8")
    directory: Path = destination_directory or tmp_path
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "Episode.pl.srt"
    destination.write_bytes(b"previous")
    source = Artifact(
        "full-intermediate",
        "group-1",
        ArtifactKind.FULL_PL,
        source_path,
        ArtifactState.READY,
        ArtifactLifetime.INTERMEDIATE,
    )
    output = Artifact(
        "full-durable",
        "group-1",
        ArtifactKind.FULL_PL,
        None,
        ArtifactState.MISSING,
        ArtifactLifetime.DURABLE,
        destination,
        language="pol",
        subtitle_format="srt",
    )
    task = PlanTask(
        "publish-full",
        "group-1",
        TaskKind.PUBLISH_ARTIFACT,
        (source.artifact_id,),
        (output.artifact_id,),
        (),
        "filesystem",
    )
    snapshot = ArtifactSnapshot({source.artifact_id: source}, {output.artifact_id: output})
    source_group = SourceGroup("group-1", "Episode", tmp_path, (source,))
    return task, snapshot, source_group, destination


def test_publish_handler_validates_private_staging_without_replacing_product(tmp_path: Path) -> None:
    task, snapshot, source_group, destination = _contract(tmp_path)
    progress = _Progress()

    result: TaskResult = PublishTaskHandler(
        run_root=tmp_path / "run",
        source_groups={source_group.group_id: source_group},
    ).execute(task, snapshot, NeverCancelledToken(), progress)

    assert destination.read_bytes() == b"previous"
    assert result.outputs[0].path == tmp_path / "run" / "group-1" / "full-durable.srt"
    assert result.outputs[0].metadata["validated"] is True
    assert progress.notifications[-1].progress_percent == 100


def test_publish_handler_rejects_destination_away_from_real_source_group(tmp_path: Path) -> None:
    task, snapshot, source_group, _ = _contract(tmp_path, destination_directory=tmp_path / "elsewhere")

    with pytest.raises(ExecutionError, match="next to"):
        PublishTaskHandler(
            run_root=tmp_path / "run",
            source_groups={source_group.group_id: source_group},
        ).execute(task, snapshot, NeverCancelledToken(), _Progress())


def test_publish_handler_cancels_blocking_stager_during_execution(tmp_path: Path) -> None:
    task, snapshot, source_group, _ = _contract(tmp_path)
    stager = _BlockingStager()
    token = EventCancellationToken()
    failures: list[ExecutionError] = []
    handler = PublishTaskHandler(
        run_root=tmp_path / "run",
        source_groups={source_group.group_id: source_group},
        publisher=stager,
    )

    def execute() -> None:
        try:
            handler.execute(task, snapshot, token, _Progress())
        except ExecutionError as error:
            failures.append(error)

    worker = threading.Thread(target=execute)
    worker.start()
    assert stager.entered.wait(1.0)
    token.cancel()
    worker.join(1.0)

    assert worker.is_alive() is False
    assert failures[0].context.code is ErrorCode.CANCELLED
