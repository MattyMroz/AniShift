from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from anishift.application.acquisition_staging import staged_file, staging_path, torrent_relative_path
from anishift.application.control import ChoiceTraits, EpisodeChoice, TorrentioReference
from anishift.application.episode_identity import IdentityVerdict
from anishift.application.release_quality import PolishClass, ResolutionClass
from anishift.application.transfers import (
    MetadataCheck,
    episode_files,
    file_map_revision,
    metadata_check,
    video_sidecars,
)
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


def test_episode_files_two_matches_ambiguous_even_with_the_reference_name() -> None:
    files: tuple[TorrentFile, ...] = (
        _file(0, "Pack/Neko to Ryuu - 01 [1080p].mkv"),
        _file(1, "Pack/Neko to Ryuu - 01 [720p].mkv"),
    )
    reference: TorrentioReference = TorrentioReference("a" * 40, 0, "Neko to Ryuu - 01 [1080p].mkv")
    assert episode_files(files, reference, _target(), "") == ()


def test_episode_files_pack_single_match_unchanged() -> None:
    files: tuple[TorrentFile, ...] = (
        _file(0, "Pack/Neko to Ryuu - 01.mkv"),
        _file(1, "Pack/Neko to Ryuu - 01.ass"),
        _file(2, "Pack/Neko to Ryuu - 02.mkv"),
    )
    assert episode_files(files, TorrentioReference("a" * 40, 2), _target(), "") == files[:2]


def _choice(*, unusable: tuple[str, ...] = ()) -> EpisodeChoice:
    return EpisodeChoice(
        anilist_id=1,
        number=1,
        reference=TorrentioReference("a" * 40, 0, "Neko to Ryuu - 01.mkv"),
        target=_target(),
        verdict=IdentityVerdict.MATCH,
        reason="match",
        traits=ChoiceTraits(PolishClass.NONE, ResolutionClass.FULL_HD, unusable),
    )


_SINGLE: tuple[TorrentFile, ...] = (_file(0, "Neko to Ryuu - 01.mkv"), _file(1, "Neko to Ryuu - 01.ass"))


@pytest.mark.parametrize(
    ("names", "stopped"),
    [
        (("Neko to Ryuu - 01 [1080p].mkv", "Neko to Ryuu - 01 [720p].mkv"), "ambiguous"),
        (("Neko to Ryuu - 01.mkv", "Neko to Ryuu - 02.mkv"), "pack"),
        (("unknown.mkv",), "no_match"),
        (("Neko to Ryuu - 01.avi",), "no_match"),
        (("Neko to Ryuu S2/Neko to Ryuu - 01.mkv",), "recheck"),
    ],
    ids=[
        "ambiguous",
        "pack",
        "no-match",
        "unsupported",
        "unique-name-reclassified",
    ],
)
def test_metadata_check_stops_an_unfit_file_list(names: tuple[str, ...], stopped: str) -> None:
    files: tuple[TorrentFile, ...] = tuple(_file(index, name) for index, name in enumerate(names))
    assert metadata_check(files, _choice(), ()) == MetadataCheck((), stopped)


_EXTRA_CASES: list[tuple[str, str, bool]] = [
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - 02.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - Kanojo.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - 02 - The Opening.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - 02 [ED123456].mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - ED.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - PV.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - PV1.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - PV 01.mkv", True),
    ("Neko to Ryuu [03].mkv", "Neko to Ryuu [04] The Menu.mkv", True),
    ("Neko to Ryuu [03].mkv", "Neko to Ryuu [04] Creditless OP.mkv", True),
    ("Neko to Ryuu Menu.mkv", "Neko to Ryuu Menu - 02 - Story.mkv", True),
    ("Neko to Ryuu Preview.mkv", "Neko to Ryuu Preview - 02 - Story.mkv", True),
    ("Menu2.mkv", "Menu2 - 02 - Story.mkv", True),
    ("NCOP - 01.mkv", "NCOP - 02 - Story.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Featurettes/Neko to Ryuu - 02.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - 02-other.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu \u2161 - NCOP.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Extras/Neko - 02.mkv", True),
    ("Neko to Ryuu - 03.mkv", "Extras/Neko to Ryuu - S01E04/Story.mkv", True),
    ("Neko to Ryuu - 03.mkv", "Extras/02/Neko to Ryuu.mkv", True),
    ("Neko to Ryuu - 03.mkv", "Other/Season 1/02/Story.mkv", True),
    ("Neko to Ryuu - 03.mkv", "Neko to Ryuu/02/Story-other.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - NCOP\u00b2.mkv", True),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - NCOP.mkv", False),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - NCOP 01.mkv", False),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - NCED2 [ABCDEF12].mkv", False),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - Creditless OP.mkv", False),
    ("Neko to Ryuu - 01.mkv", "Extras/Making Of.mkv", False),
    ("Neko to Ryuu - 01.mkv", "Neko to Ryuu - PV-trailer.mp4", False),
]

