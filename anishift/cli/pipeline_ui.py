"""Render the Enter-key pipeline, prompts, progress and final report."""

from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from contextlib import ExitStack, nullcontext
from pathlib import Path
from typing import Final, Literal, cast

from natsort import os_sorted
from rich.progress import TaskID

from anishift.bootstrap import AppContext
from anishift.errors import AniShiftError
from anishift.pipeline import discover_inputs, run_pipeline
from anishift.pipeline.compose_only import compose_existing
from anishift.pipeline.llm_queue import LlmProgressState
from anishift.pipeline.narration import scope_id_for_source
from anishift.pipeline.recovery import RecoveryAction, RecoveryContext
from anishift.pipeline.types import FileOutcome, FileStatus, PipelineReport, ProgressPhase
from anishift.platform.binaries import Binary, BinaryNotFoundError
from anishift.services.extraction.tracks import is_polish_language
from anishift.services.extraction.types import MediaInfo, TrackInfo, TrackSelection
from anishift.services.subtitles.classifier import StyleVerdict
from anishift.services.tts.engines.edge.constants import MAREK_VOICE_ID, ZOFIA_VOICE_ID
from anishift.services.tts.engines.elevenbytes.constants import DALLIN_ALIAS
from anishift.services.tts.types import (
    SpeechBatchProgress,
    SpeechRequestProgress,
    SpeechRetryProgress,
)
from anishift.setup.installer import InstallerError, ensure_binary
from anishift.utils.rich_console import MultiProgressManager, StatusType, console, get_status_icon
from anishift.utils.timer import Timer, format_duration

__all__ = ["run_compose_command", "run_pipeline_command"]

_STATUS_ICON: dict[FileStatus, StatusType] = {
    "done": "success",
    "failed": "error",
    "cancelled": "warning",
    "not_processed": "warning",
}
"""Map file statuses to console icons."""

_COMPOSITION_PHASE_STEP: Final[int] = 10
"""Percent step between printed composition progress lines."""

_SECONDS_PER_MINUTE: Final[int] = 60
"""Scale used when announcing the estimated rendering time."""

_PIPELINE_PROGRESS_DESCRIPTION_LENGTH: Final[int] = 72
"""Maximum stage, provider, voice and filename width for pipeline rows."""

_PIPELINE_PROGRESS_PHASE_WIDTH: Final[int] = 14
"""Fixed phase-label width keeping filenames aligned between transitions."""

_PROGRESS_COMPLETE: Final[int] = 100
"""Completed percentage used by extraction and translation progress rows."""

_PIPELINE_STAGE_RANK: Final[Mapping[str, int]] = {
    "extracting": 0,
    "translating": 1,
    "tts": 2,
    "audio": 3,
    "terminal": 4,
}
"""Monotonic stage precedence preventing late callbacks from regressing rows."""


