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


@dataclass(frozen=True, slots=True)
class TorrentInfo:
    """One torrent as reported by the torrent client."""

    name: str
    info_hash: str
    progress: float
    state: str
    save_path: str
