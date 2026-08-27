"""Deterministic workspace discovery without media or subtitle probing."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Final

from anishift.application.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    GroupConflict,
    GroupConflictKind,
    SourceGroup,
    create_artifact_id,
    create_group_id,
)

# ── Constants ──────────────────────────────────────────────────────────────

_PRIMARY_SOURCE_KINDS: Final[Mapping[str, ArtifactKind]] = MappingProxyType(
    {
        ".mkv": ArtifactKind.VIDEO_MKV,
        ".mp4": ArtifactKind.VIDEO_MP4,
        ".txt": ArtifactKind.STANDALONE_TEXT,
    }
)
"""The one statement of which filename suffix names a primary source, and of which kind."""

_PRIMARY_KINDS: Final[frozenset[ArtifactKind]] = frozenset(_PRIMARY_SOURCE_KINDS.values())
"""Artifact kinds a primary source can carry, read off the suffixes that name them."""

PRIMARY_SOURCE_SUFFIXES: Final[frozenset[str]] = frozenset(_PRIMARY_SOURCE_KINDS)
"""Folded suffixes of every primary source, for any caller judging one filename."""


class DiscoveryWarningKind(StrEnum):
    """Non-blocking conditions surfaced by workspace discovery."""

    ORPHAN_ARTIFACT = "orphan_artifact"


@dataclass(frozen=True, slots=True)
class DiscoveryWarning:
    """One non-blocking discovery condition tied to a filesystem path."""

    kind: DiscoveryWarningKind
    message: str
    path: Path


@dataclass(frozen=True, slots=True)
class ArtifactName:
    """Filename-only classification before any format validation."""

    path: Path
    stem: str
    kind: ArtifactKind
    is_primary: bool
    is_derived: bool
    subtitle_format: str | None = None
    audio_codec: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Source groups, ungrouped conflicts, and warnings from one directory scan."""

    groups: tuple[SourceGroup, ...]
    ungrouped_conflicts: tuple[GroupConflict, ...]
    warnings: tuple[DiscoveryWarning, ...]


def discover_groups(root: Path) -> DiscoveryResult:
    """Read *root* once and deterministically group supported artifact names."""
    paths: tuple[Path, ...] = tuple(
        sorted(
            (path for path in root.iterdir() if path.is_file()),
            key=lambda path: (path.name.casefold(), path.name),
        )
    )
    candidates: tuple[ArtifactName, ...] = tuple(
        candidate for path in paths if (candidate := classify_artifact(path)) is not None
    )
    groups: tuple[SourceGroup, ...] = group_candidates(candidates)
    grouped_keys: set[tuple[str, str]] = {
        (group.directory.as_posix().casefold(), group.stem.casefold()) for group in groups
    }
    warnings: tuple[DiscoveryWarning, ...] = tuple(
        DiscoveryWarning(
            kind=DiscoveryWarningKind.ORPHAN_ARTIFACT,
            message="Artifact has no primary MKV, MP4, or TXT source",
            path=candidate.path,
        )
        for candidate in candidates
        if _candidate_group_key(candidate) not in grouped_keys
    )
    return DiscoveryResult(groups=groups, ungrouped_conflicts=(), warnings=warnings)


def is_primary_source(path: Path) -> bool:
    """Return whether *path* names an MKV, MP4, or standalone TXT source."""
    candidate: ArtifactName | None = classify_artifact(path)
    return candidate is not None and candidate.is_primary


def is_derived_product(path: Path) -> bool:
    """Return whether *path* follows a durable AniShift product name."""
    candidate: ArtifactName | None = classify_artifact(path)
    return candidate is not None and candidate.is_derived


def classify_artifact(path: Path) -> ArtifactName | None:
    """Classify one supported filename without touching its contents."""
    lowered: str = path.name.casefold()
    classifiers = (
        _classify_derived_subtitle,
        _classify_final_container,
        _classify_source_subtitle,
        _classify_audio_product,
        _classify_primary_source,
    )
    for classifier in classifiers:
        candidate: ArtifactName | None = classifier(path, lowered)
        if candidate is not None:
            return candidate
    return None


def group_candidates(candidates: Sequence[ArtifactName]) -> tuple[SourceGroup, ...]:
    """Group classified names by directory and normalized stem."""
    buckets: dict[tuple[str, str], list[ArtifactName]] = {}
    for candidate in candidates:
        buckets.setdefault(_candidate_group_key(candidate), []).append(candidate)

    groups: list[SourceGroup] = []
    for key in sorted(buckets):
        bucket: tuple[ArtifactName, ...] = tuple(sorted(buckets[key], key=_candidate_sort_key))
        if not any(candidate.is_primary for candidate in bucket):
            continue
        groups.append(_build_source_group(bucket))
    return tuple(groups)


def _classify_derived_subtitle(path: Path, lowered: str) -> ArtifactName | None:
    variants: tuple[tuple[str, ArtifactKind], ...] = (
        (".spoken.pl.ass", ArtifactKind.SPOKEN_PL),
        (".spoken.pl.srt", ArtifactKind.SPOKEN_PL),
        (".displayed.pl.ass", ArtifactKind.DISPLAYED_PL),
        (".displayed.pl.srt", ArtifactKind.DISPLAYED_PL),
        (".pl.ass", ArtifactKind.FULL_PL),
        (".pl.srt", ArtifactKind.FULL_PL),
    )
    for suffix, kind in variants:
        if lowered.endswith(suffix):
            return _artifact_name(
                path,
                path.name[: -len(suffix)],
                kind,
                subtitle_format=suffix.rsplit(".", maxsplit=1)[-1],
            )
    return None


