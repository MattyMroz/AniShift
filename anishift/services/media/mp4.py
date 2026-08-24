"""MP4 identification adapter backed by FFprobe."""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from anishift.application.cancellation import CancellationToken
from anishift.platform.binaries import Binary, require_binary
from anishift.services.media._errors import invalid_probe_payload, process_probe_error
from anishift.services.media._process import ProcessExecutionError, ProcessRunner, SubprocessRunner
from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind


def identify_mp4(
    path: Path,
    *,
    cancel: CancellationToken,
    timeout_s: float,
    runner: ProcessRunner | None = None,
) -> MediaCatalog:
    """Identify one MP4 file and return neutral metadata."""
    process_runner: ProcessRunner = runner or SubprocessRunner()
    executable: Path = require_binary(Binary.FFPROBE)
    command: tuple[str, ...] = (
        str(executable),
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    )
    try:
        result = process_runner.run(command, cancel=cancel, timeout_s=timeout_s)
    except ProcessExecutionError as error:
        raise process_probe_error(path, "ffprobe", error) from error
    return parse_mp4_catalog(path, result.stdout)


def parse_mp4_catalog(path: Path, payload: str) -> MediaCatalog:
    """Parse FFprobe JSON into the neutral media catalog."""
    try:
        raw: dict[str, Any] = _object_dict(json.loads(payload), "root")
        streams_raw: list[object] = _object_list(raw.get("streams"), "streams")
        streams: list[dict[str, Any]] = [stream for stream in streams_raw if isinstance(stream, dict)]
        tracks: tuple[MediaTrack, ...] = tuple(
            mapped for stream in streams if (mapped := _map_stream(stream)) is not None
        )
        format_raw: dict[str, Any] = _object_dict(raw.get("format", {}), "format")
        duration_us: int = _catalog_duration_us(format_raw, streams)
        return MediaCatalog(
            path=path,
            container=ContainerKind.MP4,
            duration_us=duration_us,
            tracks=tuple(sorted(tracks, key=lambda track: track.track_id)),
        )
    except (json.JSONDecodeError, InvalidOperation, KeyError, TypeError, ValueError) as error:
        raise invalid_probe_payload(path, "ffprobe", error) from error


def _map_stream(stream: dict[str, Any]) -> MediaTrack | None:
    kind_value: object = stream.get("codec_type")
    if not isinstance(kind_value, str):
        return None
    try:
        kind: MediaTrackKind = MediaTrackKind(kind_value)
    except ValueError:
        return None
    track_id: int = _required_nonnegative_int(stream.get("index"), "index")
    codec_id: str = _required_text(stream.get("codec_name"), "codec_name")
    tags: dict[str, Any] = _object_dict(stream.get("tags", {}), "tags")
    disposition: dict[str, Any] = _object_dict(stream.get("disposition", {}), "disposition")
    language: str | None = _optional_text(tags.get("language"))
    name: str | None = _optional_text(tags.get("title", tags.get("handler_name")))
    subtitle_format: str | None = _subtitle_format(kind, codec_id, stream)
    return MediaTrack(
        track_id=track_id,
        kind=kind,
        codec_id=codec_id,
        language=language,
        name=name,
        is_default=bool(disposition.get("default", 0)),
        is_forced=bool(disposition.get("forced", 0)),
        subtitle_format=subtitle_format,
    )


def _subtitle_format(
    kind: MediaTrackKind,
    codec_id: str,
    stream: dict[str, Any],
) -> str | None:
    if kind is not MediaTrackKind.SUBTITLES:
        return None
    codec_tag: str | None = _optional_text(stream.get("codec_tag_string"))
    if codec_id in {"mov_text", "subrip"} or codec_tag == "tx3g":
        return "srt"
    if codec_id in {"ass", "ssa"}:
        return "ass"
    return None


def _catalog_duration_us(format_raw: dict[str, Any], streams: list[dict[str, Any]]) -> int:
    values: list[Decimal] = []
    for value in (format_raw.get("duration"), *(stream.get("duration") for stream in streams)):
        if value in {None, "N/A"}:
            continue
        parsed: Decimal = Decimal(str(value))
        if parsed.is_finite() and parsed >= 0:
            values.append(parsed)
    if not values:
        return 0
    return int((max(values) * 1_000_000).to_integral_value(rounding=ROUND_HALF_UP))


def _object_dict(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(field)
    return value


def _object_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(field)
    return value


def _required_nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(field)
    return value


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(field)
    return value.strip().casefold()


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized: str = value.strip().casefold()
    if not normalized or normalized == "und":
        return None
    return normalized