_EXTRA_IDS: list[str] = [
    "two-episodes",
    "unrecognized-video",
    "marker-word-in-episode-title",
    "marker-like-checksum",
    "bare-ed",
    "pv",
    "attached-pv-number",
    "separated-pv-number",
    "bracketed-episode-number",
    "bracketed-number-beside-marker",
    "menu-series-without-number",
    "preview-series-without-number",
    "attached-number-series",
    "ncop-series",
    "plex-folder-with-number",
    "plex-suffix-with-number",
    "roman-numeral",
    "extras-folder-with-number",
    "numbered-folder-under-extras",
    "numbered-folder-in-extras",
    "numbered-folders-under-other",
    "numbered-folder-above-plex-suffix",
    "superscript-number",
    "ncop",
    "separated-ncop-number",
    "nced-with-checksum",
    "creditless",
    "extras-folder",
    "plex-suffix",
]


@pytest.mark.parametrize(("first", "second", "pack"), _EXTRA_CASES, ids=_EXTRA_IDS)
def test_metadata_check_counts_only_episode_videos(first: str, second: str, *, pack: bool) -> None:
    files: tuple[TorrentFile, ...] = (_file(0, first), _file(1, second))
    assert metadata_check(files, _choice(), ()).stopped == ("pack" if pack else None)


@pytest.mark.parametrize("series", ["Ed", "Menu", "The Menu", "CM", "PV", "Preview", "Teaser", "Yokoku"])
def test_metadata_check_stops_a_pack_of_a_series_named_like_a_marker(series: str) -> None:
    choice: EpisodeChoice = _choice()
    named: EpisodeChoice = replace(
        choice,
        reference=replace(choice.reference, file_name=f"{series} - 01.mkv"),
        target={**choice.target, "aliases": [series]},
    )
    files: tuple[TorrentFile, ...] = (_file(0, f"{series} - 01.mkv"), _file(1, f"{series} - 02 - Story.mkv"))
    assert metadata_check(files, named, ()) == MetadataCheck((), "pack")


@pytest.mark.parametrize(
    "extra",
    [
        "Neko to Ryuu - NCOP.avi",
        "Extras/Making Of.mkv",
        "Neko to Ryuu - x-trailer.mp4",
    ],
)
def test_metadata_check_binds_the_episode_beside_recognized_extras(extra: str) -> None:
    files: tuple[TorrentFile, ...] = (*_SINGLE, _file(2, extra))
    assert metadata_check(files, _choice(), ()) == MetadataCheck(_SINGLE)


@pytest.mark.parametrize(
    ("name", "stopped"),
    [
        ("Pack/Neko to Ryuu - 01 [English Dub].mkv", "recheck"),
        ("Pack/Neko to Ryuu - 01 [HardSub].mkv", "no_match"),
        ("Pack/Neko to Ryuu - 01 [RAW].mkv", "no_match"),
    ],
    ids=["dub", "hardsub", "raw"],
)
def test_metadata_check_rechecks_the_name_revealed_by_the_client(name: str, stopped: str) -> None:
    files: tuple[TorrentFile, ...] = (_file(0, name),)
    assert metadata_check(files, _choice(), ()) == MetadataCheck((), stopped)


def test_metadata_check_weighs_the_revealed_name_with_the_release_name() -> None:
    choice: EpisodeChoice = _choice()
    files: tuple[TorrentFile, ...] = (_file(0, "Pack/Neko to Ryuu - 01 [English Dub].mkv"),)
    dual: EpisodeChoice = replace(choice, reference=replace(choice.reference, release="Neko to Ryuu [Dual-Audio]"))
    assert metadata_check(files, dual, ()) == MetadataCheck(files)


def test_metadata_check_keeps_the_offered_evaluation_of_the_same_name() -> None:
    choice: EpisodeChoice = _choice()
    name: str = "Neko to Ryuu - 01 [English Dub].mkv"
    offered: EpisodeChoice = replace(choice, reference=replace(choice.reference, file_name=name))
    files: tuple[TorrentFile, ...] = (_file(0, f"Pack/{name}"),)
    assert metadata_check(files, offered, ()) == MetadataCheck(files)


def test_metadata_check_binds_one_matching_video_with_its_sidecars() -> None:
    assert metadata_check(_SINGLE, _choice(), ()) == MetadataCheck(_SINGLE)


@pytest.mark.parametrize(
    ("protected", "stopped"),
    [
        (frozenset({("a" * 40, "neko to ryuu - 01.mkv")}), "taken"),
        (frozenset({("a" * 40, None)}), "taken"),
        (frozenset({("a" * 40, "other.mkv")}), None),
        (frozenset({("b" * 40, "neko to ryuu - 01.mkv")}), None),
    ],
    ids=["same-path", "whole-hash", "other-path", "other-hash"],
)
def test_metadata_check_uses_protected_paths(protected: frozenset[tuple[str, str | None]], stopped: str | None) -> None:
    check: MetadataCheck = metadata_check(_SINGLE, _choice(), protected)
    assert check == MetadataCheck(() if stopped else _SINGLE, stopped)


def test_metadata_check_rechecks_the_usability_snapshot() -> None:
    assert metadata_check(_SINGLE, _choice(unusable=("hardsub",)), ()) == MetadataCheck((), "recheck")


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
