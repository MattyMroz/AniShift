"""Run-scoped TTS task adapter and private narration-manifest contract."""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Never, Protocol

from anishift.application.artifacts import Artifact, ArtifactKind
from anishift.application.cancellation import CancellationToken
from anishift.application.events import WorkerNotification, WorkerNotificationKind
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, ProducedArtifact, TaskResult
from anishift.application.scheduler_contracts import TaskProgressSink
from anishift.application.task_paths import task_staging_path
from anishift.errors import ErrorCode, ErrorContext, ExecutionError
from anishift.services.subtitles import SubtitleKind, load_subtitles, split_subtitles, subtitle_kind
from anishift.services.tts import (
    SpeechBatch,
    SpeechBatchProgress,
    SpeechBatchResult,
    SpeechBatchStatus,
    SpeechRequest,
    SpeechRequestProgress,
    SpeechRetryProgress,
)
from anishift.services.tts.validation import is_speech_text

__all__ = [
    "NarrationManifest",
    "NarrationManifestClip",
    "NarrationTiming",
    "TtsTaskHandler",
    "build_narration_manifest",
    "load_narration_manifest",
]


class TtsExecutor(Protocol):
    """One run-scoped synchronous TTS facade sharing its provider runtime."""

    def synthesize(self, batch: SpeechBatch, *, callbacks: TtsProgressObserver) -> SpeechBatchResult:
        """Synthesize one group batch on the shared event-loop thread."""
        ...

    def cancel(self) -> None:
        """Cancel all provider work belonging to the current run."""
        ...

    def close(self) -> None:
        """Close the shared provider runtime exactly once after the run."""
        ...


class TtsProgressObserver(Protocol):
    """Subset of TTS progress callbacks consumed by the facade."""

    def on_batch_state(self, state: SpeechBatchProgress) -> None: ...

    def on_request_committed(self, update: SpeechRequestProgress) -> None: ...

    def on_request_retry(self, update: SpeechRetryProgress) -> None: ...


@dataclass(frozen=True, slots=True)
class NarrationManifestClip:
    """One validated TTS clip paired with its subtitle timing."""

    request_id: str
    start_ms: int
    end_ms: int
    source_order: int
    path: Path
    format: str
    sample_rate: int
    channels: int
    duration_ms: int


@dataclass(frozen=True, slots=True)
class NarrationManifest:
    """Private handoff from synthesis to audio mixing."""

    scope_id: str
    clips: tuple[NarrationManifestClip, ...]


@dataclass(frozen=True, slots=True)
class NarrationTiming:
    """Caller-owned timing paired with one opaque TTS request ID."""

    request_id: str
    start_ms: int
    end_ms: int
    source_order: int


class _ProgressObserver:
    __slots__ = ("_progress", "_task_id")

    def __init__(self, task_id: str, progress: TaskProgressSink) -> None:
        self._task_id: str = task_id
        self._progress: TaskProgressSink = progress

    def on_batch_state(self, state: SpeechBatchProgress) -> None:
        total: int = state.total_required_requests
        percent: int = 100 if total == 0 else state.committed_required_requests * 100 // total
        self._progress.emit(WorkerNotification(WorkerNotificationKind.PROGRESS, self._task_id, percent))

    def on_request_committed(self, update: SpeechRequestProgress) -> None:
        del update

    def on_request_retry(self, update: SpeechRetryProgress) -> None:
        message: str = f"TTS retry {update.retry_number}/{update.max_retries}"
        self._progress.emit(WorkerNotification(WorkerNotificationKind.RETRY, self._task_id, message=message))


class TtsTaskHandler:
    """Synthesize one spoken-subtitle artifact through a run-scoped facade."""

    __slots__ = ("_group_ranks", "_run_root", "_service")

    def __init__(self, service: TtsExecutor, *, run_root: Path, group_ranks: Mapping[str, int]) -> None:
        self._service: TtsExecutor = service
        self._run_root: Path = run_root
        self._group_ranks: dict[str, int] = dict(group_ranks)
        ranks: tuple[int, ...] = tuple(self._group_ranks.values())
        if any(type(rank) is not int or rank < 0 for rank in ranks) or len(ranks) != len(set(ranks)):
            message: str = "TTS group ranks must be unique non-negative integers"
            raise ValueError(message)

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        """Synthesize a complete batch and write its validated private manifest."""
        cancel.raise_if_cancelled()
        if task.kind is not TaskKind.SYNTHESIZE_SPEECH or len(task.requires) != 1 or len(task.produces) != 1:
            _raise_execution("TTS handler requires one synthesize task input and output")
        source: Artifact = artifacts.require_ready(task.requires[0])
        output: Artifact = artifacts.require_output(task.produces[0])
        valid_contract: bool = (
            source.kind is ArtifactKind.SPOKEN_PL
            and source.path is not None
            and output.kind is ArtifactKind.TTS_MANIFEST
        )
        if not valid_contract:
            _raise_execution("TTS task requires spoken Polish subtitles and a manifest output")
        if source.path is None:
            _raise_execution("TTS spoken input requires a runtime path")
        kind: SubtitleKind | None = subtitle_kind(source.path)
        if kind is None:
            _raise_execution("TTS spoken input must be ASS or SRT")
        split = split_subtitles(load_subtitles(source.path), kind=kind)
        requests: list[SpeechRequest] = []
        timings: list[NarrationTiming] = []
        for line in split.spoken:
            if not is_speech_text(line.text):
                continue
            request_id: str = f"{task.group_id}-{line.order}"
            requests.append(SpeechRequest(request_id, line.text, len(requests)))
            timings.append(NarrationTiming(request_id, line.start, line.end, line.order))
        batch_rank: int | None = self._group_ranks.get(task.group_id)
        if batch_rank is None:
            _raise_execution("TTS task group is missing its natural-order rank")
        batch = SpeechBatch(task.group_id, batch_rank, tuple(requests))
        stop = threading.Event()
        watcher = threading.Thread(target=self._watch_cancel, args=(cancel, stop), daemon=True)
        watcher.start()
        try:
            result: SpeechBatchResult = self._service.synthesize(
                batch,
                callbacks=_ProgressObserver(task.task_id, progress),
            )
        finally:
            stop.set()
            watcher.join()
        cancel.raise_if_cancelled()
        try:
            manifest: NarrationManifest = build_narration_manifest(
                result,
                tuple(timings),
                expected_scope_id=task.group_id,
            )
        except ValueError as error:
            raise ExecutionError(str(error)) from error
        destination: Path = task_staging_path(self._run_root, task, output, ".json")
        destination.write_text(json.dumps(_manifest_json(manifest), ensure_ascii=False), encoding="utf-8")
        metadata: dict[str, str | int | bool] = {"clip_count": len(manifest.clips)}
        return TaskResult(task.task_id, (ProducedArtifact(output.artifact_id, destination, metadata),))

    def cancel(self) -> None:
        """Forward run cancellation to the shared TTS facade."""
        self._service.cancel()

    def close(self) -> None:
        """Close the shared TTS facade once at the run boundary."""
        self._service.close()

    def _watch_cancel(self, cancel: CancellationToken, stop: threading.Event) -> None:
        while not stop.wait(0.05):
            if cancel.is_cancelled():
                self._service.cancel()
                return


