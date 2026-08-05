"""Typed failures raised by the composition domain."""

from __future__ import annotations

from anishift.errors import AniShiftError, FatalError

__all__ = [
    "CompositionCancelledError",
    "CompositionConfigError",
    "CompositionError",
    "CompositionProcessError",
    "CompositionValidationError",
]


class CompositionError(AniShiftError):
    """Base error for muxing, rendering, and result placement."""


class CompositionConfigError(CompositionError, FatalError):
    """Composition settings or binaries cannot produce a result."""


class CompositionProcessError(CompositionError, FatalError):
    """An mkvmerge or FFmpeg subprocess failed."""


class CompositionValidationError(CompositionError, FatalError):
    """A produced file failed its post-run validation."""


class CompositionCancelledError(CompositionError, FatalError):
    """Composition stopped because cancellation was requested."""
