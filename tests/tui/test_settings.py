from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, Final, cast

import pytest
from textual.widgets import Input, OptionList

from anishift.application import AppService
from anishift.config import Settings, UserSettings, user_settings
from anishift.config.field_access import read_setting_value
from anishift.config.field_catalog import SettingSpec, SettingValueType
from anishift.config.user_settings import save_user_settings, tts_profile_key
from anishift.services.tts.engines.elevenbytes.constants import DALLIN_ALIAS, DALLIN_VOICE_ID
from anishift.tui import ui_state
from anishift.tui.app import AniShiftApp
from anishift.tui.dialogs.base import DialogScreen
from anishift.tui.dialogs.value import range_text
from anishift.tui.settings.editors import number_text, value_summary
from anishift.tui.settings.secrets import secret_status
from anishift.tui.settings.tree import SettingDomain, domain_of
from anishift.tui.strings import (
    SECRET_CONFIGURED,
    SECRET_MISSING,
    SECRET_OVERRIDDEN,
    SECRET_STORED,
    SETTING_UNSET,
)
from anishift.tui.theme import DARK_THEME_ID

_FULL_SIZE: Final[tuple[int, int]] = (100, 30)

_SETTLE_PAUSES: Final[int] = 30

_CUSTOM_VOICES_LABEL: Final[str] = "ElevenBytes custom voices"

_GEMINI_ENV: Final[str] = "ANISHIFT_GEMINI_API_KEY"

_GAIN_ID: Final[str] = "narrator_mix_base_gain_db"

_GAIN_LABEL: Final[str] = "Narrator base gain"

_NOISY_GAIN: Final[float] = 0.1 + 0.2

_NOISY_GAIN_TEXT: Final[str] = "0.30000000000000004"

_TINY_GAIN: Final[float] = 1e-05

_TINY_GAIN_TEXT: Final[str] = "0.00001"

_HINT_STEP: Final[float] = 0.125

_NUMERIC_TYPES: Final[frozenset[SettingValueType]] = frozenset(
    {
        SettingValueType.INTEGER,
        SettingValueType.OPTIONAL_INTEGER,
        SettingValueType.FLOAT,
        SettingValueType.OPTIONAL_FLOAT,
    }
)


@pytest.fixture
def state_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target: Path = tmp_path / "ui_state.json"
    monkeypatch.setattr(ui_state, "ui_state_path", lambda: target)
    return target


@pytest.fixture
def persisted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[AppService, Path]:
    target: Path = tmp_path / "settings.json"
    monkeypatch.setattr(user_settings, "config_path", lambda: target)
    env_file: Path = tmp_path / ".env"
    service: AppService = AppService(
        workspace_root=tmp_path,
        settings=Settings(_env_file=env_file),
        user_settings=UserSettings(),
        inspector=cast("Any", object()),
        handler_factory=cast("Any", lambda *args, **kwargs: None),
        settings_saver=save_user_settings,
        env_file=env_file,
    )
    return service, target


@pytest.fixture
def service(tmp_path: Path) -> AppService:
    env_file: Path = tmp_path / ".env"
    return AppService(
        workspace_root=tmp_path,
        settings=Settings(_env_file=env_file),
        user_settings=UserSettings(),
        inspector=cast("Any", object()),
        handler_factory=cast("Any", lambda *args, **kwargs: None),
        settings_saver=lambda draft: None,
        env_file=env_file,
    )


def test_confirming_a_number_commits_it_and_returns_to_the_panel(service: AppService, state_file: Path) -> None:
    _ = state_file

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_field(pilot, app, "tts", "retries")
            assert app.screen.query_one("#value-input", Input).value == "3"
            await pilot.press("up")
            await pilot.press("enter")
            await _settle(pilot)
            assert service.settings_snapshot().tts_max_retries == 4
            assert _top_dialog(app) == "SelectDialog"

    _run(scenario())


def test_leaving_a_number_editor_keeps_the_stored_value(service: AppService, state_file: Path) -> None:
    _ = state_file

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_field(pilot, app, "tts", "retries")
            await pilot.press("up")
            await pilot.press("escape")
            await _settle(pilot)
            assert service.settings_snapshot().tts_max_retries == 3
            assert _top_dialog(app) == "SelectDialog"

    _run(scenario())


