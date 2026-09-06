from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from rich.cells import cell_len

from anishift.application import AppService, AutoPreset, AutoPresetDraft
from anishift.application.intents import (
    BurnSubtitleProduct,
    MkvTrackProduct,
    Mp4AudioSource,
    ProductIntent,
    ProductKind,
    SubtitleOutputFormat,
    SubtitleSourcePolicy,
    TranslationAction,
)
from anishift.cli.interactive.settings import (
    _POINTER,
    _PRODUCTS,
    _ROOT_RESET_PARTIAL,
    SettingsController,
    _Editor,
    _PendingEdit,
)
from anishift.config.field_access import assign_setting_value, read_preset_value
from anishift.config.field_catalog import (
    SettingCatalogContext,
    SettingScope,
    SettingSpec,
    SettingValue,
    setting_catalog,
)
from anishift.config.presets import default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings

_POLICY_ROWS = (
    "setting:subtitle_source_policy",
    "setting:source_subtitle_language",
    "setting:translation_action",
    "setting:subtitle_output_format",
)

_CONTAINER_ROWS = ("setting:mkv_tracks", "setting:mp4_audio_source", "setting:burn_subtitle_product")


class FakeAutoService:
    def __init__(self) -> None:
        self.settings: UserSettings = UserSettings()
        self.saves: list[tuple[str, SettingValue]] = []
        self.resets: int = 0
        self.preset: AutoPreset = default_preset_file().presets[0]
        self.preset_saves: list[AutoPreset] = []
        self.fail_preset_writes: bool = False
        self.environment: Settings = Settings.model_construct()

    def settings_snapshot(self) -> UserSettings:
        return self.settings

    def settings_catalog(self, draft: UserSettings | None = None) -> tuple[SettingSpec, ...]:
        context: SettingCatalogContext = SettingCatalogContext.from_user_settings(
            draft if draft is not None else self.settings
        )
        return setting_catalog(context)

    def update_setting(self, setting_id: str, value: SettingValue) -> UserSettings:
        self.saves.append((setting_id, value))
        specs: dict[str, SettingSpec] = {spec.setting_id: spec for spec in self.settings_catalog()}
        assign_setting_value(self.settings, specs[setting_id], value)
        self.settings.__post_init__()
        return self.settings

    def reset_settings(self) -> UserSettings:
        self.resets += 1
        self.settings = UserSettings()
        return self.settings

    def current_settings(self) -> Settings:
        return self.environment

    def environment_setting_statuses(self) -> tuple[()]:
        return ()

    def default_preset_id(self) -> str:
        return self.preset.preset_id

    def get_preset(self, preset_id: str) -> AutoPreset:
        assert preset_id == self.preset.preset_id
        return self.preset

    def save_preset(self, draft: AutoPresetDraft) -> AutoPreset:
        if self.fail_preset_writes:
            raise OSError("synthetic preset write failure")
        self.preset = draft.to_preset()
        self.preset_saves.append(self.preset)
        return self.preset


@pytest.fixture
def service() -> FakeAutoService:
    return FakeAutoService()


@pytest.fixture
def panel(service: FakeAutoService) -> SettingsController:
    return SettingsController(cast("AppService", service), lambda: None)


def _with_products(service: FakeAutoService, *kinds: ProductKind) -> None:
    service.preset = replace(service.preset, products=ProductIntent(frozenset(kinds)))


def _keys(panel: SettingsController) -> tuple[str, ...]:
    return tuple(item.key for item in panel._items)


def _activate(panel: SettingsController, key: str) -> None:
    for index, item in enumerate(panel._items):
        if item.key == key:
            panel._selected = index
            panel.handle_key("enter")
            return
    raise AssertionError(f"{key} is not on this screen")


def _focus(panel: SettingsController, key: str) -> None:
    panel._selected = next(index for index, item in enumerate(panel._items) if item.key == key)


def _open(panel: SettingsController, setting_id: str) -> None:
    _activate(panel, "category:auto")
    _activate(panel, f"setting:{setting_id}")


