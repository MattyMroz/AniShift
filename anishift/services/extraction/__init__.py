"""MKV extraction services."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from anishift.services.extraction.service import ExtractionService, extract_tracks, identify, parse_media_info

from anishift.services.extraction.errors import ExtractionError
from anishift.services.extraction.types import (
    ExtractionRequest,
    ExtractionResult,
    ExtractionTargetFormat,
    LegacyExtractionResult,
    MediaInfo,
    TrackInfo,
    TrackSelection,
    format_extension,
    is_text_subtitle_codec,
)

__all__ = [
    "ExtractionError",
    "ExtractionRequest",
    "ExtractionResult",
    "ExtractionService",
    "ExtractionTargetFormat",
    "LegacyExtractionResult",
    "MediaInfo",
    "TrackInfo",
    "TrackSelection",
    "extract_tracks",
    "format_extension",
    "identify",
    "is_text_subtitle_codec",
    "parse_media_info",
]

_LAZY_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "ExtractionService": ("anishift.services.extraction.service", "ExtractionService"),
    "extract_tracks": ("anishift.services.extraction.service", "extract_tracks"),
    "identify": ("anishift.services.extraction.service", "identify"),
    "parse_media_info": ("anishift.services.extraction.service", "parse_media_info"),
}
"""Service exports deferred to keep type-only package imports cycle-free."""


def __getattr__(name: str) -> object:
    """Resolve service facades only when a caller requests them."""
    target: tuple[str, str] | None = _LAZY_EXPORTS.get(name)
    if target is None:
        msg = f"module {__name__!r} has no attribute {name!r}"
        raise AttributeError(msg)
    module_name, attribute_name = target
    value: object = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
