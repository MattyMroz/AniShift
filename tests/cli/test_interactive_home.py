from __future__ import annotations

from pathlib import Path

from rich.text import Text

from anishift.cli.interactive.app import _fit_frame, _home_content
from anishift.cli.interactive.home import HomeAction, working_directory_label
from anishift.cli.interactive.mascot import MascotState, mascot_art
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
    assert (medium.show_mascot, medium.show_full_wordmark) == (False, True)
    assert (narrow.show_mascot, narrow.show_full_wordmark, narrow.brand_rows) == (False, False, 1)


def test_auto_geometry_reserves_progress_and_footer_below_the_brand() -> None:
    geometry: AutoGeometry = resolve_auto_geometry(120, 32, 4)

    assert geometry.show_mascot is False
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
