"""Source identification and validation of produced containers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Final, Never

from anishift.errors import ErrorCode, ErrorContext
from anishift.services.composition.errors import (
    CompositionProcessError,
    CompositionValidationError,
)
from anishift.services.extraction.service import identify
from anishift.services.extraction.types import MediaInfo

__all__ = [
    "audio_codec_name",
    "source_duration_us",
    "source_tracks",
    "validate_burned",
    "validate_merged",
]

# ── Constants ────────────────────────────────────────────────────────────────

_DURATION_TOLERANCE_MS: Final[int] = 2_000
"""Accepted difference between source and rendered duration."""

_PROBE_TIMEOUT_S: Final[float] = 120.0
"""Timeout for one ffprobe invocation."""

_MICROSECONDS_PER_SECOND: Final[int] = 1_000_000
"""Scale between FFprobe seconds and the microseconds used internally."""

_MICROSECONDS_PER_MILLISECOND: Final[int] = 1_000
"""Scale between microseconds and the milliseconds used in tolerances."""

_NEW_PROCESS_GROUP: Final[int] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
"""Windows flag preventing console Ctrl+C from leaking into child processes."""


def source_tracks(path: Path) -> MediaInfo:
    """Return the current track layout of one container.

    Identification runs immediately before assembling, so the result reflects
    the file on disk rather than a snapshot from an earlier stage.
    """
    return identify(path)


def audio_codec_name(path: Path, *, ffprobe: Path) -> str:
    """Return the codec name of a file's first audio stream.

    The name comes from the file that is actually mapped into the render — the
    narration sidecar when one exists — so the copy-or-transcode decision is
    never taken from a different stream.
    """
    payload: dict[str, Any] = _probe_json(
        path,
        ffprobe=ffprobe,
        arguments=("-select_streams", "a:0", "-show_entries", "stream=codec_name"),
    )
    streams: object = payload.get("streams", [])
    if not isinstance(streams, list) or not streams:
        return ""
    first: object = streams[0]
    name: object = first.get("codec_name") if isinstance(first, dict) else None
    return name if isinstance(name, str) else ""


def source_duration_us(path: Path, *, ffprobe: Path) -> int:
    """Return the container duration in microseconds."""
    payload: dict[str, Any] = _probe_json(
        path,
        ffprobe=ffprobe,
        arguments=("-show_entries", "format=duration"),
    )
    container: object = payload.get("format", {})
    raw: object = container.get("duration") if isinstance(container, dict) else None
    if not isinstance(raw, str):
        return 0
    try:
        seconds: float = float(raw)
    except ValueError:
        return 0
    return max(0, round(seconds * _MICROSECONDS_PER_SECOND))


def validate_merged(path: Path, *, expected_track_names: tuple[str, ...]) -> None:
    """Confirm a merged container carries every track this run appended.

    Track names are checked instead of counting Polish tracks: a source that
    was already Polish would satisfy a count on its own, so a merge that added
    nothing would pass unnoticed.
    """
    _require_non_empty(path)
    info: MediaInfo = identify(path)
    present: frozenset[str] = frozenset(track.name for track in info.tracks)
    missing: tuple[str, ...] = tuple(name for name in expected_track_names if name not in present)
    if missing:
        _raise_validation(
            "Merged container is missing appended tracks",
            details={"expected": len(expected_track_names), "missing": len(missing)},
        )


def validate_burned(path: Path, *, expected_duration_us: int, ffprobe: Path) -> None:
    """Confirm a rendered MP4 decodes and matches the source duration."""
    _require_non_empty(path)
    payload: dict[str, Any] = _probe_json(
        path,
        ffprobe=ffprobe,
        arguments=("-show_entries", "format=duration:stream=codec_type"),
    )
    streams: object = payload.get("streams", [])
    if not isinstance(streams, list) or not any(
        isinstance(stream, dict) and stream.get("codec_type") == "video" for stream in streams
    ):
        _raise_validation("Rendered file carries no video stream", details={})
    if expected_duration_us <= 0:
        return
    actual_us: int = source_duration_us(path, ffprobe=ffprobe)
    drift_ms: int = abs(actual_us - expected_duration_us) // _MICROSECONDS_PER_MILLISECOND
    if drift_ms > _DURATION_TOLERANCE_MS:
        _raise_validation(
            "Rendered duration does not match the source",
            details={"drift_ms": drift_ms},
        )


def _require_non_empty(path: Path) -> None:
    """Reject a result that was never written or stayed empty."""
    if not path.is_file() or path.stat().st_size == 0:
        _raise_validation("Composed file is missing or empty", details={"name": path.name})


def _probe_json(path: Path, *, ffprobe: Path, arguments: tuple[str, ...]) -> dict[str, Any]:
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
    try:
        completed: subprocess.CompletedProcess[str] = subprocess.run(  # noqa: S603 - bundled binary with typed arguments
            list(command),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PROBE_TIMEOUT_S,
            check=True,
            creationflags=_NEW_PROCESS_GROUP,
        )
    except (subprocess.SubprocessError, OSError) as error:
        _raise_probe("ffprobe failed to read the composed file", cause=error)
    try:
        payload: Any = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        _raise_probe("ffprobe returned malformed JSON", cause=error)
    return payload if isinstance(payload, dict) else {}


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
