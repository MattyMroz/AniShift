from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from anishift.application.acquisition import (
    AcquisitionService,
    ClientStatus,
    DownloadReceipt,
    ReleaseCatalog,
    ReleaseChoice,
    catalog_releases,
    series_directory_name,
)
from anishift.errors import ErrorCode, ErrorContext, FatalError
from anishift.services.torrents import Release, ReleaseName, TorrentInfo


class _ClientDownError(FatalError):
    pass


class _Source:
    def __init__(self, releases: tuple[Release, ...]) -> None:
        self.releases: tuple[Release, ...] = releases
        self.queries: list[str] = []

    def search(self, query: str) -> tuple[Release, ...]:
        self.queries.append(query)
        return self.releases


class _Client:
    def __init__(self, *, reachable: bool = True, extension: bool = False) -> None:
        self.reachable: bool = reachable
        self.preference_values: dict[str, object] = {"incomplete_files_ext": extension}
        self.added: list[tuple[str, Path, str]] = []
        self.tracked: list[TorrentInfo] = []

    def version(self) -> str:
        self._require()
        return "5.2.3"

    def preferences(self) -> dict[str, object]:
        self._require()
        return dict(self.preference_values)

    def set_preferences(self, values: Mapping[str, object]) -> None:
        self._require()
        self.preference_values.update(values)

    def add_torrent(self, torrent_url: str, *, save_path: Path, category: str) -> None:
        self._require()
        self.added.append((torrent_url, save_path, category))

    def torrents(self, category: str) -> tuple[TorrentInfo, ...]:
        self._require()
        return tuple(self.tracked)

    def _require(self) -> None:
        if not self.reachable:
            raise _ClientDownError(
                context=ErrorContext(
                    code=ErrorCode.TORRENT_CLIENT_UNAVAILABLE,
                    message="qBittorrent Web UI is not reachable",
                    suggestion="Enable the Web UI",
                )
            )


def _release(title: str, *, seeders: int = 10) -> Release:
    return Release(
        title=title,
        torrent_url=f"https://nyaa.si/download/{abs(hash(title)) % 10_000}.torrent",
        info_hash="0" * 40,
        seeders=seeders,
        size_text="1.0 GiB",
        published=None,
    )


_BASE_NAME: ReleaseName = ReleaseName(
    group="SubsPlease",
    series="Neko to Ryuu",
    episode=None,
    season=None,
    resolution=1080,
    batch=False,
    version=None,
)


_NAMES: dict[str, ReleaseName] = {
    "sp-10": replace(_BASE_NAME, episode=Decimal(10)),
    "sp-11": replace(_BASE_NAME, episode=Decimal(11)),
    "sp-11v2": replace(_BASE_NAME, episode=Decimal(11), version=2),
    "dkb-11": replace(_BASE_NAME, group="DKB", episode=Decimal(11)),
    "sp-720": replace(_BASE_NAME, episode=Decimal(9), resolution=720),
    "unknown": replace(_BASE_NAME, episode=Decimal(8), resolution=None),
    "batch": replace(_BASE_NAME, batch=True),
}


def _parse(title: str) -> ReleaseName:
    return _NAMES[title]


def _service(client: _Client, tmp_path: Path, releases: tuple[Release, ...] = ()) -> AcquisitionService:
    return AcquisitionService(source=_Source(releases), client=client, workspace_root=tmp_path, parse_name=_parse)


def test_catalog_hides_low_and_unknown_quality_and_counts_them() -> None:
    catalog: ReleaseCatalog = catalog_releases(
        (_release("sp-10"), _release("sp-720"), _release("unknown")),
        _parse,
    )

    assert catalog.hidden == 2
    assert [choice.release.title for group in catalog.groups for choice in group.choices] == ["sp-10"]


