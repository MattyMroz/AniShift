from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from anishift.config.user_settings import UserSettings
from anishift.setup import fonts


def _prepare(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, settings: UserSettings, code: int = 0) -> dict[str, Any]:
    seen: dict[str, Any] = {"saved": None, "commands": []}

    def _run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        seen["commands"].append(command)
        if code == 0:
            font: Path = tmp_path / "fonts" / fonts.DIALOGUE_FONT
            font.parent.mkdir(parents=True, exist_ok=True)
            font.write_bytes(b"font")
        return subprocess.CompletedProcess(command, code, b"", b"")

    def _save(value: UserSettings) -> None:
        seen["saved"] = value

    monkeypatch.setattr(fonts, "external_dir", lambda: tmp_path)
    monkeypatch.setattr(shutil, "which", lambda name: f"C:/tools/{name}.exe")
    monkeypatch.setattr(subprocess, "run", _run)
    monkeypatch.setattr(fonts, "load_user_settings", lambda: settings)
    monkeypatch.setattr(fonts, "save_user_settings", _save)
    return seen


@pytest.mark.unit
def test_install_fonts_clones_the_repository_and_chooses_its_dialogue_font(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, Any] = _prepare(monkeypatch, tmp_path, UserSettings())

    result = fonts.install_fonts()

    assert result.outcome == "installed"
    assert seen["commands"][0][:3] == ["gh", "repo", "clone"]
    assert seen["saved"].dialogue_font_file == str(tmp_path / "fonts" / fonts.DIALOGUE_FONT)


@pytest.mark.unit
def test_install_fonts_updates_an_existing_clone_and_keeps_a_chosen_font(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "fonts" / ".git").mkdir(parents=True)
    seen: dict[str, Any] = _prepare(monkeypatch, tmp_path, UserSettings(dialogue_font_file="C:/own.ttf"))

    result = fonts.install_fonts()

    assert result.outcome == "installed"
    assert seen["commands"][0][3:5] == ["pull", "--ff-only"]
    assert seen["saved"] is None


@pytest.mark.unit
def test_install_fonts_skips_without_access_to_the_repository(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seen: dict[str, Any] = _prepare(monkeypatch, tmp_path, UserSettings(), code=1)

    result = fonts.install_fonts()

    assert result.outcome == "skipped"
    assert seen["saved"] is None


@pytest.mark.unit
def test_install_fonts_skips_when_the_tool_is_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _prepare(monkeypatch, tmp_path, UserSettings())
    monkeypatch.setattr(shutil, "which", lambda name: None)

    assert fonts.install_fonts().outcome == "skipped"
