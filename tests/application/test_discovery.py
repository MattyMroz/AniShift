from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from anishift.application.artifacts import (
    ArtifactKind,
    ArtifactState,
    GroupConflictKind,
    create_group_id,
)
from anishift.application.discovery import (
    ArtifactName,
    DiscoveryIndex,
    DiscoveryWarningKind,
    classify_artifact,
    discover_groups,
    group_candidates,
    is_derived_product,
    is_primary_source,
)
from anishift.application.selection import choose_auto_sidecar, choose_primary_video


def _touch(root: Path, *names: str) -> None:
    for name in names:
        path: Path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()


def test_discovery_groups_mkv_and_mp4_and_prefers_mkv() -> None:
    root = Path.cwd()
    candidates = (
        classify_artifact(root / "1.mp4"),
        classify_artifact(root / "1.mkv"),
    )
    names = tuple(candidate for candidate in candidates if candidate is not None)
    group = group_candidates(names, root)[0]
    assert group.stem == "1"
    assert {artifact.kind for artifact in group.artifacts} == {
        ArtifactKind.VIDEO_MKV,
        ArtifactKind.VIDEO_MP4,
    }
    selected = choose_primary_video(group.artifacts)
    assert selected is not None
    assert selected.kind is ArtifactKind.VIDEO_MKV


def test_discovery_groups_exact_sidecars_and_prefers_ass(tmp_path: Path) -> None:
    _touch(tmp_path, "1.mkv", "1.ass", "1.srt")
    group = discover_groups(tmp_path).groups[0]
    selected = choose_auto_sidecar(group.artifacts)
    assert selected is not None
    assert selected.path == tmp_path / "1.ass"
    assert selected.state is ArtifactState.CANDIDATE


def test_auto_sidecar_skips_invalid_ass(tmp_path: Path) -> None:
    _touch(tmp_path, "1.mkv", "1.ass", "1.srt")
    group = discover_groups(tmp_path).groups[0]
    candidates = tuple(
        replace(artifact, state=ArtifactState.INVALID) if artifact.path == tmp_path / "1.ass" else artifact
        for artifact in group.artifacts
    )
    selected = choose_auto_sidecar(candidates)
    assert selected is not None
    assert selected.path == tmp_path / "1.srt"


def test_standalone_txt_creates_group(tmp_path: Path) -> None:
    _touch(tmp_path, "notes.txt")
    result = discover_groups(tmp_path)
    assert len(result.groups) == 1
    assert result.groups[0].artifacts[0].kind is ArtifactKind.STANDALONE_TEXT


def test_txt_and_video_create_one_blocked_group(tmp_path: Path) -> None:
    _touch(tmp_path, "1.txt", "1.mkv")
    result = discover_groups(tmp_path)
    assert len(result.groups) == 1
    assert tuple(conflict.kind for conflict in result.groups[0].conflicts) == (GroupConflictKind.TXT_WITH_VIDEO,)


def test_derived_products_attach_without_becoming_primary(tmp_path: Path) -> None:
    _touch(
        tmp_path,
        "1.mkv",
        "1.pl.ass",
        "1.spoken.pl.srt",
        "1.displayed.pl.ass",
        "1.eac3",
        "1.pl.mp4",
    )
    group = discover_groups(tmp_path).groups[0]
    assert {artifact.kind for artifact in group.artifacts} == {
        ArtifactKind.VIDEO_MKV,
        ArtifactKind.FULL_PL,
        ArtifactKind.SPOKEN_PL,
        ArtifactKind.DISPLAYED_PL,
        ArtifactKind.NARRATION_AUDIO,
        ArtifactKind.FINAL_MP4,
    }


def test_derived_product_without_primary_only_warns(tmp_path: Path) -> None:
    _touch(tmp_path, "1.pl.srt")
    result = discover_groups(tmp_path)
    assert result.groups == ()
    assert tuple(warning.kind for warning in result.warnings) == (DiscoveryWarningKind.ORPHAN_ARTIFACT,)


def test_unmarked_sidecar_without_video_does_not_create_group(tmp_path: Path) -> None:
    _touch(tmp_path, "1.ass")
    result = discover_groups(tmp_path)
    assert result.groups == ()
    assert result.warnings[0].path == tmp_path / "1.ass"


def test_displayed_word_is_only_special_in_subtitle_product_suffix(tmp_path: Path) -> None:
    _touch(tmp_path, "show.displayed.mkv")
    group = discover_groups(tmp_path).groups[0]
    assert group.stem == "show.displayed"
    assert group.artifacts[0].kind is ArtifactKind.VIDEO_MKV


def test_final_container_never_creates_source_group(tmp_path: Path) -> None:
    _touch(tmp_path, "show.pl.mkv", "show.pl.mp4")
    result = discover_groups(tmp_path)
    assert result.groups == ()
    assert all(warning.kind is DiscoveryWarningKind.ORPHAN_ARTIFACT for warning in result.warnings)


def test_classification_helpers_cover_primary_and_derived_names() -> None:
    assert is_primary_source(Path("episode.mkv")) is True
    assert is_primary_source(Path("episode.mp4")) is True
    assert is_primary_source(Path("episode.txt")) is True
    assert is_primary_source(Path("episode.ass")) is False
    assert is_derived_product(Path("episode.pl.srt")) is True
    assert is_derived_product(Path("episode.spoken.pl.ass")) is True
    assert is_derived_product(Path("episode.flac")) is True
    assert is_derived_product(Path("episode.pl.mkv")) is True


