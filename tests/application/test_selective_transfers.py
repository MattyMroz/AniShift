from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from anishift.application.acquisition_staging import staged_file, staging_path, torrent_relative_path
from anishift.application.control import TorrentioReference
from anishift.application.transfers import episode_files, file_map_revision, video_sidecars
from anishift.services.torrents import TorrentFile

pytestmark = pytest.mark.unit


def _file(index: int, name: str) -> TorrentFile:
    return TorrentFile(index, name, 100, 0.0, 0)


def _target() -> dict[str, object]:
    return {"aliases": ["Neko to Ryuu"], "type": "TV", "local_episode": 1, "season": 1, "episode": 1}


@pytest.mark.parametrize("hint", [None, 0, 1, 999])
def test_unique_name_ignores_wrong_or_missing_source_index_and_padding(hint: int | None) -> None:
    files: tuple[TorrentFile, ...] = (
        _file(0, "Pack/.pad/128"),
        _file(3, "Pack/E01.mkv"),
        _file(5, "Pack/E02.mkv"),
    )
    reference: TorrentioReference = TorrentioReference("a" * 40, hint, "E01.mkv")
    assert episode_files(files, reference, {}, "Pack") == (files[1],)


def test_duplicate_basename_uses_h1_on_the_full_paths() -> None:
    files: tuple[TorrentFile, ...] = (
        _file(2, "Neko to Ryuu/Season 1/01.mkv"),
        _file(4, "Other Series/Season 1/01.mkv"),
    )
    reference: TorrentioReference = TorrentioReference("a" * 40, 4, "01.mkv")
    assert episode_files(files, reference, _target(), "") == (files[0],)


@pytest.mark.parametrize(
    "names",
    [
        ("Neko to Ryuu/Season 1/01.mkv", "Neko to Ryuu/Season 1/01.mp4"),
        ("Other Series/01.mkv", "Other Series/02.mkv"),
        ("unknown.mkv", "unknown2.mp4"),
        ("Neko to Ryuu - 01.avi",),
    ],
)
def test_ambiguous_missing_uncertain_and_unsupported_matches_require_manual_choice(names: tuple[str, ...]) -> None:
    files: tuple[TorrentFile, ...] = tuple(_file(index, name) for index, name in enumerate(names))
    assert episode_files(files, TorrentioReference("a" * 40, 0), _target(), "") == ()


def test_sidecars_require_exact_stem_and_directory_and_supported_extensions() -> None:
    names: tuple[str, ...] = (
        "Pack/01.mkv",
        "Pack/01.ass",
        "Pack/01.srt",
        "Pack/01.ssa",
        "Pack/01.flac",
        "Pack/01.m4a",
        "Pack/010.ass",
        "Pack/01.en.ass",
        "Other/01.ass",
        "Pack/01.ttf",
        "Pack/01.jpg",
        "Pack/01.mp4",
        "Pack/NCOP.mkv",
        "Pack/01.aac",
    )
    files: tuple[TorrentFile, ...] = tuple(_file(index, name) for index, name in enumerate(names))
    assert video_sidecars(files, files[0]) == files[:6]


def test_file_map_revision_ignores_progress_and_order_but_changes_with_file_identity() -> None:
    files: tuple[TorrentFile, ...] = (_file(0, "E01.mkv"), _file(2, "E01.ass"), _file(5, "E03.mkv"))
    assert file_map_revision(files) == file_map_revision(
        tuple(replace(item, priority=1, progress=0.5) for item in reversed(files))
    )
    for changed in (replace(files[0], name="E02.mkv"), replace(files[0], size=99), replace(files[0], index=9)):
        assert file_map_revision((changed, *files[1:])) != file_map_revision(files)


@pytest.mark.parametrize(
    "files",
    [
        (_file(0, "one.mkv"), _file(0, "two.mkv")),
        (_file(0, "Pack/one.mkv"), _file(1, "pack/ONE.mkv")),
    ],
)
def test_nonunique_metadata_is_rejected(files: tuple[TorrentFile, ...]) -> None:
    with pytest.raises(ValueError, match="unique"):
        file_map_revision(files)


@pytest.mark.parametrize(
    "name",
    [
        "../one.mkv",
        "folder/../one.mkv",
        "C:/one.mkv",
        "C:one.mkv",
        "//server/share/one.mkv",
        "/one.mkv",
        "one.mkv:stream",
        "folder/NUL.mkv",
        "folder/one.mkv.",
        "folder/one.mkv ",
        "folder//one.mkv",
        "folder/./one.mkv",
        "folder/one\x00.mkv",
        "folder/one?.mkv",
        "",
    ],
)
def test_unsafe_windows_paths_never_enter_a_file_map_or_staging(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError, match="safe relative Windows path"):
        torrent_relative_path(name)
    with pytest.raises(ValueError, match="safe relative Windows path"):
        staged_file(tmp_path, name)
    if name:
        with pytest.raises(ValueError, match="safe relative Windows path"):
            file_map_revision((_file(0, name),))


def test_staging_is_isolated_without_creating_a_run_marker(tmp_path: Path) -> None:
    destination: Path = staging_path(tmp_path, "operation-1")
    assert destination == tmp_path / "temp/.acquisition/operation-1/data"
    assert not destination.exists()
    assert staged_file(destination, r"Pack\E01.mkv") == destination / "Pack/E01.mkv"
    with pytest.raises(ValueError, match="one directory component"):
        staging_path(tmp_path, "nested/operation")


def test_staging_rejects_a_linked_ancestor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    linked: Path = tmp_path / "temp"
    monkeypatch.setattr(Path, "is_junction", lambda path: path == linked)
    with pytest.raises(ValueError, match="symlink or junction"):
        staging_path(tmp_path, "operation-1")


def test_workspace_below_a_junction_does_not_validate_outside_its_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace: Path = tmp_path / "workspace"
    checked: list[Path] = []

    def junction(path: Path) -> bool:
        checked.append(path)
        return path == tmp_path

    monkeypatch.setattr(Path, "is_junction", junction)
    assert staging_path(workspace, "operation-1") == workspace / "temp/.acquisition/operation-1/data"
    assert checked
    assert all(path.is_relative_to(workspace) for path in checked)