class _PipelineProgressRows:
    """Keep every automatic pipeline stage on one naturally ordered row per file."""

    def __init__(
        self,
        progress: MultiProgressManager,
        paths: tuple[Path, ...],
        context: AppContext,
    ) -> None:
        self._context: AppContext = context
        self._progress = progress
        self._task_ids = {path: progress.add_task(self._description(path, "Extracting")) for path in os_sorted(paths)}
        self._task_ids_by_name = {path.name: task_id for path, task_id in self._task_ids.items()}
        self._paths_by_task_id = {int(task_id): path for path, task_id in self._task_ids.items()}
        self._paths_by_scope = {
            scope_id_for_source(path, workspace_root=context.workspace_root): path for path in paths
        }
        self._claimed_paths: set[Path] = set()
        self._stage_by_task_id: dict[int, Literal["extracting", "translating"]] = {
            int(task_id): "extracting" for task_id in self._task_ids.values()
        }
        self._tts_label: str = _tts_progress_label(context)
        self._tts_started: set[Path] = set()
        self._audio_started: set[Path] = set()
        self._stage_rank: dict[Path, int] = dict.fromkeys(
            paths,
            _PIPELINE_STAGE_RANK["extracting"],
        )
        self._tts_visible_required: dict[Path, int] = dict.fromkeys(paths, 0)
        self._terminal_paths: set[Path] = set()
        self._closed: bool = False
        self._lock: threading.Lock = threading.Lock()

    def add_task(self, description: str, *, total: int = 100) -> int:
        """Return the preallocated row requested by the extraction phase."""
        del total
        with self._lock:
            path: Path = next(path for path in self._task_ids if path.name == description)
            task_id: int = int(self._task_ids_by_name[description])
            if path.suffix.lower() == ".txt" or path in self._claimed_paths:
                self._stage_rank[path] = _PIPELINE_STAGE_RANK["translating"]
                self._stage_by_task_id[task_id] = "translating"
                self._set_bar(TaskID(task_id))
                self._progress.reset_task(TaskID(task_id))
                self._progress.update_description(
                    TaskID(task_id),
                    self._description(path, "Translating"),
                )
            self._claimed_paths.add(path)
            return task_id

    def update(self, task_id: int, completed: int) -> None:
        """Forward extraction completion to the preallocated row."""
        with self._lock:
            if self._closed:
                return
            path = self._paths_by_task_id[task_id]
            expected_rank: int = _PIPELINE_STAGE_RANK[self._stage_by_task_id[task_id]]
            if self._stage_rank[path] > expected_rank or path in self._terminal_paths:
                return
            self._progress.update(TaskID(task_id), completed)
            if completed >= _PROGRESS_COMPLETE:
                phase: str = "Translated" if self._stage_by_task_id[task_id] == "translating" else "Extracted"
                self._progress.update_description(
                    TaskID(task_id),
                    self._description(path, phase),
                )

    def on_progress(self, path: Path, state: LlmProgressState) -> None:
        """Reset the same row for translation and complete it on success."""
        with self._lock:
            if (
                self._closed
                or path in self._terminal_paths
                or self._stage_rank[path] > _PIPELINE_STAGE_RANK["translating"]
            ):
                return
            self._stage_rank[path] = _PIPELINE_STAGE_RANK["translating"]
            task_id = self._task_ids[path]
            self._set_bar(task_id)
            if state == "translating":
                self._stage_by_task_id[int(task_id)] = "translating"
                self._progress.reset_task(task_id)
                self._progress.update_description(
                    task_id,
                    self._description(path, "Translating"),
                )
                return
            if state == "done":
                self._progress.update(task_id, _PROGRESS_COMPLETE)
                self._progress.update_description(
                    task_id,
                    self._description(path, "Translated"),
                )
                return
            if state in {"failed", "cancelled", "not_processed"}:
                phase = {
                    "failed": "Failed",
                    "cancelled": "Cancelled",
                    "not_processed": "Not processed",
                }[state]
                self._progress.update_description(task_id, self._description(path, phase))
                self._progress.stop_task(task_id)

    def on_batch_state(self, state: SpeechBatchProgress) -> None:
        """Render committed required TTS events as a real percentage."""
        with self._lock:
            path = self._active_path(state.scope_id)
            if path is None or path in self._terminal_paths or self._stage_rank[path] > _PIPELINE_STAGE_RANK["tts"]:
                return
            self._stage_rank[path] = _PIPELINE_STAGE_RANK["tts"]
            task_id = self._task_ids[path]
            self._set_bar(task_id)
            if path not in self._tts_started:
                self._tts_started.add(path)
                self._progress.reset_task(task_id)
            required: int = state.total_required_requests
            committed: int = state.committed_required_requests
            visible: int = max(
                self._tts_visible_required[path],
                state.received_required_requests,
                state.committed_required_requests,
            )
            self._tts_visible_required[path] = visible
            percentage: int = (
                _PROGRESS_COMPLETE
                if required == 0 or committed >= required
                else min(
                    _PROGRESS_COMPLETE - 1,
                    (visible * _PROGRESS_COMPLETE + required - 1) // required,
                )
            )
            self._progress.update(task_id, percentage)
            self._progress.update_description(
                task_id,
                self._description(path, "Synthesizing", self._tts_label),
            )

    def on_request_committed(self, update: SpeechRequestProgress) -> None:
        """Accept request-level callbacks while aggregate state owns the row."""
        del update

    def on_request_retry(self, update: SpeechRetryProgress) -> None:
        """Show retry state without replacing the file's aggregate percentage."""
        with self._lock:
            path = self._active_path(update.scope_id)
            if path is None or path in self._terminal_paths:
                return
            task_id = self._task_ids[path]
            detail: str = f"{self._tts_label} · {update.retry_number}/{update.max_retries}"
            self._progress.update_description(
                task_id,
                self._description(path, "Retrying", detail),
            )

    def on_audio_phase(self, scope_id: str, phase: str) -> None:
        """Switch the same row to a spinner for coarse audio phases."""
        with self._lock:
            path = self._active_path(scope_id)
            if path is None or path in self._terminal_paths:
                return
            self._stage_rank[path] = max(
                self._stage_rank[path],
                _PIPELINE_STAGE_RANK["audio"],
            )
            task_id = self._task_ids[path]
            if phase == "done":
                return
            if path not in self._audio_started:
                self._audio_started.add(path)
                self._progress.reset_task(task_id)
            self._progress.set_task_presentation(
                task_id,
                show_bar=False,
                show_percentage=False,
                show_spinner=True,
            )
            label: str = {
                "normalizing": "Audio normalize",
                "timeline": "Audio timeline",
                "mixing": "Audio mixing",
                "narration_resume": "Audio resume",
                "skipped_no_spoken": "Audio skipped",
            }.get(phase, "Audio")
            self._progress.update_description(
                task_id,
                self._description(path, label, self._tts_label),
            )

    def on_pipeline_terminal(
        self,
        scope_id: str,
        state: Literal["done", "failed", "cancelled", "not_processed"],
    ) -> None:
        """Freeze one row in its final state without changing its position."""
        with self._lock:
            path = self._active_path(scope_id)
            if path is None:
                return
            self._set_terminal(path, state)

    def on_pipeline_retry(self, scope_id: str) -> None:
        """Reopen one terminal row before a retry runtime starts."""
        with self._lock:
            path = self._active_path(scope_id)
            if path is None:
                return
            self._terminal_paths.discard(path)
            self._stage_rank[path] = _PIPELINE_STAGE_RANK["tts"]
            self._tts_visible_required[path] = 0
            self._tts_started.discard(path)
            self._audio_started.discard(path)
            self._tts_label = _tts_progress_label(self._context)
            task_id = self._task_ids[path]
            self._set_bar(task_id)
            self._progress.reset_task(task_id)
            self._progress.update_description(
                task_id,
                self._description(path, "Synthesizing", self._tts_label),
            )

    def finalize(self, report: PipelineReport) -> None:
        """Reconcile every preallocated row with the authoritative report."""
        with self._lock:
            if self._closed:
                return
            for outcome in report.outcomes:
                if outcome.source in self._task_ids:
                    self._set_terminal(outcome.source, outcome.status, force=True)

    def close(self) -> None:
        """Ignore callbacks after the enclosing Live display begins closing."""
        with self._lock:
            self._closed = True

    def _active_path(self, scope_id: str) -> Path | None:
        if self._closed:
            return None
        return self._paths_by_scope.get(scope_id)

    def _set_bar(self, task_id: TaskID) -> None:
        self._progress.set_task_presentation(
            task_id,
            show_bar=True,
            show_percentage=True,
            show_spinner=False,
        )

    def _set_terminal(
        self,
        path: Path,
        state: Literal["done", "failed", "cancelled", "not_processed"],
        *,
        force: bool = False,
    ) -> None:
        if path in self._terminal_paths and not force:
            return
        self._terminal_paths.add(path)
        self._stage_rank[path] = _PIPELINE_STAGE_RANK["terminal"]
        task_id = self._task_ids[path]
        self._set_bar(task_id)
        phase: str = {
            "done": "Done",
            "failed": "Failed",
            "cancelled": "Cancelled",
            "not_processed": "Not processed",
        }[state]
        if state == "done":
            self._progress.update(task_id, _PROGRESS_COMPLETE)
        else:
            self._progress.reset_task(task_id)
        self._progress.update_description(task_id, self._description(path, phase))
        self._progress.stop_task(task_id)

    @staticmethod
    def _description(path: Path, phase: str, detail: str = "") -> str:
        suffix: str = f" {detail} ·" if detail else ""
        return f"{phase:<{_PIPELINE_PROGRESS_PHASE_WIDTH}}{suffix} {path.name}"


