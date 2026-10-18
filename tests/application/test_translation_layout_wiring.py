from __future__ import annotations

import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Final, cast

import pytest

from anishift.application.control_payloads import decode_intent
from anishift.application.planning import ExecutionPlan, ProcessingOrderPolicy, RunSettingsSnapshot, TaskKind
from anishift.application.runtime import _chunk_config, _dialogue_font, _layout_limits
from anishift.application.translation_handler import text_spoken_lines
from anishift.config.user_settings import UserSettings
from anishift.services.subtitles.layout import LayoutLimits
from anishift.services.translation.chunk_config import ChunkConfig

_SYSTEM_ARIAL: Final[Path] = Path("C:/Windows/Fonts/arial.ttf")


def _snapshot(**changes: object) -> RunSettingsSnapshot:
    defaults: dict[str, object] = {
        "translation_profile_id": "google",
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
    assert _layout_limits(_plan(snapshot)) == LayoutLimits(max_chars=60, max_lines=3)
    assert _chunk_config(_plan(snapshot)) == ChunkConfig(chunk_chars=1200)


def test_a_larger_context_produces_fewer_narrator_lines() -> None:
    text = "\n\n".join(f"Akapit numer {index} z tekstem, ktory zajmuje trochę miejsca." for index in range(40))
    small = text_spoken_lines(text, ChunkConfig(chunk_chars=300))
    large = text_spoken_lines(text, ChunkConfig(chunk_chars=3000))
    assert len(small) > len(large)


def test_the_default_layout_is_used_when_none_is_supplied() -> None:
    text = "\n\n".join(f"Akapit numer {index} z tekstem, ktory zajmuje trochę miejsca." for index in range(40))
    assert text_spoken_lines(text) == text_spoken_lines(text, ChunkConfig())


def test_a_stored_snapshot_without_the_dialogue_font_decodes_with_it_turned_off() -> None:
    stored: dict[str, object] = {
        key: value for key, value in asdict(_snapshot()).items() if key != "dialogue_font_file"
    }

    assert decode_intent(RunSettingsSnapshot, stored).dialogue_font_file == ""
    assert UserSettings().dialogue_font_file == _snapshot().dialogue_font_file == ""


@pytest.mark.skipif(not _SYSTEM_ARIAL.is_file(), reason="the Windows Arial font is not available")
def test_the_runtime_builds_the_dialogue_font_from_the_snapshot_for_layout_and_containers(tmp_path: Path) -> None:
    font: Path = Path(shutil.copyfile(_SYSTEM_ARIAL, tmp_path / "arial.ttf"))
    plan: ExecutionPlan = _plan(_snapshot(dialogue_font_file=str(font)))

    built = _dialogue_font(plan, frozenset({TaskKind.COMPOSE_MKV}))

    assert built is not None
    assert (built.family, built.files) == ("Arial", (font,))
    assert _dialogue_font(plan, frozenset({TaskKind.SYNTHESIZE_SPEECH})) is None


def test_the_runtime_keeps_the_episode_fonts_when_the_dialogue_font_is_unusable_or_unset(tmp_path: Path) -> None:
    kinds: frozenset[TaskKind] = frozenset({TaskKind.TRANSLATE_SUBTITLES})

    assert _dialogue_font(_plan(_snapshot(dialogue_font_file=str(tmp_path / "gone.ttf"))), kinds) is None
    assert _dialogue_font(_plan(_snapshot()), kinds) is None
