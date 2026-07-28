"""Run extraction and subtitle splitting for workspace inputs."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from natsort import os_sorted

from anishift.bootstrap import AppContext
from anishift.config.user_settings import config_path
from anishift.config.workspace import ensure_workspace_dir
from anishift.errors import AniShiftError, ErrorCode, ErrorContext
from anishift.services.extraction import extract_tracks, identify
from anishift.services.extraction.tracks import select_tracks
from anishift.services.extraction.types import MediaInfo, TrackSelection
from anishift.services.subtitles import (
    DisplayedLine,
    SpokenLine,
    is_drawing,
    load_subtitles,
    preview_styles,
    read_txt,
    split_subtitles,
    spoken_to_srt,
    subtitle_kind,
    visible_text,
    visible_verses,
    write_displayed,
    write_full,
    write_spoken,
    write_translated,
    write_translated_displayed,
    write_translated_spoken,
)
from anishift.services.translation.constants import DEFAULT_BATCH_SIZE
from anishift.utils.safe_fs import safe_rmtree

from .types import (
    FileFailure,
    FileOutcome,
    LlmSettings,
    PipelineInteraction,
    PipelineReport,
    ProgressPhase,
    ProgressReporter,
    StepName,
    TranslationSettings,
)

if TYPE_CHECKING:
    from anishift.pipeline.llm_queue import (
        LlmFailureHandler,
        LlmProgressHandler,
        LlmQueueInput,
        SharedProviderState,
    )
    from anishift.services.subtitles.types import SubtitleSplit
    from anishift.services.translation import TranslationConfig
    from anishift.services.translation.protocols import TranslationEngineFactory
    from anishift.services.translation.types import FileTranslation

ProgressPhaseFactory = Callable[[], ProgressPhase]
"""Build one transient progress display for a single pipeline phase."""

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


@dataclass(slots=True)
class _MkvState:
    """Carry one MKV's extract result and split forward to the translate phase.

    Attributes:
        outcome: The file outcome built during extraction (mutated in place
            when the translate phase writes its result).
        split: The subtitle split to translate, or ``None`` when the file
            needs no translation (already Polish, no dialogue, or failed).
        kind: Subtitle format of the split, used to name the translated file.
    """

    outcome: FileOutcome
    split: SubtitleSplit | None
    kind: str = "srt"


@dataclass(frozen=True, slots=True)
class _TranslationVerses:
    """Rendered verse groups for both translated subtitle products."""

    displayed: tuple[tuple[str, ...], ...]
    spoken: tuple[tuple[str, ...], ...]


def run_pipeline(
    context: AppContext,
    *,
    interaction: PipelineInteraction | None = None,
    progress_factory: ProgressPhaseFactory | None = None,
    llm_failure_handler: LlmFailureHandler | None = None,
    llm_progress_handler: LlmProgressHandler | None = None,
) -> PipelineReport:
    """Process every discovered input in two phases, isolating failures per file.

    Extraction runs first for all MKVs (one transient progress row each),
    then translation runs for the files that need it (its rows replace the
    extraction rows in place). Text inputs are handled after the MKV phases.
    """
    ensure_workspace_dir(context.workspace_root)
    files = discover_inputs(context.workspace_root)
    if not files:
        return PipelineReport(())
    mkvs = [path for path in files if path.suffix.lower() == _MKV_SUFFIX]
    txts = [path for path in files if path.suffix.lower() == _TXT_SUFFIX]
    translation = _translation_settings(context)
    cancel = threading.Event()
    txt_outcomes: dict[Path, FileOutcome]
    if translation.engine == "llm":
        from anishift.pipeline.llm_queue import LlmQueueInput  # noqa: PLC0415 - LLM-only path

        queue_input = LlmQueueInput(files)
        states: dict[Path, _MkvState] = {}

        def enqueue_extracted(path: Path, state: _MkvState) -> None:
            states[path] = state
            if state.split is not None:
                queue_input.put(path)

        with ThreadPoolExecutor(max_workers=1) as queue_executor:
            queued = queue_executor.submit(
                _translate_llm_inputs,
                queue_input,
                states,
                context,
                cancel,
                on_provider_failure=llm_failure_handler,
                on_progress=llm_progress_handler,
            )
            try:
                try:
                    for path in txts:
                        queue_input.put(path)
                    extracted = _extract_phase(
                        mkvs,
                        context.workspace_root,
                        interaction,
                        progress_factory,
                        cancel,
                        on_complete=enqueue_extracted,
                    )
                    states.update(extracted)
                finally:
                    queue_input.close()
                txt_outcomes = queued.result()
            except KeyboardInterrupt:
                cancel.set()
                queue_input.close()
                raise
    else:
        states = _extract_phase(mkvs, context.workspace_root, interaction, progress_factory, cancel)
        _translate_phase(states, context.workspace_root, translation, progress_factory, cancel)
        txt_outcomes = {path: _process_txt(path, translation, cancel=cancel) for path in txts}
    outcomes = {path: state.outcome for path, state in states.items()}
    outcomes.update(txt_outcomes)
    return PipelineReport(tuple(outcomes[path] for path in files))


def _translation_settings(context: AppContext) -> TranslationSettings:
    """Resolve translation parameters from the wired context once."""
    prefs = context.user_settings
    fallback_chain = () if prefs.translation_engine == "llm" else tuple(prefs.translation_fallback_chain)
    prompt_root = config_path().parent / "prompts"
    if prefs.translation_engine == "llm":
        from anishift.services.translation.engines.llm.prompts import (  # noqa: PLC0415
            PromptRegistry,
        )

        registry = PromptRegistry(custom_root=prompt_root)
        registry.resolve("task", prefs.llm_prompt_id)
        registry.resolve("style", prefs.llm_style_id)
        for module_id in prefs.llm_module_ids:
            registry.resolve("module", module_id)
    return TranslationSettings(
        engine=prefs.translation_engine,
        fallback_chain=fallback_chain,
        batch_size=prefs.translation_batch_size,
        max_retries=prefs.translation_max_retries,
        deepl_api_key=context.settings.deepl_api_key,
        llm=LlmSettings(
            provider=prefs.llm_provider,
            model=prefs.llm_provider_model_id,
            prompt_id=prefs.llm_prompt_id,
            style_id=prefs.llm_style_id,
            module_ids=tuple(prefs.llm_module_ids),
            max_concurrency=prefs.llm_max_concurrency,
            max_retries=prefs.translation_max_retries,
            prompt_root=prompt_root,
            temperature=prefs.llm_temperature,
            top_p=prefs.llm_top_p,
            max_output_tokens=prefs.llm_max_output_tokens,
            anthropic_api_key=context.settings.anthropic_api_key,
            gemini_api_key=context.settings.gemini_api_key,
            openai_api_key=context.settings.openai_api_key,
            deepseek_api_key=context.settings.deepseek_api_key,
            openrouter_api_key=context.settings.openrouter_api_key,
            openai_compatible_api_key=context.settings.openai_compatible_api_key,
            openai_compatible_base_url=context.settings.openai_compatible_base_url,
        ),
    )


def _extract_phase(  # noqa: PLR0913 - extraction wiring plus optional ready callback
    mkvs: Sequence[Path],
    workspace_root: Path,
    interaction: PipelineInteraction | None,
    progress_factory: ProgressPhaseFactory | None,
    cancel: threading.Event,
    *,
    on_complete: Callable[[Path, _MkvState], None] | None = None,
) -> dict[Path, _MkvState]:
    """Extract every MKV, one transient progress row each, keeping order."""
    if not mkvs:
        return {}
    if interaction is not None:
        states: dict[Path, _MkvState] = {}
        for path in mkvs:
            state = _extract_mkv(
                path,
                workspace_root,
                interaction=interaction,
                on_progress=None,
                cancel=cancel,
            )
            states[path] = state
            if on_complete is not None:
                on_complete(path, state)
        return states
    if progress_factory is None:
        states = {}
        for path in mkvs:
            state = _extract_mkv(
                path,
                workspace_root,
                interaction=None,
                on_progress=None,
                cancel=cancel,
            )
            states[path] = state
            if on_complete is not None:
                on_complete(path, state)
        return states
    with progress_factory() as progress:
        return _extract_concurrently(
            mkvs,
            workspace_root,
            progress,
            cancel,
            on_complete=on_complete,
        )


def _extract_concurrently(
    mkvs: Sequence[Path],
    workspace_root: Path,
    progress: ProgressReporter,
    cancel: threading.Event,
    *,
    on_complete: Callable[[Path, _MkvState], None] | None = None,
) -> dict[Path, _MkvState]:
    """Run extraction across a worker pool with one progress row per file."""
    task_ids = {path: progress.add_task(path.name) for path in mkvs}
    futures: dict[Path, Future[_MkvState]] = {}
    with ThreadPoolExecutor(max_workers=_worker_count(len(mkvs))) as pool:
        for path in mkvs:
            futures[path] = pool.submit(
                _extract_mkv,
                path,
                workspace_root,
                interaction=None,
                on_progress=_progress_callback(progress, task_ids.get(path)),
                cancel=cancel,
            )
        pending = set(futures.values())
        by_future = {future: path for path, future in futures.items()}
        states: dict[Path, _MkvState] = {}
        try:
            while pending:
                done, pending = wait(pending, timeout=_WAIT_POLL_SECONDS)
                for future in done:
                    path = by_future[future]
                    state = future.result()
                    states[path] = state
                    if on_complete is not None:
                        on_complete(path, state)
        except KeyboardInterrupt:
            cancel.set()
            wait(set(futures.values()))
            raise
    return states


def _translate_phase(
    states: dict[Path, _MkvState],
    workspace_root: Path,
    translation: TranslationSettings,
    progress_factory: ProgressPhaseFactory | None,
    cancel: threading.Event,
) -> None:
    """Translate the files that need it, replacing the extraction rows in place."""
    pending = [path for path, state in states.items() if state.split is not None]
    if not pending:
        return
    if progress_factory is None:
        for path in pending:
            _translate_one(path, states[path], workspace_root, translation, cancel, progress=None, task_id=None)
        return
    with progress_factory() as progress:
        task_ids = {path: progress.add_task(path.name) for path in pending}
        for path in pending:
            _translate_one(
                path, states[path], workspace_root, translation, cancel, progress=progress, task_id=task_ids[path]
            )


def _translate_llm_inputs(  # noqa: PLR0913 - queue wiring keeps callbacks explicit
    ready_paths: Sequence[Path] | LlmQueueInput,
    states: dict[Path, _MkvState],
    context: AppContext,
    cancel: threading.Event,
    *,
    on_provider_failure: LlmFailureHandler | None = None,
    on_progress: LlmProgressHandler | None = None,
) -> dict[Path, FileOutcome]:
    """Translate ready MKV and TXT inputs through the central concurrent queue."""
    from anishift.pipeline.llm_queue import LlmQueueConfig, run_llm_queue  # noqa: PLC0415 - LLM-only path
    from anishift.pipeline.llm_runtime import PipelineLlmRuntime  # noqa: PLC0415 - LLM-only path

    def build_worker(
        provider_state: SharedProviderState,
    ) -> Callable[[Path, SharedProviderState], FileOutcome]:
        current = _translation_settings(context)
        llm_settings = current.llm
        if llm_settings is None:
            msg = "LLM settings are unavailable"
            raise RuntimeError(msg)

        def worker(path: Path, _state: SharedProviderState) -> FileOutcome:
            with PipelineLlmRuntime(
                llm_settings,
                cancel=cancel,
                observer=provider_state,
                title=path.stem,
            ) as runtime:
                if path.suffix.lower() == _MKV_SUFFIX:
                    state = states[path]
                    try:
                        _translate_one(
                            path,
                            state,
                            context.workspace_root,
                            current,
                            cancel,
                            progress=None,
                            task_id=None,
                            engine_factory=runtime.engine_factory(),
                        )
                    except AniShiftError as error:
                        _mark_raised_translation_error(
                            state.outcome,
                            error,
                            step="write" if state.outcome.translation is not None else "translate",
                        )
                    except OSError as error:
                        state.outcome.status = "failed"
                        state.outcome.failure = FileFailure(
                            "write" if state.outcome.translation is not None else "translate",
                            ErrorCode.IO_ERROR.value,
                            str(error),
                            "Check file permissions and free disk space.",
                        )
                    state.outcome.llm_calls = tuple(runtime.records)
                    return state.outcome
                outcome = _process_txt(
                    path,
                    current,
                    cancel=cancel,
                    engine_factory=runtime.engine_factory(),
                )
                outcome.llm_calls = tuple(runtime.records)
                return outcome

        return worker

    def not_processed(path: Path, error: ErrorContext) -> FileOutcome:
        failure = FileFailure("translate", error.code.value, error.message, error.suggestion)
        if path.suffix.lower() == _MKV_SUFFIX:
            outcome = states[path].outcome
            outcome.status = "not_processed"
            outcome.failure = failure
            return outcome
        return FileOutcome(path, "not_processed", failure=failure)

    queued = run_llm_queue(
        ready_paths,
        worker_factory=build_worker,
        not_processed_factory=not_processed,
        config=LlmQueueConfig(
            configured_limit=lambda: context.user_settings.llm_max_concurrency,
            cancel=cancel,
            on_provider_failure=on_provider_failure,
            on_progress=on_progress,
        ),
    )
    return {path: outcome for path, outcome in queued.items() if path.suffix.lower() == _TXT_SUFFIX}


def _translate_one(  # noqa: PLR0913 - one file's translate step wiring
    path: Path,
    state: _MkvState,
    workspace_root: Path,
    translation: TranslationSettings,
    cancel: threading.Event,
    *,
    progress: ProgressReporter | None,
    task_id: int | None,
    engine_factory: TranslationEngineFactory | None = None,
) -> None:
    """Translate one file's split and write the result, updating its outcome."""
    split = state.split
    if split is None:
        return
    result = _translate_split(split, translation, cancel, engine_factory=engine_factory)
    if progress is not None and task_id is not None:
        progress.update(task_id, 100)
    state.outcome.translation = result
    state.outcome.translated_lines = len(result.spoken)
    state.outcome.translation_engine = result.engine_id
    state.outcome.translation_failed_lines = result.failed_lines
    if not result.is_success:
        _mark_translation_failed(state.outcome, result, step="translate")
        return
    _write_translation_products(path, state, result, workspace_root)


