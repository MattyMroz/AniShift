from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.cancellation import EventCancellationToken, NeverCancelledToken
from anishift.application.composition_handler import CompositionTaskHandler
from anishift.application.events import WorkerNotification
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.errors import AniShiftError, ErrorCode, ExecutionError
from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.composition import (
    CompositionConfig,
    CompositionProgressSink,
    CompositionService,
    ContainerCompositionRequest,
    ContainerCompositionResult,
    CoverCompositionRequest,
    CoverCompositionResult,
)

FFMPEG = resolve_binary(Binary.FFMPEG)
FFPROBE = resolve_binary(Binary.FFPROBE)


class _Progress:
    def __init__(self) -> None:
        self.notifications: list[WorkerNotification] = []

    def emit(self, notification: WorkerNotification) -> None:
        self.notifications.append(notification)


class _Composer:
    def __init__(self, *, invalid_output: bool = False) -> None:
        self.requests: list[ContainerCompositionRequest] = []
        self.cover_requests: list[CoverCompositionRequest] = []
        self.invalid_output: bool = invalid_output

    def compose_cover(
        self,
        request: CoverCompositionRequest,
        *,
        callbacks: CompositionProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> CoverCompositionResult:
        assert cancel is not None
        assert cancel.is_set() is False
        self.cover_requests.append(request)
        if callbacks is not None:
            callbacks.on_composition_phase("", "burning", 40)
            callbacks.on_composition_phase("", "burning", 100)
        request.destination.write_bytes(b"cover")
        return CoverCompositionResult(
            request.still_image,
            request.audio,
            request.destination,
            0 if self.invalid_output else request.destination.stat().st_size,
            3_370_000,
            12.0,
        )

    def compose_container(
        self,
        request: ContainerCompositionRequest,
        *,
        callbacks: CompositionProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> ContainerCompositionResult:
        assert cancel is not None
        assert cancel.is_set() is False
        self.requests.append(request)
        if callbacks is not None:
            callbacks.on_composition_phase("", "burning", 25)
            callbacks.on_composition_phase("", "burning", 100)
        request.destination.write_bytes(b"container")
        return ContainerCompositionResult(
            request.source_video,
            request.target,
            request.destination,
            0 if self.invalid_output else request.destination.stat().st_size,
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
    assert [event.progress_percent for event in progress.notifications] == [25, 99, 100]


def test_composition_handler_does_not_complete_before_validation(tmp_path: Path) -> None:
    task, snapshot, destination = _snapshot(tmp_path)
    progress: _Progress = _Progress()

    with pytest.raises(ExecutionError, match="invalid container result"):
        CompositionTaskHandler(_Composer(invalid_output=True), run_root=tmp_path / "run").execute(
            task,
            snapshot,
            NeverCancelledToken(),
            progress,
        )

    assert [event.progress_percent for event in progress.notifications] == [25, 99]
    assert destination.read_bytes() == b"previous"


def test_composition_handler_rejects_cancelled_task_before_service_call(tmp_path: Path) -> None:
    task, snapshot, _ = _snapshot(tmp_path)
    service = _Composer()
    token = EventCancellationToken()
    token.cancel()

    with pytest.raises(ExecutionError) as raised:
        CompositionTaskHandler(service, run_root=tmp_path / "run").execute(task, snapshot, token, _Progress())

    assert raised.value.context.code is ErrorCode.CANCELLED
    assert service.requests == []


def _cover_snapshot(
    tmp_path: Path,
    *,
    image_name: str = "Book.png",
    size: tuple[int, int] = (101, 55),
    audio_kind: ArtifactKind = ArtifactKind.SOURCE_AUDIO,
) -> tuple[PlanTask, ArtifactSnapshot, Path]:
    image_path = tmp_path / image_name
    Image.new("RGBA", size, (10, 20, 30, 128)).save(image_path)
    audio_path = tmp_path / "Book.m4a"
    audio_path.write_bytes(b"audio")
    destination = tmp_path / "Book.cover.mp4"
    image = Artifact(
        "image",
        "group-1",
        ArtifactKind.SOURCE_IMAGE,
        image_path,
        ArtifactState.READY,
        ArtifactLifetime.SOURCE,
        image_path,
    )
    audio = Artifact(
        "audio",
        "group-1",
        audio_kind,
        audio_path,
        ArtifactState.READY,
        ArtifactLifetime.SOURCE,
        audio_path,
    )
    output = Artifact(
        "cover",
        "group-1",
        ArtifactKind.COVER_MP4,
        None,
        ArtifactState.MISSING,
        ArtifactLifetime.DURABLE,
        destination,
    )
    task = PlanTask(
        "compose-cover",
        "group-1",
        TaskKind.COMPOSE_COVER,
        (image.artifact_id, audio.artifact_id),
        (output.artifact_id,),
        (),
        "composition:balanced",
    )
    snapshot = ArtifactSnapshot({image.artifact_id: image, audio.artifact_id: audio}, {output.artifact_id: output})
    return task, snapshot, destination


def test_cover_handler_keeps_the_planned_film_private_from_the_worker(tmp_path: Path) -> None:
    task: PlanTask
    snapshot: ArtifactSnapshot
    destination: Path
    task, snapshot, destination = _cover_snapshot(tmp_path)
    service: _Composer = _Composer()
    progress: _Progress = _Progress()

    result: TaskResult = CompositionTaskHandler(service, run_root=tmp_path / "run").execute(
        task,
        snapshot,
        NeverCancelledToken(),
        progress,
    )

    assert not destination.exists()
    assert service.cover_requests[0].destination == tmp_path / "run" / "group-1" / "cover.mp4"
    assert result.outputs[0].path.read_bytes() == b"cover"
    assert result.outputs[0].metadata["audio_duration_us"] == 3_370_000
    assert [event.progress_percent for event in progress.notifications] == [40, 99, 100]


def test_cover_handler_does_not_complete_before_validation(tmp_path: Path) -> None:
    task, snapshot, destination = _cover_snapshot(tmp_path)

    with pytest.raises(ExecutionError, match="invalid cover result"):
        CompositionTaskHandler(_Composer(invalid_output=True), run_root=tmp_path / "run").execute(
            task,
            snapshot,
            NeverCancelledToken(),
            _Progress(),
        )

    assert not destination.exists()


@pytest.mark.parametrize("audio_kind", [ArtifactKind.SOURCE_AUDIO, ArtifactKind.NARRATION_AUDIO])
def test_cover_handler_plays_the_recording_whichever_place_classified_it(
    tmp_path: Path,
    audio_kind: ArtifactKind,
) -> None:
    task, snapshot, _ = _cover_snapshot(tmp_path, audio_kind=audio_kind)
    service: _Composer = _Composer()

    result: TaskResult = CompositionTaskHandler(service, run_root=tmp_path / "run").execute(
        task,
        snapshot,
        NeverCancelledToken(),
        _Progress(),
    )

    assert result.outputs[0].path.read_bytes() == b"cover"
    assert service.cover_requests[0].audio == tmp_path / "Book.m4a"


def test_cover_handler_refuses_a_task_that_carries_no_recording_to_play(tmp_path: Path) -> None:
    task, snapshot, _ = _cover_snapshot(tmp_path)
    soundless: PlanTask = replace(task, requires=(task.requires[0],))
    service = _Composer()

    with pytest.raises(ExecutionError, match="exactly one cover audio"):
        CompositionTaskHandler(service, run_root=tmp_path / "run").execute(
            soundless,
            snapshot,
            NeverCancelledToken(),
            _Progress(),
        )

    assert service.cover_requests == []


@pytest.mark.skipif(FFMPEG is None or FFPROBE is None, reason="bundled FFmpeg is unavailable")
@pytest.mark.parametrize(
    ("image_name", "size"),
    [
        ("Book.png", (101, 55)),
        ("Ok%adka 50% zażółć.png", (101, 55)),
        ("Book.png", (55, 101)),
        ("Book.png", (3840, 2160)),
    ],
)
def test_a_real_cover_keeps_the_whole_recording_and_plays_as_an_mp4(
    tmp_path: Path,
    image_name: str,
    size: tuple[int, int],
) -> None:
    task: PlanTask
    snapshot: ArtifactSnapshot
    task, snapshot, _ = _cover_snapshot(tmp_path, image_name=image_name, size=size)
    audio: Path | None = snapshot.require_ready("audio").path
    assert audio is not None
    subprocess.run(  # noqa: S603
        [str(FFMPEG), "-y", "-hide_banner", "-f", "lavfi", "-i", "sine=duration=3.37", "-c:a", "aac", str(audio)],
        check=True,
        capture_output=True,
    )
    service: CompositionService = CompositionService(CompositionConfig(), ffmpeg=FFMPEG, ffprobe=FFPROBE)

    result: TaskResult = CompositionTaskHandler(service, run_root=tmp_path / "run").execute(
        task,
        snapshot,
        NeverCancelledToken(),
        _Progress(),
    )

    produced: Path = result.outputs[0].path
    probed = subprocess.run(  # noqa: S603
        [
            str(FFPROBE),
            "-v",
            "error",
            "-of",
            "json",
            "-show_format",
            "-show_streams",
            str(produced),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload: dict[str, list[dict[str, object]]] = json.loads(probed.stdout)
    kinds: dict[str, dict[str, object]] = {str(stream["codec_type"]): stream for stream in payload["streams"]}
    assert set(kinds) == {"video", "audio"}
    assert (kinds["video"]["width"], kinds["video"]["height"]) == (1920, 1080)
    assert kinds["video"]["r_frame_rate"] == "25/1"
    audio_duration: float = float(str(kinds["audio"]["duration"]))
    video_duration: float = float(str(kinds["video"]["duration"]))
    assert audio_duration == pytest.approx(3.37, abs=0.05)
    assert video_duration >= audio_duration
    assert video_duration - audio_duration <= 0.04


@pytest.mark.skipif(FFMPEG is None or FFPROBE is None, reason="bundled FFmpeg is unavailable")
def test_an_interrupted_cover_encode_leaves_no_product_and_no_half_written_file(tmp_path: Path) -> None:
    image: Path = tmp_path / "Book.png"
    Image.new("RGB", (1280, 720), (10, 20, 30)).save(image)
    audio: Path = tmp_path / "Book.m4a"
    subprocess.run(  # noqa: S603
        [str(FFMPEG), "-y", "-hide_banner", "-f", "lavfi", "-i", "sine=duration=90", "-c:a", "aac", str(audio)],
        check=True,
        capture_output=True,
    )
    destination: Path = tmp_path / "Book.cover.mp4"
    cancel: threading.Event = threading.Event()

    class _CancellingSink:
        def on_composition_phase(self, name: str, phase: str, percent: int | None) -> None:
            del name, phase, percent
            cancel.set()

    service: CompositionService = CompositionService(CompositionConfig(), ffmpeg=FFMPEG, ffprobe=FFPROBE)

    with pytest.raises(AniShiftError):
        service.compose_cover(
            CoverCompositionRequest(still_image=image, audio=audio, destination=destination),
            callbacks=_CancellingSink(),
            cancel=cancel,
        )

    assert not destination.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["Book.m4a", "Book.png"]


@pytest.mark.skipif(FFMPEG is None or FFPROBE is None, reason="bundled FFmpeg is unavailable")
def test_real_composition_emits_progress_and_keeps_destination_private(tmp_path: Path) -> None:
    task, snapshot, destination = _snapshot(tmp_path)
    source: Path | None = snapshot.require_ready("video").path
    assert source is not None
    subprocess.run(  # noqa: S603
        [
            str(FFMPEG),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x120:rate=10:duration=1",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    progress: _Progress = _Progress()
    service: CompositionService = CompositionService(CompositionConfig(), ffmpeg=FFMPEG, ffprobe=FFPROBE)

    result: TaskResult = CompositionTaskHandler(service, run_root=tmp_path / "run").execute(
        task,
        snapshot,
        NeverCancelledToken(),
        progress,
    )

    assert destination.read_bytes() == b"previous"
    assert result.outputs[0].path.stat().st_size > 0
    assert len(progress.notifications) > 1
    assert all(
        event.progress_percent is not None and event.progress_percent < 100 for event in progress.notifications[:-1]
    )
    assert progress.notifications[-1].progress_percent == 100
