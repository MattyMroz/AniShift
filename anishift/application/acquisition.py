"""Release discovery and download hand-off through one torrent source and one torrent client."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from anishift.errors import AniShiftError
from anishift.utils.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from anishift.services.torrents import Release, ReleaseName

__all__ = [
    "DOWNLOAD_CATEGORY",
    "MIN_RESOLUTION",
    "AcquisitionService",
    "ClientStatus",
    "DownloadReceipt",
    "ReleaseCatalog",
    "ReleaseChoice",
    "SeriesGroup",
    "TorrentClient",
    "TorrentSource",
    "catalog_releases",
    "series_directory_name",
]

logger = get_logger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

MIN_RESOLUTION: Final[int] = 1080
"""Lowest vertical resolution a release must declare to be listed."""

DOWNLOAD_CATEGORY: Final[str] = "AniShift"
"""Category every torrent added by AniShift carries inside the client."""

INCOMPLETE_EXTENSION_PREFERENCE: Final[str] = "incomplete_files_ext"
"""Client preference appending ``.!qB`` to files still being downloaded, which the watch skips."""

_INVALID_NAME_CHARACTERS: Final[re.Pattern[str]] = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
"""Characters Windows refuses inside one path component."""

_RESERVED_NAMES: Final[frozenset[str]] = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}
)
"""Device names Windows refuses as a file or directory name regardless of extension."""

_FALLBACK_DIRECTORY: Final[str] = "Nieznana seria"
"""Directory used when a release title leaves nothing usable for a folder name."""


class TorrentSource(Protocol):
    """Index of public releases answering one free-text title query."""

    def search(self, query: str) -> tuple[Release, ...]:
        """Return the releases matching *query*, newest first as the index lists them."""
        ...


class TorrentClient(Protocol):
    """Local torrent client that stores files where AniShift tells it to."""

    def version(self) -> str:
        """Return the client version, proving the Web UI answers."""
        ...

    def preferences(self) -> dict[str, object]:
        """Return the client preferences relevant checks read."""
        ...

    def set_preferences(self, values: Mapping[str, object]) -> None:
        """Change the given client preferences."""
        ...

    def add_torrent(self, torrent_url: str, *, save_path: Path, category: str) -> None:
        """Queue one torrent so its files land in *save_path*."""
        ...


@dataclass(frozen=True, slots=True)
class ReleaseChoice:
    """One release together with the facts parsed from its name."""

    release: Release
    name: ReleaseName


@dataclass(frozen=True, slots=True)
class SeriesGroup:
    """Releases of one series by one release group, newest episode first."""

    series: str
    group: str
    choices: tuple[ReleaseChoice, ...]


@dataclass(frozen=True, slots=True)
class ReleaseCatalog:
    """Listed release groups and the number of releases hidden by the quality rule."""

    groups: tuple[SeriesGroup, ...]
    hidden: int


@dataclass(frozen=True, slots=True)
class DownloadReceipt:
    """What was handed to the client and where its files will appear."""

    count: int
    directory: Path


@dataclass(frozen=True, slots=True)
class ClientStatus:
    """Whether the client answers and whether it marks incomplete files."""

    reachable: bool
    version: str = ""
    incomplete_extension: bool = False
    problem: str = ""
    suggestion: str = ""


def catalog_releases(
    releases: Sequence[Release],
    parse_name: Callable[[str], ReleaseName],
    *,
    min_resolution: int = MIN_RESOLUTION,
) -> ReleaseCatalog:
    """Group releases of the required quality by series and release group."""
    buckets: dict[tuple[str, str], list[ReleaseChoice]] = {}
    labels: dict[tuple[str, str], tuple[str, str]] = {}
    hidden: int = 0
    for release in releases:
        name: ReleaseName = parse_name(release.title)
        if name.resolution is None or name.resolution < min_resolution:
            hidden += 1
            continue
        group: str = name.group or "?"
        key: tuple[str, str] = (name.series.casefold(), group.casefold())
        labels.setdefault(key, (name.series, group))
        buckets.setdefault(key, []).append(ReleaseChoice(release, name))
    groups: list[SeriesGroup] = [
        SeriesGroup(labels[key][0], labels[key][1], tuple(sorted(choices, key=_choice_order)))
        for key, choices in buckets.items()
    ]
    groups.sort(key=_group_order)
    return ReleaseCatalog(tuple(groups), hidden)


def series_directory_name(series: str) -> str:
    """Turn a series title into one directory name Windows accepts."""
    cleaned: str = _INVALID_NAME_CHARACTERS.sub("", series)
    cleaned = " ".join(cleaned.split()).rstrip(". ")
    if not cleaned:
        return _FALLBACK_DIRECTORY
    if cleaned.split(".", maxsplit=1)[0].upper() in _RESERVED_NAMES:
        return f"_{cleaned}"
    return cleaned


class AcquisitionService:
    """Search releases and hand the chosen ones to the client, saving into the library."""

    def __init__(
        self,
        *,
        source: TorrentSource,
        client: TorrentClient,
        workspace_root: Path,
        parse_name: Callable[[str], ReleaseName],
        category: str = DOWNLOAD_CATEGORY,
    ) -> None:
        self._source: TorrentSource = source
        self._client: TorrentClient = client
        self._workspace_root: Path = workspace_root
        self._parse_name: Callable[[str], ReleaseName] = parse_name
        self._category: str = category

    def search(self, query: str) -> ReleaseCatalog:
        """Return the listed releases for *query*, grouped and filtered by quality."""
        releases: tuple[Release, ...] = self._source.search(query)
        catalog: ReleaseCatalog = catalog_releases(releases, self._parse_name)
        logger.info(
            "Releases searched", listed=sum(len(group.choices) for group in catalog.groups), hidden=catalog.hidden
        )
        return catalog

    def download(self, choices: Sequence[ReleaseChoice]) -> DownloadReceipt:
        """Queue every chosen release into the series directory of the library."""
        if not choices:
            msg = "At least one release must be chosen"
            raise ValueError(msg)
        directory: Path = self.series_directory(choices[0])
        for choice in choices:
            self._client.add_torrent(
                choice.release.torrent_url,
                save_path=self.series_directory(choice),
                category=self._category,
            )
        logger.info("Releases queued in the torrent client", count=len(choices))
        return DownloadReceipt(len(choices), directory)

    def series_directory(self, choice: ReleaseChoice) -> Path:
        """Return the library directory the files of *choice* will be saved into."""
        return self._workspace_root / series_directory_name(choice.name.series)

    def client_status(self) -> ClientStatus:
        """Report whether the client answers and marks incomplete files."""
        try:
            version: str = self._client.version()
            preferences: dict[str, object] = self._client.preferences()
        except AniShiftError as problem:
            logger.warning("Torrent client unavailable", error_class=type(problem).__name__)
            return ClientStatus(reachable=False, problem=str(problem), suggestion=problem.context.suggestion)
        return ClientStatus(
            reachable=True,
            version=version,
            incomplete_extension=bool(preferences.get(INCOMPLETE_EXTENSION_PREFERENCE, False)),
        )

    def setup_client(self) -> ClientStatus:
        """Make the client mark incomplete files, so the watch never takes a partial download."""
        status: ClientStatus = self.client_status()
        if not status.reachable:
            return status
        self._client.set_preferences({INCOMPLETE_EXTENSION_PREFERENCE: True})
        logger.info("Torrent client configured for incomplete-file suffixes")
        return self.client_status()


def _choice_order(choice: ReleaseChoice) -> tuple[int, Decimal, int]:
    episode: Decimal | None = choice.name.episode
    if episode is None:
        return (1, Decimal(0), 0)
    return (0, -episode, -(choice.name.version or 0))


def _group_order(group: SeriesGroup) -> tuple[int, str, str]:
    seeders: int = sum(choice.release.seeders for choice in group.choices)
    return (-seeders, group.series.casefold(), group.group.casefold())