def _worker_count(item_count: int) -> int:
    """Return a worker count scaled to the machine for I/O-bound extraction.

    Extraction is disk-bound, so the count grows with the core-count square
    root rather than the raw core count, which saturates the disk and stops
    helping past a handful of workers.
    """
    cores = os.cpu_count() or 1
    root: int = round(cores**0.5)
    return max(1, min(item_count, root + _WORKER_IO_HEADROOM))


def _extract_mkv(  # noqa: PLR0911 - each early return is a distinct extraction outcome
    mkv: Path,
    workspace_root: Path,
    *,
    interaction: PipelineInteraction | None,
    on_progress: Callable[[int], None] | None,
    cancel: threading.Event,
) -> _MkvState:
    """Run identify, select, extract, split and write for one MKV.

    Stops before translation: when the file needs translating the split is
    returned in the state for the translate phase; otherwise the state's
    split is ``None`` and the outcome is already final.
    """
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
            return _MkvState(FileOutcome(mkv, "done", warnings=warnings), None)
        step = "extract"
        extracted = extract_tracks(info, selection, work_dir, on_progress=on_progress, cancel=cancel)
        if extracted.subtitle_path is None:
            outcome = FileOutcome(
                mkv, "done", audio_path=extracted.audio_path, already_polish=selection.already_polish, warnings=warnings
            )
            return _MkvState(outcome, None)
        step = "split"
        kind = subtitle_kind(extracted.subtitle_path)
        if kind is None:
            failed = _failed(mkv, step, ErrorCode.SUBTITLE_PARSE_FAILED, "Unsupported subtitle format", "")
            return _MkvState(failed, None)
        subs = load_subtitles(extracted.subtitle_path)
        verdicts = None
        chosen = None
        if interaction is not None and kind == "ass":
            verdicts, samples = preview_styles(subs)
            chosen = interaction.choose_spoken_styles(mkv, verdicts, samples)
        split = split_subtitles(subs, kind=kind, spoken_styles=chosen, verdicts=verdicts)
        if split.stats.total_events == 0:
            warnings += ("subtitles contain no dialogue events",)
            outcome = FileOutcome(
                mkv,
                "done",
                extracted.audio_path,
                extracted.subtitle_path,
                already_polish=selection.already_polish,
                warnings=warnings,
            )
            return _MkvState(outcome, None)
        outcome = FileOutcome(
            source=mkv,
            status="done",
            audio_path=extracted.audio_path,
            subtitle_path=extracted.subtitle_path,
            already_polish=selection.already_polish,
            spoken_lines=split.stats.spoken_lines,
            displayed_events=split.stats.displayed_events,
            drawing_events=split.stats.drawing_events,
            collapsed_away=split.stats.collapsed_away,
            warnings=warnings,
        )
        needs_translation = _should_translate(split, selection.already_polish)
        if selection.already_polish:
            step = "write"
            _write_polish_products(mkv, outcome, split, workspace_root, kind)
        return _MkvState(outcome, split if needs_translation else None, kind=kind)
    except AniShiftError as exc:
        if exc.context.code is ErrorCode.CANCELLED:
            cancelled = FileOutcome(
                mkv,
                "cancelled",
                failure=FileFailure(step, exc.context.code.value, exc.context.message, exc.context.suggestion),
            )
            return _MkvState(cancelled, None)
        return _MkvState(_failed(mkv, step, exc.context.code, exc.context.message, exc.context.suggestion), None)
    except OSError as exc:
        failed = _failed(mkv, step, ErrorCode.IO_ERROR, str(exc), "Check file permissions and free disk space")
        return _MkvState(failed, None)


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


