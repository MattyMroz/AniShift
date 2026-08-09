"""Atomic publication of durable workflow artifacts."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Never

from anishift.application.artifacts import Artifact, ArtifactKind, ArtifactLifetime, ArtifactState, SourceGroup
from anishift.errors import ErrorCode, ErrorContext, ExecutionError
from anishift.platform.binaries import Binary, BinaryNotFoundError, require_binary
from anishift.services.audio.commands import SubprocessRunner
from anishift.services.audio.errors import AudioError
from anishift.services.audio.probe import probe_audio, validate_decode
from anishift.services.subtitles.errors import SubtitleError
from anishift.services.subtitles.service import load_subtitles

__all__ = ["ArtifactPublisher", "PublishRequest"]

# ── Constants ────────────────────────────────────────────────────────────────

_EXPECTED_SUFFIXES: Final[dict[ArtifactKind, frozenset[str]]] = {
    ArtifactKind.FULL_PL: frozenset({".ass", ".srt"}),
    ArtifactKind.SOURCE_SUBTITLES: frozenset({".ass", ".srt"}),
    ArtifactKind.SPOKEN_PL: frozenset({".ass", ".srt"}),
    ArtifactKind.DISPLAYED_PL: frozenset({".ass", ".srt"}),
    ArtifactKind.NARRATION_AUDIO: frozenset({".aac", ".ac3", ".eac3", ".flac", ".m4a", ".mp3", ".opus", ".wav"}),
}
"""Allowed file suffixes for durable products published by the workflow."""

_VALIDATION_TIMEOUT_S: Final[float] = 120.0
"""Maximum time for one sidecar probe or complete audio decode."""


@dataclass(frozen=True, slots=True)
class PublishRequest:
    """One validated durable artifact transfer."""

    source: Path
    target: Artifact
    source_group: SourceGroup

    def __post_init__(self) -> None:
        if self.target.state is not ArtifactState.MISSING or self.target.lifetime is not ArtifactLifetime.DURABLE:
            msg = "Publication target must be a missing durable artifact"
            raise ValueError(msg)
        if self.target.path is not None or self.target.planned_destination is None:
            msg = "Publication target must carry only its planned destination"
            raise ValueError(msg)
        if self.source == self.destination:
            msg = "Publication source and destination must differ"
            raise ValueError(msg)
        if self.target.group_id != self.source_group.group_id:
            msg = "Publication target must belong to its source group"
            raise ValueError(msg)
        if self.destination.parent != self.source_group.directory:
            msg = "Publication destination must be next to the source group"
            raise ValueError(msg)
        allowed_suffixes: frozenset[str] | None = _EXPECTED_SUFFIXES.get(self.expected_kind)
        if allowed_suffixes is None:
            msg = f"Artifact kind {self.expected_kind.value!r} is not a durable publishable product"
            raise ValueError(msg)
        if self.destination.suffix.casefold() not in allowed_suffixes:
            msg = "Publication destination suffix does not match the expected artifact kind"
            raise ValueError(msg)

    @property
    def destination(self) -> Path:
        """Return the validated durable destination."""
        destination: Path | None = self.target.planned_destination
        if destination is None:
            msg = "Publication target has no destination"
            raise ValueError(msg)
        return destination

    @property
    def expected_kind(self) -> ArtifactKind:
        """Return the artifact kind retained by publication."""
        return self.target.kind


class ArtifactPublisher:
    """Validate and atomically replace one durable product."""

    def publish(self, request: PublishRequest) -> Artifact:
        """Publish a temporary result without exposing partial destination bytes."""
        _validate_product(request.source, request.expected_kind)
        request.destination.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path = _temporary_sibling(request.destination)
        try:
            shutil.copy2(request.source, temporary)
            _validate_product(temporary, request.expected_kind)
            temporary.replace(request.destination)
        except OSError as error:
            _raise_publication_error("Artifact publication failed", cause=error)
        finally:
            temporary.unlink(missing_ok=True)
        return replace(
            request.target,
            path=request.destination,
            state=ArtifactState.READY,
        )


def _temporary_sibling(destination: Path) -> Path:
    descriptor: int
    raw_path: str
    descriptor, raw_path = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.stem}-",
        suffix=f".tmp{destination.suffix}",
    )
    os.close(descriptor)
    return Path(raw_path)


def _validate_product(path: Path, expected_kind: ArtifactKind) -> None:
    allowed_suffixes: frozenset[str] = _EXPECTED_SUFFIXES[expected_kind]
    try:
        is_valid: bool = path.is_file() and path.stat().st_size > 0
    except OSError as error:
        _raise_publication_error("Published artifact cannot be inspected", cause=error)
    if not is_valid or path.suffix.casefold() not in allowed_suffixes:
        _raise_publication_error("Published artifact is missing, empty, or has an unexpected format")
    if expected_kind is ArtifactKind.NARRATION_AUDIO:
        try:
            _validate_audio(path)
        except (AudioError, BinaryNotFoundError) as error:
            _raise_publication_error("Published audio failed content validation", cause=error)
        return
    try:
        load_subtitles(path)
    except SubtitleError as error:
        _raise_publication_error("Published subtitles failed content validation", cause=error)


def _validate_audio(path: Path) -> None:
    """Require a probed audio stream and a successful complete decode."""
    runner: SubprocessRunner = SubprocessRunner()
    ffprobe: Path = require_binary(Binary.FFPROBE)
    ffmpeg: Path = require_binary(Binary.FFMPEG)
    probe_audio(path, ffprobe=ffprobe, runner=runner, timeout_s=_VALIDATION_TIMEOUT_S)
    validate_decode(path, ffmpeg=ffmpeg, runner=runner, timeout_s=_VALIDATION_TIMEOUT_S)


def _raise_publication_error(message: str, *, cause: BaseException | None = None) -> Never:
    context: ErrorContext = ErrorContext(
        code=ErrorCode.IO_ERROR,
        message=message,
        suggestion="Check the generated product and available disk space, then run the group again.",
    )
    error: ExecutionError = ExecutionError(context=context)
    if cause is not None:
        raise error from cause
    raise error
