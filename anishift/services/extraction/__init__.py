"""MKV extraction services."""

from __future__ import annotations

from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.service import extract_tracks, identify, parse_media_info
from anishift.services.extraction.types import (
    ExtractionResult,
    MediaInfo,
    TrackInfo,
    TrackSelection,
    format_extension,
    is_text_subtitle_codec,
)

__all__ = [
    "ExtractionError",
    "ExtractionResult",
    "MediaInfo",
    "TrackInfo",
    "TrackSelection",
    "extract_tracks",
    "format_extension",
    "identify",
    "is_text_subtitle_codec",
    "parse_media_info",
]