def load_narration_manifest(path: Path) -> NarrationManifest:
    """Load and validate one private narration manifest."""
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
        return _decode_manifest(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        context = ErrorContext(code=ErrorCode.TTS_FAILED, message="Narration manifest is invalid")
        raise ExecutionError(context=context) from error


def build_narration_manifest(
    result: SpeechBatchResult,
    timings: tuple[NarrationTiming, ...],
    *,
    expected_scope_id: str,
    allow_skipped_requests: bool = False,
) -> NarrationManifest:
    """Validate one TTS result and restore caller-owned timing by request ID."""
    if result.status is not SpeechBatchStatus.COMPLETED or result.failure is not None:
        _raise_manifest("TTS batch did not complete")
    if result.scope_id != expected_scope_id:
        _raise_manifest("TTS result scope does not match the submitted batch")
    timing_by_id: dict[str, NarrationTiming] = {timing.request_id: timing for timing in timings}
    if len(timing_by_id) != len(timings):
        _raise_manifest("Narration timing contains duplicate request IDs")
    expected_ids: set[str] = set(timing_by_id)
    returned_ids: tuple[str, ...] = tuple(execution.request.request_id for execution in result.requests)
    if len(returned_ids) != len(set(returned_ids)) or set(returned_ids) != expected_ids:
        _raise_manifest("TTS result request IDs do not match the submitted batch")
    clips: list[NarrationManifestClip] = []
    for execution in result.requests:
        clip = execution.speech_clip
        timing: NarrationTiming | None = timing_by_id.get(execution.request.request_id)
        if timing is None:
            _raise_manifest("Completed TTS batch lacks a required clip")
        if clip is None:
            if allow_skipped_requests:
                continue
            _raise_manifest("Completed TTS batch lacks a required clip")
        if clip.request_id != execution.request.request_id:
            _raise_manifest("TTS clip ID does not match its request")
        clips.append(
            NarrationManifestClip(
                clip.request_id,
                timing.start_ms,
                timing.end_ms,
                timing.source_order,
                clip.path,
                clip.format.value,
                clip.sample_rate,
                clip.channels,
                clip.duration_ms,
            )
        )
    return NarrationManifest(result.scope_id, tuple(clips))


def _manifest_json(manifest: NarrationManifest) -> dict[str, object]:
    return {
        "scope_id": manifest.scope_id,
        "clips": [
            {
                "request_id": clip.request_id,
                "start_ms": clip.start_ms,
                "end_ms": clip.end_ms,
                "source_order": clip.source_order,
                "path": str(clip.path),
                "format": clip.format,
                "sample_rate": clip.sample_rate,
                "channels": clip.channels,
                "duration_ms": clip.duration_ms,
            }
            for clip in manifest.clips
        ],
    }


def _manifest_clip(value: object) -> NarrationManifestClip:
    if not isinstance(value, dict):
        raise TypeError
    return NarrationManifestClip(
        request_id=str(value["request_id"]),
        start_ms=int(value["start_ms"]),
        end_ms=int(value["end_ms"]),
        source_order=int(value["source_order"]),
        path=Path(str(value["path"])),
        format=str(value["format"]),
        sample_rate=int(value["sample_rate"]),
        channels=int(value["channels"]),
        duration_ms=int(value["duration_ms"]),
    )


def _decode_manifest(payload: object) -> NarrationManifest:
    if not isinstance(payload, dict) or not isinstance(payload.get("scope_id"), str):
        raise TypeError
    raw_clips: object = payload.get("clips")
    if not isinstance(raw_clips, list):
        raise TypeError
    clips: tuple[NarrationManifestClip, ...] = tuple(_manifest_clip(item) for item in raw_clips)
    return NarrationManifest(payload["scope_id"], clips)


def _raise_execution(message: str) -> Never:
    raise ExecutionError(message)


def _raise_manifest(message: str) -> Never:
    raise ValueError(message)
