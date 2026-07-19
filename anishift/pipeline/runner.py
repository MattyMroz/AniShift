"""Run extraction and subtitle splitting for workspace inputs."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import TYPE_CHECKING, Final

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
    spoken_to_srt,
    subtitle_kind,
    txt_to_spoken,
    visible_text,
    write_displayed,
)
from anishift.services.translation.constants import DEFAULT_BATCH_SIZE
from anishift.utils.safe_fs import safe_rmtree

from .types import (
    FileFailure,
    FileOutcome,
    PipelineInteraction,
    PipelineReport,
    ProgressReporter,
    StepName,
    TranslationSettings,
)

if TYPE_CHECKING:
    from anishift.services.subtitles.types import SubtitleSplit
    from anishift.services.translation import TranslationConfig
    from anishift.services.translation.types import FileTranslation

__all__ = ["discover_inputs", "run_pipeline"]

# ── Constants ─────────────────────────────────────────────────────────────────

_WORKER_IO_HEADROOM: Final[int] = 2
"""Extra workers added over the core-count square root for I/O latency."""

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
    translation = _translation_settings(context)
    cancel = threading.Event()
    outcomes = _process_mkvs(mkvs, context.workspace_root, interaction, progress, cancel, translation)
    outcomes.update({path: _process_txt(path, translation) for path in txts})
    return PipelineReport(tuple(outcomes[path] for path in files))


def _translation_settings(context: AppContext) -> TranslationSettings:
    """Resolve translation parameters from the wired context once."""
    prefs = context.user_settings
    return TranslationSettings(
        engine=prefs.translation_engine,
        fallback_chain=tuple(prefs.translation_fallback_chain),
        batch_size=prefs.translation_batch_size,
        max_retries=prefs.translation_max_retries,
        deepl_api_key=context.settings.deepl_api_key,
    )


def _process_mkvs(  # noqa: PLR0913 - orchestration entry: each dependency is distinct
    mkvs: Sequence[Path],
    workspace_root: Path,
    interaction: PipelineInteraction | None,
    progress: ProgressReporter | None,
    cancel: threading.Event,
    translation: TranslationSettings,
) -> dict[Path, FileOutcome]:
    """Process MKVs sequentially for manual mode and concurrently otherwise."""
    if interaction is not None:
        return {
            path: _process_mkv(
                path, workspace_root, interaction=interaction, on_progress=None, cancel=cancel, translation=translation
            )
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
                translation=translation,
            )
        pending = set(futures.values())
        try:
            while pending:
                _done, pending = wait(pending, timeout=_WAIT_POLL_SECONDS)
        except KeyboardInterrupt:
            cancel.set()
            wait(set(futures.values()))
            raise
    return {path: future.result() for path, future in futures.items()}


def _worker_count(item_count: int) -> int:
    """Return a worker count scaled to the machine for I/O-bound extraction.

    Extraction is disk-bound, so the count grows with the core-count square
    root rather than the raw core count, which saturates the disk and stops
    helping past a handful of workers.
    """
    cores = os.cpu_count() or 1
    root: int = round(cores**0.5)
    return max(1, min(item_count, root + _WORKER_IO_HEADROOM))


def _process_mkv(  # noqa: PLR0911, PLR0913 - orchestration entry: each dependency is distinct
    mkv: Path,
    workspace_root: Path,
    *,
    interaction: PipelineInteraction | None,
    on_progress: Callable[[int], None] | None,
    cancel: threading.Event,
    translation: TranslationSettings,
) -> FileOutcome:
    """Run identify, select, extract, split, write and translate for one MKV."""
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
        step = "translate"
        result = None
        if _should_translate(split, selection.already_polish):
            result = _translate_split(split, translation, cancel)
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
            translation=result,
            translated_lines=len(result.spoken) if result is not None else 0,
            translation_engine=result.engine_id if result is not None else "",
            translation_failed_lines=result.failed_lines if result is not None else 0,
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


def _should_translate(split: SubtitleSplit, already_polish: bool) -> bool:
    """Whether the translate step runs (skip Polish files and empty splits)."""
    if already_polish:
        return False
    return bool(split.stats.spoken_lines or split.stats.displayed_events)


def _displayed_visible_texts(split: SubtitleSplit) -> list[str]:
    """Return the visible texts of displayed Dialogue events, in order."""
    dialogue = [event for event in split.subs.events if event.type == "Dialogue"]
    return [
        visible_text(event.text)
        for event, decision in zip(dialogue, split.decisions, strict=True)
        if decision == "displayed"
    ]


def _translate_config(translation: TranslationSettings) -> TranslationConfig:
    """Build a TranslationConfig from the runner settings (lazy import)."""
    from anishift.services.translation import TranslationConfig  # noqa: PLC0415 - lazy: keep engines off import path

    return TranslationConfig(
        engine=translation.engine,
        source_lang="auto",
        batch_size=translation.batch_size if translation.batch_size > 0 else DEFAULT_BATCH_SIZE,
        max_retries=translation.max_retries,
        api_key=translation.deepl_api_key,
    )


def _translate_split(
    split: SubtitleSplit,
    translation: TranslationSettings,
    cancel: threading.Event,
) -> FileTranslation:
    """Translate the spoken and displayed streams of one split."""
    from anishift.services.translation import TranslationService  # noqa: PLC0415 - lazy: keep engines off import path

    service = TranslationService(_translate_config(translation), fallback_chain=translation.fallback_chain)
    return service.translate_file(
        list(split.spoken),
        _displayed_visible_texts(split),
        source_lang="auto",
        cancel=cancel,
    )


def _process_txt(path: Path, translation: TranslationSettings) -> FileOutcome:
    """Convert one text input into narrator lines and translate them."""
    from anishift.services.translation import TranslationService  # noqa: PLC0415 - lazy: keep engines off import path

    try:
        spoken = txt_to_spoken(path)
        if not spoken:
            return FileOutcome(path, "done")
        service = TranslationService(_translate_config(translation), fallback_chain=translation.fallback_chain)
        result = service.translate_file(list(spoken), [], source_lang="auto")
        translated_path = spoken_to_srt(result.spoken, path.with_suffix(".pl.srt")) if result.is_success else None
        return FileOutcome(
            path,
            "done",
            translated_path=translated_path,
            spoken_lines=len(spoken),
            translation=result,
            translated_lines=len(result.spoken),
            translation_engine=result.engine_id,
            translation_failed_lines=result.failed_lines,
        )
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
