"""Application adapters for narration mixing and audio transcoding tasks."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final, Never, Protocol

from anishift.application.artifacts import Artifact, ArtifactKind
from anishift.application.cancellation import CancellationToken
from anishift.application.events import WorkerNotification, WorkerNotificationKind
from anishift.application.intents import NarrationTimeline
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.products import product_suffix
from anishift.application.results import ArtifactSnapshot, ProducedArtifact, TaskResult
from anishift.application.scheduler_contracts import TaskProgressSink
from anishift.application.task_paths import task_staging_path
from anishift.application.tts_handler import load_narration_manifest
from anishift.errors import ExecutionError
from anishift.services.audio import AudioRenderRequest, AudioRenderResult, AudioRenderStatus, TimedClip
from anishift.services.audio.types import AudioFormat

__all__ = ["AudioTaskHandler"]

# ── Constants ────────────────────────────────────────────────────────────────

_MIX_INPUT_COUNTS: Final[Mapping[str, int]] = MappingProxyType({"video": 2, "standalone": 1})
"""Inputs each mix really reads: a video mix adds the original audio a standalone recording never has."""

_IN_PROGRESS_PERCENT: Final[int] = 99
"""Highest measured percentage before the output passes handler validation."""


class AudioMixer(Protocol):
    """Configured narration renderer used for one run."""

    def render(
        self,
        request: AudioRenderRequest,
        *,
        callbacks: AudioProgressObserver | None = None,
        on_percent: Callable[[int], None] | None = None,
        cancel: threading.Event | None = None,
    ) -> AudioRenderResult:
        """Render one narration mix."""
        ...


class AudioTranscoder(Protocol):
    """Configured single-stream audio transcoder."""

    def transcode(
        self,
        source: Path,
        destination: Path,
        *,
        cancel: threading.Event,
        on_percent: Callable[[int], None] | None = None,
    ) -> Path:
        """Transcode one ready audio source into the configured profile."""
        ...


class AudioProgressObserver(Protocol):
    """Observer accepted by the audio renderer."""

    def on_audio_phase(self, scope_id: str, phase: str) -> None:
        """Observe one internal audio phase."""
        ...


class _ProgressObserver:
    __slots__ = ("_phase", "_progress", "_task_id")

    def __init__(self, task_id: str, progress: TaskProgressSink) -> None:
        self._task_id: str = task_id
        self._progress: TaskProgressSink = progress
        self._phase: str = "audio"

    def on_audio_phase(self, scope_id: str, phase: str) -> None:
        del scope_id
        self._phase = phase
        self._progress.emit(WorkerNotification(WorkerNotificationKind.PROGRESS, self._task_id, None, phase))

    def on_percent(self, percent: int) -> None:
        self._progress.emit(
            WorkerNotification(
                WorkerNotificationKind.PROGRESS,
                self._task_id,
                min(percent, _IN_PROGRESS_PERCENT),
                self._phase,
            )
        )


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
                result = self._transcode(task, artifacts, event, progress)
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
        mix_source: str = _mix_source(task)
        if len(task.requires) != _MIX_INPUT_COUNTS[mix_source] or len(task.produces) != 1:
            _raise_execution("Narration mixing requires the inputs of its own mix source and one output")
        inputs: tuple[Artifact, ...] = tuple(artifacts.require_ready(item) for item in task.requires)
        manifest_artifact: Artifact = _one(inputs, ArtifactKind.TTS_MANIFEST)
        source_audio_path: Path | None = None
        if mix_source == "video":
            source_audio_path = _one(inputs, ArtifactKind.SOURCE_AUDIO).path
            if source_audio_path is None:
                _raise_execution("Narration mixing received an invalid artifact contract")
        output: Artifact = artifacts.require_output(task.produces[0])
        if manifest_artifact.path is None or output.kind is not ArtifactKind.NARRATION_AUDIO:
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
        destination: Path = task_staging_path(
            self._run_root,
            task,
            output,
            product_suffix(ArtifactKind.NARRATION_AUDIO, audio_profile=profile),
        )
        observer: _ProgressObserver = _ProgressObserver(task.task_id, progress)
        rendered: AudioRenderResult = self._mixer.render(
            AudioRenderRequest(
                manifest.scope_id,
                synthetic_source,
                source_audio_path,
                clips,
                self._run_root / task.group_id / "audio",
                destination,
                paragraph_pauses=manifest.timeline is NarrationTimeline.CONTINUOUS,
            ),
            callbacks=observer,
            on_percent=observer.on_percent,
            cancel=cancel,
        )
        if rendered.status not in {AudioRenderStatus.COMPLETED, AudioRenderStatus.RESUME_HIT}:
            _raise_execution("Narration audio was not rendered")
        path: Path | None = rendered.output_path
        if path != destination or not path.is_file():
            _raise_execution("Narration renderer returned an invalid output")
        return TaskResult(task.task_id, (ProducedArtifact(output.artifact_id, path, {"validated": True}),))

    def _transcode(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: threading.Event,
        progress: TaskProgressSink,
    ) -> TaskResult:
        if len(task.requires) != 1 or len(task.produces) != 1:
            _raise_execution("Audio transcoding requires one input and output")
        source: Artifact = artifacts.require_ready(task.requires[0])
        output: Artifact = artifacts.require_output(task.produces[0])
        if source.path is None or source.kind is not ArtifactKind.NARRATION_AUDIO:
            _raise_execution("Audio transcoding requires ready narration audio")
        profile: str = _profile(task, output)
        destination: Path = task_staging_path(
            self._run_root,
            task,
            output,
            product_suffix(ArtifactKind.NARRATION_AUDIO, audio_profile=profile),
        )
        observer: _ProgressObserver = _ProgressObserver(task.task_id, progress)
        observer.on_audio_phase(task.group_id, "transcoding")
        path: Path = self._transcoder.transcode(
            source.path,
            destination,
            cancel=cancel,
            on_percent=observer.on_percent,
        )
        if path != destination or not path.is_file():
            _raise_execution("Audio transcoder returned an invalid output")
        return TaskResult(task.task_id, (ProducedArtifact(output.artifact_id, path, {"validated": True}),))


def _one(artifacts: tuple[Artifact, ...], kind: ArtifactKind) -> Artifact:
    matching: tuple[Artifact, ...] = tuple(artifact for artifact in artifacts if artifact.kind is kind)
    if len(matching) != 1:
        _raise_execution(f"Audio task requires exactly one {kind.value} artifact")
    return matching[0]


def _mix_source(task: PlanTask) -> str:
    value: str | int | bool | None = dict(task.parameters).get("mix_source")
    if not isinstance(value, str) or value not in _MIX_INPUT_COUNTS:
        _raise_execution("Narration mixing requires a planned mix source")
    return value


def _profile(task: PlanTask, output: Artifact) -> str:
    value: str | int | bool | None = dict(task.parameters).get("output_profile")
    if not isinstance(value, str) or output.audio_codec != value:
        _raise_execution("Audio output profile does not match the planned artifact")
    return value


def _mirror_cancel(cancel: CancellationToken, event: threading.Event, stop: threading.Event) -> None:
    while not stop.wait(0.05):
        if cancel.is_cancelled():
            event.set()
            return


def _raise_execution(message: str) -> Never:
    raise ExecutionError(message)
