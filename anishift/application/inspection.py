"""Workspace inspection through media probing and complete artifact validation."""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Final

from anishift.application.artifacts import (
    Artifact,
    ArtifactKind,
    ArtifactLifetime,
    ArtifactState,
    GroupConflict,
    SourceGroup,
    create_artifact_id,
)
from anishift.application.cancellation import CancellationToken
from anishift.application.discovery import DiscoveryResult
from anishift.application.intents import ExternalAudioRole
from anishift.application.planning import DEFAULT_AUDIO_TOLERANCE_US
from anishift.application.selection import choose_primary_video
from anishift.errors import ErrorCode, ErrorContext, ExecutionError, MediaProbeError
from anishift.platform.binaries import Binary, require_binary
from anishift.services.media._process import (
    ProcessExecutionError,
    ProcessFailureReason,
    ProcessRunner,
    SubprocessRunner,
)
from anishift.services.media.probe import MediaProbe
from anishift.services.media.types import MediaCatalog
from anishift.services.subtitles.errors import SubtitleError
from anishift.services.subtitles.service import load_subtitles

_DEFAULT_PROBE_TIMEOUT_SECONDS: Final[float] = 120.0
"""Default upper bound for one media or audio inspection subprocess."""


_MAX_INSPECTION_WORKERS: Final[int] = 8
"""Upper bound on groups probed at once, because probing waits on subprocesses."""


@dataclass(frozen=True, slots=True)
class InspectionWarning:
    """One invalid artifact retained for user-visible manual diagnostics."""

    code: str
    message: str
    group_id: str
    artifact_id: str