def test_switching_the_engine_refreshes_the_dependent_rows(service: AppService, state_file: Path) -> None:
    _ = state_file

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("tts")
            await _settle(pilot)
            assert any(_CUSTOM_VOICES_LABEL in label for label in _labels(app))
            await _open_field(pilot, app, "tts", "engine")
            _filter(app, "edge")
            await pilot.pause()
            await pilot.press("enter")
            await _settle(pilot)
            assert service.settings_snapshot().tts_engine == "edge"
            assert not any(_CUSTOM_VOICES_LABEL in label for label in _labels(app))

    _run(scenario())


def test_each_voice_keeps_its_own_profile(service: AppService) -> None:
    service.update_setting("tts_engine", "edge")
    voices: tuple[str, ...] = _voice_ids(service)
    first, second = voices[0], voices[1]
    service.update_setting("tts_voice_id", first)
    service.update_setting("tts_profile.postprocess_tempo", 1.8)
    service.update_setting("tts_voice_id", second)
    assert _tempo(service) != pytest.approx(1.8)
    service.update_setting("tts_voice_id", first)
    assert _tempo(service) == pytest.approx(1.8)


def test_an_engine_round_trip_keeps_the_stored_voice_profile(service: AppService) -> None:
    service.update_setting("tts_profile.postprocess_tempo", 1.8)
    service.update_setting("tts_engine", "edge")
    service.update_setting("tts_engine", "elevenbytes")
    service.update_setting("tts_voice_id", DALLIN_ALIAS)
    profiles = service.settings_snapshot().tts_voice_profiles
    stored: float = profiles[tts_profile_key("elevenbytes", DALLIN_VOICE_ID)].postprocess_tempo
    assert stored == pytest.approx(1.8)


def test_a_whole_speech_number_reads_as_plain_digits() -> None:
    assert value_summary(3) == "3"
    assert value_summary(100) == "100"
    assert value_summary(-2.0) == "-2"


def test_a_speech_number_with_a_decimal_part_reads_without_its_storage_artifact() -> None:
    assert value_summary(1.25) == "1.25"
    assert value_summary(_NOISY_GAIN) == "0.3"
    assert value_summary(_TINY_GAIN) == _TINY_GAIN_TEXT


def test_an_optional_speech_number_that_holds_nothing_reads_as_unset() -> None:
    assert value_summary(None) == SETTING_UNSET


def test_no_shown_speech_number_falls_back_to_exponent_notation() -> None:
    assert number_text(_TINY_GAIN) == _TINY_GAIN_TEXT
    assert number_text(1e20) == "100000000000000000000"


def test_every_speech_range_hint_spells_its_bounds_the_way_a_row_does(service: AppService) -> None:
    draft: UserSettings = service.settings_snapshot()
    specs: tuple[SettingSpec, ...] = tuple(
        spec
        for spec in service.settings_catalog(draft)
        if domain_of(spec.setting_id) is SettingDomain.TTS and spec.value_type in _NUMERIC_TYPES
    )
    assert specs
    divergent: list[str] = [
        spec.setting_id
        for spec in specs
        for bound in (spec.minimum, spec.maximum)
        if bound is not None
        and number_text(bound) not in range_text(minimum=spec.minimum, maximum=spec.maximum, step=_HINT_STEP)
    ]
    assert divergent == []


def test_a_speech_row_hides_the_storage_artifact_the_settings_file_keeps(
    persisted: tuple[AppService, Path], state_file: Path
) -> None:
    _ = state_file
    service, target = persisted
    service.update_setting(_GAIN_ID, _NOISY_GAIN)
    assert _NOISY_GAIN_TEXT in target.read_text(encoding="utf-8")

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("tts")
            await _settle(pilot)
            _filter(app, _GAIN_LABEL)
            await pilot.pause()
            rows: list[str] = _labels(app)
            assert [row for row in rows if _GAIN_LABEL in row and "0.3" in row]
            assert [row for row in rows if _NOISY_GAIN_TEXT in row] == []

    _run(scenario())


def test_leaving_a_number_editor_keeps_the_settings_file_byte_identical(
    persisted: tuple[AppService, Path], state_file: Path
) -> None:
    _ = state_file
    service, target = persisted
    service.update_setting(_GAIN_ID, _NOISY_GAIN)
    stored: bytes = target.read_bytes()

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_field(pilot, app, "tts", _GAIN_LABEL)
            assert app.screen.query_one("#value-input", Input).value == _NOISY_GAIN_TEXT
            await pilot.press("escape")
            await _settle(pilot)

    _run(scenario())
    assert target.read_bytes() == stored


