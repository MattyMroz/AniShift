from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import cast

import pytest

from anishift.application import AppService, SessionRecord, SignInOutcome
from anishift.cli.interactive.settings import SettingsController
from anishift.cli.interactive.settings_editors import format_voice_input, parse_voice_input
from anishift.config.field_access import assign_setting_value
from anishift.config.field_catalog import (
    SettingCatalogContext,
    SettingSpec,
    SettingValue,
    setting_catalog,
)
from anishift.config.user_settings import CustomVoiceSetting, UserSettings
from anishift.services.tts.engines.elevenreader.types import AccountSettings, DocumentTrace


class FakeSettingsService:
    def __init__(self) -> None:
        self.settings = UserSettings()
        self.saves: list[tuple[str, SettingValue]] = []
        self.session: SessionRecord | None = None
        self.sign_in_outcome: SignInOutcome | OSError = SignInOutcome.SIGNED_IN

    def settings_snapshot(self) -> UserSettings:
        return self.settings

    def settings_catalog(self, draft: UserSettings | None = None) -> tuple[SettingSpec, ...]:
        context = SettingCatalogContext.from_user_settings(draft if draft is not None else self.settings)
        return setting_catalog(context)

    def update_setting(self, setting_id: str, value: SettingValue) -> UserSettings:
        self.saves.append((setting_id, value))
        specs = {spec.setting_id: spec for spec in self.settings_catalog()}
        assign_setting_value(self.settings, specs[setting_id], value)
        self.settings.__post_init__()
        return self.settings

    def elevenreader_session(self) -> SessionRecord | None:
        return self.session

    def elevenreader_sign_in(self) -> SignInOutcome:
        if isinstance(self.sign_in_outcome, OSError):
            raise self.sign_in_outcome
        self.session = SessionRecord(
            signed_in=self.sign_in_outcome is SignInOutcome.SIGNED_IN,
            checked_at=datetime(2026, 10, 30, 13, 3, tzinfo=UTC),
        )
        return self.sign_in_outcome


@pytest.fixture
def service() -> FakeSettingsService:
    return FakeSettingsService()


@pytest.fixture
def panel(service: FakeSettingsService) -> SettingsController:
    return SettingsController(cast("AppService", service), lambda: None)


def _activate(panel: SettingsController, key: str) -> None:
    for index, item in enumerate(panel._items):
        if item.key == key:
            panel._selected = index
            panel.handle_key("enter")
            return
    raise AssertionError(f"{key} is not on this screen")


def _type(panel: SettingsController, text: str) -> None:
    for character in text:
        panel.handle_key("space" if character == " " else f"text:{character}")


def _open_voices(panel: SettingsController) -> None:
    _activate(panel, "category:tts")
    _activate(panel, "setting:elevenbytes_custom_voices")


def _keys(panel: SettingsController) -> tuple[str, ...]:
    return tuple(item.key for item in panel._items)


def test_the_voice_list_is_reachable_from_the_narration_category(panel: SettingsController) -> None:
    _open_voices(panel)
    assert "voice-add" in _keys(panel)


def test_the_narration_category_shows_the_voice_row(panel: SettingsController) -> None:
    _activate(panel, "category:tts")
    assert "setting:elevenbytes_custom_voices" in _keys(panel)


def test_an_empty_list_is_reported_as_such(panel: SettingsController) -> None:
    _activate(panel, "category:tts")
    row = next(item for item in panel._items if item.key == "setting:elevenbytes_custom_voices")
    assert row.current == "brak"


def test_a_stored_voice_is_listed_by_its_alias(panel: SettingsController, service: FakeSettingsService) -> None:
    service.settings.elevenbytes_custom_voices = [CustomVoiceSetting("kaja", "Kaja", "voice-1")]
    _activate(panel, "category:tts")
    row = next(item for item in panel._items if item.key == "setting:elevenbytes_custom_voices")
    assert row.current == "kaja"


def test_a_new_voice_is_added_by_one_typed_line(panel: SettingsController, service: FakeSettingsService) -> None:
    _open_voices(panel)
    _activate(panel, "voice-add")
    _type(panel, "kaja | Kaja | voice-1")
    panel.handle_key("enter")
    assert service.settings.elevenbytes_custom_voices == [CustomVoiceSetting("kaja", "Kaja", "voice-1")]


def test_the_added_voice_shows_up_on_the_list(panel: SettingsController) -> None:
    _open_voices(panel)
    _activate(panel, "voice-add")
    _type(panel, "kaja | Kaja | voice-1")
    panel.handle_key("enter")
    assert "voice:kaja" in _keys(panel)


def test_an_existing_voice_opens_prefilled(panel: SettingsController, service: FakeSettingsService) -> None:
    service.settings.elevenbytes_custom_voices = [CustomVoiceSetting("kaja", "Kaja", "voice-1")]
    _open_voices(panel)
    _activate(panel, "voice:kaja")
    assert panel._editor is not None
    assert panel._editor.buffer == "kaja | Kaja | voice-1"