def run_pipeline_command(context: AppContext) -> None:
    """Process workspace inputs on Enter and render the resulting report."""
    pipeline_timer = Timer("pipeline", auto_start=True)
    paths = discover_inputs(context.workspace_root)
    if not paths:
        console.print("[warning]Workspace is empty[/warning] — drop MKV files into workspace/ and press Enter.")
        return
    if not _ensure_binaries(paths):
        return
    try:
        if context.user_settings.mode == "manual":
            manual_llm_progress = (
                (lambda path, state: _render_llm_progress(context, path, state))
                if context.user_settings.translation_engine == "llm"
                else None
            )
            report = run_pipeline(
                context,
                interaction=_ManualInteraction(),
                llm_failure_handler=lambda recovery: _choose_recovery(context, recovery),
                llm_progress_handler=manual_llm_progress,
                tts_failure_handler=lambda recovery: _choose_recovery(context, recovery),
                composition_ui=CompositionConsole(),
            )
        else:
            report = _run_auto_pipeline(context, tuple(paths))
    except KeyboardInterrupt:
        console.print("[warning]Interrupted.[/warning]")
        return
    except AniShiftError as error:
        _render_pipeline_error(error)
        return
    pipeline_timer.stop()
    _render_report(report)
    format_duration(
        pipeline_timer.duration_ns,
        pipeline_timer.start_date,
        pipeline_timer.end_date,
        mode="minimal",
    )


