"""Translate file outcomes into composition plans and assemble them."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Protocol

from anishift.application.composition_handler import LegacyCompositionAdapter
from anishift.errors import AniShiftError, ErrorCode
from anishift.pipeline.narration import scope_id_for_source
from anishift.pipeline.types import CompositionUi, FileOutcome
from anishift.services.composition.errors import CompositionProcessError
from anishift.services.composition.probe import source_duration_us
from anishift.services.composition.service import CompositionProgressSink
from anishift.services.composition.types import (
    AttachedSubtitle,
    CompositionPlan,
    CompositionResult,
    CompositionStatus,
    OutputVariant,
    SubtitleRole,
)
from anishift.utils.logger import get_logger
from anishift.utils.safe_fs import safe_rmtree

__all__ = ["BurnEstimate", "CompositionAssembler", "build_plan", "compose_outcomes", "estimate_burn_cost"]

# ── Constants ────────────────────────────────────────────────────────────────

_FULL_TRACK_NAME: Final[str] = "Napisy PL"
"""Track name for the complete Polish subtitle stream."""

_DISPLAYED_TRACK_NAME: Final[str] = "Napisy poboczne PL"
"""Track name for on-screen signs and notes."""

_POLISH_LANGUAGE: Final[str] = "pol"
"""Language assigned to every track this application adds."""

_BURN_SECONDS_PER_MINUTE: Final[float] = 10.0
"""Render seconds per minute of video used for the pre-run estimate, measured
at 1080p with the balanced preset and kept slightly pessimistic."""

_MICROSECONDS_PER_MINUTE: Final[int] = 60_000_000
"""Scale between probed microseconds and the minutes used in the estimate."""

_FAILED_STATUS: Final[str] = "failed"
"""Composition status stored when assembling one file raised a typed error."""

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BurnEstimate:
    """Predicted cost of rendering a batch, shown before work starts."""

    file_count: int
    estimated_seconds: float


class CompositionAssembler(Protocol):
    """Composition entry point the pipeline loop drives.

    Satisfied by ``CompositionService``; declared here so the loop can run
    against a substitute without resolving external binaries.
    """

    @property
    def ffprobe(self) -> Path:
        """Return the FFprobe binary used for pre-run estimates."""
        ...

    def compose(
        self,
        plan: CompositionPlan,
        *,
        callbacks: CompositionProgressSink | None = None,
        cancel: threading.Event | None = None,
    ) -> CompositionResult:
        """Assemble one planned file and validate the result."""
        ...


def build_plan(
    outcome: FileOutcome,
    *,
    variant: OutputVariant,
    workspace_root: Path,
    scope_id: str,
    subtitle_kind: str = "ass",
) -> CompositionPlan | None:
    """Return the composition plan for one processed file, or ``None``.

    The truth tables from the stage requirements live here: an already-Polish
    source never receives a duplicate full track, and burning prefers the
    displayed-only stream whenever a lector exists.
    """
    destination: Path = _destination_dir(outcome, variant=variant, workspace_root=workspace_root)
    temporary_root: Path = workspace_root / "temp" / scope_id
    if variant is OutputVariant.BURN:
        burn_subtitle: Path | None = _burn_subtitle(outcome)
        if burn_subtitle is None and outcome.mixed_audio_path is None:
            return None
        return CompositionPlan(
            source_path=outcome.source,
            variant=variant,
            narration_audio=outcome.mixed_audio_path,
            burn_subtitle=burn_subtitle,
            source_subtitle_kind=subtitle_kind,
            scope_id=scope_id,
            temporary_root=temporary_root,
            destination_dir=destination,
        )
    subtitles: tuple[AttachedSubtitle, ...] = _attached_subtitles(outcome)
    if not subtitles and outcome.mixed_audio_path is None:
        return None
    return CompositionPlan(
        source_path=outcome.source,
        variant=variant,
        narration_audio=outcome.mixed_audio_path,
        subtitles=subtitles,
        source_subtitle_kind=subtitle_kind,
        scope_id=scope_id,
        temporary_root=temporary_root,
        destination_dir=destination,
    )


def _attached_subtitles(outcome: FileOutcome) -> tuple[AttachedSubtitle, ...]:
    """Return subtitle tracks to mux, skipping a duplicate Polish source."""
    attached: list[AttachedSubtitle] = []
    if outcome.translated_path is not None and not outcome.already_polish:
        attached.append(
            AttachedSubtitle(outcome.translated_path, SubtitleRole.FULL, _POLISH_LANGUAGE, _FULL_TRACK_NAME),
        )
    if outcome.displayed_path is not None:
        attached.append(
            AttachedSubtitle(
                outcome.displayed_path,
                SubtitleRole.DISPLAYED,
                _POLISH_LANGUAGE,
                _DISPLAYED_TRACK_NAME,
            ),
        )
    return tuple(attached)


def _burn_subtitle(outcome: FileOutcome) -> Path | None:
    """Return the single stream to render into the picture."""
    if outcome.mixed_audio_path is not None:
        return outcome.displayed_path
    if outcome.translated_path is not None:
        return outcome.translated_path
    return outcome.subtitle_path


def _destination_dir(outcome: FileOutcome, *, variant: OutputVariant, workspace_root: Path) -> Path:
    """Return where the artifact belongs for the requested variant."""
    del variant, workspace_root
    return outcome.source.parent


def estimate_burn_cost(plans: tuple[CompositionPlan, ...], *, ffprobe: Path) -> BurnEstimate:
    """Return a coarse render-cost estimate shown before burning starts.

    The estimate scales with the playing time of each source, read through
    FFprobe. ``FileOutcome.audio_time_ms`` measures how long the audio stage
    ran, not how long the episode is, so it cannot be used here.
    """
    total_us: int = sum(_playing_time_us(plan.source_path, ffprobe=ffprobe) for plan in plans)
    minutes: float = total_us / _MICROSECONDS_PER_MINUTE
    return BurnEstimate(file_count=len(plans), estimated_seconds=minutes * _BURN_SECONDS_PER_MINUTE)


def _playing_time_us(source: Path, *, ffprobe: Path) -> int:
    """Return one source's playing time, or zero when probing fails.

    An unreadable source only shortens the announcement; the render itself
    still reports the real failure a moment later.
    """
    try:
        return source_duration_us(source, ffprobe=ffprobe)
    except CompositionProcessError:
        logger.debug("Burn estimate skipped one source", source=source.name)
        return 0


def compose_outcomes(  # noqa: PLR0913 - one explicit argument per composition concern
    outcomes: dict[Path, FileOutcome],
    *,
    service: CompositionAssembler,
    variant: OutputVariant,
    workspace_root: Path,
    ui: CompositionUi | None = None,
    cancel: threading.Event | None = None,
) -> dict[Path, FileOutcome]:
    """Assemble every finished file and record why the others were skipped.

    Shared by the full pipeline and by ``/compose`` so both take exactly the
    same decisions. One file's failure never stops the batch. The service is
    built by the caller, which keeps this loop testable without real binaries.
    """
    composed: dict[Path, FileOutcome] = dict(outcomes)
    adapter: LegacyCompositionAdapter = LegacyCompositionAdapter(service)
    plans: dict[Path, CompositionPlan] = {}
    for path, outcome in outcomes.items():
        plan: CompositionPlan | None = _plan_for(outcome, variant=variant, workspace_root=workspace_root)
        if plan is None:
            composed[path] = replace(outcome, composition_status=CompositionStatus.SKIPPED_NOTHING_TO_ADD.value)
            logger.info("Composition skipped", source=path.name, reason="nothing_to_add")
            continue
        plans[path] = plan
    if variant is OutputVariant.BURN and ui is not None:
        estimate: BurnEstimate = estimate_burn_cost(tuple(plans.values()), ffprobe=service.ffprobe)
        ui.on_burn_estimate(estimate.file_count, estimate.estimated_seconds)
    for path, plan in plans.items():
        if cancel is not None and cancel.is_set():
            break
        composed[path] = _compose_one(
            adapter,
            composed[path],
            plan,
            workspace_root=workspace_root,
            ui=ui,
            cancel=cancel,
        )
    return composed


def _plan_for(outcome: FileOutcome, *, variant: OutputVariant, workspace_root: Path) -> CompositionPlan | None:
    """Return the plan for one finished outcome, or ``None`` when unusable."""
    if outcome.status != "done":
        return None
    return build_plan(
        outcome,
        variant=variant,
        workspace_root=workspace_root,
        scope_id=scope_id_for_source(outcome.source, workspace_root=workspace_root),
        subtitle_kind=_subtitle_kind(outcome),
    )


def _compose_one(  # noqa: PLR0913 - one explicit argument per composition concern
    service: LegacyCompositionAdapter,
    outcome: FileOutcome,
    plan: CompositionPlan,
    *,
    workspace_root: Path,
    ui: CompositionUi | None,
    cancel: threading.Event | None,
) -> FileOutcome:
    """Compose one file, keeping a typed failure local to that file."""
    try:
        result: CompositionResult = service.compose(plan, callbacks=ui, cancel=cancel)
    except AniShiftError as error:
        if error.context.code is ErrorCode.CANCELLED:
            raise
        logger.warning("Composition failed", source=plan.source_path.name, code=error.context.code.value)
        return replace(outcome, composition_status=_FAILED_STATUS, composition_warnings=(error.context.message,))
    if result.status is CompositionStatus.COMPLETED:
        _discard_scope(workspace_root, plan.scope_id)
    return replace(
        outcome,
        composed_path=result.output_path,
        composition_status=result.status.value,
        composition_warnings=result.warnings,
    )


def _discard_scope(workspace_root: Path, scope_id: str) -> None:
    """Remove the transient working directory of one finished file."""
    scope_dir: Path = workspace_root / "temp" / scope_id
    if not scope_dir.exists():
        return
    try:
        safe_rmtree(scope_dir)
    except OSError:
        logger.warning("Transient scope directory could not be removed", scope_id=scope_id)


def _subtitle_kind(outcome: FileOutcome) -> str:
    """Return the subtitle format of the products written for one file."""
    subtitle: Path | None = outcome.translated_path or outcome.displayed_path or outcome.subtitle_path
    return "srt" if subtitle is not None and subtitle.suffix.casefold() == ".srt" else "ass"
