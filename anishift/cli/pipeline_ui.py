"""Render the Enter-key pipeline, prompts, progress and final report."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import ExitStack, nullcontext
from pathlib import Path
from typing import cast

from rich.progress import TaskID

from anishift.bootstrap import AppContext
from anishift.errors import AniShiftError
from anishift.pipeline import discover_inputs, run_pipeline
from anishift.pipeline.llm_queue import LlmFailureAction, LlmProgressState
from anishift.pipeline.types import FileOutcome, FileStatus, PipelineReport, ProgressPhase
from anishift.platform.binaries import Binary, BinaryNotFoundError
from anishift.services.extraction.tracks import is_polish_language
from anishift.services.extraction.types import MediaInfo, TrackInfo, TrackSelection
from anishift.services.subtitles.classifier import StyleVerdict
from anishift.setup.installer import InstallerError, ensure_binary
from anishift.utils.rich_console import MultiProgressManager, StatusType, console, get_status_icon

__all__ = ["run_pipeline_command"]

_STATUS_ICON: dict[FileStatus, StatusType] = {
    "done": "success",
    "failed": "error",
    "cancelled": "warning",
    "not_processed": "warning",
}
"""Map file statuses to console icons."""


class _LlmProgressRows:
    """Map LLM queue transitions onto ordinary zero-to-complete progress tasks."""

    def __init__(self, progress: MultiProgressManager) -> None:
        self._progress = progress
        self._task_ids: dict[Path, TaskID] = {}

    def on_progress(self, path: Path, state: LlmProgressState) -> None:
        """Start one standard row at zero and complete it on success."""
        if state == "translating":
            if path not in self._task_ids:
                self._task_ids[path] = self._progress.add_task(f"Translating {path.name}")
            return
        if state == "done":
            task_id = self._task_ids.get(path)
            if task_id is not None:
                self._progress.update(task_id, 100)
            return
        if state in {"failed", "cancelled", "not_processed"}:
            task_id = self._task_ids.pop(path, None)
            if task_id is not None:
                self._progress.stop_task(task_id)


def run_pipeline_command(context: AppContext) -> None:
    """Process workspace inputs on Enter and render the resulting report."""
    paths = discover_inputs(context.workspace_root)
    if not paths:
        console.print("[warning]Workspace is empty[/warning] — drop MKV files into workspace/ and press Enter.")
        return
    if not _ensure_binaries(paths):
        return
    try:
        if context.user_settings.mode == "manual":
            report = run_pipeline(
                context,
                interaction=_ManualInteraction(),
                llm_failure_handler=lambda outcome, completed, pending: _choose_llm_failure(
                    context,
                    outcome,
                    completed,
                    pending,
                ),
                llm_progress_handler=lambda path, state: _render_llm_progress(context, path, state),
            )
        elif context.user_settings.translation_engine == "llm":
            report = _run_llm_auto_pipeline(context)
        else:
            report = run_pipeline(
                context,
                progress_factory=_progress_phase,
                llm_failure_handler=lambda outcome, completed, pending: _choose_llm_failure(
                    context,
                    outcome,
                    completed,
                    pending,
                ),
                llm_progress_handler=lambda path, state: _render_llm_progress(context, path, state),
            )
    except KeyboardInterrupt:
        console.print("[warning]Interrupted.[/warning]")
        return
    except AniShiftError as error:
        _render_pipeline_error(error)
        return
    _render_report(report)


def _progress_phase() -> ProgressPhase:
    """Build one transient progress display whose rows clear when it stops."""
    return cast(ProgressPhase, MultiProgressManager(show_download=False, transient=True))


def _run_llm_auto_pipeline(context: AppContext) -> PipelineReport:
    """Render extraction and LLM requests with one standard multi-progress display."""
    progress = MultiProgressManager(show_download=False, transient=True)
    llm_rows = _LlmProgressRows(progress)

    with ExitStack() as live:
        live.enter_context(progress)

        def choose_failure(outcome: FileOutcome, completed: int, pending: int) -> LlmFailureAction:
            live.close()
            action = _choose_llm_failure(context, outcome, completed, pending)
            if action == "settings":
                live.enter_context(progress)
            return action

        return run_pipeline(
            context,
            progress_factory=lambda: cast(ProgressPhase, nullcontext(progress)),
            llm_failure_handler=choose_failure,
            llm_progress_handler=llm_rows.on_progress,
        )


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


def _choose_llm_failure(
    context: AppContext,
    outcome: FileOutcome,
    completed: int,
    pending: int,
) -> LlmFailureAction:
    """Show a clear provider failure and wait for an explicit safe decision."""
    from anishift.cli.settings_panel import open_settings_panel  # noqa: PLC0415 - interactive failure path

    failure = outcome.failure
    message = failure.message if failure is not None else "LLM provider failed"
    console.print(f"[error]{message}[/error]")
    console.print(f"[warning]Completed {completed} · waiting {pending}[/warning]")
    console.print("[bold]> settings[/bold]\n[bold]> finish[/bold]")
    while True:
        answer = input("> ").strip().lower()
        if answer == "settings":
            open_settings_panel(context)
            return "settings"
        if answer == "finish":
            return "finish"
        console.print("[warning]Choose 'settings' or 'finish'.[/warning]")


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