def _walk_to(panel: SettingsController, value: str) -> None:
    editor: _Editor | None = panel._editor
    assert editor is not None
    for _ in range(len(editor.options)):
        if editor.options[editor.selected].value == value:
            return
        panel.handle_key("down")
    raise AssertionError(f"{value} is not offered")


def _choose(panel: SettingsController, setting_id: str, value: str) -> None:
    _open(panel, setting_id)
    _walk_to(panel, value)
    panel.handle_key("enter")


def _flush(panel: SettingsController) -> None:
    pending: _PendingEdit | None = panel._pending
    if pending is not None:
        pending.deadline = 0.0
    panel.flush_pending()


def _shown(panel: SettingsController, setting_id: str) -> str:
    return next(item.current for item in panel._items if item.key == f"setting:{setting_id}")


def _flat(service: FakeAutoService, preset: AutoPreset) -> dict[str, SettingValue]:
    specs: list[SettingSpec] = [spec for spec in service.settings_catalog() if spec.scope is SettingScope.AUTO_PRESET]
    return {spec.setting_id: read_preset_value(preset, spec) for spec in specs}


def test_auto_sits_right_after_output_in_the_root_menu(panel: SettingsController) -> None:
    keys: tuple[str, ...] = _keys(panel)

    assert keys.index("category:auto") == keys.index("category:output") + 1


def test_the_auto_screen_lists_policies_and_hides_container_rows_without_their_products(
    panel: SettingsController,
) -> None:
    _activate(panel, "category:auto")

    assert _keys(panel) == (*_POLICY_ROWS, "reset-scope:auto", "back")
    assert "AUTO" in panel.render(80, 24).plain


def test_container_rows_appear_once_their_products_are_requested(
    panel: SettingsController,
    service: FakeAutoService,
) -> None:
    _with_products(service, ProductKind.FULL_PL, ProductKind.MKV, ProductKind.MP4)
    _activate(panel, "category:auto")

    assert _keys(panel) == (*_POLICY_ROWS, *_CONTAINER_ROWS, "reset-scope:auto", "back")


def test_only_the_container_that_is_requested_shows_its_rows(
    panel: SettingsController,
    service: FakeAutoService,
) -> None:
    _with_products(service, ProductKind.FULL_PL, ProductKind.MKV)
    _activate(panel, "category:auto")

    assert "setting:mkv_tracks" in _keys(panel)
    assert "setting:mp4_audio_source" not in _keys(panel)
    assert "setting:burn_subtitle_product" not in _keys(panel)


@pytest.mark.parametrize(
    ("setting_id", "value", "shown"),
    [
        ("subtitle_source_policy", "embedded", "Osadzone w MKV"),
        ("translation_action", "translate", "Zawsze tłumacz · także polskie źródło"),
        ("subtitle_output_format", "ass", "ASS"),
        ("mp4_audio_source", "original", "Oryginalne audio"),
        ("burn_subtitle_product", "full_pl", "Polskie napisy"),
    ],
)
def test_choosing_a_policy_saves_it_and_leaves_the_rest_alone(
    panel: SettingsController,
    service: FakeAutoService,
    setting_id: str,
    value: str,
    shown: str,
) -> None:
    _with_products(service, ProductKind.FULL_PL, ProductKind.NARRATION_AUDIO, ProductKind.MP4)
    before: dict[str, SettingValue] = _flat(service, service.preset)

    _choose(panel, setting_id, value)

    after: dict[str, SettingValue] = _flat(service, service.preset)
    assert len(service.preset_saves) == 1
    assert service.saves == []
    assert panel._editor is None
    assert panel._feedback is None
    assert _shown(panel, setting_id) == shown
    assert after.pop(setting_id) == value
    assert before.pop(setting_id) != value
    assert after == before
    assert (service.preset.preset_id, service.preset.name) == ("default", "Polish lector")


def test_choosing_the_stored_value_again_writes_nothing(panel: SettingsController, service: FakeAutoService) -> None:
    _choose(panel, "subtitle_source_policy", "auto")

    assert service.preset_saves == []
    assert panel._editor is None


