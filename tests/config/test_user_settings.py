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


def test_load_non_utf8_file_returns_defaults(config_file: Path) -> None:
    config_file.write_bytes(b"\xff\xfe not utf-8 \x80\x81")
    assert load_user_settings() == UserSettings()


@pytest.mark.usefixtures("config_file")
def test_defaults_include_all_panel_fields() -> None:
    s = UserSettings()
    assert s.translation_engine == "google"
    assert s.tts_engine == "edge"
    assert s.voice == "pl-PL-MarekNeural"
    assert s.tempo == 1.0
    assert s.volume == 100
    assert s.output_variant == "merge"


@pytest.mark.usefixtures("config_file")
def test_full_roundtrip_preserves_every_field() -> None:
    original = UserSettings(
        mode="manual",
        translation_engine="deepl",
        tts_engine="elevenlabs",
        voice="pl-PL-ZofiaNeural",
        tempo=1.25,
        volume=80,
        output_variant="burn",
        move_results_to_output=True,
    )
    save_user_settings(original)
    assert load_user_settings() == original


def test_load_out_of_range_tempo_falls_back_to_default(config_file: Path) -> None:
    config_file.write_text(json.dumps({"tempo": 9.0}), encoding="utf-8")
    assert load_user_settings().tempo == 1.0


def test_load_out_of_range_volume_falls_back_to_default(config_file: Path) -> None:
    config_file.write_text(json.dumps({"volume": 500}), encoding="utf-8")
    assert load_user_settings().volume == 100


def test_load_invalid_output_variant_falls_back_to_default(config_file: Path) -> None:
    config_file.write_text(json.dumps({"output_variant": "bogus"}), encoding="utf-8")
    assert load_user_settings().output_variant == "merge"


def test_load_wrong_typed_tempo_falls_back_to_default(config_file: Path) -> None:
    config_file.write_text(json.dumps({"tempo": "fast"}), encoding="utf-8")
    assert load_user_settings().tempo == 1.0


@pytest.mark.parametrize("raw", ["false", "true", 1, 0, None])
def test_load_wrong_typed_move_results_falls_back_to_default(raw: object, config_file: Path) -> None:
    config_file.write_text(json.dumps({"move_results_to_output": raw}), encoding="utf-8")
    assert load_user_settings().move_results_to_output is False
