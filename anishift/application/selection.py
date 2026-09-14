"""Pure deterministic source-selection policies shared by discovery, planning and every frontend."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactState, GroupConflictKind
from anishift.application.intents import (
    AUDIOBOOK_PRODUCTS,
    TRANSLATE_PRODUCTS,
    VIDEO_PRODUCTS,
    NarrationTimeline,
    ProductKind,
)
from anishift.application.workflows import WorkflowRoute, WorkflowTarget

if TYPE_CHECKING:
    from anishift.application.inspection import InspectedSourceGroup

# ── Constants ──────────────────────────────────────────────────────────────

_TEXT_SOURCE_KINDS: Final[frozenset[ArtifactKind]] = frozenset(
    {ArtifactKind.SOURCE_SUBTITLES, ArtifactKind.STANDALONE_TEXT},
)
"""Artifact kinds already carrying the text one group needs before any run."""

_VIDEO_KINDS: Final[frozenset[ArtifactKind]] = frozenset({ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4})
"""Container kinds a video target can read its picture from."""

_CONTENT_SOURCE_KINDS: Final[Mapping[WorkflowTarget, frozenset[ArtifactKind]]] = MappingProxyType(
    {
        WorkflowTarget.VIDEO: _TEXT_SOURCE_KINDS,
        WorkflowTarget.TRANSLATE: _TEXT_SOURCE_KINDS,
        WorkflowTarget.AUDIOBOOK: _TEXT_SOURCE_KINDS,
        WorkflowTarget.COVER: frozenset(_TEXT_SOURCE_KINDS | {ArtifactKind.SOURCE_AUDIO}),
    }
)
"""Kinds carrying the content one target reads, counted to keep an ambiguous set out of automatic work."""

_AWAITED_KINDS: Final[Mapping[WorkflowTarget, frozenset[ArtifactKind]]] = MappingProxyType(
    {
        WorkflowTarget.VIDEO: frozenset(_TEXT_SOURCE_KINDS | _VIDEO_KINDS),
        WorkflowTarget.TRANSLATE: _TEXT_SOURCE_KINDS,
        WorkflowTarget.AUDIOBOOK: _TEXT_SOURCE_KINDS,
        WorkflowTarget.COVER: frozenset(_TEXT_SOURCE_KINDS | {ArtifactKind.SOURCE_AUDIO, ArtifactKind.SOURCE_IMAGE}),
    }
)
"""Every kind one target reads, so a file still arriving is named as such instead of as a missing one."""

_CONTAINER_PRODUCTS: Final[frozenset[ProductKind]] = frozenset({ProductKind.MKV, ProductKind.MP4})
"""Products that are a film, which nothing can write without a picture to put inside them."""

_TEXT_ONLY_PRODUCTS: Final[frozenset[ProductKind]] = frozenset({ProductKind.FULL_PL})
"""The single document a plain text file can become, because it carries neither styles nor a picture."""


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


class ReadinessReason(StrEnum):
    """The one condition keeping a group out of automatic work, named for the user."""

    PLACE_STARTS_NO_WORK = "place_starts_no_work"
    SOURCE_INCOMPLETE = "source_incomplete"
    AMBIGUOUS_CONTENT_SOURCE = "ambiguous_content_source"
    SOURCE_PATH_COLLISION = "source_path_collision"
    CONTENT_SOURCE_MISSING = "content_source_missing"
    VIDEO_MISSING = "video_missing"
    SIDECAR_MISSING = "sidecar_missing"
    AMBIGUOUS_SIDECAR = "ambiguous_sidecar"
    SUBTITLE_SOURCE_MISSING = "subtitle_source_missing"
    UNSUPPORTED_SOURCE = "unsupported_source"
    IMAGE_MISSING = "image_missing"
    AMBIGUOUS_IMAGE = "ambiguous_image"


@dataclass(frozen=True, slots=True)
class GroupReadiness:
    """Whether one inspected group may be run, and the single reason it may not."""

    ready: bool
    reason: ReadinessReason | None = None

    def __post_init__(self) -> None:
        if self.ready and self.reason is not None:
            msg = "A group ready to run cannot carry a waiting reason"
            raise ValueError(msg)
        if not self.ready and self.reason is None:
            msg = "A group kept waiting must name exactly one reason"
            raise ValueError(msg)


def resolve_readiness(group: InspectedSourceGroup) -> GroupReadiness:
    """Judge one inspected group against the input its place requires, naming one stable reason."""
    route: WorkflowRoute = group.source.route
    target: WorkflowTarget | None = route.target
    if target is None:
        return GroupReadiness(ready=False, reason=ReadinessReason.PLACE_STARTS_NO_WORK)
    if group.conflicts:
        return GroupReadiness(ready=False, reason=_conflict_reason(group.conflicts[0].kind))
    if _arriving(group, _AWAITED_KINDS[target]):
        return GroupReadiness(ready=False, reason=ReadinessReason.SOURCE_INCOMPLETE)
    if target is WorkflowTarget.VIDEO:
        return _video_readiness(group, route)
    if target is WorkflowTarget.COVER:
        return _cover_readiness(group)
    return _text_readiness(group, target)


def legal_products(group: InspectedSourceGroup) -> frozenset[ProductKind]:
    """Return the products one group can really be asked for, judged by its place and the sources it holds."""
    target: WorkflowTarget | None = group.source.route.target
    if target is WorkflowTarget.AUDIOBOOK:
        return AUDIOBOOK_PRODUCTS
    if target is WorkflowTarget.TRANSLATE:
        return TRANSLATE_PRODUCTS
    if _ready_of_kinds(group, frozenset({ArtifactKind.STANDALONE_TEXT})):
        return _TEXT_ONLY_PRODUCTS
    if not _ready_of_kinds(group, _VIDEO_KINDS):
        return VIDEO_PRODUCTS - _CONTAINER_PRODUCTS
    return VIDEO_PRODUCTS


def legal_narration_timelines(group: InspectedSourceGroup) -> frozenset[NarrationTimeline]:
    """Return the readings one group can really be asked for, because only a timed script can keep its own times."""
    if group.source.route.target is not WorkflowTarget.AUDIOBOOK:
        return frozenset()
    if _ready_of_kinds(group, frozenset({ArtifactKind.STANDALONE_TEXT})):
        return frozenset({NarrationTimeline.CONTINUOUS})
    return frozenset(NarrationTimeline)


def group_is_ready(group: InspectedSourceGroup) -> bool:
    """Whether one inspected group may be run, judged by the single rule of `resolve_readiness`."""
    return resolve_readiness(group).ready


def ready_group_ids(groups: Sequence[InspectedSourceGroup]) -> tuple[str, ...]:
    """Return the ID of every group a run may take, in the order the caller listed them."""
    return tuple(group.group_id for group in groups if group_is_ready(group))


def _conflict_reason(kind: GroupConflictKind) -> ReadinessReason:
    """Name the condition one discovery conflict really is, never a source set it did not judge."""
    match kind:
        case GroupConflictKind.SOURCE_PATH_COLLISION:
            return ReadinessReason.SOURCE_PATH_COLLISION
        case GroupConflictKind.TXT_WITH_VIDEO | GroupConflictKind.AMBIGUOUS_PRIMARY:
            return ReadinessReason.AMBIGUOUS_CONTENT_SOURCE


def _video_readiness(group: InspectedSourceGroup, route: WorkflowRoute) -> GroupReadiness:
    if not _ready_of_kinds(group, _VIDEO_KINDS):
        return GroupReadiness(ready=False, reason=ReadinessReason.VIDEO_MISSING)
    sidecars: tuple[Artifact, ...] = _ready_of_kinds(group, frozenset({ArtifactKind.SOURCE_SUBTITLES}))
    if route.requires_sidecar:
        if not sidecars:
            return GroupReadiness(ready=False, reason=ReadinessReason.SIDECAR_MISSING)
        if len(sidecars) > 1:
            return GroupReadiness(ready=False, reason=ReadinessReason.AMBIGUOUS_SIDECAR)
        return GroupReadiness(ready=True)
    if not sidecars and not _has_embedded_text(group):
        return GroupReadiness(ready=False, reason=ReadinessReason.SUBTITLE_SOURCE_MISSING)
    return GroupReadiness(ready=True)


def _text_readiness(group: InspectedSourceGroup, target: WorkflowTarget) -> GroupReadiness:
    content: tuple[Artifact, ...] = _ready_of_kinds(group, _CONTENT_SOURCE_KINDS[target])
    if not content:
        return GroupReadiness(ready=False, reason=ReadinessReason.CONTENT_SOURCE_MISSING)
    if len(content) > 1:
        return GroupReadiness(ready=False, reason=ReadinessReason.AMBIGUOUS_CONTENT_SOURCE)
    if target is not WorkflowTarget.TRANSLATE and _is_ass_subtitle(content[0]):
        return GroupReadiness(ready=False, reason=ReadinessReason.UNSUPPORTED_SOURCE)
    return GroupReadiness(ready=True)


def _cover_readiness(group: InspectedSourceGroup) -> GroupReadiness:
    content: GroupReadiness = _text_readiness(group, WorkflowTarget.COVER)
    if not content.ready:
        return content
    images: tuple[Artifact, ...] = _ready_of_kinds(group, frozenset({ArtifactKind.SOURCE_IMAGE}))
    if not images:
        return GroupReadiness(ready=False, reason=ReadinessReason.IMAGE_MISSING)
    if len(images) > 1:
        return GroupReadiness(ready=False, reason=ReadinessReason.AMBIGUOUS_IMAGE)
    return GroupReadiness(ready=True)


def _ready_of_kinds(group: InspectedSourceGroup, kinds: frozenset[ArtifactKind]) -> tuple[Artifact, ...]:
    return tuple(
        artifact for artifact in group.artifacts if artifact.kind in kinds and artifact.state is ArtifactState.READY
    )


def _arriving(group: InspectedSourceGroup, kinds: frozenset[ArtifactKind]) -> bool:
    """Whether a source the target reads lies on disk unread, because a writer still holds it or nobody looked yet."""
    return any(
        artifact.kind in kinds
        and artifact.path is not None
        and artifact.state in {ArtifactState.CANDIDATE, ArtifactState.MISSING}
        for artifact in group.artifacts
    )


def _is_ass_subtitle(artifact: Artifact) -> bool:
    return artifact.kind is ArtifactKind.SOURCE_SUBTITLES and artifact.subtitle_format == "ass"


def _artifact_path_key(artifact: Artifact) -> tuple[str, str]:
    if artifact.path is None:
        return "", ""
    return artifact.path.name.casefold(), artifact.path.name


def _has_embedded_text(group: InspectedSourceGroup) -> bool:
    """Whether an identified container of the group carries a subtitle track."""
    return any(
        track.subtitle_format is not None for catalog in group.media_catalogs.values() for track in catalog.tracks
    )
