from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from anishift.platform import installed
from anishift.platform.installed import find_installed

pytestmark = pytest.mark.unit

_LOCATIONS: Final[tuple[tuple[str, str], ...]] = (
    ("ANISHIFT_TEST_FIRST_ROOT", "Tool/tool.exe"),
    ("ANISHIFT_TEST_SECOND_ROOT", "Tool/tool.exe"),
)


def _place(root: Path) -> Path:
    executable: Path = root / "Tool" / "tool.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"")
    return executable


def _searched(found: str | None, searched: list[str]) -> object:
    def which(name: str) -> str | None:
        searched.append(name)
        return found

    return which


def test_find_installed_first_location_wins_over_later_and_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first: Path = _place(tmp_path / "first")
    _place(tmp_path / "second")
    searched: list[str] = []
    monkeypatch.setenv("ANISHIFT_TEST_FIRST_ROOT", str(tmp_path / "first"))
    monkeypatch.setenv("ANISHIFT_TEST_SECOND_ROOT", str(tmp_path / "second"))
    monkeypatch.setattr(installed, "which", _searched("elsewhere", searched))

    assert find_installed(_LOCATIONS, "tool") == first
    assert searched == []


def test_find_installed_unset_variable_and_missing_file_are_skipped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ANISHIFT_TEST_FIRST_ROOT", raising=False)
    monkeypatch.setenv("ANISHIFT_TEST_SECOND_ROOT", str(tmp_path / "empty"))
    (tmp_path / "empty" / "Tool" / "tool.exe").mkdir(parents=True)
    monkeypatch.setattr(installed, "which", lambda _name: None)

    assert find_installed(_LOCATIONS, "tool") is None


def test_find_installed_without_locations_searches_path_by_stem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    searched: list[str] = []
    monkeypatch.delenv("ANISHIFT_TEST_FIRST_ROOT", raising=False)
    monkeypatch.delenv("ANISHIFT_TEST_SECOND_ROOT", raising=False)
    monkeypatch.setattr(installed, "which", _searched(str(tmp_path / "tool.exe"), searched))

    assert find_installed(_LOCATIONS, "tool") == tmp_path / "tool.exe"
    assert searched == ["tool"]
