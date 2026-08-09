from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from anishift.application.artifacts import ArtifactKind, ArtifactState, GroupConflictKind
from anishift.application.discovery import (
    ArtifactName,
    DiscoveryWarningKind,
    choose_auto_sidecar,
    choose_primary_video,
    classify_artifact,
    discover_groups,
    group_candidates,
    is_derived_product,
    is_primary_source,
)


def _touch(root: Path, *names: str) -> None:
    for name in names:
        (root / name).touch()


def test_discovery_groups_mkv_and_mp4_and_prefers_mkv() -> None:
    root = Path.cwd()
    candidates = (
        classify_artifact(root / "1.mp4"),
        classify_artifact(root / "1.mkv"),
    )
    names = tuple(candidate for candidate in candidates if candidate is not None)
    group = group_candidates(names)[0]
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
    group = group_candidates(candidates)[0]
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