def test_walking_a_policy_editor_and_escaping_writes_nothing(
    panel: SettingsController,
    service: FakeAutoService,
) -> None:
    _open(panel, "subtitle_source_policy")
    panel.handle_key("down")
    panel.handle_key("down")
    panel.handle_key("escape")
    _flush(panel)

    assert service.preset_saves == []
    assert service.preset.subtitle_source_policy is SubtitleSourcePolicy.AUTO


def test_arrows_step_a_policy_row_and_save_once_the_keys_stop(
    panel: SettingsController,
    service: FakeAutoService,
) -> None:
    _activate(panel, "category:auto")
    _focus(panel, "setting:subtitle_source_policy")

    panel.handle_key("right")

    assert service.preset_saves == []
    assert _shown(panel, "subtitle_source_policy") == "Plik obok źródła"
    _flush(panel)
    assert service.preset.subtitle_source_policy is SubtitleSourcePolicy.SIDECAR
    assert len(service.preset_saves) == 1


def test_stepping_back_to_the_stored_policy_saves_nothing(
    panel: SettingsController,
    service: FakeAutoService,
) -> None:
    _activate(panel, "category:auto")
    _focus(panel, "setting:subtitle_source_policy")
    panel.handle_key("right")
    panel.handle_key("left")
    _flush(panel)

    assert service.preset_saves == []
    assert panel._feedback is None


def test_left_on_a_track_list_row_goes_back_instead_of_stepping(
    panel: SettingsController,
    service: FakeAutoService,
) -> None:
    _with_products(service, ProductKind.MKV)
    _activate(panel, "category:auto")
    _focus(panel, "setting:mkv_tracks")

    panel.handle_key("left")

    assert panel._category is None
    assert service.preset_saves == []


def test_the_language_override_is_typed_then_cleared(panel: SettingsController, service: FakeAutoService) -> None:
    _open(panel, "source_subtitle_language")
    for character in "eng":
        panel.handle_key(f"text:{character}")
    panel.handle_key("enter")

    assert service.preset.source_subtitle_language == "eng"
    assert _shown(panel, "source_subtitle_language") == "eng"

    _activate(panel, "setting:source_subtitle_language")
    for _ in range(3):
        panel.handle_key("backspace")
    panel.handle_key("enter")

    assert service.preset.source_subtitle_language is None
    assert _shown(panel, "source_subtitle_language") == "domyślnie"
    assert len(service.preset_saves) == 2


def test_mkv_tracks_toggle_with_space_and_an_empty_list_is_kept(
    panel: SettingsController,
    service: FakeAutoService,
) -> None:
    _with_products(service, ProductKind.MKV)
    _open(panel, "mkv_tracks")
    _walk_to(panel, "narration_audio")
    panel.handle_key("space")
    _flush(panel)

    assert service.preset.products.mkv_tracks == frozenset({MkvTrackProduct.NARRATION_AUDIO})

    panel.handle_key("space")
    _flush(panel)
    panel.handle_key("escape")

    assert service.preset.products.mkv_tracks == frozenset()
    assert _shown(panel, "mkv_tracks") == "brak"
    assert len(service.preset_saves) == 2


def test_track_rows_show_their_polish_labels(panel: SettingsController, service: FakeAutoService) -> None:
    service.preset = replace(
        service.preset,
        products=ProductIntent(
            frozenset({ProductKind.MKV}),
            mkv_tracks=frozenset({MkvTrackProduct.FULL_PL_SUBTITLES, MkvTrackProduct.NARRATION_AUDIO}),
        ),
    )
    _activate(panel, "category:auto")

    assert _shown(panel, "mkv_tracks") == "Polskie napisy, Polski lektor"


def test_the_translation_row_names_its_effect_on_polish_products(panel: SettingsController) -> None:
    _activate(panel, "category:auto")

    assert "tłumaczy, gdy źródło nie jest polskie" in _shown(panel, "translation_action")


