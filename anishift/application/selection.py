"""Pure deterministic source-selection policies shared by discovery and planning."""

from __future__ import annotations

from collections.abc import Sequence

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactState


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


def _artifact_path_key(artifact: Artifact) -> tuple[str, str]:
    if artifact.path is None:
        return "", ""
    return artifact.path.name.casefold(), artifact.path.name
