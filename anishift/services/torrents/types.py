"""Neutral torrent release, parsed name, and client entry contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Release:
    """One torrent entry as published by a release index."""

    title: str
    torrent_url: str
    info_hash: str
    seeders: int
    size_text: str
    published: datetime | None
    subtitle_language: str | None = None


@dataclass(frozen=True, slots=True)
class ReleaseName:
    """Fields recognized inside one release title."""

    group: str | None
    series: str
    episode: Decimal | None
    season: int | None
    resolution: int | None
    batch: bool
    version: int | None
    subtitle_language: str | None = None
    dubbed: bool = False

    @property
    def is_pack(self) -> bool:
        """Whether the release covers a whole season or an episode range instead of one episode."""
        return self.batch or (self.season is not None and self.episode is None)


@dataclass(frozen=True, slots=True)
class TorrentInfo:
    """One torrent as reported by the torrent client."""

    name: str
    info_hash: str
    progress: float
    state: str
    save_path: str
    amount_left: int | None = None
    completed: int | None = None


@dataclass(frozen=True, slots=True)
class TorrentFile:
    """Selection and completion of one path relative to the torrent save directory."""

    index: int
    name: str
    size: int
    progress: float
    priority: int

    def __post_init__(self) -> None:
        if not self.name or self.index < 0 or self.size < 0 or not 0.0 <= self.progress <= 1.0 or self.priority < 0:
            msg = "Torrent file metadata is invalid"
            raise ValueError(msg)