@dataclass(frozen=True, slots=True)
class InspectedSourceGroup:
    """A discovery group enriched with validated artifacts and media catalogs."""

    source: SourceGroup
    artifacts: tuple[Artifact, ...]
    media_catalogs: Mapping[str, MediaCatalog]
    conflicts: tuple[GroupConflict, ...]

    def __post_init__(self) -> None:
        artifact_ids: tuple[str, ...] = tuple(artifact.artifact_id for artifact in self.artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            msg = "Inspected artifact IDs must be unique"
            raise ValueError(msg)
        if any(artifact.group_id != self.source.group_id for artifact in self.artifacts):
            msg = "Inspected artifacts must belong to their source group"
            raise ValueError(msg)
        catalogs: dict[str, MediaCatalog] = dict(self.media_catalogs)
        if any(artifact_id not in artifact_ids for artifact_id in catalogs):
            msg = "Media catalog must reference an inspected artifact"
            raise ValueError(msg)
        object.__setattr__(self, "media_catalogs", MappingProxyType(catalogs))

    @property
    def group_id(self) -> str:
        """Return the stable ID of the underlying source group."""
        return self.source.group_id


@dataclass(frozen=True, slots=True)
class InspectedWorkspace:
    """Immutable validated input passed to the product planner."""

    groups: tuple[InspectedSourceGroup, ...]
    warnings: tuple[InspectionWarning, ...]


class WorkspaceInspector:
    """Validate discovery results without mutating their source artifacts."""

    def __init__(
        self,
        probe: MediaProbe,
        *,
        runner: ProcessRunner | None = None,
        ffmpeg: Path | None = None,
        timeout_s: float = _DEFAULT_PROBE_TIMEOUT_SECONDS,
        audio_tolerance_us: int = DEFAULT_AUDIO_TOLERANCE_US,
    ) -> None:
        if timeout_s <= 0 or audio_tolerance_us < 0:
            msg = "Inspection timeout must be positive and audio tolerance non-negative"
            raise ValueError(msg)
        self._probe: MediaProbe = probe
        self._runner: ProcessRunner = runner or SubprocessRunner()
        self._ffmpeg: Path | None = ffmpeg
        self._timeout_s: float = timeout_s
        self._audio_tolerance_us: int = audio_tolerance_us

    def inspect(
        self,
        discovery: DiscoveryResult,
        *,
        cancel: CancellationToken,
    ) -> InspectedWorkspace:
        """Probe containers and validate local artifact contents group by group."""
        cancel.raise_if_cancelled()
        sources: tuple[SourceGroup, ...] = discovery.groups
        if not sources:
            return InspectedWorkspace(groups=(), warnings=())
        with ThreadPoolExecutor(
            max_workers=min(len(sources), _MAX_INSPECTION_WORKERS),
            thread_name_prefix="anishift-inspect",
        ) as pool:
            inspected: tuple[tuple[InspectedSourceGroup, tuple[InspectionWarning, ...]], ...] = tuple(
                pool.map(lambda source: self._inspect_group(source, cancel=cancel), sources)
            )
        return InspectedWorkspace(
            groups=tuple(group for group, _ in inspected),
            warnings=tuple(warning for _, group_warnings in inspected for warning in group_warnings),
        )

    def register_external_subtitle(
        self,
        group: InspectedSourceGroup,
        path: Path,
        *,
        declared_language: str | None,
        cancel: CancellationToken,
    ) -> InspectedSourceGroup:
        """Validate and register one manual ASS or SRT source outside discovery."""
        cancel.raise_if_cancelled()
        subtitle_format: str = path.suffix.casefold().removeprefix(".")
        if subtitle_format not in {"ass", "srt"}:
            msg = "External subtitles must use ASS or SRT format"
            raise ExecutionError(msg)
        language: str | None = _declared_language(declared_language)
        self._require_valid_subtitles(path, cancel=cancel)
        artifact: Artifact = Artifact(
            artifact_id=_external_artifact_id(group.group_id, ArtifactKind.SOURCE_SUBTITLES, path),
            group_id=group.group_id,
            kind=ArtifactKind.SOURCE_SUBTITLES,
            path=path,
            state=ArtifactState.READY,
            lifetime=ArtifactLifetime.SOURCE,
            planned_destination=path,
            language=language,
            subtitle_format=subtitle_format,
        )
        return _append_external_artifact(group, artifact)

    def register_external_audio(
        self,
        group: InspectedSourceGroup,
        path: Path,
        *,
        role: ExternalAudioRole,
        cancel: CancellationToken,
    ) -> InspectedSourceGroup:
        """Fully decode and register one manual audio source with duration parity."""
        cancel.raise_if_cancelled()
        duration_us: int = self._decode_audio_duration(path, cancel=cancel)
        video_duration_us: int = _primary_video_duration(group)
        if abs(duration_us - video_duration_us) > self._audio_tolerance_us:
            msg = "External audio duration differs from the selected video beyond tolerance"
            raise ExecutionError(msg)
        kind: ArtifactKind = (
            ArtifactKind.SOURCE_AUDIO if role is ExternalAudioRole.SOURCE_AUDIO else ArtifactKind.NARRATION_AUDIO
        )
        artifact: Artifact = Artifact(
            artifact_id=_external_artifact_id(group.group_id, kind, path),
            group_id=group.group_id,
            kind=kind,
            path=path,
            state=ArtifactState.READY,
            lifetime=ArtifactLifetime.SOURCE,
            planned_destination=path,
            audio_codec=None,
            duration_us=duration_us,
        )
        return _append_external_artifact(group, artifact)

    def _inspect_group(
        self,
        source: SourceGroup,
        *,
        cancel: CancellationToken,
    ) -> tuple[InspectedSourceGroup, tuple[InspectionWarning, ...]]:
        cancel.raise_if_cancelled()
        catalogs: dict[str, MediaCatalog] = {}
        artifacts: list[Artifact] = []
        warnings: list[InspectionWarning] = []
        for artifact in source.artifacts:
            if artifact.kind in {ArtifactKind.VIDEO_MKV, ArtifactKind.VIDEO_MP4}:
                inspected, catalog, warning = self._inspect_video(artifact, cancel=cancel)
                artifacts.append(inspected)
                if catalog is not None:
                    catalogs[artifact.artifact_id] = catalog
                if warning is not None:
                    warnings.append(warning)
                continue
            artifacts.append(artifact)

        enriched: list[Artifact] = []
        for artifact in artifacts:
            inspected, warning = self._inspect_non_video(
                artifact,
                catalogs=catalogs,
                cancel=cancel,
            )
            enriched.append(inspected)
            if warning is not None:
                warnings.append(warning)
        return (
            InspectedSourceGroup(
                source=source,
                artifacts=tuple(enriched),
                media_catalogs=catalogs,
                conflicts=source.conflicts,
            ),
            tuple(warnings),
        )

    def _inspect_video(
        self,
        artifact: Artifact,
        *,
        cancel: CancellationToken,
    ) -> tuple[Artifact, MediaCatalog | None, InspectionWarning | None]:
        if artifact.path is None:
            return self._invalid(artifact, "media_missing", "Media source has no path")
        try:
            catalog: MediaCatalog = self._probe.identify(
                artifact.path,
                cancel=cancel,
                timeout_s=self._timeout_s,
            )
        except MediaProbeError as error:
            if error.context.code is ErrorCode.CANCELLED:
                raise
            invalid, _, warning = self._invalid(
                artifact,
                "media_invalid",
                "Media source could not be identified",
            )
            return invalid, None, warning
        return replace(artifact, state=ArtifactState.READY, duration_us=catalog.duration_us), catalog, None

    def _inspect_non_video(
        self,
        artifact: Artifact,
        *,
        catalogs: Mapping[str, MediaCatalog],
        cancel: CancellationToken,
    ) -> tuple[Artifact, InspectionWarning | None]:
        if artifact.kind in {
            ArtifactKind.SOURCE_SUBTITLES,
            ArtifactKind.FULL_PL,
            ArtifactKind.SPOKEN_PL,
            ArtifactKind.DISPLAYED_PL,
        }:
            return self._inspect_subtitles(artifact, cancel=cancel)
        if artifact.kind is ArtifactKind.STANDALONE_TEXT:
            return self._inspect_text(artifact, cancel=cancel)
        if artifact.kind is ArtifactKind.NARRATION_AUDIO:
            return self._inspect_audio(artifact, catalogs=catalogs, cancel=cancel)
        return artifact, None

    def _inspect_subtitles(
        self,
        artifact: Artifact,
        *,
        cancel: CancellationToken,
    ) -> tuple[Artifact, InspectionWarning | None]:
        if artifact.path is None:
            invalid, _, warning = self._invalid(artifact, "subtitle_missing", "Subtitle has no path")
            return invalid, warning
        try:
            self._require_valid_subtitles(artifact.path, cancel=cancel)
        except ExecutionError as error:
            if error.context.code is ErrorCode.CANCELLED:
                raise
            invalid, _, warning = self._invalid(
                artifact,
                "subtitle_invalid",
                "Subtitle file is empty or invalid",
            )
            return invalid, warning
        language: str | None = artifact.language
        if artifact.kind in {ArtifactKind.FULL_PL, ArtifactKind.SPOKEN_PL, ArtifactKind.DISPLAYED_PL}:
            language = "pol"
        return replace(artifact, state=ArtifactState.READY, language=language), None

    def _inspect_text(
        self,
        artifact: Artifact,
        *,
        cancel: CancellationToken,
    ) -> tuple[Artifact, InspectionWarning | None]:
        cancel.raise_if_cancelled()
        try:
            content: str = "" if artifact.path is None else artifact.path.read_text(encoding="utf-8")
        except OSError, UnicodeError:
            content = ""
        if not content.strip():
            invalid, _, warning = self._invalid(artifact, "text_invalid", "TXT source is empty or invalid")
            return invalid, warning
        return replace(artifact, state=ArtifactState.READY), None

    def _inspect_audio(
        self,
        artifact: Artifact,
        *,
        catalogs: Mapping[str, MediaCatalog],
        cancel: CancellationToken,
    ) -> tuple[Artifact, InspectionWarning | None]:
        if artifact.path is None:
            invalid, _, warning = self._invalid(artifact, "audio_missing", "Audio has no path")
            return invalid, warning
        try:
            duration_us: int = self._decode_audio_duration(artifact.path, cancel=cancel)
            video_duration_us: int = _catalog_video_duration(catalogs)
        except ExecutionError as error:
            if error.context.code is ErrorCode.CANCELLED:
                raise
            invalid, _, warning = self._invalid(
                artifact,
                "audio_invalid",
                "Audio failed full decode or duration validation",
            )
            return invalid, warning
        if abs(duration_us - video_duration_us) > self._audio_tolerance_us:
            invalid, _, warning = self._invalid(
                artifact,
                "audio_duration_mismatch",
                "Audio duration differs from video beyond tolerance",
            )
            return invalid, warning
        return replace(artifact, state=ArtifactState.READY, duration_us=duration_us), None

    def _require_valid_subtitles(self, path: Path, *, cancel: CancellationToken) -> None:
        cancel.raise_if_cancelled()
        try:
            subtitles = load_subtitles(path)
        except SubtitleError as error:
            msg = "Subtitle validation failed"
            raise _inspection_error(msg) from error
        cancel.raise_if_cancelled()
        if not subtitles.events:
            msg = "Subtitle file contains no events"
            raise _inspection_error(msg)

    def _decode_audio_duration(self, path: Path, *, cancel: CancellationToken) -> int:
        if not path.is_file() or path.stat().st_size == 0:
            msg = "Audio input is missing or empty"
            raise _inspection_error(msg, code=ErrorCode.AUDIO_FAILED)
        executable: Path = self._ffmpeg or require_binary(Binary.FFMPEG)
        command: tuple[str, ...] = (
            str(executable),
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-vn",
            "-sn",
            "-dn",
            "-progress",
            "pipe:1",
            "-nostats",
            "-f",
            "null",
            "-",
        )
        try:
            result = self._runner.run(command, cancel=cancel, timeout_s=self._timeout_s)
        except ProcessExecutionError as error:
            raise _audio_execution_error(error) from error
        return _completed_duration_us(result.stdout)

    def _invalid(
        self,
        artifact: Artifact,
        code: str,
        message: str,
    ) -> tuple[Artifact, None, InspectionWarning]:
        invalid: Artifact = replace(artifact, state=ArtifactState.INVALID)
        return (
            invalid,
            None,
            InspectionWarning(
                code=code,
                message=message,
                group_id=artifact.group_id,
                artifact_id=artifact.artifact_id,
            ),
        )


def _append_external_artifact(group: InspectedSourceGroup, artifact: Artifact) -> InspectedSourceGroup:
    if any(existing.artifact_id == artifact.artifact_id for existing in group.artifacts):
        msg = "External artifact is already registered for this group"
        raise ExecutionError(msg)
    return replace(group, artifacts=(*group.artifacts, artifact))


def _external_artifact_id(group_id: str, kind: ArtifactKind, path: Path) -> str:
    normalized_external_path: str = path.resolve().as_posix().casefold()
    return create_artifact_id(
        group_id,
        kind,
        Path(path.name),
        variant=f"external:{normalized_external_path}",
    )


def _declared_language(language: str | None) -> str | None:
    if language is None:
        return None
    normalized: str = language.strip().casefold()
    if not normalized or normalized == "und":
        msg = "Declared subtitle language cannot be blank or undefined"
        raise ExecutionError(msg)
    return normalized


def _primary_video_duration(group: InspectedSourceGroup) -> int:
    primary: Artifact | None = choose_primary_video(group.artifacts)
    if primary is None:
        msg = "External audio requires a valid video source"
        raise _inspection_error(msg)
    catalog: MediaCatalog | None = group.media_catalogs.get(primary.artifact_id)
    if catalog is None or catalog.duration_us <= 0:
        msg = "External audio requires known video duration"
        raise _inspection_error(msg)
    return catalog.duration_us


def _catalog_video_duration(catalogs: Mapping[str, MediaCatalog]) -> int:
    durations: tuple[int, ...] = tuple(catalog.duration_us for catalog in catalogs.values() if catalog.duration_us > 0)
    if not durations:
        msg = "Audio validation requires known video duration"
        raise _inspection_error(msg)
    return durations[0]


def _completed_duration_us(progress: str) -> int:
    values: dict[str, str] = {}
    for raw_line in progress.splitlines():
        key, separator, value = raw_line.partition("=")
        if separator:
            values[key] = value
    if values.get("progress") != "end":
        msg = "Audio decode did not complete"
        raise _inspection_error(msg, code=ErrorCode.AUDIO_FAILED)
    try:
        duration: Decimal = Decimal(values["out_time_us"])
    except (KeyError, InvalidOperation) as error:
        msg = "Audio decode returned invalid duration"
        raise _inspection_error(msg, code=ErrorCode.AUDIO_FAILED) from error
    if not duration.is_finite() or duration <= 0:
        msg = "Audio decode returned invalid duration"
        raise _inspection_error(msg, code=ErrorCode.AUDIO_FAILED)
    return int(duration)


def _audio_execution_error(error: ProcessExecutionError) -> ExecutionError:
    code_by_reason: dict[ProcessFailureReason, ErrorCode] = {
        ProcessFailureReason.START_FAILED: ErrorCode.IO_ERROR,
        ProcessFailureReason.CANCELLED: ErrorCode.CANCELLED,
        ProcessFailureReason.TIMED_OUT: ErrorCode.TIMEOUT,
        ProcessFailureReason.NONZERO_EXIT: ErrorCode.AUDIO_FAILED,
    }
    return ExecutionError(
        context=ErrorContext(
            code=code_by_reason[error.reason],
            message="External audio failed complete decode validation",
            suggestion="Choose a complete audio file matching the video duration.",
            details={"operation": "external_audio_decode", "reason": error.reason.value},
        )
    )


def _inspection_error(message: str, *, code: ErrorCode = ErrorCode.UNKNOWN) -> ExecutionError:
    return ExecutionError(
        context=ErrorContext(
            code=code,
            message=message,
            suggestion="Choose a complete supported artifact and try again.",
            details={"operation": "workspace_inspection"},
        )
    )