def _displayed_lines(split: SubtitleSplit) -> list[DisplayedLine]:
    """Return translatable displayed events with their source-file order."""
    dialogue = [event for event in split.subs.events if event.type == "Dialogue"]
    return [
        DisplayedLine(
            start=event.start,
            end=event.end,
            text=visible_text(event.text),
            order=order,
        )
        for order, (event, decision) in enumerate(zip(dialogue, split.decisions, strict=True))
        if decision == "displayed" and not is_drawing(event.text)
    ]


def _write_translation_products(
    path: Path,
    state: _MkvState,
    result: FileTranslation,
    workspace_root: Path,
) -> None:
    """Write complete, spoken-only and displayed-only translated products."""
    split = state.split
    if split is None:
        return
    verses = _translation_verses(split, result)
    stem = path.stem
    kind = state.kind
    state.outcome.translated_path = write_translated(
        split,
        verses.displayed,
        verses.spoken,
        workspace_root / f"{stem}.pl.{kind}",
    )
    state.outcome.spoken_path = write_translated_spoken(
        split,
        verses.spoken,
        workspace_root / f"{stem}.spoken.pl.{kind}",
    )
    state.outcome.displayed_path = write_translated_displayed(
        split,
        verses.displayed,
        workspace_root / f"{stem}.displayed.pl.{kind}",
    )


