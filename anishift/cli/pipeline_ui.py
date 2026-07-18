"""Render the Enter-key pipeline, prompts, progress and final report."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from anishift.bootstrap import AppContext
from anishift.errors import AniShiftError
from anishift.pipeline import discover_inputs, run_pipeline
from anishift.pipeline.types import FileOutcome, PipelineReport, ProgressReporter
from anishift.platform.binaries import Binary, BinaryNotFoundError
from anishift.services.extraction.types import MediaInfo, TrackInfo, TrackSelection
from anishift.services.subtitles.classifier import StyleVerdict
from anishift.setup.installer import InstallerError, ensure_binary
from anishift.utils.rich_console import MultiProgressManager, StatusType, console, get_status_icon

__all__ = ["run_pipeline_command"]

_STATUS_ICON: dict[str, StatusType] = {
    "done": "success",
    "failed": "error",
    "cancelled": "warning",
}
"""Map file statuses to console icons."""


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
            report = run_pipeline(context, interaction=_ManualInteraction())
        else:
            with MultiProgressManager() as progress:
                report = run_pipeline(context, progress=cast(ProgressReporter, progress))
    except KeyboardInterrupt:
        console.print("[warning]Interrupted.[/warning]")
        return
    _render_report(report)


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


def _render_report(report: PipelineReport) -> None:
    """Render all file outcomes and the summary footer."""
    counts = {"done": 0, "failed": 0, "cancelled": 0}
    for outcome in report.outcomes:
        counts[outcome.status] += 1
        _render_outcome(outcome)
    console.print(f"Done {counts['done']} · Failed {counts['failed']} · Cancelled {counts['cancelled']}")
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
        if outcome.displayed_path is not None:
            console.print(f"    [gray]-> {outcome.displayed_path}[/gray]")
    elif outcome.status == "failed" and outcome.failure is not None:
        console.print(f"{icon} {outcome.source.name} [{outcome.failure.step}] {outcome.failure.message}")
        if outcome.failure.suggestion:
            console.print(f"    [gray]-> {outcome.failure.suggestion}[/gray]")
    else:
        console.print(f"{icon} {outcome.source.name} interrupted")
    for warning in outcome.warnings:
        console.print(f"{get_status_icon('warning')} {warning}")


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
        already_polish = subtitle is not None and subtitle.language.lower() in {"pol", "pl"}
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
