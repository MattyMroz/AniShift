"""Torrent release search and torrent client API."""

from anishift.services.torrents.errors import TorrentClientError, TorrentError, TorrentSourceError
from anishift.services.torrents.knaben import KnabenSource
from anishift.services.torrents.names import parse_release_name
from anishift.services.torrents.nekobt import NekoBTSource
from anishift.services.torrents.nyaa import parse_feed, search_releases
from anishift.services.torrents.qbittorrent import QBittorrentClient
from anishift.services.torrents.torrentio import TorrentioSource
from anishift.services.torrents.tsukihime import TsukiHimeSource
from anishift.services.torrents.types import Release, ReleaseName, TorrentFile, TorrentInfo

__all__ = [
    "KnabenSource",
    "NekoBTSource",
    "QBittorrentClient",
    "Release",
    "ReleaseName",
    "TorrentClientError",
    "TorrentError",
    "TorrentFile",
    "TorrentInfo",
    "TorrentSourceError",
    "TorrentioSource",
    "TsukiHimeSource",
    "parse_feed",
    "parse_release_name",
    "search_releases",
]