def _classify_final_container(path: Path, lowered: str) -> ArtifactName | None:
    variants: tuple[tuple[str, ArtifactKind], ...] = (
        (".pl.mkv", ArtifactKind.FINAL_MKV),
        (".pl.mp4", ArtifactKind.FINAL_MP4),
    )
    for suffix, kind in variants:
        if lowered.endswith(suffix):
            return _artifact_name(path, path.name[: -len(suffix)], kind)
    return None


def _classify_source_subtitle(path: Path, lowered: str) -> ArtifactName | None:
    if not (lowered.endswith(".ass") or lowered.endswith(".srt")):
        return None
    return _artifact_name(
        path,
        path.stem,
        ArtifactKind.SOURCE_SUBTITLES,
        subtitle_format=path.suffix[1:].casefold(),
    )


def _classify_audio_product(path: Path, lowered: str) -> ArtifactName | None:
    codecs: tuple[str, ...] = ("eac3", "m4a", "mp3", "opus", "flac", "wav")
    for codec in codecs:
        suffix: str = f".{codec}"
        if lowered.endswith(suffix):
            return _artifact_name(
                path,
                path.name[: -len(suffix)],
                ArtifactKind.NARRATION_AUDIO,
                audio_codec=codec,
            )
    return None


def _classify_primary_source(path: Path, lowered: str) -> ArtifactName | None:
    for suffix, kind in _PRIMARY_SOURCE_KINDS.items():
        if lowered.endswith(suffix):
            return _artifact_name(path, path.stem, kind)
    return None


def _artifact_name(
    path: Path,
    stem: str,
    kind: ArtifactKind,
    *,
    subtitle_format: str | None = None,
    audio_codec: str | None = None,
) -> ArtifactName | None:
    normalized_stem: str = stem.strip()
    if not normalized_stem:
        return None
    return ArtifactName(
        path=path,
        stem=normalized_stem,
        kind=kind,
        is_primary=kind in _PRIMARY_KINDS,
        is_derived=kind
        in {
            ArtifactKind.FULL_PL,
            ArtifactKind.SPOKEN_PL,
            ArtifactKind.DISPLAYED_PL,
            ArtifactKind.NARRATION_AUDIO,
            ArtifactKind.FINAL_MKV,
            ArtifactKind.FINAL_MP4,
        },
        subtitle_format=subtitle_format,
        audio_codec=audio_codec,
    )


def _build_source_group(candidates: tuple[ArtifactName, ...]) -> SourceGroup:
    first: ArtifactName = candidates[0]
    group_id: str = create_group_id(Path(), first.stem)
    discovered_artifacts: tuple[Artifact, ...] = tuple(_to_artifact(candidate, group_id) for candidate in candidates)
    artifacts_by_id: dict[str, Artifact] = {}
    for artifact in discovered_artifacts:
        artifacts_by_id.setdefault(artifact.artifact_id, artifact)
    return SourceGroup(
        group_id=group_id,
        stem=first.stem,
        directory=first.path.parent,
        artifacts=tuple(artifacts_by_id.values()),
        conflicts=_find_conflicts(candidates),
    )


def _to_artifact(candidate: ArtifactName, group_id: str) -> Artifact:
    lifetime: ArtifactLifetime = ArtifactLifetime.DURABLE if candidate.is_derived else ArtifactLifetime.SOURCE
    return Artifact(
        artifact_id=create_artifact_id(group_id, candidate.kind, Path(candidate.path.name)),
        group_id=group_id,
        kind=candidate.kind,
        path=candidate.path,
        state=ArtifactState.CANDIDATE,
        lifetime=lifetime,
        planned_destination=candidate.path,
        subtitle_format=candidate.subtitle_format,
        audio_codec=candidate.audio_codec,
    )


def _find_conflicts(candidates: tuple[ArtifactName, ...]) -> tuple[GroupConflict, ...]:
    conflicts: list[GroupConflict] = []
    primary: tuple[ArtifactName, ...] = tuple(candidate for candidate in candidates if candidate.is_primary)
    has_text: bool = any(candidate.kind is ArtifactKind.STANDALONE_TEXT for candidate in primary)
    has_video: bool = any(candidate.kind in {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4} for candidate in primary)
    if has_text and has_video:
        conflicts.append(
            GroupConflict(
                kind=GroupConflictKind.TXT_WITH_VIDEO,
                message="TXT and video with the same stem would publish the same subtitle product",
                paths=tuple(candidate.path for candidate in primary),
            )
        )

    primary_counts: Counter[ArtifactKind] = Counter(candidate.kind for candidate in primary)
    duplicated_primary_paths: tuple[Path, ...] = tuple(
        candidate.path for candidate in primary if primary_counts[candidate.kind] > 1
    )
    if duplicated_primary_paths:
        conflicts.append(
            GroupConflict(
                kind=GroupConflictKind.AMBIGUOUS_PRIMARY,
                message="More than one primary source has the same kind and normalized stem",
                paths=duplicated_primary_paths,
            )
        )
    return tuple(conflicts)


def _candidate_group_key(candidate: ArtifactName) -> tuple[str, str]:
    return candidate.path.parent.as_posix().casefold(), candidate.stem.casefold()


def _candidate_sort_key(candidate: ArtifactName) -> tuple[int, int, str, str]:
    kind_order: dict[ArtifactKind, int] = {
        ArtifactKind.VIDEO_MKV: 0,
        ArtifactKind.VIDEO_MP4: 1,
        ArtifactKind.STANDALONE_TEXT: 2,
        ArtifactKind.SOURCE_SUBTITLES: 3,
    }
    format_order: int = 0 if candidate.subtitle_format == "ass" else 1
    return (
        kind_order.get(candidate.kind, 4),
        format_order,
        candidate.path.name.casefold(),
        candidate.path.name,
    )
