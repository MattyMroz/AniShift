"""Tests for panel-preference load/save (config/settings.json)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from anishift.config import user_settings
from anishift.config.user_settings import (
    UserSettings,
    load_user_settings,
    save_user_settings,
)


@pytest.fixture
def config_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point config_path() at a temp file and return its path."""
    target = tmp_path / "settings.json"
    monkeypatch.setattr(user_settings, "config_path", lambda: target)
    return target


@pytest.mark.usefixtures("config_file")
def test_load_missing_file_returns_defaults() -> None:
    settings = load_user_settings()
    assert settings == UserSettings()
    assert settings.mode == "auto"
    assert settings.move_results_to_output is False


@pytest.mark.usefixtures("config_file")
def test_save_then_load_roundtrip() -> None:
    save_user_settings(UserSettings(mode="manual", move_results_to_output=True))
    loaded = load_user_settings()
    assert loaded.mode == "manual"
    assert loaded.move_results_to_output is True


def test_save_creates_parent_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "config" / "settings.json"
    monkeypatch.setattr(user_settings, "config_path", lambda: nested)
    save_user_settings(UserSettings())
    assert nested.is_file()


def test_load_ignores_unknown_keys(config_file: Path) -> None:
    config_file.write_text(json.dumps({"mode": "manual", "bogus": 123}), encoding="utf-8")
    loaded = load_user_settings()
    assert loaded.mode == "manual"
    assert not hasattr(loaded, "bogus")


def test_load_invalid_mode_falls_back_to_default(config_file: Path) -> None:
    config_file.write_text(json.dumps({"mode": "nonsense"}), encoding="utf-8")
    assert load_user_settings().mode == "auto"


def test_load_corrupt_json_returns_defaults(config_file: Path) -> None:
    config_file.write_text("{ not valid json ", encoding="utf-8")
    assert load_user_settings() == UserSettings()


def test_load_non_object_json_returns_defaults(config_file: Path) -> None:
    config_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert load_user_settings() == UserSettings()