class CompositionConsole:
    """Render composition progress and the pre-run cost of burning."""

    def on_composition_phase(self, scope_id: str, phase: str, percent: int) -> None:
        """Print one line per completed decile of a composition phase.

        FFmpeg reports several times per second; the pipeline's own progress
        rows are already gone by this stage, so the text stays coarse.
        """
        if percent % _COMPOSITION_PHASE_STEP:
            return
        console.print(f"[gray]{phase} {scope_id}: {percent}%[/gray]")

    def on_burn_estimate(self, file_count: int, estimated_seconds: float) -> None:
        """Announce the batch size and rough duration before rendering."""
        if file_count == 0:
            return
        minutes: int = max(1, round(estimated_seconds / _SECONDS_PER_MINUTE))
        console.print(
            f"{get_status_icon('info')} Burning {file_count} file(s), roughly {minutes} min — "
            "press Ctrl+C to stop at any point.",
        )


def run_compose_command(context: AppContext) -> None:
    """Assemble results from existing files, without translation or TTS."""
    paths = discover_inputs(context.workspace_root)
    if not paths:
        console.print("[warning]Workspace is empty[/warning] — drop MKV files into workspace/ and press Enter.")
        return
    if not _ensure_binaries(paths):
        return
    try:
        outcomes = compose_existing(context, ui=CompositionConsole())
    except KeyboardInterrupt:
        console.print("[warning]Interrupted.[/warning]")
        return
    except AniShiftError as error:
        _render_pipeline_error(error)
        return
    _render_composition_summary(outcomes)


def _render_composition_summary(outcomes: tuple[FileOutcome, ...]) -> None:
    """Print one line per composed file and per skipped or failed file."""
    if not outcomes:
        console.print("[warning]Nothing to assemble[/warning] — no products and no Polish subtitles found.")
        return
    report = PipelineReport(outcomes)
    for outcome in outcomes:
        _render_composition_line(outcome)
    console.print(
        f"Composed {report.composed_files} · Skipped {len(report.skipped_compositions)} · "
        f"Failed {len(report.failed_compositions)}"
    )


def _render_composition_footer(report: PipelineReport) -> None:
    """Print the composition counters when the step actually ran."""
    if not any(outcome.composition_status for outcome in report.outcomes):
        return
    console.print(
        f"Composed {report.composed_files} · Skipped {len(report.skipped_compositions)} · "
        f"Failed {len(report.failed_compositions)}"
    )


def _render_composition_line(outcome: FileOutcome) -> None:
    """Print one file's composition result with its reason when skipped."""
    if outcome.composed_path is not None:
        console.print(f"{get_status_icon('success')} {outcome.source.name} -> {outcome.composed_path.name}")
    elif outcome.composition_status:
        console.print(f"{get_status_icon('warning')} {outcome.source.name}: {outcome.composition_status}")
    for warning in outcome.composition_warnings:
        console.print(f"    [gray]{warning}[/gray]")


def _progress_phase() -> ProgressPhase:
    """Build one transient progress display whose rows clear when it stops."""
    return cast(ProgressPhase, MultiProgressManager(show_download=False, transient=True))


