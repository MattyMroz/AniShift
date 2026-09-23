"""Deterministic workspace discovery without media or subtitle probing."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
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
from anishift.application.products import ProductName, classify_product
from anishift.application.workflows import ROOT_ROUTE, WorkflowRoute, WorkflowTarget, WorkspacePlace, route_within
from anishift.paths import TEMP_DIRECTORY

# ── Constants ──────────────────────────────────────────────────────────────

_PRIMARY_SOURCE_KINDS: Final[Mapping[str, ArtifactKind]] = MappingProxyType(
    {
        ".mkv": ArtifactKind.VIDEO_MKV,
        ".mp4": ArtifactKind.VIDEO_MP4,
        ".txt": ArtifactKind.STANDALONE_TEXT,
    }
)
"""The one statement of which filename suffix names a container or standalone text source, and of which kind."""

PRIMARY_SOURCE_SUFFIXES: Final[frozenset[str]] = frozenset(_PRIMARY_SOURCE_KINDS)
"""Folded suffixes of every primary source of plain video work, for any caller judging one filename."""

SOURCE_SUBTITLE_FORMATS: Final[Mapping[str, str]] = MappingProxyType({".ass": "ass", ".ssa": "ass", ".srt": "srt"})
"""Subtitle suffixes discovery accepts and the working format each one is read and written as."""

_SOURCE_IMAGE_SUFFIXES: Final[frozenset[str]] = frozenset({".png", ".jpg", ".jpeg"})
"""Still-image suffixes a cover accepts as the single frame of its export."""

_VIDEO_PRIMARY_KINDS: Final[frozenset[ArtifactKind]] = frozenset(_PRIMARY_SOURCE_KINDS.values())
"""Main sources of plain video work; TXT stays visible for the manual flow without starting work by itself."""

_PRIMARY_KINDS_BY_TARGET: Final[Mapping[WorkflowTarget, frozenset[ArtifactKind]]] = MappingProxyType(
    {
        WorkflowTarget.VIDEO: _VIDEO_PRIMARY_KINDS,
        WorkflowTarget.TRANSLATE: frozenset({ArtifactKind.STANDALONE_TEXT, ArtifactKind.SOURCE_SUBTITLES}),
        WorkflowTarget.AUDIOBOOK: frozenset({ArtifactKind.STANDALONE_TEXT, ArtifactKind.SOURCE_SUBTITLES}),
        WorkflowTarget.COVER: frozenset(
            {ArtifactKind.STANDALONE_TEXT, ArtifactKind.SOURCE_SUBTITLES, ArtifactKind.SOURCE_AUDIO}
        ),
    }
)
"""Artifact kinds carrying the main content source of one execution target."""

_DERIVED_KINDS: Final[frozenset[ArtifactKind]] = frozenset(
    {
        ArtifactKind.FULL_PL,
        ArtifactKind.SPOKEN_PL,
        ArtifactKind.DISPLAYED_PL,
        ArtifactKind.TRANSLATED_TEXT,
        ArtifactKind.NARRATION_AUDIO,
        ArtifactKind.FINAL_MKV,
        ArtifactKind.FINAL_MP4,
        ArtifactKind.COVER_MP4,
    }
)
"""Artifact kinds a durable AniShift product carries, whatever place it was found in."""

_TASK_PLACES: Final[frozenset[WorkspacePlace]] = frozenset(
    {WorkspacePlace.SUBS, WorkspacePlace.TRANSLATE, WorkspacePlace.AUDIOBOOK, WorkspacePlace.COVER}
)
"""Places whose whole set is awaited, so every source there stays visible before the main one arrives."""


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


class DiscoveryIndex:
    """Apply filesystem notifications to the library's in-memory filename index."""

    def __init__(self, root: Path) -> None:
        self._root: Path = root
        self._candidates: dict[Path, ArtifactName] | None = None

    def discover(self, changed_paths: Sequence[Path] | None = None) -> DiscoveryResult:
        """Reconcile the library or inspect only paths named by filesystem notifications."""
        resolver: _RouteResolver = _RouteResolver(self._root)
        if changed_paths is None or self._candidates is None:
            candidates: dict[Path, ArtifactName] = {
                path: candidate
                for path in _iter_source_paths(self._root)
                if (candidate := classify_artifact(path, resolver.route_of(path.parent))) is not None
            }
        else:
            candidates = dict(self._candidates)
            for path in set(changed_paths):
                candidates = {known: item for known, item in candidates.items() if not known.is_relative_to(path)}
                if not self._visible(path):
                    continue
                sources: Iterator[Path] = (
                    _iter_source_paths(self._root) if path == self._root else _iter_entry_sources(path)
                )
                for source in sources:
                    if (candidate := classify_artifact(source, resolver.route_of(source.parent))) is not None:
                        candidates[source] = candidate
        self._candidates = candidates
        ordered: tuple[ArtifactName, ...] = tuple(
            candidates[path] for path in sorted(candidates, key=lambda path: _relative_sort_key(path, self._root))
        )
        return _discovered(ordered, self._root, resolver)

    def _visible(self, path: Path) -> bool:
        if not path.is_relative_to(self._root):
            return False
        relative: Path = path.relative_to(self._root)
        if relative.parts and relative.parts[0].casefold() == TEMP_DIRECTORY:
            return False
        if any(part.startswith(".") or part == ".." for part in relative.parts):
            return False
        return not any(
            _leads_elsewhere(parent) for parent in (path, *path.parents) if parent.is_relative_to(self._root)
        )


