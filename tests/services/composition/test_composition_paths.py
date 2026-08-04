from __future__ import annotations

from pathlib import Path

import pytest

from anishift.services.composition.paths import (
    escape_filter_path,
    filter_safe_copy,
    output_path,
    temporary_sibling,
)
from anishift.services.composition.types import OutputVariant


@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        (OutputVariant.MERGE, "Episode.pl.mkv"),
        (OutputVariant.BURN, "Episode.pl.mp4"),
    ],
)
def test_output_path_uses_polish_infix(tmp_path: Path, variant: OutputVariant, expected: str) -> None:
    result = output_path(tmp_path / "Episode.mkv", variant, tmp_path / "output")

    assert result.name == expected
    assert result.parent == tmp_path / "output"


def test_output_path_keeps_polish_characters_and_spaces(tmp_path: Path) -> None:
    source = tmp_path / "Zażółć gęślą jaźń - 04 [1080p].mkv"

    result = output_path(source, OutputVariant.MERGE, tmp_path)

    assert result.name == "Zażółć gęślą jaźń - 04 [1080p].pl.mkv"


def test_escape_filter_path_escapes_drive_colon_and_brackets() -> None:
    escaped = escape_filter_path(Path("C:/anime/[Erai-raws] show - 04.ass"))

    assert escaped.startswith("'")
    assert escaped.endswith("'")
    assert "C\\:" in escaped
    assert "\\[" in escaped
    assert "\\]" in escaped


def test_escape_filter_path_uses_forward_slashes() -> None:
    assert escape_filter_path(Path("C:\\anime\\show.ass")) == "'C\\:/anime/show.ass'"


def test_filter_safe_copy_strips_apostrophes(tmp_path: Path) -> None:
    source = tmp_path / "Heroine Saint No, I'm an All-Works Maid.ass"
    source.write_text("[Script Info]\n", encoding="utf-8")
    work_dir = tmp_path / "work"

    copy = filter_safe_copy(source, work_dir)

    assert "'" not in copy.name
    assert copy.exists()
    assert copy.read_text(encoding="utf-8") == "[Script Info]\n"


def test_filter_safe_copy_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "show's episode.ass"
    source.write_text("x", encoding="utf-8")
    work_dir = tmp_path / "work"

    first = filter_safe_copy(source, work_dir)
    second = filter_safe_copy(source, work_dir)

    assert first == second


def test_filter_safe_copy_refreshes_changed_content(tmp_path: Path) -> None:
    source = tmp_path / "show's episode.ass"
    source.write_text("first", encoding="utf-8")
    work_dir = tmp_path / "work"
    filter_safe_copy(source, work_dir)
    source.write_text("second", encoding="utf-8")

    copy = filter_safe_copy(source, work_dir)

    assert copy.read_text(encoding="utf-8") == "second"


def test_filter_safe_copy_separates_names_equal_after_stripping(tmp_path: Path) -> None:
    first_source = tmp_path / "show's episode.ass"
    second_source = tmp_path / "shows episode.ass"
    first_source.write_text("a", encoding="utf-8")
    second_source.write_text("bb", encoding="utf-8")
    work_dir = tmp_path / "work"

    assert filter_safe_copy(first_source, work_dir) != filter_safe_copy(second_source, work_dir)


def test_temporary_sibling_lives_next_to_destination(tmp_path: Path) -> None:
    destination = tmp_path / "output" / "Episode.pl.mkv"

    temporary = temporary_sibling(destination)

    assert temporary.parent == destination.parent
    assert temporary.name.endswith(".tmp.mkv")
    assert temporary.exists()
