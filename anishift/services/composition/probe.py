"""Source identification and validation of produced containers."""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path
from typing import Any, Final, Never

from anishift.application.cancellation import (
    CancellationToken,
    NeverCancelledToken,
    ThreadEventCancellationToken,
)
from anishift.errors import ErrorCode, ErrorContext, MediaProbeError
from anishift.services.composition.errors import (
    CompositionCancelledError,
    CompositionProcessError,
    CompositionValidationError,
)
from anishift.services.media import DefaultMediaProbe, MediaCatalog
from anishift.services.media._process import (
    ProcessExecutionError,
    ProcessFailureReason,
    ProcessRunner,
    SubprocessRunner,
)

__all__ = [
    "audio_codec_name",
    "source_duration_us",
    "source_tracks",
    "validate_burned",
    "validate_merged",
]

# ── Constants ────────────────────────────────────────────────────────────────

_DURATION_TOLERANCE_MS: Final[int] = 2_000
"""Accepted difference between expected and rendered product duration."""

_PROBE_TIMEOUT_S: Final[float] = 120.0
"""Timeout for one ffprobe invocation."""

_MICROSECONDS_PER_SECOND: Final[int] = 1_000_000
"""Scale between FFprobe seconds and the microseconds used internally."""

_MICROSECONDS_PER_MILLISECOND: Final[int] = 1_000
"""Scale between microseconds and the milliseconds used in tolerances."""


def source_tracks(
    path: Path,
    *,
    cancel: threading.Event | None = None,
    runner: ProcessRunner | None = None,
) -> MediaCatalog:
    """Return the current track layout of one container."""
    try:
        return DefaultMediaProbe(runner=runner).identify(
            path,
            cancel=_cancellation_token(cancel),
            timeout_s=_PROBE_TIMEOUT_S,
        )
    except MediaProbeError as error:
        if error.context.code is ErrorCode.CANCELLED:
            raise CompositionCancelledError(context=error.context) from error
        raise CompositionProcessError(context=error.context) from error


def audio_codec_name(
    path: Path,
    *,
    ffprobe: Path,
    cancel: threading.Event | None = None,
    runner: ProcessRunner | None = None,
) -> str:
    """Return the codec name of a file's first audio stream."""
    payload: dict[str, Any] = _probe_json(
        path,
        ffprobe=ffprobe,
        arguments=("-select_streams", "a:0", "-show_entries", "stream=codec_name"),
        cancel=cancel,
        runner=runner,
    )
    streams: object = payload.get("streams", [])
    if not isinstance(streams, list) or not streams:
        return ""
    first: object = streams[0]
    name: object = first.get("codec_name") if isinstance(first, dict) else None
    return name if isinstance(name, str) else ""


def source_duration_us(
    path: Path,
    *,
    ffprobe: Path,
    video_only: bool = False,
    cancel: threading.Event | None = None,
    runner: ProcessRunner | None = None,
) -> int:
    """Return container or video duration in microseconds, including Matroska tags."""
    arguments: tuple[str, ...] = (
        ("-select_streams", "v:0", "-show_entries", "format=duration:stream=duration:stream_tags=DURATION")
        if video_only
        else ("-show_entries", "format=duration")
    )
    payload: dict[str, Any] = _probe_json(
        path,
        ffprobe=ffprobe,
        arguments=arguments,
        cancel=cancel,
        runner=runner,
    )
    return _first_stream_duration_us(payload) if video_only else _container_duration_us(payload)


def _container_duration_us(payload: dict[str, Any]) -> int:
    """Read the container-level duration from one probe result."""
    container: object = payload.get("format", {})
    return _duration_us(container.get("duration")) if isinstance(container, dict) else 0


def _first_stream_duration_us(payload: dict[str, Any]) -> int:
    """Read the selected stream duration or its Matroska duration tag."""
    streams: object = payload.get("streams")
    if not isinstance(streams, list) or not streams or not isinstance(streams[0], dict):
        return 0
    stream: dict[str, Any] = streams[0]
    duration_us: int
    if (duration_us := _duration_us(stream.get("duration"))) > 0:
        return duration_us
    tags: object = stream.get("tags")
    return _duration_us(tags.get("DURATION")) if isinstance(tags, dict) else 0


def _duration_us(raw: object) -> int:
    """Convert finite seconds or an HH:MM:SS timestamp to microseconds."""
    if not isinstance(raw, str):
        return 0
    try:
        parts: list[float] = [float(part) for part in raw.split(":")]
    except ValueError:
        return 0
    if len(parts) not in {1, 3} or not all(math.isfinite(part) and part >= 0 for part in parts):
        return 0
    seconds: float = sum(part * 60**index for index, part in enumerate(reversed(parts)))
    microseconds: float = seconds * _MICROSECONDS_PER_SECOND
    return round(microseconds) if math.isfinite(microseconds) else 0