class _RouteResolver:
    """Resolve the work route of a directory once per scan, since resolving a path touches the filesystem."""

    def __init__(self, root: Path) -> None:
        self._root: Path = root.resolve()
        self._routes: dict[Path, WorkflowRoute] = {}

    def route_of(self, directory: Path) -> WorkflowRoute:
        """Return the route *directory* belongs to."""
        cached: WorkflowRoute | None = self._routes.get(directory)
        if cached is not None:
            return cached
        route: WorkflowRoute = route_within(self._root, directory.resolve())
        self._routes[directory] = route
        return route


def discover_groups(root: Path) -> DiscoveryResult:
    """Read *root* with its subfolders once and deterministically group supported artifact names."""
    paths: tuple[Path, ...] = tuple(sorted(_iter_source_paths(root), key=lambda path: _relative_sort_key(path, root)))
    resolver: _RouteResolver = _RouteResolver(root)
    candidates: tuple[ArtifactName, ...] = tuple(
        candidate
        for path in paths
        if (candidate := classify_artifact(path, resolver.route_of(path.parent))) is not None
    )
    return _discovered(candidates, root, resolver)


def _discovered(candidates: Sequence[ArtifactName], root: Path, resolver: _RouteResolver) -> DiscoveryResult:
    groups: tuple[SourceGroup, ...] = _grouped(candidates, root, resolver)
    grouped_keys: set[tuple[str, str]] = {
        (group.directory.as_posix().casefold(), group.stem.casefold()) for group in groups
    }
    warnings: tuple[DiscoveryWarning, ...] = tuple(
        DiscoveryWarning(
            kind=DiscoveryWarningKind.ORPHAN_ARTIFACT,
            message="Artifact has no main source its place accepts",
            path=candidate.path,
        )
        for candidate in candidates
        if _candidate_group_key(candidate) not in grouped_keys
    )
    return DiscoveryResult(groups=groups, ungrouped_conflicts=(), warnings=warnings)


def is_primary_source(path: Path) -> bool:
    """Return whether *path* names a main source of plain video work: MKV, MP4, or standalone TXT."""
    candidate: ArtifactName | None = classify_artifact(path)
    return candidate is not None and candidate.is_primary


def is_derived_product(path: Path) -> bool:
    """Return whether *path* follows a durable AniShift product name."""
    candidate: ArtifactName | None = classify_artifact(path)
    return candidate is not None and candidate.is_derived


def classify_artifact(path: Path, route: WorkflowRoute = ROOT_ROUTE) -> ArtifactName | None:
    """Classify one supported filename for the work *route* of its place, without touching its contents."""
    product: ProductName | None = classify_product(path.name)
    if product is not None:
        return _named_product(path, product, route)
    lowered: str = path.name.casefold()
    source_subtitle: ArtifactName | None = _classify_source_subtitle(path, lowered, route)
    if source_subtitle is not None:
        return source_subtitle
    source_image: ArtifactName | None = _classify_source_image(path, lowered, route)
    if source_image is not None:
        return source_image
    return _classify_primary_source(path, lowered, route)


def group_candidates(candidates: Sequence[ArtifactName], root: Path) -> tuple[SourceGroup, ...]:
    """Group classified names by directory and normalized stem, keying IDs on paths relative to *root*."""
    return _grouped(candidates, root, _RouteResolver(root))


def _grouped(candidates: Sequence[ArtifactName], root: Path, resolver: _RouteResolver) -> tuple[SourceGroup, ...]:
    buckets: dict[tuple[str, str], list[ArtifactName]] = {}
    for candidate in candidates:
        buckets.setdefault(_candidate_group_key(candidate), []).append(candidate)

    groups: list[SourceGroup] = []
    for key in sorted(buckets):
        bucket: tuple[ArtifactName, ...] = tuple(sorted(buckets[key], key=_candidate_sort_key))
        route: WorkflowRoute = resolver.route_of(bucket[0].path.parent)
        if not any(_anchors_group(candidate, route) for candidate in bucket):
            continue
        groups.append(_build_source_group(bucket, root, route))
    return tuple(groups)


def _iter_source_paths(root: Path) -> Iterator[Path]:
    for entry in _iter_visible_entries(root):
        if entry.name.casefold() == TEMP_DIRECTORY and entry.is_dir():
            continue
        yield from _iter_entry_sources(entry)


def _iter_entry_sources(entry: Path) -> Iterator[Path]:
    if _leads_elsewhere(entry):
        return
    if entry.is_dir():
        for child in _iter_visible_entries(entry):
            yield from _iter_entry_sources(child)
        return
    if entry.is_file():
        yield entry