def _write_polish_products(
    path: Path,
    outcome: FileOutcome,
    split: SubtitleSplit,
    workspace_root: Path,
    kind: str,
) -> None:
    """Write final products for an already-Polish source without translation."""
    stem = path.stem
    outcome.translated_path = write_full(split, workspace_root / f"{stem}.pl.{kind}")
    outcome.spoken_path = write_spoken(split, workspace_root / f"{stem}.spoken.pl.{kind}")
    outcome.displayed_path = write_displayed(split, workspace_root / f"{stem}.displayed.pl.{kind}")


def _translation_verses(split: SubtitleSplit, result: FileTranslation) -> _TranslationVerses:
    """Build layout-aware displayed and readability-aware spoken verses."""
    from anishift.services.translation.linebreak import (  # noqa: PLC0415 - lazy: keep engines off import path
        split_for_layout,
        split_line,
    )

    dialogue = [event for event in split.subs.events if event.type == "Dialogue"]
    displayed_events = [
        event
        for event, decision in zip(dialogue, split.decisions, strict=True)
        if decision == "displayed" and not is_drawing(event.text)
    ]
    displayed = tuple(
        split_for_layout(text, visible_verses(event.text))
        for event, text in zip(displayed_events, result.displayed, strict=True)
    )
    spoken = tuple(split_line(line.text) for line in result.spoken)
    return _TranslationVerses(displayed, spoken)


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
    *,
    engine_factory: TranslationEngineFactory | None = None,
) -> FileTranslation:
    """Translate the spoken and displayed streams of one split."""
    from anishift.services.translation import TranslationService  # noqa: PLC0415 - lazy: keep engines off import path

    service = TranslationService(
        _translate_config(translation),
        fallback_chain=translation.fallback_chain,
        engine_factory=engine_factory,
    )
    return service.translate_file(
        list(split.spoken),
        _displayed_lines(split),
        source_lang="auto",
        cancel=cancel,
    )


