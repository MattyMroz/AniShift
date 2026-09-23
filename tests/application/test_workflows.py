from __future__ import annotations

import sys
from pathlib import Path

import pytest

from anishift.application.workflows import (
    ROOT_ROUTE,
    WorkflowTarget,
    WorkspacePlace,
    resolve_route,
    route_within,
)

_DRIVE_RELATIVE: tuple[str, ...] = ("C:subs", "C:subs/01.mkv", "C:/subs") if sys.platform == "win32" else ()


def test_the_workspace_root_stays_plain_video_work() -> None:
    assert resolve_route(Path()) is ROOT_ROUTE
    assert resolve_route(Path("Kanojo mo Kanojo")).target is WorkflowTarget.VIDEO
    assert resolve_route(Path("Sezon 2/Odcinki")).place is WorkspacePlace.ROOT


@pytest.mark.parametrize(
    ("relative", "place", "target", "sidecar"),
    [
        ("subs", WorkspacePlace.SUBS, WorkflowTarget.VIDEO, True),
        ("translate", WorkspacePlace.TRANSLATE, WorkflowTarget.TRANSLATE, False),
        ("audiobook", WorkspacePlace.AUDIOBOOK, WorkflowTarget.AUDIOBOOK, False),
        ("cover", WorkspacePlace.COVER, WorkflowTarget.COVER, False),
    ],
)
def test_each_task_folder_names_exactly_one_target(
    relative: str, place: WorkspacePlace, target: WorkflowTarget, *, sidecar: bool
) -> None:
    route = resolve_route(Path(relative))
    assert (route.place, route.target, route.requires_sidecar) == (place, target, sidecar)
    assert route.starts_automatic_work


def test_a_task_folder_keeps_its_target_through_manual_nesting() -> None:
    deep = resolve_route(Path("audiobook/Zimowe tytuły/Frieren/Sezon 1"))
    assert deep.place is WorkspacePlace.AUDIOBOOK
    assert deep.target is WorkflowTarget.AUDIOBOOK


def test_a_reserved_name_deeper_in_the_tree_is_ordinary_video_work() -> None:
    assert resolve_route(Path("Frieren/subs")).target is WorkflowTarget.VIDEO
    assert resolve_route(Path("Frieren/subs/01")).place is WorkspacePlace.ROOT


@pytest.mark.parametrize(
    ("written", "place", "target", "sidecar"),
    [
        ("SUBS", WorkspacePlace.SUBS, WorkflowTarget.VIDEO, True),
        ("Translate", WorkspacePlace.TRANSLATE, WorkflowTarget.TRANSLATE, False),
        ("AudioBook", WorkspacePlace.AUDIOBOOK, WorkflowTarget.AUDIOBOOK, False),
        ("COVER", WorkspacePlace.COVER, WorkflowTarget.COVER, False),
        ("Ready", WorkspacePlace.READY, None, False),
        ("TEMP", WorkspacePlace.TEMP, None, False),
    ],
)
def test_a_reserved_name_is_recognised_whatever_its_case(
    written: str, place: WorkspacePlace, target: WorkflowTarget | None, *, sidecar: bool
) -> None:
    route = resolve_route(Path(written))
    assert (route.place, route.target, route.requires_sidecar) == (place, target, sidecar)


@pytest.mark.parametrize(
    ("written", "place", "target"),
    [
        ("subs.", WorkspacePlace.SUBS, WorkflowTarget.VIDEO),
        ("subs ", WorkspacePlace.SUBS, WorkflowTarget.VIDEO),
        ("Cover. ..", WorkspacePlace.COVER, WorkflowTarget.COVER),
        ("ready.", WorkspacePlace.READY, None),
        ("temp ", WorkspacePlace.TEMP, None),
    ],
)
def test_a_trailing_dot_or_space_never_smuggles_a_reserved_name_past_the_router(
    written: str, place: WorkspacePlace, target: WorkflowTarget | None
) -> None:
    route = resolve_route(Path(written) / "01.mkv")
    assert (route.place, route.target) == (place, target)


@pytest.mark.parametrize("relative", ["/subs", "//serwer/udzial/subs", *_DRIVE_RELATIVE])
def test_a_path_carrying_a_drive_or_a_root_anchor_is_outside(relative: str) -> None:
    route = resolve_route(Path(relative))
    assert route.place is WorkspacePlace.OUTSIDE
    assert not route.starts_automatic_work


@pytest.mark.parametrize("relative", ["ready", "ready/Frieren", "temp", "temp/run-1"])
def test_the_places_owned_by_the_application_never_start_automatic_work(relative: str) -> None:
    assert not resolve_route(Path(relative)).starts_automatic_work


@pytest.mark.parametrize("relative", [".stan", ".stan/subs", "audiobook/.robocze", "subs/.git/objects"])
def test_hidden_data_never_starts_automatic_work(relative: str) -> None:
    route = resolve_route(Path(relative))
    assert route.place is WorkspacePlace.HIDDEN
    assert not route.starts_automatic_work


@pytest.mark.parametrize("relative", ["../obok", "audiobook/../../obok", "subs/.."])
def test_a_path_climbing_out_of_the_workspace_is_outside(relative: str) -> None:
    route = resolve_route(Path(relative))
    assert route.place is WorkspacePlace.OUTSIDE
    assert not route.starts_automatic_work


def test_an_absolute_path_is_never_mistaken_for_a_relative_place(tmp_path: Path) -> None:
    assert resolve_route(tmp_path / "subs").place is WorkspacePlace.OUTSIDE


def test_route_within_reads_a_real_place_under_the_workspace(tmp_path: Path) -> None:
    root = (tmp_path / "workspace").resolve()
    place = root / "translate" / "Notatki"
    place.mkdir(parents=True)
    assert route_within(root, place.resolve()).target is WorkflowTarget.TRANSLATE
    assert route_within(root, root.resolve()) is ROOT_ROUTE


def test_route_within_refuses_a_task_folder_that_really_leads_out(tmp_path: Path) -> None:
    root = (tmp_path / "workspace").resolve()
    root.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    try:
        (root / "cover").symlink_to(elsewhere, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are unavailable on this system")
    escape = (root / "cover").resolve()
    assert route_within(root, escape).place is WorkspacePlace.OUTSIDE
    assert not route_within(root, escape).starts_automatic_work


def test_a_sibling_directory_of_the_workspace_is_outside(tmp_path: Path) -> None:
    root = (tmp_path / "workspace").resolve()
    root.mkdir()
    sibling = (tmp_path / "workspace-kopia").resolve()
    sibling.mkdir()
    assert route_within(root, sibling / "subs").place is WorkspacePlace.OUTSIDE
