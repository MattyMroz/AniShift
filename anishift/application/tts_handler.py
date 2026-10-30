"""Run-scoped TTS task adapter and private narration-manifest contract."""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Final, Never, Protocol

from anishift.application.artifacts import Artifact, ArtifactKind
from anishift.application.cancellation import CancellationToken, mirror_cancel
from anishift.application.events import WorkerNotification, WorkerNotificationKind
from anishift.application.intents import NarrationTimeline
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, ProducedArtifact, TaskResult
from anishift.application.scheduler_contracts import TaskProgressSink
from anishift.application.sign_narration import (
    SignSelection,
    free_intervals,
    load_sign_candidates,
    reachable_signs,
    select_signs,
)
from anishift.application.task_paths import task_staging_path
from anishift.errors import ErrorCode, ErrorContext, ExecutionError
from anishift.services.audio import TimedClip
from anishift.services.audio.timeline import plan_timeline
from anishift.services.audio.types import AudioFormat
from anishift.services.subtitles import (
    SignCandidate,
    SpokenLine,
    SubtitleKind,
    load_subtitles,
    split_subtitles,
    subtitle_kind,
    txt_to_spoken,
)
from anishift.services.tts import (
    SpeechBatch,
    SpeechBatchProgress,
    SpeechBatchResult,
    SpeechRequest,
    SpeechRequestProgress,
    SpeechRetryProgress,
    SynthesizedRequest,
)
from anishift.services.tts.validation import is_speech_text
from anishift.text.boundaries import ends_sentence
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from pysubs2 import SSAFile

    from anishift.services.audio.types import NormalizedClip, TimelinePlan

