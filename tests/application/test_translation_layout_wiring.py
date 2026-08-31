from __future__ import annotations

from typing import cast

from anishift.application.planning import ExecutionPlan, ProcessingOrderPolicy, RunSettingsSnapshot
from anishift.application.runtime import _layout_config
from anishift.application.translation_handler import text_spoken_lines
from anishift.config.user_settings import UserSettings
from anishift.services.translation.layout_config import LayoutConfig


def _snapshot(**changes: object) -> RunSettingsSnapshot:
    defaults: dict[str, object] = {
        "translation_profile_id": "google",
        "translation_fallback_chain": ("deepl",),
        "translation_max_retries": 3,
        "translation_concurrency": 2,
        "llm_profile_id": "gemini",
        "llm_max_concurrency": 2,
        "tts_profile_id": "elevenbytes",
        "tts_max_retries": 3,
        "tts_group_jobs": 1,
        "audio_profile_id": "eac3",
        "composition_profile_id": "mkv",
        "processing_order_policy": ProcessingOrderPolicy.READY_FIRST,
    }
    return RunSettingsSnapshot(**{**defaults, **changes})  # type: ignore[arg-type]


def _plan(snapshot: RunSettingsSnapshot) -> ExecutionPlan:
    return cast("ExecutionPlan", type("_Plan", (), {"settings": snapshot})())


def test_the_snapshot_carries_the_shipped_layout_defaults() -> None:
    snapshot = _snapshot()
    assert snapshot.subtitle_max_chars_per_line == 42
    assert snapshot.subtitle_max_lines_per_event == 2
    assert snapshot.translation_chunk_chars == 750


def test_user_settings_and_the_snapshot_agree_on_the_defaults() -> None:
    settings = UserSettings()
    snapshot = _snapshot()
    assert settings.subtitle_max_chars_per_line == snapshot.subtitle_max_chars_per_line
    assert settings.subtitle_max_lines_per_event == snapshot.subtitle_max_lines_per_event
    assert settings.translation_chunk_chars == snapshot.translation_chunk_chars


def test_the_runtime_carries_every_chosen_limit_into_the_layout() -> None:
    snapshot = _snapshot(
        subtitle_max_chars_per_line=60,
        subtitle_max_lines_per_event=3,
        translation_chunk_chars=1200,
    )
    layout = _layout_config(_plan(snapshot))
    assert layout == LayoutConfig(max_chars_per_line=60, max_lines_per_event=3, chunk_chars=1200)


def test_a_larger_context_produces_fewer_narrator_lines() -> None:
    text = "\n\n".join(f"Akapit numer {index} z tekstem, ktory zajmuje trochę miejsca." for index in range(40))
    small = text_spoken_lines(text, LayoutConfig(chunk_chars=300))
    large = text_spoken_lines(text, LayoutConfig(chunk_chars=3000))
    assert len(small) > len(large)


def test_the_default_layout_is_used_when_none_is_supplied() -> None:
    text = "\n\n".join(f"Akapit numer {index} z tekstem, ktory zajmuje trochę miejsca." for index in range(40))
    assert text_spoken_lines(text) == text_spoken_lines(text, LayoutConfig())
