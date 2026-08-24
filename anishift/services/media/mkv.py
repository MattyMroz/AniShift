"""Matroska identification adapter backed by MKVToolNix."""

from __future__ import annotations

from pathlib import Path

from anishift.application.cancellation import CancellationToken
from anishift.platform.binaries import Binary, require_binary
from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.service import parse_media_info
from anishift.services.extraction.types import MediaInfo, TrackInfo, format_extension
from anishift.services.media._errors import invalid_probe_payload, process_probe_error
from anishift.services.media._process import ProcessExecutionError, ProcessRunner, SubprocessRunner
from anishift.services.media.types import ContainerKind, MediaCatalog, MediaTrack, MediaTrackKind


def identify_mkv(
    path: Path,
    *,
    cancel: CancellationToken,
    timeout_s: float,
    runner: ProcessRunner | None = None,
) -> MediaCatalog:
    """Identify one Matroska file and return neutral metadata."""
    process_runner: ProcessRunner = runner or SubprocessRunner()
    executable: Path = require_binary(Binary.MKVMERGE)
    command: tuple[str, ...] = (
        str(executable),
        "--ui-language",
        "en",
        "-J",
        str(path),
    )
    try:
        result = process_runner.run(command, cancel=cancel, timeout_s=timeout_s)
    except ProcessExecutionError as error:
        raise process_probe_error(path, "mkvmerge", error) from error
    return parse_mkv_catalog(path, result.stdout)


def parse_mkv_catalog(path: Path, payload: str) -> MediaCatalog:
    """Map existing Matroska identify JSON to the neutral catalog."""
    try:
        info: MediaInfo = parse_media_info(path, payload)
        tracks: tuple[MediaTrack, ...] = tuple(
            mapped for track in info.tracks if (mapped := _map_track(track)) is not None
        )
        return MediaCatalog(
            path=path,
            container=ContainerKind.MKV,
            duration_us=info.duration_us,
            tracks=tracks,
            attachments=info.attachments,
        )
    except (ExtractionError, TypeError, ValueError) as error:
        raise invalid_probe_payload(path, "mkvmerge", error) from error


def _map_track(track: TrackInfo) -> MediaTrack | None:
    try:
        kind: MediaTrackKind = MediaTrackKind(track.type)
    except ValueError:
        return None
    subtitle_format: str | None = None
    if kind is MediaTrackKind.SUBTITLES:
        extension: str = format_extension(track.codec_id)
        if extension in {"ass", "ssa", "srt"}:
            subtitle_format = "ass" if extension == "ssa" else extension
    return MediaTrack(
        track_id=track.id,
        kind=kind,
        codec_id=track.codec_id,
        language=_optional_text(track.language),
        name=_optional_text(track.name),
        is_default=track.default,
        is_forced=track.forced,
        subtitle_format=subtitle_format,
    )


def _optional_text(value: str) -> str | None:
    normalized: str = value.strip()
    if not normalized or normalized.casefold() == "und":
        return None
    return normalized.casefold()