def test_dropping_mkv_on_the_output_screen_clears_its_tracks_but_keeps_policies(
    panel: SettingsController,
    service: FakeAutoService,
) -> None:
    service.preset = replace(
        service.preset,
        products=ProductIntent(
            frozenset({ProductKind.FULL_PL, ProductKind.MKV}),
            mkv_tracks=frozenset({MkvTrackProduct.NARRATION_AUDIO}),
        ),
        subtitle_source_policy=SubtitleSourcePolicy.EMBEDDED,
        source_subtitle_language="eng",
    )
    _activate(panel, "category:output")
    panel._selected = next(index for index, (product, _label) in enumerate(_PRODUCTS) if product is ProductKind.MKV)

    panel.handle_key("space")

    assert service.preset.products == ProductIntent(frozenset({ProductKind.FULL_PL}))
    assert service.preset.subtitle_source_policy is SubtitleSourcePolicy.EMBEDDED
    assert service.preset.source_subtitle_language == "eng"


def test_a_failed_policy_write_keeps_the_editor_and_retries_on_enter(
    panel: SettingsController,
    service: FakeAutoService,
) -> None:
    service.fail_preset_writes = True
    _choose(panel, "subtitle_source_policy", "embedded")

    assert panel._editor is not None
    assert panel._feedback is not None
    assert "Nie udało się zapisać" in panel._feedback.text
    assert service.preset.subtitle_source_policy is SubtitleSourcePolicy.AUTO

    service.fail_preset_writes = False
    panel.handle_key("enter")

    assert service.preset_saves[-1].subtitle_source_policy is SubtitleSourcePolicy.EMBEDDED
    assert panel._editor is None
    assert panel._feedback is None


def test_a_failed_language_write_is_retried_and_cancelled_without_a_restart(
    panel: SettingsController,
    service: FakeAutoService,
) -> None:
    service.fail_preset_writes = True
    _open(panel, "source_subtitle_language")
    panel.handle_key("text:e")
    panel.handle_key("enter")

    assert panel._editor is not None
    assert panel._pending is not None
    assert panel._feedback is not None
    assert service.preset.source_subtitle_language is None

    service.fail_preset_writes = False
    panel.handle_key("enter")

    assert service.preset.source_subtitle_language == "e"
    assert panel._pending is None
    assert panel._editor is None

    service.fail_preset_writes = True
    _activate(panel, "setting:source_subtitle_language")
    panel.handle_key("text:x")
    assert panel.handle_key("interrupt") is not None
    panel.handle_key("escape")

    assert panel._editor is not None
    assert service.preset.source_subtitle_language == "e"


def test_the_auto_reset_asks_first_and_restores_the_whole_preset_under_its_own_identity(
    panel: SettingsController,
    service: FakeAutoService,
) -> None:
    service.preset = replace(
        default_preset_file().presets[0],
        preset_id="mine",
        name="Mine",
        products=ProductIntent(frozenset({ProductKind.MKV}), mkv_tracks=frozenset({MkvTrackProduct.NARRATION_AUDIO})),
        subtitle_source_policy=SubtitleSourcePolicy.SIDECAR,
        translation_action=TranslationAction.DO_NOT_TRANSLATE,
        source_subtitle_language="pol",
        subtitle_output_format=SubtitleOutputFormat.ASS,
    )
    _activate(panel, "category:auto")
    _activate(panel, "reset-scope:auto")
    assert panel._editor is not None
    assert panel._editor.title == "PRZYWRÓCIĆ DOMYŚLNE · AUTO?"
    panel.handle_key("enter")
    assert service.preset_saves == []

    _activate(panel, "reset-scope:auto")
    panel.handle_key("down")
    panel.handle_key("enter")

    assert service.preset == replace(default_preset_file().presets[0], preset_id="mine", name="Mine")
    assert panel._editor is None
    assert panel._feedback is None
    assert _keys(panel) == (*_POLICY_ROWS, "reset-scope:auto", "back")