def _txt_spoken_lines(text: str) -> tuple[SpokenLine, ...]:
    """Chunk plain text hierarchically and wrap each chunk as a narrator line."""
    from anishift.services.translation.chunking import chunk_text  # noqa: PLC0415 - lazy: keep engines off import path

    flattened = (" ".join(chunk.split()) for chunk in chunk_text(text))
    return tuple(SpokenLine(start=0, end=0, text=chunk, style="") for chunk in flattened if chunk)


def _process_txt(
    path: Path,
    translation: TranslationSettings,
    *,
    cancel: threading.Event,
    engine_factory: TranslationEngineFactory | None = None,
) -> FileOutcome:
    """Convert one text input into narrator lines and translate them."""
    from anishift.services.translation import TranslationService  # noqa: PLC0415 - lazy: keep engines off import path

    try:
        spoken = _txt_spoken_lines(read_txt(path))
        if not spoken:
            return FileOutcome(path, "done")
        service = TranslationService(
            _translate_config(translation),
            fallback_chain=translation.fallback_chain,
            engine_factory=engine_factory,
        )
        result = service.translate_file(list(spoken), [], source_lang="auto", cancel=cancel)
        outcome = FileOutcome(
            path,
            "done",
            spoken_lines=len(spoken),
            translation=result,
            translated_lines=len(result.spoken),
            translation_engine=result.engine_id,
            translation_failed_lines=result.failed_lines,
        )
        if not result.is_success:
            _mark_translation_failed(outcome, result, step="txt")
        else:
            outcome.translated_path = spoken_to_srt(result.spoken, path.with_suffix(".pl.srt"))
    except AniShiftError as exc:
        if exc.context.code is ErrorCode.CANCELLED:
            failure = FileFailure(
                "txt",
                exc.context.code.value,
                exc.context.message,
                exc.context.suggestion,
            )
            return FileOutcome(path, "cancelled", failure=failure)
        return _failed(path, "txt", exc.context.code, exc.context.message, exc.context.suggestion)
    except OSError as exc:
        return _failed(path, "txt", ErrorCode.IO_ERROR, str(exc), "Check file permissions")
    return outcome


