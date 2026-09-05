from __future__ import annotations

from pathlib import Path

import pytest
from rich.text import Text

from anishift.cli.interactive.app import _fit_frame, _home_content
from anishift.cli.interactive.home import HomeAction, brand_for_geometry, working_directory_label
from anishift.cli.interactive.mascot import MascotState, mascot_art
from anishift.cli.interactive.mascot_native import NATIVE_MASCOT_ANCHOR
from anishift.cli.interactive.prompts import (
    AutoGeometry,
    HomeGeometry,
    resolve_auto_geometry,
    resolve_home_geometry,
    status_line,
)


def test_home_offers_exactly_four_actions_in_the_required_order() -> None:
    content: Text = _home_content(120, 40, 0, MascotState.IDLE)
    labels: list[str] = ["Auto", "Ręczny", "Ustawienia", "Wyjście"]
    rows: list[str] = [line.strip().removeprefix("\u276f").strip() for line in content.plain.split("\n")]

    assert [row for row in rows if row][-5:] == [*labels, "↑↓ · Enter"]
    assert len(HomeAction) == len(labels)


def test_the_footer_keeps_the_directory_and_version_at_opposite_edges() -> None:
    frame: Text = _fit_frame(Text(), "0.1.0", r"~\Desktop\PROJECTS\AniShift", 80, 10)
    lines: list[str] = frame.plain.split("\n")

    assert len(lines) == 10
    assert lines[-1].startswith(r"~\Desktop\PROJECTS\AniShift")
    assert lines[-1].endswith("v0.1.0")
    assert len(lines[-1]) == 79


def test_a_narrow_footer_truncates_the_directory_before_the_version() -> None:
    status: str = status_line("0.1.0", r"~\Desktop\PROJECTS\AniShift", 20)

    assert status.startswith("…")
    assert status.endswith("v0.1.0")
    assert status.count("v0.1.0") == 1
    assert len(status) == 19


def test_home_geometry_preserves_a_fixed_brand_and_falls_back_to_a_compact_layout() -> None:
    wide: HomeGeometry = resolve_home_geometry(120, 30)
    medium: HomeGeometry = resolve_home_geometry(60, 16)
    narrow: HomeGeometry = resolve_home_geometry(50, 12)

    assert (wide.mascot_columns, wide.mascot_rows, wide.brand_rows) == (18, 10, 10)
    assert (wide.show_mascot, wide.show_full_wordmark) == (True, True)
    assert (medium.show_mascot, medium.show_full_wordmark, medium.brand_rows) == (False, False, 1)
    assert (narrow.show_mascot, narrow.show_full_wordmark, narrow.brand_rows) == (False, False, 1)


def test_auto_geometry_reserves_progress_and_footer_below_the_brand() -> None:
    geometry: AutoGeometry = resolve_auto_geometry(120, 32, 4)

    assert geometry.show_mascot is True
    assert geometry.show_full_wordmark is True
    assert geometry.progress_row > geometry.top_padding
    assert geometry.progress_row >= geometry.top_padding + geometry.brand_rows
    assert geometry.progress_row + 4 <= geometry.terminal_rows - 1


def test_the_working_directory_stays_relative_to_the_user_home() -> None:
    inside: str = working_directory_label(Path("/users/tester/Desktop/AniShift"), Path("/users/tester"))
    outside: str = working_directory_label(Path("/opt/anishift"), Path("/users/tester"))

    assert inside == r"~\Desktop\AniShift"
    assert outside == "anishift"


def test_the_mascot_asset_renders_to_the_requested_terminal_size() -> None:
    mascot: Text | None = mascot_art(20, 8)

    assert mascot is not None
    assert len(mascot.split("\n")) == 8
    assert mascot.cell_len > 0


@pytest.mark.parametrize("columns", [120, 80, 60, 35, 22])
def test_a_narrow_home_keeps_the_slime_and_uses_a_fitting_wordmark(columns: int) -> None:
    geometry = resolve_home_geometry(columns, 30)
    brand = brand_for_geometry(geometry, native_mascot=True)

    assert geometry.show_mascot
    assert NATIVE_MASCOT_ANCHOR in brand.plain
    assert all(line.cell_len <= columns for line in brand.split("\n"))


def test_the_wordmark_stays_still_while_the_native_slime_animates() -> None:
    geometry = resolve_home_geometry(120, 30)
    frames: list[Text] = [
        brand_for_geometry(geometry, native_mascot=True, animation_phase=phase) for phase in range(24)
    ]
    positions: list[int] = [frame.plain.index(NATIVE_MASCOT_ANCHOR) for frame in frames]

    assert len(set(positions)) == 1
    assert {len(frame.split("\n")) for frame in frames} == {geometry.brand_rows}
    assert all(frame == frames[0] for frame in frames)