def test_the_output_reset_restores_the_auto_policies_too(panel: SettingsController, service: FakeAutoService) -> None:
    service.preset = replace(service.preset, subtitle_source_policy=SubtitleSourcePolicy.EMBEDDED)
    _activate(panel, "category:output")
    panel._selected = len(_PRODUCTS)
    panel.handle_key("enter")
    panel.handle_key("down")
    panel.handle_key("enter")

    assert service.preset == default_preset_file().presets[0]


def test_the_root_reset_restores_preferences_and_the_preset(
    panel: SettingsController, service: FakeAutoService
) -> None:
    service.settings.subtitle_max_chars_per_line = 100
    service.preset = replace(service.preset, translation_action=TranslationAction.TRANSLATE)
    _activate(panel, "reset-settings")
    panel.handle_key("down")
    panel.handle_key("enter")

    assert service.resets == 1
    assert service.settings.subtitle_max_chars_per_line == 42
    assert service.preset == default_preset_file().presets[0]
    assert panel._feedback is None


def test_a_root_reset_whose_preset_write_fails_says_so_and_can_be_retried(
    panel: SettingsController,
    service: FakeAutoService,
) -> None:
    changed: AutoPreset = replace(service.preset, translation_action=TranslationAction.TRANSLATE)
    service.preset = changed
    service.fail_preset_writes = True
    _activate(panel, "reset-settings")
    panel.handle_key("down")
    panel.handle_key("enter")

    assert service.resets == 1
    assert service.preset == changed
    assert panel._editor is not None
    assert panel._feedback is not None
    assert panel._feedback.text == _ROOT_RESET_PARTIAL
    assert "Enter ponawia" in panel.render(100, 30).plain

    service.fail_preset_writes = False
    panel.handle_key("enter")

    assert service.resets == 2
    assert service.preset == default_preset_file().presets[0]
    assert panel._editor is None
    assert panel._feedback is None


def test_a_fresh_controller_shows_what_was_saved(panel: SettingsController, service: FakeAutoService) -> None:
    _choose(panel, "subtitle_source_policy", "embedded")
    _activate(panel, "setting:source_subtitle_language")
    for character in "eng":
        panel.handle_key(f"text:{character}")
    panel.handle_key("enter")

    fresh: SettingsController = SettingsController(cast("AppService", service), lambda: None)
    _activate(fresh, "category:auto")

    assert _shown(fresh, "subtitle_source_policy") == "Osadzone w MKV"
    assert _shown(fresh, "source_subtitle_language") == "eng"


@pytest.mark.parametrize("rows", [10, 12, 16])
def test_every_auto_row_fits_a_narrow_short_terminal_with_a_fixed_back_row(
    panel: SettingsController,
    service: FakeAutoService,
    rows: int,
) -> None:
    _with_products(service, ProductKind.FULL_PL, ProductKind.MKV, ProductKind.MP4)
    _activate(panel, "category:auto")
    for index in range(len(panel._items)):
        panel._selected = index
        frame: str = panel.render(40, rows).plain
        lines: list[str] = frame.splitlines()
        assert len(lines) <= rows
        assert max(cell_len(line) for line in lines) <= 40
        assert "Cofnij" in frame
        assert _POINTER in frame


def test_a_burn_choice_needs_mp4_and_is_dropped_with_it(panel: SettingsController, service: FakeAutoService) -> None:
    _with_products(service, ProductKind.FULL_PL, ProductKind.MP4)
    _choose(panel, "burn_subtitle_product", "displayed_pl")
    assert service.preset.products.burn_subtitle_product is BurnSubtitleProduct.DISPLAYED_PL
    panel.handle_key("escape")

    _activate(panel, "category:output")
    panel._selected = next(index for index, (product, _label) in enumerate(_PRODUCTS) if product is ProductKind.MP4)
    panel.handle_key("space")

    assert service.preset_saves[-1].products.burn_subtitle_product is BurnSubtitleProduct.NONE
    assert service.preset_saves[-1].products.mp4_audio_source is Mp4AudioSource.AUTO