def test_duplicate_normalized_primary_names_report_conflict() -> None:
    candidates = (
        ArtifactName(Path("workspace/1.mkv"), "1", ArtifactKind.VIDEO_MKV, True, False),
        ArtifactName(Path("workspace/1.MKV"), "1", ArtifactKind.VIDEO_MKV, True, False),
    )
    group = group_candidates(candidates, Path("workspace"))[0]
    assert tuple(conflict.kind for conflict in group.conflicts) == (GroupConflictKind.AMBIGUOUS_PRIMARY,)


def test_discovery_result_is_independent_of_filesystem_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _touch(tmp_path, "1.srt", "1.mkv", "1.ass", "2.mp4", "2.pl.srt")
    original_iterdir = Path.iterdir
    paths = tuple(original_iterdir(tmp_path))
    orders = (paths, tuple(reversed(paths)), paths[::2] + paths[1::2])
    results = []
    current_order: tuple[Path, ...] = paths

    def fake_iterdir(path: Path) -> Iterator[Path]:
        if path == tmp_path:
            return iter(current_order)
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    for order in orders:
        current_order = order
        results.append(discover_groups(tmp_path))
    assert results[1:] == [results[0], results[0]]


def test_group_in_subfolder_is_discovered_with_its_own_directory(tmp_path: Path) -> None:
    _touch(tmp_path, "Series A/01.mkv", "Series A/01.ass")
    groups = discover_groups(tmp_path).groups
    assert len(groups) == 1
    assert groups[0].stem == "01"
    assert groups[0].directory == tmp_path / "Series A"


def test_group_in_root_keeps_the_flat_workspace_identifier(tmp_path: Path) -> None:
    _touch(tmp_path, "01.mkv")
    group = discover_groups(tmp_path).groups[0]
    assert group.group_id == create_group_id(Path(), "01")


def test_subfolder_group_identifier_uses_the_relative_directory(tmp_path: Path) -> None:
    _touch(tmp_path, "Series A/01.mkv")
    group = discover_groups(tmp_path).groups[0]
    assert group.group_id == create_group_id(Path("Series A"), "01")


def test_same_stem_in_two_subfolders_creates_two_distinct_groups(tmp_path: Path) -> None:
    _touch(tmp_path, "Series A/01.mkv", "Series B/01.mkv")
    groups = discover_groups(tmp_path).groups
    assert {group.directory for group in groups} == {tmp_path / "Series A", tmp_path / "Series B"}
    assert len({group.group_id for group in groups}) == 2


def test_managed_temp_tree_below_root_is_never_discovered(tmp_path: Path) -> None:
    _touch(tmp_path, "temp/run-1/01.mkv")
    result = discover_groups(tmp_path)
    assert result.groups == ()
    assert result.warnings == ()


def test_temp_folder_below_a_subfolder_is_still_discovered(tmp_path: Path) -> None:
    _touch(tmp_path, "Series A/temp/01.mkv")
    groups = discover_groups(tmp_path).groups
    assert len(groups) == 1
    assert groups[0].directory == tmp_path / "Series A" / "temp"


def test_hidden_directories_and_files_are_never_discovered(tmp_path: Path) -> None:
    _touch(tmp_path, ".foo/01.mkv", ".01.mkv")
    result = discover_groups(tmp_path)
    assert result.groups == ()
    assert result.warnings == ()


def test_nested_discovery_is_independent_of_filesystem_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _touch(tmp_path, "02.mkv", "Series A/01.mkv", "Series A/01.ass", "Series B/01.mkv")
    original_iterdir = Path.iterdir
    reversed_order: bool = False

    def fake_iterdir(path: Path) -> Iterator[Path]:
        return iter(sorted(original_iterdir(path), reverse=reversed_order))

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    ascending = discover_groups(tmp_path)
    reversed_order = True
    descending = discover_groups(tmp_path)
    assert descending == ascending
    assert len(ascending.groups) == 3


def test_changed_paths_update_the_index_without_walking_unchanged_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _touch(tmp_path, "Series/01.mkv", "Other/01.mkv")
    index: DiscoveryIndex = DiscoveryIndex(tmp_path)
    initial = index.discover()
    source: Path = tmp_path / "Series" / "02.mkv"
    source.touch()
    visited: list[Path] = []

    def forbidden(path: Path) -> Iterator[Path]:
        visited.append(path)
        raise AssertionError("An individual file change must not walk directories")

    monkeypatch.setattr(Path, "iterdir", forbidden)
    updated = index.discover((source, source))
    assert len(updated.groups) == len(initial.groups) + 1
    assert not visited
    assert index.discover(()) == updated
    source.unlink()
    assert index.discover((source,)) == initial


def test_a_directory_rename_replaces_its_indexed_groups_and_preserves_exclusions(tmp_path: Path) -> None:
    _touch(tmp_path, "Series/01.mkv", "Series/.hidden/02.mkv", "temp/work/03.mkv", ".hidden/04.mkv")
    index: DiscoveryIndex = DiscoveryIndex(tmp_path)
    initial = index.discover()
    original: Path = tmp_path / "Series"
    renamed: Path = tmp_path / "Renamed"
    original.rename(renamed)

    changed = index.discover((original, renamed, tmp_path / "temp" / "work"))

    assert len(changed.groups) == 1
    assert changed.groups[0].directory == renamed
    assert changed.groups[0].group_id != initial.groups[0].group_id
    assert index.discover((tmp_path,)) == discover_groups(tmp_path) == changed