@pytest.mark.parametrize("auto", [False, True])
def test_native_raster_padding_does_not_lower_the_wordmark(auto: bool) -> None:
    geometry: HomeGeometry | AutoGeometry = (
        resolve_auto_geometry(120, 40, 4, (18, 11)) if auto else resolve_home_geometry(120, 40, (18, 11))
    )
    frame = brand_for_geometry(geometry, native_mascot=True)
    lines: list[str] = frame.plain.split("\n")
    anchor: int = next(index for index, line in enumerate(lines) if NATIVE_MASCOT_ANCHOR in line)
    wordmark_bottom: int = max(index for index, line in enumerate(lines) if "═" in line)

    assert wordmark_bottom - anchor == 9
    assert len(lines) == 11


@pytest.mark.parametrize("columns", [35, 50, 60, 75])
def test_only_the_slime_remains_when_the_full_wordmark_cannot_fit(columns: int) -> None:
    geometry = resolve_home_geometry(columns, 30)
    brand = brand_for_geometry(geometry, native_mascot=True)

    assert geometry.show_mascot
    assert not geometry.show_full_wordmark
    assert brand.plain.strip() == NATIVE_MASCOT_ANCHOR


def test_the_text_slime_bounces_without_changing_its_reservation() -> None:
    geometry = resolve_home_geometry(22, 30)
    resting = brand_for_geometry(geometry, animation_phase=0)
    jumping = brand_for_geometry(geometry, animation_phase=11)

    assert resting.plain != jumping.plain
    assert len(resting.split("\n")) == len(jumping.split("\n")) == geometry.brand_rows


@pytest.mark.parametrize("rows", [3, 4, 6, 8, 10, 12, 24])
@pytest.mark.parametrize("selected", [0, 1, 2, 3])
def test_small_home_always_keeps_the_selected_action_visible(rows: int, selected: int) -> None:
    content = _home_content(80, rows, selected, MascotState.IDLE)
    frame = _fit_frame(content, "1.0.0", "workspace", 80, rows)

    assert "\u276f" in frame.plain
    assert ("Auto", "Ręczny", "Ustawienia", "Wyjście")[selected] in frame.plain
    assert frame.plain.split("\n")[-1].endswith("v1.0.0")


@pytest.mark.parametrize("size", [(120, 40), (120, 41), (80, 24), (60, 30), (30, 24), (80, 12)])
def test_home_balances_the_gaps_above_and_below_the_menu(size: tuple[int, int]) -> None:
    columns, rows = size
    content = _home_content(columns, rows, 0, MascotState.IDLE, native_size=(18, 11))
    frame = _fit_frame(content, "1.0.0", "workspace", columns, rows)
    lines: list[str] = frame.plain.split("\n")
    menu_top: int = next(index for index, line in enumerate(lines) if "Auto" in line)
    menu_bottom: int = next(index for index, line in enumerate(lines) if "↑↓" in line)
    brand_bottom: int = max(index for index, line in enumerate(lines[:menu_top]) if line.strip())
    geometry = resolve_home_geometry(columns, rows, (18, 11))
    if geometry.show_mascot:
        anchor: int = next(index for index, line in enumerate(lines) if NATIVE_MASCOT_ANCHOR in line)
        brand_bottom = max(brand_bottom, anchor + geometry.mascot_rows - 1)
    above: int = menu_top - brand_bottom - 1
    below: int = rows - menu_bottom - 2

    assert abs(above - below) <= 1


@pytest.mark.parametrize("size", [(120, 40), (120, 41), (80, 30), (60, 30)])
@pytest.mark.parametrize("phase", [0, 11, 19])
def test_home_padding_uses_resting_silhouette_and_excludes_footer(size: tuple[int, int], phase: int) -> None:
    columns, rows = size
    content = _home_content(columns, rows, 0, MascotState.IDLE, native_size=(18, 11), animation_phase=phase)
    frame = _fit_frame(content, "1.0.0", "workspace", columns, rows)
    lines: list[str] = frame.plain.split("\n")
    anchor: int = next(index for index, line in enumerate(lines) if NATIVE_MASCOT_ANCHOR in line)
    menu_top: int = next(index for index, line in enumerate(lines) if "Auto" in line)
    menu_bottom: int = next(index for index, line in enumerate(lines) if "↑↓" in line)
    gaps: tuple[int, int, int] = (anchor + 3, menu_top - anchor - 11, rows - menu_bottom - 2)

    assert max(gaps) - min(gaps) <= 1
    assert lines[-1].endswith("v1.0.0")
