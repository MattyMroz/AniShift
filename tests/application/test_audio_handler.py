from __future__ import annotations

import json
import threading
import wave
from collections.abc import Callable
from pathlib import Path

import pytest

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.audio_handler import AudioProgressObserver, AudioTaskHandler
from anishift.application.cancellation import EventCancellationToken, NeverCancelledToken
from anishift.application.events import WorkerNotification
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.errors import ErrorCode, ExecutionError
from anishift.platform.binaries import Binary, resolve_binary
from anishift.services.audio import (
    AudioConfig,
    AudioRenderRequest,
    AudioRenderResult,
    AudioRenderStatus,
    AudioTranscodeService,
)

FFMPEG = resolve_binary(Binary.FFMPEG)
FFPROBE = resolve_binary(Binary.FFPROBE)


class _Progress:
    def __init__(self) -> None:
        self.notifications: list[WorkerNotification] = []

    def emit(self, notification: WorkerNotification) -> None:
        self.notifications.append(notification)


class _Mixer:
    def render(
        self,
        request: AudioRenderRequest,
        *,
        callbacks: AudioProgressObserver | None = None,
        on_percent: Callable[[int], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> AudioRenderResult:
        assert cancel is not None
        assert cancel.is_set() is False
        if callbacks is not None:
            callbacks.on_audio_phase(request.scope_id, "mixing")
        if on_percent is not None:
            on_percent(40)
            on_percent(100)
        output = request.source_path.with_suffix(".eac3")
        output.write_bytes(b"mixed")
        return AudioRenderResult(request.scope_id, AudioRenderStatus.COMPLETED, None, output, None, (), (), "n", "m")


class _Transcoder:
    def __init__(self, *, invalid_output: bool = False) -> None:
        self.invalid_output: bool = invalid_output

    def transcode(
        self,
        source: Path,
        destination: Path,
        *,
        cancel: threading.Event,
        on_percent: Callable[[int], None] | None = None,
    ) -> Path:
        assert cancel.is_set() is False
        destination.write_bytes(source.read_bytes())
        if on_percent is not None:
            on_percent(50)
            on_percent(100)
        return source if self.invalid_output else destination


def _ready(artifact_id: str, kind: ArtifactKind, path: Path) -> Artifact:
    return Artifact(artifact_id, "group-1", kind, path, ArtifactState.READY, ArtifactLifetime.SOURCE, path)


def _output(artifact_id: str) -> Artifact:
    return Artifact(
        artifact_id,
        "group-1",
        ArtifactKind.NARRATION_AUDIO,
        None,
        ArtifactState.MISSING,
        ArtifactLifetime.INTERMEDIATE,
        audio_codec="eac3",
    )


def test_audio_handler_mixes_manifest_and_source_audio(tmp_path: Path) -> None:
    source_path = tmp_path / "source.ac3"
    source_path.write_bytes(b"source")
    clip_path = tmp_path / "clip.mp3"
    clip_path.write_bytes(b"clip")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "scope_id": "group-1",
                "clips": [
                    {
                        "request_id": "r1",
                        "start_ms": 100,
                        "end_ms": 900,
                        "source_order": 0,
                        "path": str(clip_path),
                        "format": "mp3",
                        "sample_rate": 24000,
                        "channels": 1,
                        "duration_ms": 500,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    source = _ready("source", ArtifactKind.SOURCE_AUDIO, source_path)
    manifest = _ready("manifest", ArtifactKind.TTS_MANIFEST, manifest_path)
    output = _output("narration")
    task = PlanTask(
        "mix",
        "group-1",
        TaskKind.MIX_NARRATION,
        ("source", "manifest"),
        ("narration",),
        (),
        "audio:default",
        (("output_profile", "eac3"),),
    )

    progress: _Progress = _Progress()
    result: TaskResult = AudioTaskHandler(_Mixer(), _Transcoder(), run_root=tmp_path / "run").execute(
        task,
        ArtifactSnapshot({"source": source, "manifest": manifest}, {"narration": output}),
        NeverCancelledToken(),
        progress,
    )

    assert result.outputs[0].path.read_bytes() == b"mixed"
    assert result.outputs[0].metadata["validated"] is True
    assert [event.progress_percent for event in progress.notifications] == [None, 40, 99, 100]


@pytest.mark.parametrize("invalid_output", [False, True])
def test_audio_handler_transcodes_ready_narration(tmp_path: Path, invalid_output: bool) -> None:
    source_path = tmp_path / "narration.wav"
    source_path.write_bytes(b"audio")
    source = _ready("source", ArtifactKind.NARRATION_AUDIO, source_path)
    output = _output("transcoded")
    task = PlanTask(
        "transcode",
        "group-1",
        TaskKind.TRANSCODE_AUDIO,
        ("source",),
        ("transcoded",),
        (),
        "audio:default",
        (("output_profile", "eac3"),),
    )

    progress: _Progress = _Progress()
    handler: AudioTaskHandler = AudioTaskHandler(
        _Mixer(),
        _Transcoder(invalid_output=invalid_output),
        run_root=tmp_path / "run",
    )
    snapshot: ArtifactSnapshot = ArtifactSnapshot({"source": source}, {"transcoded": output})
    if invalid_output:
        with pytest.raises(ExecutionError, match="invalid output"):
            handler.execute(task, snapshot, NeverCancelledToken(), progress)
        assert [event.progress_percent for event in progress.notifications] == [None, 50, 99]
        return
    result: TaskResult = handler.execute(
        task,
        snapshot,
        NeverCancelledToken(),
        progress,
    )

    assert result.outputs[0].path.suffix == ".eac3"
    assert result.outputs[0].path.read_bytes() == b"audio"
    assert [event.progress_percent for event in progress.notifications] == [None, 50, 99, 100]


def test_audio_handler_rejects_cancelled_task_before_service_call(tmp_path: Path) -> None:
    token = EventCancellationToken()
    token.cancel()
    task = PlanTask(
        "audio",
        "group-1",
        TaskKind.TRANSCODE_AUDIO,
        ("source",),
        ("output",),
        (),
        "audio:default",
        (("output_profile", "eac3"),),
    )

    with pytest.raises(ExecutionError) as raised:
        AudioTaskHandler(_Mixer(), _Transcoder(), run_root=tmp_path / "run").execute(
            task,
            ArtifactSnapshot({}, {}),
            token,
            _Progress(),
        )

    assert raised.value.context.code is ErrorCode.CANCELLED


@pytest.mark.skipif(FFMPEG is None or FFPROBE is None, reason="bundled FFmpeg is unavailable")
def test_real_audio_handler_reports_measured_progress_before_success(tmp_path: Path) -> None:
    source_path: Path = tmp_path / "narration.wav"
    with wave.open(str(source_path), "wb") as source_wav:
        source_wav.setnchannels(1)
        source_wav.setsampwidth(2)
        source_wav.setframerate(48_000)
        source_wav.writeframes(b"\x00" * 96_000)
    source: Artifact = _ready("source", ArtifactKind.NARRATION_AUDIO, source_path)
    output: Artifact = _output("transcoded")
    task: PlanTask = PlanTask(
        "transcode",
        "group-1",
        TaskKind.TRANSCODE_AUDIO,
        ("source",),
        ("transcoded",),
        (),
        "audio:default",
        (("output_profile", "eac3"),),
    )
    progress: _Progress = _Progress()
    transcoder: AudioTranscodeService = AudioTranscodeService(AudioConfig(), ffmpeg=FFMPEG, ffprobe=FFPROBE)

    result: TaskResult = AudioTaskHandler(_Mixer(), transcoder, run_root=tmp_path / "run").execute(
        task,
        ArtifactSnapshot({"source": source}, {"transcoded": output}),
        NeverCancelledToken(),
        progress,
    )

    assert result.outputs[0].metadata["validated"] is True
    assert result.outputs[0].path.stat().st_size > 0
    assert progress.notifications[0].progress_percent is None
    assert any(event.progress_percent == 99 for event in progress.notifications[:-1])
    assert all(event.progress_percent != 100 for event in progress.notifications[:-1])
    assert progress.notifications[-1].progress_percent == 100
