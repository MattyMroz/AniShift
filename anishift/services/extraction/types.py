"""Extraction domain value objects and codec helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

__all__ = [
    "ExtractionRequest",
    "ExtractionResult",
    "ExtractionTargetFormat",
    "LegacyExtractionResult",
    "MediaInfo",
    "TrackInfo",
    "TrackSelection",
    "format_extension",
    "is_text_subtitle_codec",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_CODEC_EXTENSION: Final[dict[str, str]] = {
    "A_AAC/MPEG2/*": "aac",
    "A_AAC/MPEG4/*": "aac",
    "A_AAC": "aac",
    "A_AC3": "ac3",
    "A_EAC3": "ac3",
    "A_ALAC": "caf",
    "A_DTS": "dts",
    "A_FLAC": "flac",
    "A_MPEG/L2": "mp2",
    "A_MPEG/L3": "mp3",
    "A_OPUS": "opus",
    "A_PCM/INT/LIT": "wav",
    "A_PCM/INT/BIG": "wav",
    "A_REAL/*": "rm",
    "A_TRUEHD": "truehd",
    "A_MLP": "mlp",
    "A_TTA1": "tta",
    "A_VORBIS": "ogg",
    "A_WAVPACK4": "wv",
    "S_HDMV/PGS": "sup",
    "S_HDMV/TEXTST": "txt",
    "S_KATE": "ogg",
    "S_TEXT/SSA": "ssa",
    "S_TEXT/ASS": "ass",
    "S_SSA": "ssa",
    "S_ASS": "ass",
    "S_TEXT/UTF8": "srt",
    "S_TEXT/ASCII": "srt",
    "S_VOBSUB": "sub",
    "S_TEXT/USF": "usf",
    "S_TEXT/WEBVTT": "vtt",
    "V_MPEG1": "mpeg",
    "V_MPEG2": "mpeg",
    "V_MPEG4/ISO/AVC": "h264",
    "V_MPEG4/ISO/HEVC": "h265",
    "V_MS/VFW/FOURCC": "avi",
    "V_REAL/*": "rm",
    "V_THEORA": "ogg",
    "V_VP8": "ivf",
    "V_VP9": "ivf",
}
"""Matroska codec id to output file extension (ported table)."""

_FALLBACK_EXTENSION: Final[str] = "mkv"
"""Extension for codec ids absent from the table."""

_TEXT_SUBTITLE_EXTENSIONS: Final[frozenset[str]] = frozenset({"ass", "srt", "ssa"})
"""Subtitle extensions stage 3 can actually process."""


@dataclass(frozen=True, slots=True)
class TrackInfo:
    """One track of an MKV container, as reported by ``mkvmerge -J``."""

    id: int
    type: str
    codec_id: str
    language: str
    language_ietf: str
    name: str
    default: bool
    num_entries: int | None
    forced: bool = False


@dataclass(frozen=True, slots=True)
class MediaInfo:
    """Identified MKV container.

    Attributes:
        path: The identified container.
        tracks: Tracks reported by ``mkvmerge -J``, sorted by id.
        attachments: File names of the container's attachments, fonts included.
    """

    path: Path
    tracks: tuple[TrackInfo, ...]
    attachments: tuple[str, ...] = ()
    duration_us: int = 0


@dataclass(frozen=True, slots=True)
class TrackSelection:
    """The audio and subtitle tracks chosen for the pipeline."""

    audio_id: int | None
    subtitle_id: int | None
    already_polish: bool


@dataclass(frozen=True, slots=True)
class LegacyExtractionResult:
    """Paths produced by one extraction run."""

    audio_path: Path | None
    subtitle_path: Path | None


class ExtractionTargetFormat(StrEnum):
    """Normalized output requested from one embedded media track."""

    ASS = "ass"
    SRT = "srt"
    AUDIO_COPY = "audio_copy"


@dataclass(frozen=True, slots=True)
class ExtractionRequest:
    """One embedded track extraction into an explicit run-scope path."""

    media_path: Path
    track_id: int
    target_format: ExtractionTargetFormat
    target_path: Path

    def __post_init__(self) -> None:
        if self.media_path.suffix.casefold() not in {".mkv", ".mp4"}:
            msg = "Extraction source must be MKV or MP4"
            raise ValueError(msg)
        if self.track_id < 0:
            msg = "Extraction track ID cannot be negative"
            raise ValueError(msg)
        if self.media_path == self.target_path:
            msg = "Extraction cannot overwrite its media source"
            raise ValueError(msg)
        expected_suffix: str | None = {
            ExtractionTargetFormat.ASS: ".ass",
            ExtractionTargetFormat.SRT: ".srt",
            ExtractionTargetFormat.AUDIO_COPY: None,
        }[self.target_format]
        if expected_suffix is not None and self.target_path.suffix.casefold() != expected_suffix:
            msg = f"Extraction target must use {expected_suffix} suffix"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Validated non-empty output from one neutral extraction request."""

    media_path: Path
    track_id: int
    target_format: ExtractionTargetFormat
    target_path: Path
    bytes_written: int

    def __post_init__(self) -> None:
        if self.track_id < 0 or self.bytes_written <= 0:
            msg = "Extraction result requires a valid track and non-empty output"
            raise ValueError(msg)


def format_extension(codec_id: str) -> str:
    """Return the output file extension for a Matroska codec id."""
    return _CODEC_EXTENSION.get(codec_id, _FALLBACK_EXTENSION)


def is_text_subtitle_codec(codec_id: str) -> bool:
    """Tell whether a subtitle codec is a processable text format."""
    return format_extension(codec_id) in _TEXT_SUBTITLE_EXTENSIONS
