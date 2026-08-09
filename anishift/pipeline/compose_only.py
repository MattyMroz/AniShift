"""Build file outcomes from products already on disk for the /compose command."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Final

from anishift.bootstrap import AppContext
from anishift.pipeline.composition_runtime import compose_outcomes
from anishift.pipeline.narration import scope_id_for_source
from anishift.pipeline.runner import discover_inputs
from anishift.pipeline.types import CompositionUi, FileOutcome
from anishift.services.composition.config import CompositionConfig
from anishift.services.composition.service import CompositionService
from anishift.services.composition.types import OutputVariant, QualityPreset
from anishift.services.extraction.service import extract_tracks, identify
from anishift.services.extraction.tracks import select_tracks
from anishift.services.extraction.types import LegacyExtractionResult, MediaInfo, TrackSelection
from anishift.utils.logger import get_logger

__all__ = ["compose_existing", "extracted_polish_outcome", "product_outcome"]

# ── Constants ─────────────────────────────────────────────────────────────────

_MKV_SUFFIX: Final[str] = ".mkv"
"""Only containers can be assembled; TXT inputs carry no video."""

_SUBTITLE_SUFFIXES: Final[tuple[str, ...]] = (".ass", ".srt")
"""Subtitle formats this application writes."""

_NARRATION_SUFFIXES: Final[tuple[str, ...]] = (".eac3", ".m4a", ".mp3", ".opus", ".flac", ".wav")
"""Sidecar extensions produced by the audio codec profiles."""

_DISPLAYED_INFIX: Final[str] = ".displayed"
"""Infix of the displayed-only subtitle product."""

logger = get_logger(__name__)


def compose_existing(
    context: AppContext,
    *,
    ui: CompositionUi | None = None,
    cancel: threading.Event | None = None,
) -> tuple[FileOutcome, ...]:
    """Assemble every workspace container from material already on disk.

    Nothing is translated or synthesized and no setting is changed: the
    requested variant and quality still come from the user's preferences.
    """
    workspace_root: Path = context.workspace_root
    outcomes: dict[Path, FileOutcome] = {}
    for source in discover_inputs(workspace_root):
        if source.suffix.casefold() != _MKV_SUFFIX:
            continue
        outcome: FileOutcome | None = _material_for(source, workspace_root=workspace_root, cancel=cancel)
        if outcome is None:
            logger.info("Composition input skipped", source=source.name, reason="no_material")
            continue
        outcomes[source] = outcome
    config: CompositionConfig = CompositionConfig(
        quality_preset=QualityPreset(context.user_settings.composition_quality_preset),
    )
    composed: dict[Path, FileOutcome] = compose_outcomes(
        outcomes,
        service=CompositionService(config),
        variant=OutputVariant(context.user_settings.output_variant),
        workspace_root=workspace_root,
        ui=ui,
        cancel=cancel,
    )
    return tuple(composed.values())


def product_outcome(source: Path, *, workspace_root: Path) -> FileOutcome | None:
    """Return an outcome built from earlier runs' products, when any exist."""
    full: Path | None = _first_subtitle(workspace_root, source.stem)
    displayed: Path | None = _first_subtitle(workspace_root, f"{source.stem}{_DISPLAYED_INFIX}")
    narration: Path | None = _narration_sidecar(source)
    if full is None and displayed is None and narration is None:
        return None
    return FileOutcome(
        source=source,
        status="done",
        translated_path=full,
        displayed_path=displayed,
        mixed_audio_path=narration,
    )


def extracted_polish_outcome(
    source: Path,
    *,
    workspace_root: Path,
    cancel: threading.Event | None = None,
) -> FileOutcome | None:
    """Return an outcome carrying the source's own Polish subtitle track.

    This is the path a container that already holds Polish subtitles takes:
    it can be assembled without ever running translation or TTS.
    """
    info: MediaInfo = identify(source)
    proposal: TrackSelection = select_tracks(info.tracks)
    if not proposal.already_polish or proposal.subtitle_id is None:
        return None
    scope_id: str = scope_id_for_source(source, workspace_root=workspace_root)
    work_dir: Path = workspace_root / "tmp" / scope_id / "compose"
    work_dir.mkdir(parents=True, exist_ok=True)
    extracted: LegacyExtractionResult = extract_tracks(
        info,
        TrackSelection(audio_id=None, subtitle_id=proposal.subtitle_id, already_polish=True),
        work_dir,
        cancel=cancel,
    )
    if extracted.subtitle_path is None:
        return None
    return FileOutcome(
        source=source,
        status="done",
        subtitle_path=extracted.subtitle_path,
        translated_path=extracted.subtitle_path,
        already_polish=True,
    )


def _material_for(
    source: Path,
    *,
    workspace_root: Path,
    cancel: threading.Event | None,
) -> FileOutcome | None:
    """Return products from an earlier run, or the source's Polish subtitles."""
    products: FileOutcome | None = product_outcome(source, workspace_root=workspace_root)
    if products is not None:
        return products
    return extracted_polish_outcome(source, workspace_root=workspace_root, cancel=cancel)


def _first_subtitle(directory: Path, stem: str) -> Path | None:
    """Return the Polish product with this stem, in either written format."""
    for suffix in _SUBTITLE_SUFFIXES:
        candidate: Path = directory / f"{stem}.pl{suffix}"
        if candidate.is_file():
            return candidate
    return None


def _narration_sidecar(source: Path) -> Path | None:
    """Return the mixed narration written next to the source, if any."""
    for suffix in _NARRATION_SUFFIXES:
        candidate: Path = source.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None
