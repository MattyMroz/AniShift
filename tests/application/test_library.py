from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from anishift.application.artifacts import ArtifactKind, create_group_id
from anishift.application.control import ProductConfirmation, ReadyGroup, WatchState
from anishift.application.control_views import LibrarySet
from anishift.application.discovery import discover_groups
from anishift.application.intents import RequestOrigin
from anishift.application.library import project_library
from anishift.application.workflows import WorkflowTarget

pytestmark = pytest.mark.unit

_STEM: str = "[Grp] Show - 02 [1080p]"


def _episode(directory: Path, stem: str = _STEM) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for suffix, body in ((".mkv", b"video"), (".eac3", b"narration"), (".pl.ass", b"subtitles")):
        (directory / f"{stem}{suffix}").write_bytes(body)


def _recorded(root: Path) -> WatchState:
    _episode(root / "ready")
    product: Path = root / "ready" / f"{_STEM}.eac3"
    stamp: os.stat_result = product.stat()
    group_id: str = create_group_id(Path("ready"), _STEM)
    record: ReadyGroup = ReadyGroup(
        "set-02",
        group_id,
        _STEM,
        ".",
        _STEM,
        WorkflowTarget.VIDEO,
        (f"ready/{_STEM}.mkv",),
        (f"ready/{_STEM}.eac3", f"ready/{_STEM}.pl.ass"),
        f"ready/{_STEM}.eac3",
    )
    confirmation: ProductConfirmation = ProductConfirmation(
        group_id,
        ArtifactKind.NARRATION_AUDIO.value,
        f"ready/{_STEM}.eac3",
        1,
        "run",
        RequestOrigin.USER,
        stamp.st_size,
        stamp.st_mtime_ns,
    )
    return WatchState(ready_groups=(record,), products=(confirmation,))


def _project(state: WatchState, root: Path) -> tuple[LibrarySet, ...]:
    return project_library(state, root, discover_groups(root).groups)


def test_project_library_lists_a_processed_set_in_a_ready_subfolder_without_any_record(tmp_path: Path) -> None:
    _episode(tmp_path / "ready" / "Nowy folder")

    sets: tuple[LibrarySet, ...] = _project(WatchState(), tmp_path)

    assert [(item.name, item.main_result, item.available, item.problem) for item in sets] == [
        (_STEM, f"ready/Nowy folder/{_STEM}.eac3", True, None)
    ]
    assert sets[0].set_id == create_group_id(Path("ready/Nowy folder"), _STEM)
    assert {item.path for item in sets[0].files} == {
        f"ready/Nowy folder/{_STEM}{suffix}" for suffix in (".mkv", ".eac3", ".pl.ass")
    }


def test_project_library_leaves_out_a_ready_source_without_a_product(tmp_path: Path) -> None:
    (tmp_path / "ready").mkdir()
    (tmp_path / "ready" / "Show.S01E03.1080p.WEB.srt").write_text("1\n", encoding="utf-8")

    assert _project(WatchState(), tmp_path) == ()


@pytest.mark.parametrize("place", ["ready/Nowy folder", "ready"])
def test_project_library_keeps_a_recorded_set_moved_or_renamed_inside_ready(tmp_path: Path, place: str) -> None:
    state: WatchState = _recorded(tmp_path)
    stem: str = f"{_STEM} renamed" if place == "ready" else _STEM
    target: Path = tmp_path / place
    target.mkdir(parents=True, exist_ok=True)
    for suffix in (".mkv", ".eac3", ".pl.ass"):
        shutil.move(tmp_path / "ready" / f"{_STEM}{suffix}", target / f"{stem}{suffix}")

    sets: tuple[LibrarySet, ...] = _project(state, tmp_path)

    assert [(item.set_id, item.name, item.main_result, item.available) for item in sets] == [
        ("set-02", stem, f"{place}/{stem}.eac3", True)
    ]
    assert sets[0].group_id == create_group_id(Path(place), stem)
    assert sets[0].target is WorkflowTarget.VIDEO


def test_project_library_matches_no_record_to_two_copies_of_its_moved_result(tmp_path: Path) -> None:
    state: WatchState = _recorded(tmp_path)
    for directory in ("ready/a", "ready/b"):
        (tmp_path / directory).mkdir()
        for suffix in (".mkv", ".eac3", ".pl.ass"):
            shutil.copy2(tmp_path / "ready" / f"{_STEM}{suffix}", tmp_path / directory / f"{_STEM}{suffix}")
    for suffix in (".mkv", ".eac3", ".pl.ass"):
        (tmp_path / "ready" / f"{_STEM}{suffix}").unlink()

    sets: tuple[LibrarySet, ...] = _project(state, tmp_path)

    assert sorted((item.set_id, item.available) for item in sets) == sorted(
        [
            ("set-02", False),
            (create_group_id(Path("ready/a"), _STEM), True),
            (create_group_id(Path("ready/b"), _STEM), True),
        ]
    )