def _run_auto_pipeline(context: AppContext, paths: tuple[Path, ...]) -> PipelineReport:
    """Render every automatic stage with one persistent row per input."""
    progress = MultiProgressManager(
        max_description_length=_PIPELINE_PROGRESS_DESCRIPTION_LENGTH,
        show_download=False,
        transient=True,
    )
    rows = _PipelineProgressRows(progress, paths, context)

    with ExitStack() as live:
        live.enter_context(progress)

        def choose_failure(recovery: RecoveryContext) -> RecoveryAction:
            live.close()
            action = _choose_recovery(context, recovery)
            if action is not RecoveryAction.FINISH:
                live.enter_context(progress)
            return action

        try:
            report: PipelineReport = run_pipeline(
                context,
                input_paths=paths,
                progress_factory=lambda: cast(ProgressPhase, nullcontext(rows)),
                llm_failure_handler=choose_failure,
                llm_progress_handler=rows.on_progress,
                tts_failure_handler=choose_failure,
                tts_progress_callbacks=rows,
            )
            rows.finalize(report)
            return report
        finally:
            rows.close()


def _tts_progress_label(context: AppContext) -> str:
    """Build a concise engine/model and human voice label for progress rows."""
    settings = context.user_settings
    engine_id: str = settings.tts_engine
    model_id: str = settings.tts_provider_model_id
    voice_id: str = settings.tts_voice_id
    if engine_id == "elevenbytes":
        custom_label: str | None = next(
            (item.label for item in settings.elevenbytes_custom_voices if item.alias.casefold() == voice_id.casefold()),
            None,
        )
        voice_label: str = "Dallin" if voice_id.casefold() == DALLIN_ALIAS else custom_label or voice_id
    elif engine_id == "edge":
        voice_label = {
            MAREK_VOICE_ID: "Marek",
            ZOFIA_VOICE_ID: "Zofia",
        }.get(voice_id, voice_id)
    elif engine_id == "sapi":
        voice_label = voice_id.title()
    else:
        voice_label = voice_id
    engine_label: str = f"{engine_id}/{model_id}" if engine_id in {"elevenbytes", "elevenlabs"} else engine_id
    return f"{engine_label} · {voice_label}"


def _ensure_binaries(paths: Sequence[Path]) -> bool:
    """Ensure both MKVToolNix binaries before starting Rich Live."""
    if not any(path.suffix.lower() == ".mkv" for path in paths):
        return True
    try:
        ensure_binary(Binary.MKVMERGE)
        ensure_binary(Binary.MKVEXTRACT)
    except InstallerError as exc:
        _render_pipeline_error(exc)
        return False
    except BinaryNotFoundError as exc:
        _render_pipeline_error(exc)
        return False
    return True


def _render_pipeline_error(error: AniShiftError) -> None:
    """Render one pipeline-level error."""
    console.print(f"[error]{error.context.message}[/error]")
    if error.context.suggestion:
        console.print(f"[gray]-> {error.context.suggestion}[/gray]")


def _render_llm_progress(context: AppContext, path: Path, state: LlmProgressState) -> None:
    """Render one durable LLM file transition without competing Rich Live displays."""
    if state == "translating":
        provider = context.user_settings.llm_provider
        model = context.user_settings.llm_provider_model_id or "default model"
        console.print(f"⏳ [info]Translating[/info] {path.name} [gray]via {provider}/{model}[/gray]")
        return
    if state == "done":
        console.print(f"{get_status_icon('success')} [success]Translated[/success] {path.name}")
        return
    if state == "failed":
        console.print(f"{get_status_icon('error')} [error]Translation failed[/error] {path.name}")
        return
    if state == "cancelled":
        console.print(f"{get_status_icon('warning')} [warning]Translation cancelled[/warning] {path.name}")
        return
    console.print(f"{get_status_icon('warning')} [warning]Translation not processed[/warning] {path.name}")


def _render_report(report: PipelineReport) -> None:
    """Render all file outcomes and the summary footer."""
    counts: dict[FileStatus, int] = {
        "done": 0,
        "failed": 0,
        "cancelled": 0,
        "not_processed": 0,
    }
    for outcome in report.outcomes:
        counts[outcome.status] += 1
        _render_outcome(outcome)
    console.print(
        f"Done {counts['done']} · Failed {counts['failed']} · "
        f"Not processed {counts['not_processed']} · Cancelled {counts['cancelled']}"
    )
    _render_llm_summary(report)
    _render_tts_summary(report)
    _render_composition_footer(report)
    if counts["cancelled"]:
        console.print("[warning]Interrupted — press Enter to run again.[/warning]")


