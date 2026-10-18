"""Application adapter for subtitle normalization and stream splitting."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Final

from anishift.application.artifacts import Artifact, ArtifactKind
from anishift.application.cancellation import CancellationToken
from anishift.application.episode_fonts import MAX_LAYOUT_INPUTS, episode_fonts
from anishift.application.events import WorkerNotification, WorkerNotificationKind
from anishift.application.planning import PlanTask, TaskKind
from anishift.application.results import ArtifactSnapshot, ProducedArtifact, TaskResult
from anishift.application.scheduler_contracts import TaskProgressSink
from anishift.application.task_paths import task_staging_path
from anishift.errors import ExecutionError
from anishift.services.subtitles import (
    SubtitleKind,
    SubtitleSplit,
    load_subtitles,
    normalize_subtitles,
    reflow_polish_dialogue,
    split_subtitles,
    subtitle_kind,
    write_displayed,
    write_spoken,
)
from anishift.services.subtitles.layout import LayoutLimits

if TYPE_CHECKING:
    from anishift.services.subtitles.restyle import DialogueFont

__all__ = ["SubtitleTaskHandler"]

# ── Constants ────────────────────────────────────────────────────────────────

_MAX_SPLIT_OUTPUTS: Final[int] = 2
"""Largest supported pair of spoken and displayed subtitle outputs."""


class SubtitleTaskHandler:
    """Execute local subtitle transformations inside one run scope."""

    __slots__ = ("_dialogue_font", "_layout", "_run_root")

    def __init__(
        self, *, run_root: Path, layout: LayoutLimits | None = None, dialogue_font: DialogueFont | None = None
    ) -> None:
        """Bind subtitle staging to one scheduler-owned run root."""
        self._run_root: Path = run_root
        self._layout: LayoutLimits = layout if layout is not None else LayoutLimits()
        self._dialogue_font: DialogueFont | None = dialogue_font

    def execute(
        self,
        task: PlanTask,
        artifacts: ArtifactSnapshot,
        cancel: CancellationToken,
        progress: TaskProgressSink,
    ) -> TaskResult:
        """Normalize one file or split it into requested Polish streams."""
        cancel.raise_if_cancelled()
        if task.kind is TaskKind.NORMALIZE_SUBTITLES:
            result: TaskResult = self._normalize(task, artifacts)
        elif task.kind is TaskKind.SPLIT_SUBTITLES:
            result = self._split(task, artifacts)
        else:
            msg = "Subtitle handler received an unsupported task"
            raise ExecutionError(msg)
        cancel.raise_if_cancelled()
        progress.emit(WorkerNotification(WorkerNotificationKind.PROGRESS, task.task_id, 100))
        return result

    def _normalize(self, task: PlanTask, artifacts: ArtifactSnapshot) -> TaskResult:
        if not 1 <= len(task.requires) <= MAX_LAYOUT_INPUTS or len(task.produces) != 1:
            msg = "Subtitle normalization requires one source, an optional source container and one output"
            raise ExecutionError(msg)
        output: Artifact = artifacts.require_output(task.produces[0])
        output_kind: SubtitleKind = _output_kind(task, output)
        if output.kind is ArtifactKind.DISPLAYED_PL and artifacts.is_absent(task.requires[0]):
            return TaskResult(task.task_id, (), (output.artifact_id,))
        source: Artifact = artifacts.require_ready(task.requires[0])
        source_path: Path = _subtitle_path(source)
        destination: Path = task_staging_path(self._run_root, task, output, f".{output_kind}")
        layout: LayoutLimits | None = None if output.kind is ArtifactKind.DISPLAYED_PL else self._layout
        normalize_subtitles(
            source_path,
            destination,
            kind=output_kind,
            layout=layout,
            fonts=None if layout is None else episode_fonts(self._run_root, task, artifacts, output),
            dialogue_font=self._dialogue_font,
        )
        return TaskResult(task.task_id, (ProducedArtifact(output.artifact_id, destination, {}),))

    def _split(self, task: PlanTask, artifacts: ArtifactSnapshot) -> TaskResult:
        if len(task.requires) != 1 or not 1 <= len(task.produces) <= _MAX_SPLIT_OUTPUTS:
            msg = "Subtitle split requires one input and one or two outputs"
            raise ExecutionError(msg)
        source: Artifact = artifacts.require_ready(task.requires[0])
        source_path: Path = _subtitle_path(source)
        source_kind: SubtitleKind | None = subtitle_kind(source_path)
        if source_kind is None:
            msg = "Subtitle split source format is unsupported"
            raise ExecutionError(msg)
        source_split: SubtitleSplit = split_subtitles(load_subtitles(source_path), kind=source_kind)
        source_split = reflow_polish_dialogue(source_split, self._layout)
        produced: list[ProducedArtifact] = []
        absent: list[str] = []
        for artifact_id in task.produces:
            output: Artifact = artifacts.require_output(artifact_id)
            output_kind: SubtitleKind = _artifact_subtitle_kind(output)
            output_split: SubtitleSplit = replace(source_split, kind=output_kind)
            destination: Path = task_staging_path(self._run_root, task, output, f".{output_kind}")
            written: Path | None
            if output.kind is ArtifactKind.SPOKEN_PL:
                written = write_spoken(output_split, destination)
            elif output.kind is ArtifactKind.DISPLAYED_PL:
                written = write_displayed(output_split, destination)
            else:
                msg = "Subtitle split output must be spoken or displayed Polish subtitles"
                raise ExecutionError(msg)
            if (
                written is None
                and output.kind is ArtifactKind.DISPLAYED_PL
                and source_split.stats.displayed_events == 0
            ):
                absent.append(output.artifact_id)
                continue
            if written is None:
                msg = f"Requested subtitle stream is empty: {output.kind.value}"
                raise ExecutionError(msg)
            produced.append(ProducedArtifact(output.artifact_id, written, {}))
        return TaskResult(task.task_id, tuple(produced), tuple(absent))


def _subtitle_path(artifact: Artifact) -> Path:
    if artifact.path is None or subtitle_kind(artifact.path) is None:
        msg = "Subtitle task requires one ready ASS or SRT input"
        raise ExecutionError(msg)
    return artifact.path


def _output_kind(task: PlanTask, output: Artifact) -> SubtitleKind:
    parameters: dict[str, str | int | bool] = dict(task.parameters)
    raw_format: str | int | bool | None = parameters.get("output_format")
    if raw_format == "ass" and output.subtitle_format == raw_format:
        return "ass"
    if raw_format == "srt" and output.subtitle_format == raw_format:
        return "srt"
    msg = "Subtitle output format does not match the planned artifact"
    raise ExecutionError(msg)


def _artifact_subtitle_kind(output: Artifact) -> SubtitleKind:
    if output.subtitle_format == "ass":
        return "ass"
    if output.subtitle_format == "srt":
        return "srt"
    msg = "Planned subtitle output requires ASS or SRT format"
    raise ExecutionError(msg)