def _failed(path: Path, step: StepName, code: ErrorCode, message: str, suggestion: str) -> FileOutcome:
    """Build a failed file outcome."""
    failure = FileFailure(step, code.value, message, suggestion)
    return FileOutcome(path, "failed", failure=failure)


def _mark_translation_failed(
    outcome: FileOutcome,
    result: FileTranslation,
    *,
    step: StepName,
) -> None:
    """Mark a translated outcome failed while preserving extraction artifacts."""
    context = result.error_context or ErrorContext(
        code=ErrorCode.TRANSLATION_FAILED,
        message=result.error or "Translation failed",
        suggestion="Check translation settings and try again.",
    )
    outcome.status = "cancelled" if context.code is ErrorCode.CANCELLED else "failed"
    outcome.failure = FileFailure(
        step,
        context.code.value,
        context.message,
        context.suggestion,
    )


def _mark_raised_translation_error(
    outcome: FileOutcome,
    error: AniShiftError,
    *,
    step: StepName,
) -> None:
    """Convert a raised typed pipeline-domain failure into a file-local outcome."""
    context = error.context
    outcome.status = "cancelled" if context.code is ErrorCode.CANCELLED else "failed"
    outcome.failure = FileFailure(
        step,
        context.code.value,
        context.message,
        context.suggestion,
    )


def _progress_callback(progress: ProgressReporter | None, task_id: int | None) -> Callable[[int], None] | None:
    """Bind one progress task to a worker callback."""
    if progress is None or task_id is None:
        return None

    def _update(percent: int) -> None:
        progress.update(task_id, percent)

    return _update