def _render_outcome(outcome: FileOutcome) -> None:
    """Render one file's summary and details."""
    icon = get_status_icon(_STATUS_ICON[outcome.status])
    if outcome.status == "done":
        suffix = " [info](already Polish)[/info]" if outcome.already_polish else ""
        console.print(
            f"{icon} {outcome.source.name} spoken {outcome.spoken_lines} · "
            f"displayed {outcome.displayed_events} · drawings {outcome.drawing_events} · "
            f"collapsed {outcome.collapsed_away}{suffix}"
        )
        if outcome.translated_path is not None:
            console.print(f"    [gray]Polish full -> {outcome.translated_path}[/gray]")
        if outcome.spoken_path is not None:
            console.print(f"    [gray]Polish spoken -> {outcome.spoken_path}[/gray]")
        if outcome.displayed_path is not None:
            console.print(f"    [gray]Polish displayed -> {outcome.displayed_path}[/gray]")
        if outcome.narrator_path is not None:
            console.print(f"    [gray]Narrator -> {outcome.narrator_path}[/gray]")
        if outcome.mixed_audio_path is not None:
            console.print(f"    [gray]Mixed audio -> {outcome.mixed_audio_path}[/gray]")
        if outcome.translation_engine:
            failed = f" · {outcome.translation_failed_lines} failed" if outcome.translation_failed_lines else ""
            console.print(
                f"    [gray]translated {outcome.translated_lines} via {outcome.translation_engine}{failed}[/gray]"
            )
    elif outcome.status in {"failed", "not_processed"} and outcome.failure is not None:
        console.print(f"{icon} {outcome.source.name} [{outcome.failure.step}] {outcome.failure.message}")
        if outcome.failure.suggestion:
            console.print(f"    [gray]-> {outcome.failure.suggestion}[/gray]")
    else:
        console.print(f"{icon} {outcome.source.name} interrupted")
    for warning in outcome.warnings:
        console.print(f"{get_status_icon('warning')} {warning}")
    if outcome.composition_status:
        _render_composition_line(outcome)


def _choose_recovery(
    context: AppContext,
    recovery: RecoveryContext,
) -> RecoveryAction:
    """Show one shared recovery prompt and wait for an explicit decision."""
    from anishift.cli.settings_panel import open_settings_panel  # noqa: PLC0415 - interactive failure path

    console.print(f"[error]{recovery.error.message}[/error]")
    console.print(
        f"[warning]Completed {len(recovery.completed_files)} · "
        f"failed {len(recovery.failed_files)} · waiting {len(recovery.pending_files)}[/warning]",
    )
    console.print("[bold]> retry[/bold]\n[bold]> settings[/bold]\n[bold]> finish[/bold]")
    while True:
        answer = input("> ").strip().lower()
        if answer == "retry":
            return RecoveryAction.RETRY
        if answer == "settings":
            open_settings_panel(context)
            return RecoveryAction.SETTINGS
        if answer == "finish":
            return RecoveryAction.FINISH
        console.print("[warning]Choose 'retry', 'settings' or 'finish'.[/warning]")


def _render_llm_summary(report: PipelineReport) -> None:
    """Render aggregate content-free LLM usage when calls are present."""
    calls = [call for outcome in report.outcomes for call in outcome.llm_calls]
    if not calls:
        return
    repairs = sum(call.purpose == "translation_repair" for call in calls)
    retries = sum(call.transport_retries for call in calls)
    omitted_context_items = sum(call.omitted_context_items for call in calls)
    input_tokens = sum(call.input_tokens or 0 for call in calls)
    output_tokens = sum(call.output_tokens or 0 for call in calls)
    total_tokens = sum(call.total_tokens or 0 for call in calls)
    costs = [call.reported_cost for call in calls if call.reported_cost is not None]
    summary = (
        f"LLM calls {len(calls)} · repairs {repairs} · retries {retries} · "
        f"tokens {input_tokens}/{output_tokens}/{total_tokens}"
    )
    if costs:
        summary += f" · provider cost {sum(costs):.6f}"
    if omitted_context_items:
        summary += f" · omitted context items {omitted_context_items}"
    console.print(f"[gray]{summary}[/gray]")