__all__ = [
    "ClipPreparer",
    "NarrationManifest",
    "NarrationManifestClip",
    "NarrationTiming",
    "TtsTaskHandler",
    "build_narration_manifest",
    "load_narration_manifest",
    "timed_clip",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_MINIMUM_WINDOW_MS: Final[int] = 1
"""Shortest placement window kept for a subtitle that carries no duration."""

_TIMED_SCRIPT_KINDS: Final[frozenset[ArtifactKind]] = frozenset(
    {ArtifactKind.SPOKEN_PL, ArtifactKind.FULL_PL, ArtifactKind.SOURCE_SUBTITLES},
)
"""Scripts whose own cues carry the times a recording is able to keep."""

_UNTIMED_SCRIPT_KINDS: Final[frozenset[ArtifactKind]] = frozenset(
    {ArtifactKind.STANDALONE_TEXT, ArtifactKind.TRANSLATED_TEXT},
)
"""Scripts carrying words alone, read in file order because they hold no times at all."""

_MAX_INPUTS: Final[int] = 2
"""Inputs of a synthesis: the script, then optionally the on-screen signs the narrator may read."""

_SIGN_MODES: Final[frozenset[str]] = frozenset({"smart", "always"})
"""Sign narration modes that plan sign candidates for synthesis."""

_PREPARE_WORKERS: Final[int] = 4
"""Clips normalized at once to measure their true length."""

logger = get_logger(__name__)


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


class ClipPreparer(Protocol):
    """Run audio service normalizing one clip exactly as the narration mix will."""

    def prepare_clip(self, clip: TimedClip, *, tmp_root: Path, cancel: threading.Event | None) -> NormalizedClip:
        """Normalize one clip into its reusable PCM artifact."""
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
    """Private handoff from synthesis to audio mixing, carrying the reading its clips were recorded for."""

    scope_id: str
    clips: tuple[NarrationManifestClip, ...]
    timeline: NarrationTimeline


@dataclass(frozen=True, slots=True)
class NarrationTiming:
    """Caller-owned timing paired with one opaque TTS request ID."""

    request_id: str
    start_ms: int
    end_ms: int
    source_order: int


@dataclass(frozen=True, slots=True)
class _SignReading:
    """Validated sign candidates of one task, the mode weighing them and the audio service measuring them."""

    mode: str
    candidates: tuple[SignCandidate, ...]
    audio: ClipPreparer


class _ProgressObserver:
    __slots__ = ("_progress", "_task_id", "_visible_required")

    def __init__(self, task_id: str, progress: TaskProgressSink) -> None:
        self._task_id: str = task_id
        self._progress: TaskProgressSink = progress
        self._visible_required: int = 0

    def on_batch_state(self, state: SpeechBatchProgress) -> None:
        required: int = state.total_required_requests
        committed: int = state.committed_required_requests
        self._visible_required = max(
            self._visible_required,
            state.received_required_requests,
            committed,
        )
        percent: int = (
            100
            if required == 0 or committed >= required
            else min(99, (self._visible_required * 100 + required - 1) // required)
        )
        self._progress.emit(WorkerNotification(WorkerNotificationKind.PROGRESS, self._task_id, percent))

    def on_request_committed(self, update: SpeechRequestProgress) -> None:
        del update

    def on_request_retry(self, update: SpeechRetryProgress) -> None:
        message: str = f"TTS retry {update.retry_number}/{update.max_retries}"
        self._progress.emit(WorkerNotification(WorkerNotificationKind.RETRY, self._task_id, message=message))


class TtsTaskHandler:
    """Read one planned script aloud through a run-scoped facade, whatever document carries it."""

    __slots__ = (
        "_allowed_voice_ids",
        "_audio",
        "_group_ranks",
        "_reads_document",
        "_run_root",
        "_service",
        "_voice_id",
    )

    def __init__(  # noqa: PLR0913 - keyword-only run dependencies
        self,
        service: TtsExecutor,
        *,
        run_root: Path,
        group_ranks: Mapping[str, int],
        voice_id: str = "",
        allowed_voice_ids: frozenset[str] = frozenset(),
        audio: ClipPreparer | None = None,
        reads_document: bool = False,
    ) -> None:
        self._service: TtsExecutor = service
        self._reads_document: bool = reads_document
        self._audio: ClipPreparer | None = audio
        self._run_root: Path = run_root
        self._voice_id: str = voice_id
        self._allowed_voice_ids: frozenset[str] = allowed_voice_ids
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
        if (
            task.kind is not TaskKind.SYNTHESIZE_SPEECH
            or not 1 <= len(task.requires) <= _MAX_INPUTS
            or len(task.produces) != 1
        ):
            _raise_execution("TTS handler requires a script, optional sign candidates and one manifest output")
        source: Artifact = artifacts.require_ready(task.requires[0])
        output: Artifact = artifacts.require_output(task.produces[0])
        if source.path is None or output.kind is not ArtifactKind.TTS_MANIFEST:
            _raise_execution("TTS task requires a readable script and a manifest output")
        _require_planned_script(task, source)
        self._require_offered_voice()
        timeline: NarrationTimeline = _planned_timeline(task)
        if timeline is NarrationTimeline.SOURCE_TIMES and source.kind in _UNTIMED_SCRIPT_KINDS:
            _raise_execution("A plain text script carries no times a recording could keep")
        lines: tuple[SpokenLine, ...] = _script_lines(source.kind, source.path)
        requests, timings = _narration_batch(task.group_id, lines, timeline, join_open_lines=self._reads_document)
        batch_rank: int | None = self._group_ranks.get(task.group_id)
        if batch_rank is None:
            _raise_execution("TTS task group is missing its natural-order rank")
        signs: _SignReading | None = _sign_reading(task, artifacts, self._audio)
        in_document: tuple[SignCandidate, ...] = signs.candidates if signs is not None and self._reads_document else ()
        sign_requests, sign_timings = _sign_batch(task.group_id, in_document, first_rank=len(requests))
        batch = SpeechBatch(task.group_id, batch_rank, (*requests, *sign_requests))
        result: SpeechBatchResult = self._synthesize(batch, task, cancel, progress)
        spoken, read_signs = _split_signs(result, frozenset(timing.request_id for timing in sign_timings))
        manifest: NarrationManifest = _manifest(spoken, timings, task.group_id, timeline)
        metadata: dict[str, str | int | bool] = {}
        if signs is not None:
            recorded: dict[int, NarrationManifestClip] | None = (
                _sign_clips(read_signs, sign_timings, task.group_id) if self._reads_document else None
            )
            manifest, metadata = self._with_signs(task, signs, manifest, recorded, cancel, progress)
        destination: Path = task_staging_path(self._run_root, task, output, ".json")
        destination.write_text(json.dumps(_manifest_json(manifest), ensure_ascii=False), encoding="utf-8")
        metadata["clip_count"] = len(manifest.clips)
        return TaskResult(task.task_id, (ProducedArtifact(output.artifact_id, destination, metadata),))

    def _synthesize(
        self, batch: SpeechBatch, task: PlanTask, cancel: CancellationToken, progress: TaskProgressSink
    ) -> SpeechBatchResult:
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
        return result

    def _with_signs(  # noqa: PLR0913 - signs read with the script arrive already recorded
        self,
        task: PlanTask,
        signs: _SignReading,
        manifest: NarrationManifest,
        recorded: dict[int, NarrationManifestClip] | None,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> tuple[NarrationManifest, dict[str, str | int | bool]]:
        """Add the sign readings that fit the pauses of the spoken lines, recording the reachable ones if unread."""
        tmp_root: Path = self._run_root / task.group_id / "audio"
        lines: tuple[NormalizedClip, ...] = _prepare(signs.audio, manifest.clips, tmp_root, cancel)
        wanted: tuple[SignCandidate, ...] = signs.candidates
        if recorded is None:
            baseline: TimelinePlan | None = plan_timeline(lines)
            wanted = () if baseline is None else reachable_signs(wanted, free_intervals(baseline), baseline.sample_rate)
            recorded = self._record_signs(task, wanted, cancel, progress)
        unrecorded: tuple[int, ...] = tuple(candidate.group for candidate in wanted if candidate.group not in recorded)
        if unrecorded:
            logger.warning("Signs left out without a recording", task_id=task.task_id, unrecorded=len(unrecorded))
        prepared: tuple[NormalizedClip, ...] = _prepare(signs.audio, tuple(recorded.values()), tmp_root, cancel)
        selection: SignSelection = select_signs(
            signs.candidates, {clip.timed_clip.source_order: clip for clip in prepared}, lines, signs.mode
        )
        readings: tuple[NarrationManifestClip, ...] = tuple(
            replace(recorded[placement.group], start_ms=placement.start_ms, end_ms=placement.end_ms)
            for placement in selection.placements
        )
        logger.info(
            "Signs chosen for narration",
            task_id=task.task_id,
            mode=signs.mode,
            candidates=len(signs.candidates),
            synthesized=len(recorded),
            read=len(readings),
        )
        metadata: dict[str, str | int | bool] = {
            "sign_decisions": ",".join(f"{group}:{reason}" for group, reason in selection.decisions),
            "sign_chars_synthesized": sum(len(candidate.text) for candidate in wanted),
            "signs_read": len(readings),
            "signs_unrecorded": ",".join(str(group) for group in unrecorded),
        }
        return replace(manifest, clips=(*manifest.clips, *readings)), metadata

    def _record_signs(
        self,
        task: PlanTask,
        wanted: tuple[SignCandidate, ...],
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> dict[int, NarrationManifestClip]:
        """Synthesize every wanted sign once; a sign skipped or failed by the engine is missing."""
        if not wanted:
            return {}
        requests, timings = _sign_batch(task.group_id, wanted, first_rank=0)
        batch = SpeechBatch(task.group_id, self._group_ranks[task.group_id], requests)
        return _sign_clips(self._synthesize(batch, task, cancel, progress), timings, task.group_id)

    def _require_offered_voice(self) -> None:
        """Refuse a voice the chosen engine does not offer before a single request is paid for."""
        if not self._allowed_voice_ids or self._voice_id in self._allowed_voice_ids:
            return
        _raise_execution("The selected voice is not one the chosen TTS engine offers")

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
    timeline: NarrationTimeline,
    allow_missing_clips: bool = False,
) -> NarrationManifest:
    """Restore caller timing by request ID; a request without a clip fails unless missing clips are allowed."""
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
            _raise_manifest("TTS batch lacks a required clip")
        if clip is None:
            if allow_missing_clips:
                continue
            _raise_manifest("TTS batch lacks a required clip")
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
    return NarrationManifest(result.scope_id, tuple(clips), timeline)


def _sign_reading(task: PlanTask, artifacts: ArtifactSnapshot, audio: ClipPreparer | None) -> _SignReading | None:
    """Return the validated signs a task plans to read, before a single request is paid for."""
    if len(task.requires) < _MAX_INPUTS:
        return None
    signs: Artifact = artifacts.require_ready(task.requires[1])
    mode: str | int | bool | None = dict(task.parameters).get("sign_narration")
    if signs.kind is not ArtifactKind.SIGN_CANDIDATES or signs.path is None or not isinstance(mode, str):
        _raise_execution("TTS sign narration requires planned sign candidates and a reading mode")
    if mode not in _SIGN_MODES or audio is None:
        _raise_execution("TTS sign narration requires a reading mode and the run audio service")
    try:
        candidates: tuple[SignCandidate, ...] = load_sign_candidates(signs.path)
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        msg: str = "Sign candidates are invalid"
        raise ExecutionError(msg) from error
    return _SignReading(mode, candidates, audio)


def _sign_batch(
    group_id: str, candidates: tuple[SignCandidate, ...], *, first_rank: int
) -> tuple[tuple[SpeechRequest, ...], tuple[NarrationTiming, ...]]:
    """Pair every sign with a request ranked from *first_rank* and the window its text is on screen."""
    requests: tuple[SpeechRequest, ...] = tuple(
        SpeechRequest(f"{group_id}-sign-{candidate.group}", candidate.text, first_rank + index)
        for index, candidate in enumerate(candidates)
    )
    timings: tuple[NarrationTiming, ...] = tuple(
        NarrationTiming(request.request_id, *_placement_window(candidate.start, candidate.end), candidate.group)
        for request, candidate in zip(requests, candidates, strict=True)
    )
    return requests, timings


def _split_signs(result: SpeechBatchResult, sign_ids: frozenset[str]) -> tuple[SpeechBatchResult, SpeechBatchResult]:
    """Split one batch result into its spoken lines and the signs read in the same batch."""
    spoken: tuple[SynthesizedRequest, ...] = tuple(
        item for item in result.requests if item.request.request_id not in sign_ids
    )
    signs: tuple[SynthesizedRequest, ...] = tuple(
        item for item in result.requests if item.request.request_id in sign_ids
    )
    return replace(result, requests=spoken), replace(result, requests=signs)


def _manifest(
    result: SpeechBatchResult,
    timings: tuple[NarrationTiming, ...],
    scope_id: str,
    timeline: NarrationTimeline,
    *,
    allow_missing_clips: bool = False,
) -> NarrationManifest:
    try:
        return build_narration_manifest(
            result,
            timings,
            expected_scope_id=scope_id,
            timeline=timeline,
            allow_missing_clips=allow_missing_clips,
        )
    except ValueError as error:
        raise ExecutionError(str(error)) from error


def _sign_clips(
    result: SpeechBatchResult, timings: tuple[NarrationTiming, ...], scope_id: str
) -> dict[int, NarrationManifestClip]:
    """Return the recorded sign clips by sign group; a sign skipped or failed by the engine is missing."""
    manifest: NarrationManifest = _manifest(
        result, timings, scope_id, NarrationTimeline.SOURCE_TIMES, allow_missing_clips=True
    )
    return {clip.source_order: clip for clip in manifest.clips}


def _prepare(
    audio: ClipPreparer,
    clips: tuple[NarrationManifestClip, ...],
    tmp_root: Path,
    cancel: CancellationToken,
) -> tuple[NormalizedClip, ...]:
    event: threading.Event = threading.Event()
    stop: threading.Event = threading.Event()

    def prepare(clip: NarrationManifestClip) -> NormalizedClip:
        cancel.raise_if_cancelled()
        return audio.prepare_clip(timed_clip(clip), tmp_root=tmp_root, cancel=event)

    watcher: threading.Thread = threading.Thread(target=mirror_cancel, args=(cancel, event, stop), daemon=True)
    watcher.start()
    try:
        with ThreadPoolExecutor(max_workers=_PREPARE_WORKERS, thread_name_prefix="anishift-tts-prepare") as pool:
            prepared: tuple[NormalizedClip, ...] = tuple(pool.map(prepare, clips))
    finally:
        stop.set()
        watcher.join()
    cancel.raise_if_cancelled()
    return prepared


def timed_clip(clip: NarrationManifestClip) -> TimedClip:
    """Return the audio clip a manifest entry places at its own timing."""
    return TimedClip(
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


def _manifest_json(manifest: NarrationManifest) -> dict[str, object]:
    return {
        "scope_id": manifest.scope_id,
        "timeline": manifest.timeline.value,
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


def _require_planned_script(task: PlanTask, source: Artifact) -> None:
    declared: str | int | bool | None = dict(task.parameters).get("script_kind")
    if declared != source.kind.value:
        _raise_execution("TTS script does not match the document the plan chose to read")
    if source.kind not in _TIMED_SCRIPT_KINDS | _UNTIMED_SCRIPT_KINDS:
        _raise_execution("TTS cannot read the requested document kind")


def _planned_timeline(task: PlanTask) -> NarrationTimeline:
    declared: str | int | bool | None = dict(task.parameters).get("narration_timeline")
    timeline: NarrationTimeline | None = next(
        (candidate for candidate in NarrationTimeline if candidate.value == declared),
        None,
    )
    if timeline is None:
        _raise_execution("TTS task requires a planned narration timeline")
    return timeline


def _script_lines(kind: ArtifactKind, path: Path) -> tuple[SpokenLine, ...]:
    """Read one script into narrator lines in file order; a spoken-only script is read whole, unclassified."""
    if kind in _UNTIMED_SCRIPT_KINDS:
        return tuple(replace(line, order=order) for order, line in enumerate(txt_to_spoken(path)))
    subtitles: SubtitleKind | None = subtitle_kind(path)
    if subtitles is None:
        _raise_execution("TTS subtitle script must be ASS or SRT")
    document: SSAFile = load_subtitles(path)
    if kind is not ArtifactKind.SPOKEN_PL:
        return split_subtitles(document, kind=subtitles).spoken
    every_style: frozenset[str] = frozenset(event.style for event in document.events)
    return split_subtitles(document, kind=subtitles, spoken_styles=every_style, verdicts=()).spoken


def _narration_batch(
    group_id: str,
    lines: tuple[SpokenLine, ...],
    timeline: NarrationTimeline,
    *,
    join_open_lines: bool,
) -> tuple[tuple[SpeechRequest, ...], tuple[NarrationTiming, ...]]:
    """Pair every pronounceable line with the window *timeline* reads it in, refusing an unreadable script."""
    spoken: list[SpokenLine] = []
    previous_order: int | None = None
    for line in lines:
        if previous_order is not None and line.order <= previous_order:
            _raise_execution("TTS script lines must arrive in strictly increasing reading order")
        previous_order = line.order
        if is_speech_text(line.text):
            spoken.append(line)
    if not spoken:
        _raise_execution("TTS script carries no pronounceable text")
    if join_open_lines and timeline is NarrationTimeline.SOURCE_TIMES:
        spoken = _join_open_lines(spoken)
    requests: list[SpeechRequest] = []
    timings: list[NarrationTiming] = []
    for line in spoken:
        request_id: str = f"{group_id}-{line.order}"
        requests.append(SpeechRequest(request_id, line.text, len(requests)))
        start, end = _timing_window(line, timeline)
        timings.append(NarrationTiming(request_id, start, end, line.order))
    return tuple(requests), tuple(timings)


def _join_open_lines(lines: list[SpokenLine]) -> list[SpokenLine]:
    """Join each line left open into the next one starting before it ends, pairs only."""
    joined: list[SpokenLine] = []
    index: int = 0
    while index < len(lines):
        line: SpokenLine = lines[index]
        following: SpokenLine | None = lines[index + 1] if index + 1 < len(lines) else None
        index += 1
        if following is None or ends_sentence(line.text) or following.start > line.end:
            joined.append(line)
            continue
        joined.append(replace(line, text=f"{line.text} {following.text}", end=max(line.end, following.end)))
        index += 1
    return joined


def _timing_window(line: SpokenLine, timeline: NarrationTimeline) -> tuple[int, int]:
    """Return the window one line is placed in, which a continuous reading leaves for the mixer to serialize."""
    if timeline is NarrationTimeline.CONTINUOUS:
        return 0, _MINIMUM_WINDOW_MS
    return _placement_window(line.start, line.end)


def _placement_window(start_ms: int, end_ms: int) -> tuple[int, int]:
    """Return a positive window, because a subtitle may carry no duration at all."""
    start: int = max(start_ms, 0)
    return start, max(end_ms, start + _MINIMUM_WINDOW_MS)


def _manifest_clip(value: object) -> NarrationManifestClip:
    if not isinstance(value, dict):
        raise TypeError
    start, end = _placement_window(int(value["start_ms"]), int(value["end_ms"]))
    return NarrationManifestClip(
        request_id=str(value["request_id"]),
        start_ms=start,
        end_ms=end,
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
    return NarrationManifest(payload["scope_id"], clips, NarrationTimeline(payload["timeline"]))


def _raise_execution(message: str) -> Never:
    raise ExecutionError(message)


def _raise_manifest(message: str) -> Never:
    raise ValueError(message)
