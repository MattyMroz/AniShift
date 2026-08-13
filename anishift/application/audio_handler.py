"""Application adapters for narration mixing and audio transcoding tasks."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Final, Never, Protocol

from anishift.application.artifacts import Artifact, ArtifactKind
from anishift.application.cancellation import CancellationToken
from anishift.application.events import WorkerNotification, WorkerNotificationKind
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, ProducedArtifact, TaskResult
from anishift.application.scheduler_contracts import TaskProgressSink
from anishift.application.task_paths import task_staging_path
from anishift.application.tts_handler import load_narration_manifest
from anishift.errors import ExecutionError
from anishift.services.audio import AudioRenderRequest, AudioRenderResult, AudioRenderStatus, TimedClip
from anishift.services.audio.types import AudioFormat

__all__ = ["AudioTaskHandler"]

# ── Constants ────────────────────────────────────────────────────────────────

_MIX_INPUT_COUNT: Final[int] = 2
"""Required source-audio and manifest inputs for narration mixing."""


class AudioMixer(Protocol):
    """Configured narration renderer used for one run."""

    def render(
        self,
        request: AudioRenderRequest,
        *,
        callbacks: AudioProgressObserver | None = None,
        cancel: threading.Event | None = None,
    ) -> AudioRenderResult:
        """Render one narration mix."""
        ...


class AudioTranscoder(Protocol):
    """Configured single-stream audio transcoder."""

    def transcode(self, source: Path, destination: Path, *, cancel: threading.Event) -> Path:
        """Transcode one ready audio source into the configured profile."""
        ...


class AudioProgressObserver(Protocol):
    """Observer accepted by the audio renderer."""

    def on_audio_phase(self, scope_id: str, phase: str) -> None:
        """Observe one internal audio phase."""
        ...


class _ProgressObserver:
    __slots__ = ("_progress", "_task_id")

    def __init__(self, task_id: str, progress: TaskProgressSink) -> None:
        self._task_id: str = task_id
        self._progress: TaskProgressSink = progress

    def on_audio_phase(self, scope_id: str, phase: str) -> None:
        del scope_id
        self._progress.emit(WorkerNotification(WorkerNotificationKind.PROGRESS, self._task_id, 0, phase))


class AudioTaskHandler:
    """Execute planned audio work without selecting products or destinations."""

    __slots__ = ("_mixer", "_run_root", "_transcoder")

    def __init__(self, mixer: AudioMixer, transcoder: AudioTranscoder, *, run_root: Path) -> None:
        self._mixer: AudioMixer = mixer
        self._transcoder: AudioTranscoder = transcoder
        self._run_root: Path = run_root

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        """Dispatch one mix or transcode operation."""
        cancel.raise_if_cancelled()
        event = threading.Event()
        stop = threading.Event()
        watcher = threading.Thread(target=_mirror_cancel, args=(cancel, event, stop), daemon=True)
        watcher.start()
        try:
            if task.kind is TaskKind.MIX_NARRATION:
                result: TaskResult = self._mix(task, artifacts, event, progress)
            elif task.kind is TaskKind.TRANSCODE_AUDIO:
                result = self._transcode(task, artifacts, event)
            else:
                _raise_execution("Audio handler received an unsupported task")
        finally:
            stop.set()
            watcher.join()
        cancel.raise_if_cancelled()
        progress.emit(WorkerNotification(WorkerNotificationKind.PROGRESS, task.task_id, 100))
        return result

    def _mix(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: threading.Event,
        progress: TaskProgressSink,
    ) -> TaskResult:
        if len(task.requires) != _MIX_INPUT_COUNT or len(task.produces) != 1:
            _raise_execution("Narration mixing requires source audio, manifest, and one output")
        inputs: tuple[Artifact, ...] = tuple(artifacts.require_ready(item) for item in task.requires)
        source: Artifact = _one(inputs, ArtifactKind.SOURCE_AUDIO)
        manifest_artifact: Artifact = _one(inputs, ArtifactKind.TTS_MANIFEST)
        output: Artifact = artifacts.require_output(task.produces[0])
        if source.path is None or manifest_artifact.path is None or output.kind is not ArtifactKind.NARRATION_AUDIO:
            _raise_execution("Narration mixing received an invalid artifact contract")
        profile: str = _profile(task, output)
        manifest = load_narration_manifest(manifest_artifact.path)
        clips: tuple[TimedClip, ...] = tuple(
            TimedClip(
                clip.request_id,
                clip.start_ms,
                clip.end_ms,
                clip.source_order,
                clip.path,
                AudioFormat(clip.format),
                clip.sample_rate,
                clip.channels,
                clip.duration_ms,
            )
            for clip in manifest.clips
        )
        synthetic_source: Path = task_staging_path(self._run_root, task, output, ".source")
        rendered: AudioRenderResult = self._mixer.render(
            AudioRenderRequest(
                manifest.scope_id,
                synthetic_source,
                source.path,
                clips,
                self._run_root / task.group_id / "audio",
            ),
            callbacks=_ProgressObserver(task.task_id, progress),
            cancel=cancel,
        )
        if rendered.status not in {AudioRenderStatus.COMPLETED, AudioRenderStatus.RESUME_HIT}:
            _raise_execution("Narration audio was not rendered")
        path: Path | None = rendered.output_path
        if path is None or not path.is_file() or path.suffix.casefold() != _profile_suffix(profile):
            _raise_execution("Narration renderer returned an invalid output")
        return TaskResult(task.task_id, (ProducedArtifact(output.artifact_id, path, {"validated": True}),))

    def _transcode(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: threading.Event,
    ) -> TaskResult:
        if len(task.requires) != 1 or len(task.produces) != 1:
            _raise_execution("Audio transcoding requires one input and output")
        source: Artifact = artifacts.require_ready(task.requires[0])
        output: Artifact = artifacts.require_output(task.produces[0])
        if source.path is None or source.kind is not ArtifactKind.NARRATION_AUDIO:
            _raise_execution("Audio transcoding requires ready narration audio")
        profile: str = _profile(task, output)
        destination: Path = task_staging_path(self._run_root, task, output, _profile_suffix(profile))
        path: Path = self._transcoder.transcode(source.path, destination, cancel=cancel)
        if path != destination or not path.is_file():
            _raise_execution("Audio transcoder returned an invalid output")
        return TaskResult(task.task_id, (ProducedArtifact(output.artifact_id, path, {"validated": True}),))


def _one(artifacts: tuple[Artifact, ...], kind: ArtifactKind) -> Artifact:
    matching: tuple[Artifact, ...] = tuple(artifact for artifact in artifacts if artifact.kind is kind)
    if len(matching) != 1:
        _raise_execution(f"Audio task requires exactly one {kind.value} artifact")
    return matching[0]


def _profile(task: PlanTask, output: Artifact) -> str:
    value: str | int | bool | None = dict(task.parameters).get("output_profile")
    if not isinstance(value, str) or output.audio_codec != value:
        _raise_execution("Audio output profile does not match the planned artifact")
    return value


def _profile_suffix(profile: str) -> str:
    return ".m4a" if profile == "aac" else f".{profile}"


def _mirror_cancel(cancel: CancellationToken, event: threading.Event, stop: threading.Event) -> None:
    while not stop.wait(0.05):
        if cancel.is_cancelled():
            event.set()
            return


def _raise_execution(message: str) -> Never:
    raise ExecutionError(message)
