"""Run extraction and subtitle splitting for workspace inputs."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Final

from natsort import os_sorted

from anishift.bootstrap import AppContext
from anishift.config.workspace import ensure_workspace_dir
from anishift.errors import AniShiftError, ErrorCode
from anishift.services.extraction import extract_tracks, identify
from anishift.services.extraction.tracks import select_tracks
from anishift.services.extraction.types import MediaInfo, TrackSelection
from anishift.services.subtitles import (
    load_subtitles,
    preview_styles,
    split_subtitles,
    subtitle_kind,
    txt_to_spoken,
    write_displayed,
)
from anishift.utils.safe_fs import safe_rmtree

from .types import FileFailure, FileOutcome, PipelineInteraction, PipelineReport, ProgressReporter, StepName

__all__ = ["discover_inputs", "run_pipeline"]

# Constants

_WORKER_CAP: Final[int] = 4
"""Upper bound on parallel file workers."""

_WAIT_POLL_SECONDS: Final[float] = 0.2
"""Future-poll interval keeping Ctrl+C responsive."""

_MKV_SUFFIX: Final[str] = ".mkv"
"""MKV discovery suffix."""

_TXT_SUFFIX: Final[str] = ".txt"
"""Plain-text discovery suffix."""

_DISPLAYED_INFIX: Final[str] = ".displayed"
"""Infix used by displayed subtitle products."""


def discover_inputs(root: Path) -> list[Path]:
    """List top-level MKV and TXT inputs in natural order."""
    if not root.is_dir():
        return []
    return os_sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in {_MKV_SUFFIX, _TXT_SUFFIX} and _DISPLAYED_INFIX not in path.name
    )


def run_pipeline(
    context: AppContext,
    *,
    interaction: PipelineInteraction | None = None,
    progress: ProgressReporter | None = None,
) -> PipelineReport:
    """Process every discovered input and isolate failures per file."""
    ensure_workspace_dir(context.workspace_root)
    files = discover_inputs(context.workspace_root)
    if not files:
        return PipelineReport(())
    mkvs = [path for path in files if path.suffix.lower() == _MKV_SUFFIX]
    txts = [path for path in files if path.suffix.lower() == _TXT_SUFFIX]
    cancel = threading.Event()
    outcomes = _process_mkvs(mkvs, context.workspace_root, interaction, progress, cancel)
    outcomes.update({path: _process_txt(path) for path in txts})
    return PipelineReport(tuple(outcomes[path] for path in files))


def _process_mkvs(
    mkvs: Sequence[Path],
    workspace_root: Path,
    interaction: PipelineInteraction | None,
    progress: ProgressReporter | None,
    cancel: threading.Event,
) -> dict[Path, FileOutcome]:
    """Process MKVs sequentially for manual mode and concurrently otherwise."""
    if interaction is not None:
        return {
            path: _process_mkv(path, workspace_root, interaction=interaction, on_progress=None, cancel=cancel)
            for path in mkvs
        }
    if not mkvs:
        return {}
    task_ids = {path: progress.add_task(path.name) for path in mkvs} if progress is not None else {}
    futures: dict[Path, Future[FileOutcome]] = {}
    with ThreadPoolExecutor(max_workers=_worker_count(len(mkvs))) as pool:
        for path in mkvs:
            futures[path] = pool.submit(
                _process_mkv,
                path,
                workspace_root,
                interaction=None,
                on_progress=_progress_callback(progress, task_ids.get(path)),
                cancel=cancel,
            )
        pending = set(futures.values())
        try:
            while pending:
                _done, pending = wait(pending, timeout=_WAIT_POLL_SECONDS)
        except KeyboardInterrupt:
            cancel.set()
            wait(set(futures.values()))
    return {path: future.result() for path, future in futures.items()}


def _worker_count(item_count: int) -> int:
    """Return a bounded worker count scaled to the machine."""
    return max(1, min(item_count, os.cpu_count() or 1, _WORKER_CAP))


def _process_mkv(  # noqa: PLR0911
    mkv: Path,
    workspace_root: Path,
    *,
    interaction: PipelineInteraction | None,
    on_progress: Callable[[int], None] | None,
    cancel: threading.Event,
) -> FileOutcome:
    """Run identify, select, extract, split and write for one MKV."""
    work_dir = workspace_root / "tmp" / mkv.stem
    step: StepName = "identify"
    try:
        if work_dir.exists():
            safe_rmtree(work_dir)
        work_dir.mkdir(parents=True)
        info = identify(mkv)
        step = "select"
        proposal = select_tracks(info.tracks)
        selection = interaction.choose_tracks(info, proposal) if interaction is not None else proposal
        warnings = _selection_warnings(info, selection)
        if selection.audio_id is None and selection.subtitle_id is None:
            return FileOutcome(mkv, "done", warnings=warnings)
        step = "extract"
        extracted = extract_tracks(info, selection, work_dir, on_progress=on_progress, cancel=cancel)
        if extracted.subtitle_path is None:
            return FileOutcome(
                mkv,
                "done",
                audio_path=extracted.audio_path,
                already_polish=selection.already_polish,
                warnings=warnings,
            )
        step = "split"
        kind = subtitle_kind(extracted.subtitle_path)
        if kind is None:
            return _failed(mkv, step, ErrorCode.SUBTITLE_PARSE_FAILED, "Unsupported subtitle format", "")
        subs = load_subtitles(extracted.subtitle_path)
        verdicts = None
        chosen = None
        if interaction is not None and kind == "ass":
            verdicts, samples = preview_styles(subs)
            chosen = interaction.choose_spoken_styles(mkv, verdicts, samples)
        split = split_subtitles(subs, kind=kind, spoken_styles=chosen, verdicts=verdicts)
        if split.stats.total_events == 0:
            warnings += ("subtitles contain no dialogue events",)
            return FileOutcome(
                mkv,
                "done",
                extracted.audio_path,
                extracted.subtitle_path,
                already_polish=selection.already_polish,
                warnings=warnings,
            )
        step = "write"
        destination = workspace_root / f"{mkv.stem}.displayed.{kind}"
        displayed = write_displayed(split, destination)
        return FileOutcome(
            source=mkv,
            status="done",
            audio_path=extracted.audio_path,
            subtitle_path=extracted.subtitle_path,
            displayed_path=displayed,
            already_polish=selection.already_polish,
            spoken_lines=split.stats.spoken_lines,
            displayed_events=split.stats.displayed_events,
            drawing_events=split.stats.drawing_events,
            collapsed_away=split.stats.collapsed_away,
            warnings=warnings,
        )
    except AniShiftError as exc:
        if exc.context.code is ErrorCode.CANCELLED:
            return FileOutcome(
                mkv,
                "cancelled",
                failure=FileFailure(
                    step,
                    exc.context.code.value,
                    exc.context.message,
                    exc.context.suggestion,
                ),
            )
        return _failed(mkv, step, exc.context.code, exc.context.message, exc.context.suggestion)
    except OSError as exc:
        return _failed(mkv, step, ErrorCode.IO_ERROR, str(exc), "Check file permissions and free disk space")


def _selection_warnings(info: MediaInfo, selection: TrackSelection) -> tuple[str, ...]:
    """Build non-fatal warnings for missing selected tracks."""
    warnings: list[str] = []
    subtitles = [track for track in info.tracks if track.type == "subtitles"]
    if selection.subtitle_id is None:
        detail = f"no text subtitle track ({len(subtitles)} picture-only)" if subtitles else "no usable subtitles"
        warnings.append(f"{detail} — later stages will skip this file")
    if selection.audio_id is None:
        warnings.append("no audio track")
    return tuple(warnings)


def _process_txt(path: Path) -> FileOutcome:
    """Convert one text input into narrator lines."""
    try:
        return FileOutcome(path, "done", spoken_lines=len(txt_to_spoken(path)))
    except AniShiftError as exc:
        return _failed(path, "txt", exc.context.code, exc.context.message, exc.context.suggestion)
    except OSError as exc:
        return _failed(path, "txt", ErrorCode.IO_ERROR, str(exc), "Check file permissions")


def _failed(path: Path, step: StepName, code: ErrorCode, message: str, suggestion: str) -> FileOutcome:
    """Build a failed file outcome."""
    failure = FileFailure(step, code.value, message, suggestion)
    return FileOutcome(path, "failed", failure=failure)


def _progress_callback(progress: ProgressReporter | None, task_id: int | None) -> Callable[[int], None] | None:
    """Bind one progress task to a worker callback."""
    if progress is None or task_id is None:
        return None

    def _update(percent: int) -> None:
        progress.update(task_id, percent)

    return _update
