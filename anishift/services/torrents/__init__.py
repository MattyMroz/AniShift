"""Torrent release search and torrent client API."""

from anishift.services.torrents.errors import TorrentClientError, TorrentError, TorrentSourceError
from anishift.services.torrents.names import parse_release_name
from anishift.services.torrents.nyaa import parse_feed, search_releases
from anishift.services.torrents.qbittorrent import QBittorrentClient
from anishift.services.torrents.types import Release, ReleaseName, TorrentInfo

__all__ = [
    "QBittorrentClient",
    "Release",
    "ReleaseName",
    "TorrentClientError",
    "TorrentError",
    "TorrentInfo",
    "TorrentSourceError",
    "parse_feed",
    "parse_release_name",
    "search_releases",
]