def test_catalog_groups_by_series_and_group_with_newest_episode_first() -> None:
    catalog: ReleaseCatalog = catalog_releases(
        (_release("sp-10", seeders=5), _release("dkb-11", seeders=50), _release("sp-11v2"), _release("sp-11")),
        _parse,
    )

    assert [(group.series, group.group) for group in catalog.groups] == [
        ("Neko to Ryuu", "DKB"),
        ("Neko to Ryuu", "SubsPlease"),
    ]
    assert [choice.release.title for choice in catalog.groups[1].choices] == ["sp-11v2", "sp-11", "sp-10"]


def test_catalog_lists_a_batch_after_numbered_episodes() -> None:
    catalog: ReleaseCatalog = catalog_releases((_release("batch"), _release("sp-10")), _parse)

    assert [choice.release.title for choice in catalog.groups[0].choices] == ["sp-10", "batch"]


@pytest.mark.parametrize(
    ("series", "expected"),
    [
        ("Neko to Ryuu", "Neko to Ryuu"),
        ('Re:Zero <Season 2> "Final"', "ReZero Season 2 Final"),
        ("  Oshi   no Ko S3 ...", "Oshi no Ko S3"),
        ("CON", "_CON"),
        ("aux.mkv", "_aux.mkv"),
        ("***", "Nieznana seria"),
    ],
)
def test_series_directory_name_is_safe_on_windows(series: str, expected: str) -> None:
    assert series_directory_name(series) == expected


def test_search_returns_the_catalog_of_the_source_answer(tmp_path: Path) -> None:
    client: _Client = _Client()
    service: AcquisitionService = _service(client, tmp_path, (_release("sp-11"), _release("sp-720")))

    catalog: ReleaseCatalog = service.search("neko")

    assert catalog.hidden == 1
    assert catalog.groups[0].choices[0].release.title == "sp-11"


def test_download_queues_every_choice_into_the_series_directory(tmp_path: Path) -> None:
    client: _Client = _Client()
    service: AcquisitionService = _service(client, tmp_path)
    choices: tuple[ReleaseChoice, ...] = (
        ReleaseChoice(_release("sp-10"), _NAMES["sp-10"]),
        ReleaseChoice(_release("sp-11"), _NAMES["sp-11"]),
    )

    receipt: DownloadReceipt = service.download(choices)

    assert receipt == DownloadReceipt(2, tmp_path / "Neko to Ryuu")
    assert [entry[1:] for entry in client.added] == [(tmp_path / "Neko to Ryuu", "AniShift")] * 2
    assert client.added[0][0].startswith("https://nyaa.si/download/")


def test_queued_hashes_lists_the_tracked_torrents_in_lowercase(tmp_path: Path) -> None:
    client: _Client = _Client()
    client.tracked.append(TorrentInfo(name="ep", info_hash="ABCDEF", progress=0.5, state="downloading", save_path="x"))

    assert _service(client, tmp_path).queued_hashes() == frozenset({"abcdef"})


def test_download_refuses_an_empty_choice(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="At least one release"):
        _service(_Client(), tmp_path).download(())


def test_client_status_reports_version_and_incomplete_extension(tmp_path: Path) -> None:
    status: ClientStatus = _service(_Client(extension=True), tmp_path).client_status()

    assert status == ClientStatus(reachable=True, version="5.2.3", incomplete_extension=True)


def test_client_status_turns_an_unreachable_client_into_a_sentence(tmp_path: Path) -> None:
    status: ClientStatus = _service(_Client(reachable=False), tmp_path).client_status()

    assert status.reachable is False
    assert "not reachable" in status.problem
    assert status.suggestion == "Enable the Web UI"


def test_setup_client_switches_the_incomplete_extension_on(tmp_path: Path) -> None:
    client: _Client = _Client(extension=False)

    status: ClientStatus = _service(client, tmp_path).setup_client()

    assert client.preference_values["incomplete_files_ext"] is True
    assert status.incomplete_extension is True


def test_setup_client_does_not_touch_an_unreachable_client(tmp_path: Path) -> None:
    client: _Client = _Client(reachable=False)

    status: ClientStatus = _service(client, tmp_path).setup_client()

    assert status.reachable is False
    assert client.preference_values["incomplete_files_ext"] is False
