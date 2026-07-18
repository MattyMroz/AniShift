"""Subtitles domain errors."""

from __future__ import annotations

from anishift.errors import FatalError

__all__ = ["SubtitleError"]


class SubtitleError(FatalError):
    """Raised when loading, splitting or writing subtitles fails."""