def validate_merged(
    path: Path,
    *,
    expected_track_names: tuple[str, ...],
    cancel: threading.Event | None = None,
    runner: ProcessRunner | None = None,
) -> None:
    """Confirm a merged container carries every track this run appended."""
    _require_non_empty(path)
    info: MediaCatalog = source_tracks(path, cancel=cancel, runner=runner)
    present: frozenset[str] = frozenset(track.name.casefold() for track in info.tracks if track.name is not None)
    missing: tuple[str, ...] = tuple(name for name in expected_track_names if name.casefold() not in present)
    if missing:
        _raise_validation(
            "Merged container is missing appended tracks",
            details={"expected": len(expected_track_names), "missing": len(missing)},
        )


def validate_burned(  # noqa: PLR0913 - separate stream and product duration contracts
    path: Path,
    *,
    expected_duration_us: int,
    ffprobe: Path,
    expected_video_duration_us: int = 0,
    cancel: threading.Event | None = None,
    runner: ProcessRunner | None = None,
) -> None:
    """Confirm a rendered MP4 preserves video and its expected product duration."""
    _require_non_empty(path)
    payload: dict[str, Any] = _probe_json(
        path,
        ffprobe=ffprobe,
        arguments=("-select_streams", "v:0", "-show_entries", "format=duration:stream=codec_type,duration"),
        cancel=cancel,
        runner=runner,
    )
    streams: object = payload.get("streams", [])
    if not isinstance(streams, list) or not any(
        isinstance(stream, dict) and stream.get("codec_type") == "video" for stream in streams
    ):
        _raise_validation("Rendered file carries no video stream", details={})
    for subject, actual_us, expected_us in (
        ("product", _container_duration_us(payload), expected_duration_us),
        ("video", _first_stream_duration_us(payload), expected_video_duration_us),
    ):
        if expected_us <= 0:
            continue
        drift_ms: int = abs(actual_us - expected_us) // _MICROSECONDS_PER_MILLISECOND
        if drift_ms > _DURATION_TOLERANCE_MS:
            _raise_validation(
                f"Rendered duration does not match the expected {subject}",
                details={"drift_ms": drift_ms},
            )


def _require_non_empty(path: Path) -> None:
    """Reject a result that was never written or stayed empty."""
    if not path.is_file() or path.stat().st_size == 0:
        _raise_validation("Composed file is missing or empty", details={"name": path.name})


def _probe_json(
    path: Path,
    *,
    ffprobe: Path,
    arguments: tuple[str, ...],
    cancel: threading.Event | None,
    runner: ProcessRunner | None,
) -> dict[str, Any]:
    """Return one ffprobe JSON payload, or raise a typed process failure."""
    command: tuple[str, ...] = (
        str(ffprobe),
        "-v",
        "error",
        "-of",
        "json",
        *arguments,
        str(path),
    )
    process_runner: ProcessRunner = runner or SubprocessRunner()
    try:
        completed = process_runner.run(
            command,
            cancel=_cancellation_token(cancel),
            timeout_s=_PROBE_TIMEOUT_S,
        )
    except ProcessExecutionError as error:
        if error.reason is ProcessFailureReason.CANCELLED:
            context = ErrorContext(code=ErrorCode.CANCELLED, message="Composition probe was cancelled")
            raise CompositionCancelledError(context=context) from error
        _raise_probe("ffprobe failed to read the composed file", cause=error)
    try:
        payload: Any = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        _raise_probe("ffprobe returned malformed JSON", cause=error)
    return payload if isinstance(payload, dict) else {}


def _cancellation_token(cancel: threading.Event | None) -> CancellationToken:
    if cancel is None:
        return NeverCancelledToken()
    return ThreadEventCancellationToken(cancel)


def _raise_probe(message: str, *, cause: Exception) -> Never:
    """Raise a typed process failure for an unusable ffprobe run."""
    context: ErrorContext = ErrorContext(
        code=ErrorCode.COMPOSITION_FAILED,
        message=message,
        suggestion="Check the produced file and the bundled FFprobe binary.",
        details={"operation": "composition_probe"},
    )
    raise CompositionProcessError(context=context) from cause


def _raise_validation(message: str, *, details: dict[str, Any]) -> Never:
    """Raise a typed validation failure for a result that was not published."""
    context: ErrorContext = ErrorContext(
        code=ErrorCode.COMPOSITION_FAILED,
        message=message,
        suggestion="Re-run composition; the previous result was not published.",
        details={"operation": "composition_validation", **details},
    )
    raise CompositionValidationError(context=context)
