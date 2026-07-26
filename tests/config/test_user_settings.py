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
    assert s.llm_provider == "gemini"
    assert s.llm_provider_model_id == "gemini-3.5-flash-lite"
    assert s.llm_max_concurrency == 4


@pytest.mark.usefixtures("config_file")
def test_full_roundtrip_preserves_every_field() -> None:
    prompt_root = user_settings.config_path().parent / "prompts"
    for directory, name in (
        ("tasks", "custom_task.txt"),
        ("styles", "custom_style.txt"),
        ("modules", "honorifics.txt"),
        ("modules", "names.txt"),
    ):
        path = prompt_root / directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name, encoding="utf-8")
    original = UserSettings(
        mode="manual",
        translation_engine="deepl",
        tts_engine="elevenlabs",
        voice="pl-PL-ZofiaNeural",
        tempo=1.25,
        volume=80,
        output_variant="burn",
        move_results_to_output=True,
        llm_provider="openrouter",
        llm_provider_model_id="vendor/custom-model",
        llm_temperature=0.2,
        llm_top_p=0.9,
        llm_max_output_tokens=4096,
        llm_prompt_id="custom_task",
        llm_style_id="custom_style",
        llm_module_ids=["honorifics", "names"],
        llm_max_concurrency=3,
    )
    save_user_settings(original)
    assert load_user_settings() == original


def test_load_stale_prompt_selection_falls_back_to_defaults(config_file: Path) -> None:
    config_file.write_text(
        json.dumps(
            {
                "llm_prompt_id": "missing_task",
                "llm_style_id": "missing_style",
                "llm_module_ids": ["missing_module"],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_user_settings()

    assert loaded.llm_prompt_id == UserSettings().llm_prompt_id
    assert loaded.llm_style_id == UserSettings().llm_style_id
    assert loaded.llm_module_ids == []


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


def test_load_migrates_legacy_llm_model(config_file: Path) -> None:
    config_file.write_text(json.dumps({"llm_model": " legacy/model "}), encoding="utf-8")
    loaded = load_user_settings()
    assert loaded.llm_provider_model_id == "legacy/model"


def test_load_prefers_new_llm_model_field(config_file: Path) -> None:
    config_file.write_text(
        json.dumps(
            {
                "llm_model": "legacy/model",
                "llm_provider_model_id": "new/model",
            }
        ),
        encoding="utf-8",
    )
    loaded = load_user_settings()
    assert loaded.llm_provider_model_id == "new/model"


def test_load_optional_llm_values_accept_none(config_file: Path) -> None:
    config_file.write_text(
        json.dumps(
            {
                "llm_temperature": None,
                "llm_top_p": None,
                "llm_max_output_tokens": None,
            }
        ),
        encoding="utf-8",
    )
    loaded = load_user_settings()
    assert loaded.llm_temperature is None
    assert loaded.llm_top_p is None
    assert loaded.llm_max_output_tokens is None


@pytest.mark.parametrize("value", [0, 5, "4", True])
def test_load_invalid_llm_concurrency_uses_default(value: object, config_file: Path) -> None:
    config_file.write_text(json.dumps({"llm_max_concurrency": value}), encoding="utf-8")
    assert load_user_settings().llm_max_concurrency == 4


@pytest.mark.parametrize("raw", ["false", "true", 1, 0, None])
def test_load_wrong_typed_move_results_falls_back_to_default(raw: object, config_file: Path) -> None:
    config_file.write_text(json.dumps({"move_results_to_output": raw}), encoding="utf-8")
    assert load_user_settings().move_results_to_output is False
