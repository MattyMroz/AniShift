"""Immutable artifact contracts shared by planning and execution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path


class ArtifactKind(StrEnum):
    """Kinds of source, intermediate, and durable workflow artifacts."""

    VIDEO_MKV = "video_mkv"
    VIDEO_MP4 = "video_mp4"
    SOURCE_SUBTITLES = "source_subtitles"
    FULL_PL = "full_pl"
    SPOKEN_PL = "spoken_pl"
    DISPLAYED_PL = "displayed_pl"
    SOURCE_AUDIO = "source_audio"
    NARRATION_AUDIO = "narration_audio"
    NORMALIZED_SUBTITLES = "normalized_subtitles"
    TTS_CLIP = "tts_clip"
    TTS_MANIFEST = "tts_manifest"
    FINAL_MKV = "final_mkv"
    FINAL_MP4 = "final_mp4"
    STANDALONE_TEXT = "standalone_text"


class ArtifactState(StrEnum):
    """Validation state of an artifact."""

    MISSING = "missing"
    CANDIDATE = "candidate"
    READY = "ready"
    INVALID = "invalid"


class ArtifactLifetime(StrEnum):
    """Ownership and cleanup lifetime of an artifact."""

    SOURCE = "source"
    INTERMEDIATE = "intermediate"
    DURABLE = "durable"


class GroupConflictKind(StrEnum):
    """Conflicts that prevent unambiguous automatic grouping."""

    TXT_WITH_VIDEO = "txt_with_video"
    SOURCE_PATH_COLLISION = "source_path_collision"
    AMBIGUOUS_PRIMARY = "ambiguous_primary"


@dataclass(frozen=True, slots=True)
class GroupConflict:
    """One deterministic conflict discovered for a source group."""

    kind: GroupConflictKind
    message: str
    paths: tuple[Path, ...]

    def __post_init__(self) -> None:
        if not self.message.strip():
            msg = "Group conflict message cannot be empty"
            raise ValueError(msg)
        if not self.paths:
            msg = "Group conflict must reference at least one path"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Artifact:
    """One immutable source, planned, or produced workflow artifact."""

    artifact_id: str
    group_id: str
    kind: ArtifactKind
    path: Path | None
    state: ArtifactState
    lifetime: ArtifactLifetime
    planned_destination: Path | None = None
    language: str | None = None
    subtitle_format: str | None = None
    audio_codec: str | None = None
    duration_us: int | None = None

    def __post_init__(self) -> None:
        if not self.artifact_id.strip() or not self.group_id.strip():
            msg = "Artifact and group IDs cannot be empty"
            raise ValueError(msg)
        if self.kind in {ArtifactKind.FINAL_MKV, ArtifactKind.FINAL_MP4} and (
            self.lifetime is not ArtifactLifetime.DURABLE
        ):
            msg = "Final containers must be durable products, never sources"
            raise ValueError(msg)
        if self.state is not ArtifactState.MISSING and self.path is None:
            msg = f"Artifact in state {self.state.value!r} requires a runtime path"
            raise ValueError(msg)
        if self.duration_us is not None and self.duration_us < 0:
            msg = "Artifact duration cannot be negative"
            raise ValueError(msg)
        self._validate_lifetime()

    def _validate_lifetime(self) -> None:
        if self.lifetime is ArtifactLifetime.SOURCE:
            if self.path is None or self.planned_destination != self.path:
                msg = "Source artifact destination must equal its runtime path"
                raise ValueError(msg)
            return
        if self.lifetime is ArtifactLifetime.INTERMEDIATE:
            if self.planned_destination is not None:
                msg = "Intermediate artifact cannot have a durable destination"
                raise ValueError(msg)
            return
        if self.planned_destination is None:
            msg = "Durable artifact requires a planned destination"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class SourceGroup:
    """All source candidates and conflicts sharing one normalized stem."""

    group_id: str
    stem: str
    directory: Path
    artifacts: tuple[Artifact, ...]
    conflicts: tuple[GroupConflict, ...] = ()

    def __post_init__(self) -> None:
        if not self.group_id.strip() or not self.stem.strip():
            msg = "Source group ID and stem cannot be empty"
            raise ValueError(msg)
        if any(artifact.group_id != self.group_id for artifact in self.artifacts):
            msg = "Every artifact must belong to its source group"
            raise ValueError(msg)
        artifact_ids: tuple[str, ...] = tuple(artifact.artifact_id for artifact in self.artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            msg = "Artifact IDs must be unique within a source group"
            raise ValueError(msg)

    def artifacts_of_kind(self, kind: ArtifactKind) -> tuple[Artifact, ...]:
        """Return artifacts of *kind* without applying an input policy."""
        return tuple(artifact for artifact in self.artifacts if artifact.kind is kind)

    def ready_artifacts_of_kind(self, kind: ArtifactKind) -> tuple[Artifact, ...]:
        """Return validated artifacts of *kind* without performing I/O."""
        return tuple(
            artifact for artifact in self.artifacts if artifact.kind is kind and artifact.state is ArtifactState.READY
        )


def create_group_id(relative_directory: Path, stem: str) -> str:
    """Create a stable group ID from a workspace-relative directory and stem."""
    normalized_directory: str = _normalize_relative_path(relative_directory)
    normalized_stem: str = stem.strip().casefold()
    if not normalized_stem:
        msg = "Group stem cannot be empty"
        raise ValueError(msg)
    digest: str = sha256(f"{normalized_directory}/{normalized_stem}".encode()).hexdigest()
    return f"group-{digest[:16]}"


def create_artifact_id(
    group_id: str,
    kind: ArtifactKind,
    relative_path: Path | None = None,
    *,
    variant: str | None = None,
) -> str:
    """Create a stable artifact ID from a source path or planned semantic variant."""
    normalized_group_id: str = group_id.strip()
    if not normalized_group_id:
        msg = "Group ID cannot be empty"
        raise ValueError(msg)
    normalized_path: str = "planned"
    if relative_path is not None:
        normalized_path = _normalize_relative_path(relative_path)
    normalized_variant: str = ""
    if variant is not None:
        normalized_variant = variant.strip().casefold()
        if not normalized_variant:
            msg = "Artifact variant cannot be blank"
            raise ValueError(msg)
    identity: str = f"{normalized_group_id}:{kind.value}:{normalized_path}:{normalized_variant}"
    digest: str = sha256(identity.encode()).hexdigest()
    return f"artifact-{digest[:20]}"


def _normalize_relative_path(path: Path) -> str:
    if path.is_absolute() or ".." in path.parts:
        msg = "Artifact identity requires a workspace-relative path"
        raise ValueError(msg)
    normalized_parts: tuple[str, ...] = tuple(part.casefold() for part in path.parts if part not in {"", "."})
    return "/".join(normalized_parts) or "."
