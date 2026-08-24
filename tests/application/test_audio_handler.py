from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState
from anishift.application.audio_handler import AudioProgressObserver, AudioTaskHandler
from anishift.application.cancellation import EventCancellationToken, NeverCancelledToken
from anishift.application.events import WorkerNotification
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, TaskResult
from anishift.errors import ErrorCode, ExecutionError
from anishift.services.audio import AudioRenderRequest, AudioRenderResult, AudioRenderStatus


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
        cancel: threading.Event | None = None,
    ) -> AudioRenderResult:
        assert cancel is not None
        assert cancel.is_set() is False
        if callbacks is not None:
            callbacks.on_audio_phase(request.scope_id, "mixing")
        output = request.source_path.with_suffix(".eac3")
        output.write_bytes(b"mixed")
        return AudioRenderResult(request.scope_id, AudioRenderStatus.COMPLETED, None, output, None, (), (), "n", "m")


class _Transcoder:
    def transcode(self, source: Path, destination: Path, *, cancel: threading.Event) -> Path:
        assert cancel.is_set() is False
        destination.write_bytes(source.read_bytes())
        return destination


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

    result: TaskResult = AudioTaskHandler(_Mixer(), _Transcoder(), run_root=tmp_path / "run").execute(
        task,
        ArtifactSnapshot({"source": source, "manifest": manifest}, {"narration": output}),
        NeverCancelledToken(),
        _Progress(),
    )

    assert result.outputs[0].path.read_bytes() == b"mixed"
    assert result.outputs[0].metadata["validated"] is True


def test_audio_handler_transcodes_ready_narration(tmp_path: Path) -> None:
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

    result: TaskResult = AudioTaskHandler(_Mixer(), _Transcoder(), run_root=tmp_path / "run").execute(
        task,
        ArtifactSnapshot({"source": source}, {"transcoded": output}),
        NeverCancelledToken(),
        _Progress(),
    )

    assert result.outputs[0].path.suffix == ".eac3"
    assert result.outputs[0].path.read_bytes() == b"audio"


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
