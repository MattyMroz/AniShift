"""Extraction domain errors."""

from __future__ import annotations

from anishift.errors import FatalError

__all__ = ["ExtractionError"]


class ExtractionError(FatalError):
    """Raised when identifying an MKV or extracting its tracks fails."""