def test_only_an_existing_voice_names_its_removal_by_an_emptied_line(
    panel: SettingsController, service: FakeSettingsService
) -> None:
    service.settings.elevenbytes_custom_voices = [CustomVoiceSetting("kaja", "Kaja", "voice-1")]
    _open_voices(panel)
    _activate(panel, "voice:kaja")
    editing: str = panel.render(100, 30).plain

    assert "pusta linia usuwa" in editing


def test_editing_a_voice_replaces_it_in_place(panel: SettingsController, service: FakeSettingsService) -> None:
    service.settings.elevenbytes_custom_voices = [
        CustomVoiceSetting("kaja", "Kaja", "voice-1"),
        CustomVoiceSetting("piotr", "Piotr", "voice-2"),
    ]
    _open_voices(panel)
    _activate(panel, "voice:kaja")
    assert panel._editor is not None
    panel._editor.buffer = "kaja | Kaja Nowa | voice-9"
    panel.handle_key("enter")
    assert service.settings.elevenbytes_custom_voices == [
        CustomVoiceSetting("kaja", "Kaja Nowa", "voice-9"),
        CustomVoiceSetting("piotr", "Piotr", "voice-2"),
    ]


def test_an_emptied_line_removes_that_voice(panel: SettingsController, service: FakeSettingsService) -> None:
    service.settings.elevenbytes_custom_voices = [
        CustomVoiceSetting("kaja", "Kaja", "voice-1"),
        CustomVoiceSetting("piotr", "Piotr", "voice-2"),
    ]
    _open_voices(panel)
    _activate(panel, "voice:kaja")
    assert panel._editor is not None
    panel._editor.buffer = ""
    panel.handle_key("enter")
    assert service.settings.elevenbytes_custom_voices == [CustomVoiceSetting("piotr", "Piotr", "voice-2")]