def _iter_visible_entries(directory: Path) -> Iterator[Path]:
    return (entry for entry in directory.iterdir() if not entry.name.startswith("."))


def _leads_elsewhere(place: Path) -> bool:
    return place.is_symlink() or place.is_junction()


def _relative_sort_key(path: Path, root: Path) -> tuple[str, str]:
    relative: str = path.relative_to(root).as_posix()
    return relative.casefold(), relative


def _named_product(path: Path, product: ProductName, route: WorkflowRoute) -> ArtifactName | None:
    named: ArtifactName | None = _artifact_name(
        path,
        product.stem,
        _source_role(product.kind, route),
        route,
        subtitle_format=product.subtitle_format,
    )
    if named is None or product.audio_codec is None:
        return named
    return replace(named, audio_codec=product.audio_codec)


def _classify_source_subtitle(path: Path, lowered: str, route: WorkflowRoute) -> ArtifactName | None:
    for suffix, subtitle_format in SOURCE_SUBTITLE_FORMATS.items():
        if lowered.endswith(suffix):
            return _artifact_name(
                path, path.stem, ArtifactKind.SOURCE_SUBTITLES, route, subtitle_format=subtitle_format
            )
    return None


def _classify_source_image(path: Path, lowered: str, route: WorkflowRoute) -> ArtifactName | None:
    if route.target is not WorkflowTarget.COVER and route.place is not WorkspacePlace.READY:
        return None
    if not any(lowered.endswith(suffix) for suffix in _SOURCE_IMAGE_SUFFIXES):
        return None
    return _artifact_name(path, path.stem, ArtifactKind.SOURCE_IMAGE, route)


def _classify_primary_source(path: Path, lowered: str, route: WorkflowRoute) -> ArtifactName | None:
    for suffix, kind in _PRIMARY_SOURCE_KINDS.items():
        if lowered.endswith(suffix):
            return _artifact_name(path, path.stem, kind, route)
    return None


def _source_role(kind: ArtifactKind, route: WorkflowRoute) -> ArtifactKind:
    if kind is ArtifactKind.NARRATION_AUDIO and route.target is WorkflowTarget.COVER:
        return ArtifactKind.SOURCE_AUDIO
    return kind


def _primary_kinds(route: WorkflowRoute) -> frozenset[ArtifactKind]:
    if route.target is None:
        return _VIDEO_PRIMARY_KINDS
    return _PRIMARY_KINDS_BY_TARGET.get(route.target, _VIDEO_PRIMARY_KINDS)


def _anchors_group(candidate: ArtifactName, route: WorkflowRoute) -> bool:
    if candidate.kind in _primary_kinds(route):
        return True
    if route.place is WorkspacePlace.READY:
        return True
    if candidate.is_derived:
        return False
    return route.place in _TASK_PLACES


def _artifact_name(
    path: Path,
    stem: str,
    kind: ArtifactKind,
    route: WorkflowRoute,
    *,
    subtitle_format: str | None = None,
) -> ArtifactName | None:
    normalized_stem: str = stem.strip()
    if not normalized_stem:
        return None
    return ArtifactName(
        path=path,
        stem=normalized_stem,
        kind=kind,
        is_primary=kind in _primary_kinds(route),
        is_derived=kind in _DERIVED_KINDS,
        subtitle_format=subtitle_format,
    )


def _build_source_group(candidates: tuple[ArtifactName, ...], root: Path, route: WorkflowRoute) -> SourceGroup:
    first: ArtifactName = candidates[0]
    group_id: str = create_group_id(first.path.parent.relative_to(root), first.stem)
    discovered_artifacts: tuple[Artifact, ...] = tuple(_to_artifact(candidate, group_id) for candidate in candidates)
    artifacts_by_id: dict[str, Artifact] = {}
    for artifact in discovered_artifacts:
        artifacts_by_id.setdefault(artifact.artifact_id, artifact)
    return SourceGroup(
        group_id=group_id,
        stem=first.stem,
        directory=first.path.parent,
        artifacts=tuple(artifacts_by_id.values()),
        conflicts=_find_conflicts(candidates, route),
        route=route,
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


def _find_conflicts(candidates: tuple[ArtifactName, ...], route: WorkflowRoute) -> tuple[GroupConflict, ...]:
    conflicts: list[GroupConflict] = []
    main_kinds: frozenset[ArtifactKind] = _primary_kinds(route)
    primary: tuple[ArtifactName, ...] = tuple(candidate for candidate in candidates if candidate.kind in main_kinds)
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
        ArtifactKind.SOURCE_AUDIO: 4,
        ArtifactKind.SOURCE_IMAGE: 5,
    }
    format_order: int = 0 if candidate.subtitle_format == "ass" else 1
    return (
        kind_order.get(candidate.kind, 6),
        format_order,
        candidate.path.name.casefold(),
        candidate.path.name,
    )
