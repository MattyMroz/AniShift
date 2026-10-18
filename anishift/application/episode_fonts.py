"""Fonts a subtitle layout task measures with: its source container's attachments and the system fonts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from anishift.application.artifacts import Artifact, ArtifactKind
from anishift.application.task_paths import task_staging_path
from anishift.errors import ExecutionError
from anishift.services.extraction import ExtractionError, extract_attachments
from anishift.services.fonts import system_font_paths
from anishift.services.subtitles import FontSources
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from pathlib import Path

    from anishift.application.planning import PlanTask
    from anishift.application.results import ArtifactSnapshot

__all__ = ["MAX_LAYOUT_INPUTS", "episode_fonts"]

# ── Constants ─────────────────────────────────────────────────────────────────

MAX_LAYOUT_INPUTS: Final[int] = 2
"""Inputs of a subtitle layout task: the subtitles, then optionally the source container carrying their fonts."""

_FONTS_SUFFIX: Final[str] = ".fonts"
"""Suffix of the task staging folder receiving the container's font attachments."""

logger = get_logger(__name__)


def episode_fonts(run_root: Path, task: PlanTask, artifacts: ArtifactSnapshot, output: Artifact) -> FontSources:
    """Extract the fonts of the task's optional source container into its staging and add the system fonts."""
    if len(task.requires) < MAX_LAYOUT_INPUTS:
        return FontSources(episode=(), system=system_font_paths())
    container: Artifact = artifacts.require_ready(task.requires[1])
    if container.path is None or container.kind is not ArtifactKind.VIDEO_MKV:
        msg = "Subtitle layout fonts require a ready MKV source container"
        raise ExecutionError(msg)
    episode: tuple[Path, ...] = ()
    try:
        episode = extract_attachments(container.path, task_staging_path(run_root, task, output, _FONTS_SUFFIX))
    except ExtractionError as exc:
        logger.warning(
            "Episode fonts unavailable, layout measures with system fonts",
            task_id=task.task_id,
            source=container.path.name,
            error_code=exc.context.code.value,
        )
    return FontSources(episode=episode, system=system_font_paths())