def _render_tts_summary(report: PipelineReport) -> None:
    """Render aggregate content-free synthesis, timing and drift metrics."""
    stats = [outcome.tts_stats for outcome in report.outcomes if outcome.tts_stats is not None]
    if not stats:
        return
    profiles: list[str] = []
    for item in stats:
        profile: str = f"{item.engine_id}/{item.provider_model_id} · {item.voice_id}"
        if profile not in profiles:
            profiles.append(profile)
    console.print(f"[gray]TTS {'; '.join(profiles)}[/gray]")
    console.print(
        "[gray]"
        f"Events {sum(item.total_requests for item in stats)} · "
        f"synthesized {sum(item.synthesized for item in stats)} · "
        f"resumed {sum(item.resume_hits for item in stats)} · "
        f"skipped {sum(item.skipped for item in stats)} · "
        f"failed {sum(item.failed for item in stats)}"
        "[/gray]",
    )
    console.print(
        "[gray]"
        f"Provider calls {sum(item.provider_calls for item in stats)} · "
        f"retries {sum(item.retries for item in stats)}"
        "[/gray]",
    )
    placements = [placement for outcome in report.outcomes for placement in outcome.audio_placements]
    if placements:
        console.print(
            "[gray]"
            f"Drift max {max(abs(item.drift_ms) for item in placements)} ms · "
            f"total {sum(abs(item.drift_ms) for item in placements)} ms"
            "[/gray]",
        )
    tts_time_ms: float = sum(item.synthesis_time_ms for item in stats)
    audio_time_ms: float = sum(outcome.audio_time_ms for outcome in report.outcomes)
    console.print(
        f"[gray]TTS {_format_elapsed(tts_time_ms)} · audio {_format_elapsed(audio_time_ms)}[/gray]",
    )


def _format_elapsed(milliseconds: float) -> str:
    """Format aggregate milliseconds as a compact minute-second duration."""
    total_seconds: int = max(0, round(milliseconds / 1000))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


class _ManualInteraction:
    """Collect track and spoken-style decisions from the terminal."""

    def choose_tracks(self, info: MediaInfo, proposal: TrackSelection) -> TrackSelection:
        """Prompt for audio and subtitle track ids."""
        console.print(f"[bold]{info.path.name}[/bold]")
        for track in info.tracks:
            console.print(_track_row(track))
        audio_id = _track_id("Audio", proposal.audio_id, [track for track in info.tracks if track.type == "audio"])
        subtitle_id = _track_id(
            "Subtitle",
            proposal.subtitle_id,
            [track for track in info.tracks if track.type == "subtitles"],
            allow_none=True,
        )
        subtitle = next((track for track in info.tracks if track.id == subtitle_id), None)
        already_polish = subtitle is not None and is_polish_language(subtitle.language)
        return TrackSelection(audio_id, subtitle_id, already_polish)

    def choose_spoken_styles(
        self,
        source: Path,
        verdicts: Sequence[StyleVerdict],
        samples: Mapping[str, tuple[str, ...]],
    ) -> set[str] | None:
        """Prompt for styles to send to the narrator."""
        console.print(f"[bold]{source.name} styles[/bold]")
        for index, verdict in enumerate(verdicts, 1):
            console.print(
                f"{index}. {verdict.style} — {verdict.category.value} "
                f"({verdict.confidence:.0%}, {verdict.line_count} lines)"
            )
            for sample in samples.get(verdict.style, ()):
                console.print(f"    [gray]{sample}[/gray]")
        while True:
            answer = input("Styles to speak [Enter = accept classifier]: ").strip()
            if not answer:
                return None
            try:
                indexes = [int(value) for value in answer.split()]
            except ValueError:
                console.print("[warning]Enter space-separated style numbers.[/warning]")
                continue
            if any(index < 1 or index > len(verdicts) for index in indexes):
                console.print("[warning]Choose only listed style numbers.[/warning]")
                continue
            return {verdicts[index - 1].style for index in indexes}


def _track_row(track: TrackInfo) -> str:
    """Format one track for the manual prompt."""
    return f"{track.id:<3} {track.type:<10} {track.codec_id:<18} {track.language:<6} {track.name}"


def _track_id(label: str, proposal: int | None, tracks: Sequence[TrackInfo], *, allow_none: bool = False) -> int | None:
    """Prompt until a valid track id or an allowed empty choice is entered."""
    proposed = "-" if proposal is None else str(proposal)
    valid = {track.id for track in tracks}
    while True:
        answer = input(f"{label} track id [{proposed}]: ").strip()
        if not answer:
            return proposal
        if allow_none and answer == "-":
            return None
        try:
            selected = int(answer)
        except ValueError:
            selected = None
        if selected in valid:
            return selected
        console.print("[warning]Select a track from the listed ids.[/warning]")
