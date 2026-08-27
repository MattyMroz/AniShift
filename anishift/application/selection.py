"""Pure deterministic source-selection policies shared by discovery, planning and every frontend."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Final

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactState

if TYPE_CHECKING:
    from anishift.application.inspection import InspectedSourceGroup

# ── Constants ──────────────────────────────────────────────────────────────

_TEXT_SOURCE_KINDS: Final[frozenset[ArtifactKind]] = frozenset(
    {ArtifactKind.SOURCE_SUBTITLES, ArtifactKind.STANDALONE_TEXT},
)
"""Artifact kinds already carrying the text one group needs before any run."""


def choose_primary_video(candidates: Sequence[Artifact]) -> Artifact | None:
    """Choose validated MKV before MP4 while retaining deterministic filename order."""
    videos: tuple[Artifact, ...] = tuple(
        artifact
        for artifact in candidates
        if artifact.kind in {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4}
        and artifact.state is not ArtifactState.INVALID
    )
    if not videos:
        return None
    return min(
        videos,
        key=lambda artifact: (
            0 if artifact.kind is ArtifactKind.VIDEO_MKV else 1,
            _artifact_path_key(artifact),
        ),
    )


def choose_auto_sidecar(candidates: Sequence[Artifact]) -> Artifact | None:
    """Choose a usable exact-stem ASS before SRT without performing I/O."""
    sidecars: tuple[Artifact, ...] = tuple(
        artifact
        for artifact in candidates
        if artifact.kind is ArtifactKind.SOURCE_SUBTITLES and artifact.state is not ArtifactState.INVALID
    )
    if not sidecars:
        return None
    return min(
        sidecars,
        key=lambda artifact: (
            0 if artifact.subtitle_format == "ass" else 1,
            _artifact_path_key(artifact),
        ),
    )


def group_is_ready(group: InspectedSourceGroup) -> bool:
    """Whether one inspected group may be run: free of conflicts and already holding text."""
    if group.conflicts:
        return False
    return _has_text_source(group) or _has_embedded_text(group)


def ready_group_ids(groups: Sequence[InspectedSourceGroup]) -> tuple[str, ...]:
    """Return the ID of every group a run may take, in the order the caller listed them."""
    return tuple(group.group_id for group in groups if group_is_ready(group))


def _artifact_path_key(artifact: Artifact) -> tuple[str, str]:
    if artifact.path is None:
        return "", ""
    return artifact.path.name.casefold(), artifact.path.name


def _has_text_source(group: InspectedSourceGroup) -> bool:
    """Whether one validated sidecar or text file already belongs to the group."""
    return any(
        artifact.kind in _TEXT_SOURCE_KINDS and artifact.state is ArtifactState.READY for artifact in group.artifacts
    )


def _has_embedded_text(group: InspectedSourceGroup) -> bool:
    """Whether an identified container of the group carries a subtitle track."""
    return any(
        track.subtitle_format is not None for catalog in group.media_catalogs.values() for track in catalog.tracks
    )
