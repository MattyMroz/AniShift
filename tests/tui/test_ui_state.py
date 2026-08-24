from __future__ import annotations

import json
from pathlib import Path

import pytest

from anishift.config.user_settings import config_path
from anishift.tui import ui_state
from anishift.tui.theme import DARK_THEME_ID, LIGHT_THEME_ID
from anishift.tui.ui_state import UiState, load_ui_state, save_ui_state, ui_state_path


@pytest.fixture
def state_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target = tmp_path / "ui_state.json"
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: target)
    return target


def test_ui_state_file_sits_next_to_settings_json() -> None:
    assert ui_state_path().parent == config_path().parent
    assert ui_state_path().name == "ui_state.json"


@pytest.mark.usefixtures("state_file")
def test_missing_file_returns_the_dark_default() -> None:
    assert load_ui_state() == UiState()
    assert load_ui_state().theme == DARK_THEME_ID


@pytest.mark.usefixtures("state_file")
def test_save_then_load_roundtrip() -> None:
    save_ui_state(UiState(theme=LIGHT_THEME_ID))
    assert load_ui_state().theme == LIGHT_THEME_ID


def test_save_creates_the_parent_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "config" / "ui_state.json"
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: nested)
    save_ui_state(UiState())
    assert nested.is_file()


def test_save_leaves_no_temporary_file_behind(state_file: Path) -> None:
    save_ui_state(UiState(theme=LIGHT_THEME_ID))
    assert sorted(path.name for path in state_file.parent.iterdir()) == ["ui_state.json"]


def test_saved_payload_is_readable_json(state_file: Path) -> None:
    save_ui_state(UiState(theme=LIGHT_THEME_ID))
    assert json.loads(state_file.read_text(encoding="utf-8")) == {"theme": LIGHT_THEME_ID}


def test_corrupt_json_falls_back_to_the_default(state_file: Path) -> None:
    state_file.write_text("{ not json", encoding="utf-8")
    assert load_ui_state() == UiState()


def test_non_object_json_falls_back_to_the_default(state_file: Path) -> None:
    state_file.write_text(json.dumps(["anishift-light"]), encoding="utf-8")
    assert load_ui_state() == UiState()


def test_unknown_theme_falls_back_to_the_default(state_file: Path) -> None:
    state_file.write_text(json.dumps({"theme": "solarized"}), encoding="utf-8")
    assert load_ui_state() == UiState()


def test_wrong_typed_theme_falls_back_to_the_default(state_file: Path) -> None:
    state_file.write_text(json.dumps({"theme": 7}), encoding="utf-8")
    assert load_ui_state() == UiState()


def test_unknown_keys_are_ignored(state_file: Path) -> None:
    state_file.write_text(
        json.dumps({"theme": LIGHT_THEME_ID, "bogus": 123}),
        encoding="utf-8",
    )
    loaded = load_ui_state()
    assert loaded == UiState(theme=LIGHT_THEME_ID)
    assert not hasattr(loaded, "bogus")
