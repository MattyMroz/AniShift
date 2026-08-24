from __future__ import annotations

from pathlib import Path

import pytest

from anishift.application.artifacts import SourceGroup
from anishift.application.intents import (
    AutoPreset,
    BurnSubtitleProduct,
    ExternalAudioRole,
    GroupIntent,
    MkvTrackProduct,
    ProductIntent,
    ProductKind,
    RunMode,
    SubtitleSourcePolicy,
    TranslationAction,
    apply_preset,
)


def _products() -> ProductIntent:
    return ProductIntent(requested_products=frozenset({ProductKind.FULL_PL}))


def test_product_intent_rejects_container_options_without_container() -> None:
    with pytest.raises(ValueError, match="MKV product"):
        ProductIntent(
            requested_products=frozenset({ProductKind.FULL_PL}),
            mkv_tracks=frozenset({MkvTrackProduct.FULL_PL_SUBTITLES}),
        )


def test_product_intent_rejects_burn_without_mp4() -> None:
    with pytest.raises(ValueError, match="MP4 product"):
        ProductIntent(
            requested_products=frozenset({ProductKind.MKV}),
            burn_subtitle_product=BurnSubtitleProduct.FULL_PL,
        )


def test_auto_intent_rejects_manual_artifact_selection() -> None:
    with pytest.raises(ValueError, match="Automatic intent"):
        GroupIntent(
            group_id="episode",
            mode=RunMode.AUTO,
            products=_products(),
            selected_subtitle_artifact_id="subtitle-fra",
        )


def test_manual_intent_accepts_external_audio_role() -> None:
    intent = GroupIntent(
        group_id="episode",
        mode=RunMode.MANUAL,
        products=ProductIntent(requested_products=frozenset({ProductKind.NARRATION_AUDIO})),
        selected_audio_artifact_id="external-audio",
        external_audio_role=ExternalAudioRole.SOURCE_AUDIO,
    )
    assert intent.external_audio_role is ExternalAudioRole.SOURCE_AUDIO


def test_manual_intent_rejects_two_subtitle_sources() -> None:
    with pytest.raises(ValueError, match="not both"):
        GroupIntent(
            group_id="episode",
            mode=RunMode.MANUAL,
            products=_products(),
            selected_subtitle_artifact_id="sidecar",
            selected_subtitle_track_id=2,
        )


def test_apply_preset_creates_one_independent_auto_intent_per_group() -> None:
    groups = (
        SourceGroup("episode-1", "episode-1", Path("workspace"), ()),
        SourceGroup("episode-2", "episode-2", Path("workspace"), ()),
    )
    preset = AutoPreset(
        preset_id="default",
        name="Default",
        products=_products(),
        subtitle_source_policy=SubtitleSourcePolicy.SIDECAR,
        translation_action=TranslationAction.TRANSLATE,
        source_subtitle_language="eng",
    )
    intents = apply_preset(preset, groups)
    assert tuple(intent.group_id for intent in intents) == ("episode-1", "episode-2")
    assert intents[0] is not intents[1]
    assert all(intent.mode is RunMode.AUTO for intent in intents)
    assert all(intent.translation_action is TranslationAction.TRANSLATE for intent in intents)


def test_apply_preset_rejects_duplicate_group_ids() -> None:
    groups = (
        SourceGroup("episode", "first", Path("workspace"), ()),
        SourceGroup("episode", "second", Path("workspace"), ()),
    )
    preset = AutoPreset("default", "Default", _products())
    with pytest.raises(ValueError, match="unique"):
        apply_preset(preset, groups)
