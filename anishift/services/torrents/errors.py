"""Torrents domain exception hierarchy."""

from __future__ import annotations

from anishift.errors import AniShiftError, TransientError

__all__ = ["TorrentClientError", "TorrentError", "TorrentSourceError"]


class TorrentError(AniShiftError):
    """Base class for every torrents-domain failure."""


class TorrentSourceError(TorrentError, TransientError):
    """Raised when a release index cannot be reached or returns an unusable feed."""


class TorrentClientError(TorrentError):
    """Raised when the torrent client is unreachable, rejects auth, or refuses a request."""