def test_secret_status_names_configured_and_missing() -> None:
    assert secret_status(configured=True) == SECRET_CONFIGURED
    assert secret_status(configured=False) == SECRET_MISSING


def test_storing_a_secret_marks_it_configured(service: AppService) -> None:
    assert service.environment_statuses()["gemini_api_key"] is False
    service.update_secret("gemini_api_key", "token")
    assert service.environment_statuses()["gemini_api_key"] is True


def test_storing_a_secret_reports_it_stored(
    service: AppService, state_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = state_file
    monkeypatch.delenv(_GEMINI_ENV, raising=False)

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_field(pilot, app, "translation", "gemini")
            app.screen.query_one("#value-input", Input).value = "token-value"
            await pilot.pause()
            await pilot.press("enter")
            await _settle(pilot)
            assert service.environment_statuses()["gemini_api_key"] is True
            feedback = app.session_state.feedback
            assert feedback is not None
            assert feedback.message == SECRET_STORED

    _run(scenario())


def test_storing_a_shadowed_secret_warns_about_the_override(
    service: AppService, state_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = state_file
    monkeypatch.setenv(_GEMINI_ENV, "shell-value")

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            await _open_field(pilot, app, "translation", "gemini")
            app.screen.query_one("#value-input", Input).value = "file-value"
            await pilot.pause()
            await pilot.press("enter")
            await _settle(pilot)
            feedback = app.session_state.feedback
            assert feedback is not None
            assert feedback.message == SECRET_OVERRIDDEN

    _run(scenario())


def test_the_theme_surface_previews_and_reverts(service: AppService, state_file: Path) -> None:
    _ = state_file

    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            assert app.theme == DARK_THEME_ID
            app.commands.dispatch("theme")
            await _settle(pilot)
            await pilot.press("down")
            await pilot.pause()
            assert app.theme != DARK_THEME_ID
            await pilot.press("escape")
            await _settle(pilot)
            assert app.theme == DARK_THEME_ID

    _run(scenario())


def test_the_theme_surface_keeps_a_confirmed_theme(service: AppService, state_file: Path) -> None:
    async def scenario() -> None:
        app: AniShiftApp = AniShiftApp(service=service)
        async with app.run_test(size=_FULL_SIZE) as pilot:
            await pilot.pause()
            app.commands.dispatch("theme")
            await _settle(pilot)
            await pilot.press("down")
            await pilot.pause()
            previewed: str = app.theme
            await pilot.press("enter")
            await _settle(pilot)
            assert previewed != DARK_THEME_ID
            assert app.theme == previewed
            assert ui_state.load_ui_state().theme == previewed

    _run(scenario())


def _run(scenario: Coroutine[Any, Any, None]) -> None:
    asyncio.run(scenario)


async def _settle(pilot: Any) -> None:
    for _ in range(_SETTLE_PAUSES):
        await pilot.pause()


def _filter(app: AniShiftApp, query: str) -> None:
    app.screen.query_one("#select-filter", Input).value = query


async def _open_field(pilot: Any, app: AniShiftApp, command: str, query: str) -> None:
    app.commands.dispatch(command)
    await _settle(pilot)
    _filter(app, query)
    await pilot.pause()
    await pilot.press("enter")
    await _settle(pilot)


def _labels(app: AniShiftApp) -> list[str]:
    listing: OptionList = app.screen.query_one("#select-list", OptionList)
    return [str(option.prompt) for option in listing.options]


def _voice_ids(service: AppService) -> tuple[str, ...]:
    draft = service.settings_snapshot()
    spec = next(spec for spec in service.settings_catalog(draft) if spec.setting_id == "tts_voice_id")
    return tuple(str(value) for value in spec.allowed_values)


def _tempo(service: AppService) -> float:
    draft = service.settings_snapshot()
    spec = next(spec for spec in service.settings_catalog(draft) if spec.setting_id == "tts_profile.postprocess_tempo")
    return float(cast("float", read_setting_value(draft, spec)))


def _top_dialog(app: AniShiftApp) -> str:
    for screen in reversed(app.screen_stack):
        if isinstance(screen, DialogScreen):
            return type(screen).__name__
    return ""
