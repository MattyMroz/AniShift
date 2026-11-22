from __future__ import annotations

import shutil
from pathlib import Path
from typing import Final

import pytest

from anishift.application.planning import ProcessingOrderPolicy, RunSettingsSnapshot
from anishift.application.runtime import RunServices, _dialogue_font
from anishift.application.translation_handler import TranslationTaskHandler, text_spoken_lines
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings
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
        "composition_profile_id": "mkv",
        "processing_order_policy": ProcessingOrderPolicy.READY_FIRST,
    }
    return RunSettingsSnapshot(**{**defaults, **changes})  # type: ignore[arg-type]


def test_the_snapshot_carries_the_shipped_layout_defaults() -> None:
    snapshot = _snapshot()
    assert snapshot.translation_chunk_chars == 750


def test_user_settings_and_the_snapshot_agree_on_the_defaults() -> None:
    settings = UserSettings()
    snapshot = _snapshot()
    assert settings.translation_chunk_chars == snapshot.translation_chunk_chars


def test_the_runtime_carries_the_chosen_chunk_size_into_the_chunk_config(tmp_path: Path) -> None:
    services: RunServices = RunServices(lambda: Settings(_env_file=None), tmp_path, {})

    handler: TranslationTaskHandler = services.translation(_snapshot(translation_chunk_chars=1200))

    assert handler._chunk_config == ChunkConfig(chunk_chars=1200)


def test_a_larger_context_produces_fewer_narrator_lines() -> None:
    text = "\n\n".join(f"Akapit numer {index} z tekstem, ktory zajmuje trochę miejsca." for index in range(40))
    small = text_spoken_lines(text, ChunkConfig(chunk_chars=300))
    large = text_spoken_lines(text, ChunkConfig(chunk_chars=3000))
    assert len(small) > len(large)


def test_the_default_layout_is_used_when_none_is_supplied() -> None:
    text = "\n\n".join(f"Akapit numer {index} z tekstem, ktory zajmuje trochę miejsca." for index in range(40))
    assert text_spoken_lines(text) == text_spoken_lines(text, ChunkConfig())


def test_the_dialogue_font_is_off_by_default_in_preferences_and_the_snapshot() -> None:
    assert UserSettings().dialogue_font_file == _snapshot().dialogue_font_file == ""


@pytest.mark.skipif(not _SYSTEM_ARIAL.is_file(), reason="the Windows Arial font is not available")
def test_the_runtime_builds_the_dialogue_font_from_the_snapshot_for_layout_and_containers(tmp_path: Path) -> None:
    font: Path = Path(shutil.copyfile(_SYSTEM_ARIAL, tmp_path / "arial.ttf"))

    built = _dialogue_font(_snapshot(dialogue_font_file=str(font)))

    assert built is not None
    assert (built.family, built.files) == ("Arial", (font,))


def test_the_runtime_keeps_the_episode_fonts_when_the_dialogue_font_is_unusable_or_unset(tmp_path: Path) -> None:
    assert _dialogue_font(_snapshot(dialogue_font_file=str(tmp_path / "gone.ttf"))) is None
    assert _dialogue_font(_snapshot()) is None
