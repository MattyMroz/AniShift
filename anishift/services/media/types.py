"""Neutral container and track contracts shared by MKV and MP4 adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ContainerKind(StrEnum):
    """Supported source container families."""

    MKV = "mkv"
    MP4 = "mp4"


class MediaTrackKind(StrEnum):
    """Neutral role of one stream inside a media container."""

    VIDEO = "video"
    AUDIO = "audio"
    SUBTITLES = "subtitles"


@dataclass(frozen=True, slots=True)
class MediaTrack:
    """One neutral video, audio, or subtitle stream."""

    track_id: int
    kind: MediaTrackKind
    codec_id: str
    language: str | None
    name: str | None
    is_default: bool
    is_forced: bool
    subtitle_format: str | None = None

    def __post_init__(self) -> None:
        if self.track_id < 0:
            msg = "Media track ID cannot be negative"
            raise ValueError(msg)
        if not self.codec_id.strip():
            msg = "Media track codec ID cannot be empty"
            raise ValueError(msg)
        if self.kind is not MediaTrackKind.SUBTITLES and self.subtitle_format is not None:
            msg = "Only subtitle tracks can declare a subtitle format"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class MediaCatalog:
    """Neutral identified container metadata without open resources."""

    path: Path
    container: ContainerKind
    duration_us: int
    tracks: tuple[MediaTrack, ...]
    attachments: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.duration_us < 0:
            msg = "Media duration cannot be negative"
            raise ValueError(msg)
        track_ids: tuple[int, ...] = tuple(track.track_id for track in self.tracks)
        if len(track_ids) != len(set(track_ids)):
            msg = "Media track IDs must be unique"
            raise ValueError(msg)

    def tracks_of_kind(self, kind: MediaTrackKind) -> tuple[MediaTrack, ...]:
        """Return tracks of one neutral kind in stable ID order."""
        return tuple(track for track in self.tracks if track.kind is kind)