def test_removing_the_selected_voice_falls_back_to_a_built_in_one(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    service.settings.elevenbytes_custom_voices = [CustomVoiceSetting("kaja", "Kaja", "voice-1")]
    service.settings.tts_voice_id = "kaja"
    _open_voices(panel)
    _activate(panel, "voice:kaja")
    assert panel._editor is not None
    panel._editor.buffer = ""
    panel.handle_key("enter")
    assert service.settings.tts_voice_id != "kaja"


def test_a_malformed_line_is_refused_without_saving(panel: SettingsController, service: FakeSettingsService) -> None:
    _open_voices(panel)
    _activate(panel, "voice-add")
    _type(panel, "kaja | Kaja")
    panel.handle_key("enter")
    assert service.settings.elevenbytes_custom_voices == []
    assert panel._editor is not None


def test_leaving_the_voice_list_returns_to_the_narration_category(panel: SettingsController) -> None:
    _open_voices(panel)
    panel.handle_key("escape")
    assert "setting:elevenbytes_custom_voices" in _keys(panel)


def test_the_voice_list_survives_a_cancelled_editor(panel: SettingsController) -> None:
    _open_voices(panel)
    _activate(panel, "voice-add")
    panel.handle_key("escape")
    assert panel._editor is None
    assert "voice-add" in _keys(panel)


@pytest.mark.parametrize("raw", ["", "kaja", "kaja | Kaja", "kaja | Kaja | voice | extra", " |  | "])
def test_the_parser_refuses_a_line_that_is_not_three_filled_parts(raw: str) -> None:
    with pytest.raises(ValueError, match="Custom voice needs"):
        parse_voice_input(raw)


def test_the_parser_trims_every_part() -> None:
    assert parse_voice_input("  kaja |  Kaja  | voice-1 ") == CustomVoiceSetting("kaja", "Kaja", "voice-1")


def test_a_formatted_voice_parses_back_into_the_same_voice() -> None:
    voice = CustomVoiceSetting("kaja", "Kaja", "voice-1")
    assert parse_voice_input(format_voice_input(voice)) == voice


def test_a_running_check_names_only_its_cancel_key(panel: SettingsController) -> None:
    panel._busy = True

    shown: str = panel.render(100, 30).plain

    assert "Esc anuluj" in shown
    assert "Enter otwórz" not in shown


def _row(panel: SettingsController, key: str) -> str:
    return next(item.current for item in panel._items if item.key == key)


def _sign_in(panel: SettingsController) -> None:
    _activate(panel, "elevenreader-sign-in")
    for worker in threading.enumerate():
        if worker.name == "anishift-elevenreader-sign-in":
            worker.join(timeout=5.0)


@pytest.mark.unit
def test_tts_items_elevenbytes_engine_hides_session_section(panel: SettingsController) -> None:
    _activate(panel, "category:tts")

    assert "elevenreader-session" not in _keys(panel)
    assert "elevenreader-sign-in" not in _keys(panel)


@pytest.mark.unit
def test_tts_items_elevenreader_unchecked_session_shows_status_and_action(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    service.settings = UserSettings(tts_engine="elevenreader")

    _activate(panel, "category:tts")

    assert _row(panel, "elevenreader-session") == "nie sprawdzono"
    assert {item.section for item in panel._items if item.key.startswith("elevenreader-")} == {"SESJA"}
    assert _row(panel, "setting:tts_voice_id") == "Piotr Fronczewski"
    assert "setting:tts_profile.concurrency" not in _keys(panel)


@pytest.mark.unit
def test_tts_items_elevenreader_saved_check_shows_local_time(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    checked_at: datetime = datetime(2026, 10, 30, 13, 3, tzinfo=UTC)
    service.settings = UserSettings(tts_engine="elevenreader")
    service.session = SessionRecord(signed_in=False, checked_at=checked_at)

    _activate(panel, "category:tts")

    assert _row(panel, "elevenreader-session") == f"nie zalogowano · {checked_at.astimezone():%d.%m %H:%M}"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("outcome", "feedback"),
    [
        (SignInOutcome.SIGNED_IN, "✓ Zalogowano"),
        (SignInOutcome.SIGNED_OUT, "✗ Nie zalogowano"),
        (SignInOutcome.BUSY, "✗ Lektor właśnie nagrywa — spróbuj po zakończeniu"),
        (SignInOutcome.NO_CHROME, "✗ Nie znaleziono Google Chrome"),
        (SignInOutcome.FAILED, "✗ Nie udało się sprawdzić sesji"),
        (OSError("chrome"), "✗ Nie udało się sprawdzić sesji"),
    ],
)
def test_sign_in_action_outcome_shows_feedback(
    panel: SettingsController,
    service: FakeSettingsService,
    outcome: SignInOutcome | OSError,
    feedback: str,
) -> None:
    service.settings = UserSettings(tts_engine="elevenreader")
    service.sign_in_outcome = outcome
    _activate(panel, "category:tts")

    _sign_in(panel)

    assert not panel._busy
    assert panel._feedback is not None
    assert panel._feedback.text == feedback


@pytest.mark.unit
def test_sign_in_action_signed_in_refreshes_session_row(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    service.settings = UserSettings(tts_engine="elevenreader")
    _activate(panel, "category:tts")

    _sign_in(panel)

    assert _row(panel, "elevenreader-session").startswith("zalogowano · ")


def _owed_session(*, restore: bool, document: bool) -> SessionRecord:
    return SessionRecord(
        signed_in=True,
        checked_at=datetime(2026, 10, 30, 13, 3, tzinfo=UTC),
        restore=AccountSettings(voice_id="previous-voice", speed=1.5) if restore else None,
        documents=(DocumentTrace(pressed_at=0.0, listed_by=0.0, titles=frozenset()),) if document else (),
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("restore", "document", "label"),
    [
        (True, True, "Na koncie mógł zostać dokument wgrany przez AniShift i zmieniony głos"),
        (False, True, "Na koncie mógł zostać dokument wgrany przez AniShift"),
        (True, False, "Na koncie mógł zostać zmieniony głos"),
    ],
)
def test_tts_items_elevenreader_owed_cleanup_shows_row_with_repair_action(
    panel: SettingsController,
    service: FakeSettingsService,
    restore: bool,
    document: bool,
    label: str,
) -> None:
    service.settings = UserSettings(tts_engine="elevenreader")
    service.session = _owed_session(restore=restore, document=document)

    _activate(panel, "category:tts")

    keys: tuple[str, ...] = _keys(panel)
    row = next(item for item in panel._items if item.key == "elevenreader-cleanup")
    assert keys.index("elevenreader-session") < keys.index("elevenreader-cleanup") < keys.index("elevenreader-sign-in")
    assert (row.label, row.current, row.section) == (label, "napraw: Zaloguj / sprawdź sesję", "SESJA")


@pytest.mark.unit
def test_tts_items_other_engine_owed_cleanup_shows_only_cleanup_row(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    service.session = _owed_session(restore=True, document=True)

    _activate(panel, "category:tts")

    row = next(item for item in panel._items if item.key == "elevenreader-cleanup")
    assert (row.current, row.section) == ("napraw: Zaloguj / sprawdź sesję", "SESJA")
    assert "elevenreader-session" not in _keys(panel)
    assert "elevenreader-sign-in" not in _keys(panel)


@pytest.mark.unit
def test_tts_items_elevenreader_nothing_owed_hides_cleanup_row(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    service.settings = UserSettings(tts_engine="elevenreader")
    service.session = _owed_session(restore=False, document=False)

    _activate(panel, "category:tts")

    assert "elevenreader-cleanup" not in _keys(panel)


@pytest.mark.unit
def test_cleanup_row_enter_runs_sign_in_and_hides_row_once_cleaned(
    panel: SettingsController,
    service: FakeSettingsService,
) -> None:
    service.settings = UserSettings(tts_engine="elevenreader")
    service.session = _owed_session(restore=True, document=True)
    _activate(panel, "category:tts")

    _activate(panel, "elevenreader-cleanup")
    for worker in threading.enumerate():
        if worker.name == "anishift-elevenreader-sign-in":
            worker.join(timeout=5.0)

    assert panel._feedback is not None
    assert panel._feedback.text == "✓ Zalogowano"
    assert "elevenreader-cleanup" not in _keys(panel)
