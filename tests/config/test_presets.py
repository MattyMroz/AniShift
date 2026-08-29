from __future__ import annotations

import json
from pathlib import Path

import pytest

from anishift.application.intents import (
    AutoPreset,
    BurnSubtitleProduct,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductIntent,
    ProductKind,
    SubtitleSourcePolicy,
)
from anishift.config.presets import (
    AutoPresetFile,
    default_preset_file,
    load_presets,
    save_presets,
)


@pytest.fixture
def preset_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "presets.json"
    monkeypatch.setattr("anishift.config.presets.presets_path", lambda: path)
    return path


def _full_preset() -> AutoPreset:
    return AutoPreset(
        preset_id="full",
        name="Full workflow",
        products=ProductIntent(
            requested_products=frozenset(
                {ProductKind.FULL_PL, ProductKind.NARRATION_AUDIO, ProductKind.MKV, ProductKind.MP4}
            ),
            burn_subtitle_product=BurnSubtitleProduct.DISPLAYED_PL,
            mkv_tracks=frozenset({MkvTrackProduct.FULL_PL_SUBTITLES, MkvTrackProduct.NARRATION_AUDIO}),
            mp4_audio_source=Mp4AudioSource.NARRATION,
        ),
    )


def test_missing_preset_file_returns_defaults_without_writing(preset_file: Path) -> None:
    loaded = load_presets()

    assert loaded == default_preset_file()
    assert not preset_file.exists()


def test_default_preset_requests_polish_subtitles_and_narration() -> None:
    preset = default_preset_file().presets[0]

    assert preset.products.requested_products == frozenset({ProductKind.FULL_PL, ProductKind.NARRATION_AUDIO})


def test_presets_round_trip_atomically(preset_file: Path) -> None:
    document = AutoPresetFile(
        schema_version=1, presets=(default_preset_file().presets[0], _full_preset()), default_preset_id="full"
    )

    save_presets(document)

    assert load_presets() == document
    assert not preset_file.with_name("presets.json.tmp").exists()


def test_one_invalid_preset_rejects_the_whole_file(preset_file: Path) -> None:
    document = {
        "schema_version": 1,
        "default_preset_id": "default",
        "presets": [
            {
                "preset_id": "default",
                "name": "Valid",
                "products": {
                    "requested_products": ["full_pl"],
                    "burn_subtitle_product": "none",
                    "mkv_tracks": [],
                    "mp4_audio_source": "auto",
                },
                "subtitle_source_policy": "auto",
                "translation_action": "auto",
                "source_subtitle_language": None,
                "subtitle_output_format": "preserve",
            },
            {"preset_id": "broken"},
        ],
    }
    preset_file.write_text(json.dumps(document), encoding="utf-8")

    assert load_presets() == default_preset_file()


def test_secret_like_unknown_field_invalidates_preset_file(preset_file: Path) -> None:
    save_presets(default_preset_file())
    document = json.loads(preset_file.read_text(encoding="utf-8"))
    document["presets"][0]["api_key"] = "secret"
    preset_file.write_text(json.dumps(document), encoding="utf-8")

    assert load_presets() == default_preset_file()


def test_duplicate_preset_ids_are_rejected() -> None:
    preset = default_preset_file().presets[0]

    with pytest.raises(ValueError, match="unique"):
        AutoPresetFile(schema_version=1, presets=(preset, preset), default_preset_id=preset.preset_id)


@pytest.mark.parametrize(
    "policy",
    [SubtitleSourcePolicy.EXTERNAL, SubtitleSourcePolicy.READY_POLISH],
)
def test_auto_preset_rejects_manual_only_subtitle_policy(policy: SubtitleSourcePolicy) -> None:
    with pytest.raises(ValueError, match="manual subtitle"):
        AutoPreset(
            preset_id="invalid",
            name="Invalid",
            products=ProductIntent(requested_products=frozenset({ProductKind.FULL_PL})),
            subtitle_source_policy=policy,
        )
