from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
from fakes import write_text_source

from anishift.application import service as service_module
from anishift.application.inspection import InspectedSourceGroup, WorkspaceInspector
from anishift.application.intents import ProductIntent, ProductKind
from anishift.application.planning import ExecutionPlan
from anishift.application.scheduler_contracts import TaskHandler
from anishift.application.service import AppService, AutoPresetDraft
from anishift.config import user_settings as user_settings_module
from anishift.config.field_catalog import SettingCondition, SettingScope, SettingSpec, SettingValueType
from anishift.config.presets import default_preset_file
from anishift.config.settings import Settings
from anishift.config.user_settings import UserSettings, save_user_settings, tts_profile_key
from anishift.errors import ConfigError, ErrorCode
from anishift.services.media import DefaultMediaProbe
from anishift.services.tts.engines.edge.constants import MAREK_VOICE_ID
from anishift.services.tts.engines.elevenbytes.constants import DALLIN_ALIAS, DALLIN_VOICE_ID


def _unused_handlers(
    run_root: Path,
    plan: ExecutionPlan,
    source_groups: Mapping[str, InspectedSourceGroup],
) -> TaskHandler:
    del run_root, plan, source_groups
    raise AssertionError("Updating settings must not execute a plan")


def _service(
    tmp_path: Path,
    user_settings: UserSettings,
    saver: Callable[[UserSettings], None],
) -> AppService:
    return AppService(
        workspace_root=tmp_path,
        settings=Settings(_env_file=None),
        user_settings=user_settings,
        inspector=WorkspaceInspector(DefaultMediaProbe()),
        handler_factory=_unused_handlers,
        preset_loader=default_preset_file,
        preset_saver=lambda value: None,
        settings_saver=saver,
    )


def test_update_setting_persists_one_field_and_adopts_it_in_memory(tmp_path: Path) -> None:
    saved: list[UserSettings] = []
    service: AppService = _service(tmp_path, UserSettings(), saved.append)

    updated: UserSettings = service.update_setting("translation_concurrency", 3)

    assert updated.translation_concurrency == 3
    assert len(saved) == 1
    assert saved[0].translation_concurrency == 3
    assert service.settings_snapshot().translation_concurrency == 3
    assert updated is not service.settings_snapshot()


def test_update_setting_refuses_unknown_secret_and_inactive_fields(tmp_path: Path) -> None:
    saved: list[UserSettings] = []
    service: AppService = _service(tmp_path, UserSettings(translation_engine="google"), saved.append)

    with pytest.raises(ConfigError, match="Unknown editable setting") as unknown:
        service.update_setting("nonexistent_setting", 1)
    with pytest.raises(ConfigError, match="Unknown editable setting"):
        service.update_setting("deepl_api_key", "secret-value")
    with pytest.raises(ConfigError, match="Unknown editable setting"):
        service.update_setting("openai_compatible_base_url", "https://example.invalid")
    with pytest.raises(ConfigError, match="not active for the current selections") as inactive:
        service.update_setting("llm_temperature", 0.5)
    with pytest.raises(ConfigError, match="Unknown editable setting"):
        service.update_setting("mkv_tracks", frozenset({"spoken_pl"}))

    assert unknown.value.context.code is ErrorCode.CONFIG_INVALID
    assert inactive.value.context.code is ErrorCode.CONFIG_INVALID
    assert inactive.value.context.suggestion
    assert saved == []
    assert service.settings_snapshot() == UserSettings(translation_engine="google")


def test_update_setting_surfaces_a_broken_catalog_dependency_instead_of_reporting_inactive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    broken: SettingSpec = SettingSpec(
        setting_id="translation_concurrency",
        label="Translation concurrency",
        description="Preference wired to a dependency no preference file stores.",
        value_type=SettingValueType.INTEGER,
        default=1,
        scope=SettingScope.GLOBAL,
        minimum=1,
        maximum=16,
        depends_on=(SettingCondition("requested_products", ("mkv",)),),
    )
    monkeypatch.setattr(service_module, "setting_catalog", lambda context: (broken,))
    saved: list[UserSettings] = []
    service: AppService = _service(tmp_path, UserSettings(), saved.append)

    with pytest.raises(ValueError, match="not a persisted user preference"):
        service.update_setting("translation_concurrency", 2)

    assert saved == []
    assert service.settings_snapshot().translation_concurrency == 1


def test_update_setting_rejects_an_out_of_range_value_without_writing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target: Path = tmp_path / "settings.json"
    monkeypatch.setattr(user_settings_module, "config_path", lambda: target)
    save_user_settings(UserSettings())
    baseline: str = target.read_text(encoding="utf-8")
    service: AppService = _service(tmp_path, UserSettings(), save_user_settings)

    with pytest.raises(ValueError, match="above its maximum"):
        service.update_setting("translation_concurrency", 99)

    assert target.read_text(encoding="utf-8") == baseline
    assert service.settings_snapshot().translation_concurrency == 1


def test_update_setting_rejects_a_wrongly_typed_value_without_writing(tmp_path: Path) -> None:
    saved: list[UserSettings] = []
    service: AppService = _service(tmp_path, UserSettings(), saved.append)

    with pytest.raises(TypeError, match="does not match its declared type"):
        service.update_setting("translation_concurrency", "three")

    assert saved == []
    assert service.settings_snapshot().translation_concurrency == 1


def test_update_setting_keeps_memory_and_disk_intact_when_saving_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target: Path = tmp_path / "settings.json"
    monkeypatch.setattr(user_settings_module, "config_path", lambda: target)
    save_user_settings(UserSettings())
    baseline: str = target.read_text(encoding="utf-8")

    def failing_saver(settings: UserSettings) -> None:
        del settings
        message: str = "settings file is locked"
        raise OSError(message)

    service: AppService = _service(tmp_path, UserSettings(), failing_saver)

    with pytest.raises(OSError, match="locked"):
        service.update_setting("translation_concurrency", 5)

    assert target.read_text(encoding="utf-8") == baseline
    assert service.settings_snapshot().translation_concurrency == 1


def test_changing_the_endpoint_drops_options_the_profile_no_longer_accepts(tmp_path: Path) -> None:
    initial: UserSettings = UserSettings(tts_engine="elevenbytes", tts_provider_model_id="run7")
    saved: list[UserSettings] = []
    service: AppService = _service(tmp_path, initial, saved.append)

    with_option: UserSettings = service.update_setting("tts_profile.engine_options.stability", 0.9)
    assert with_option.active_tts_profile.engine_options == {"stability": 0.9}

    switched: UserSettings = service.update_setting("tts_provider_model_id", "run6")

    assert switched.tts_provider_model_id == "run6"
    assert switched.active_tts_profile.engine_options == {}
    assert saved[-1].active_tts_profile.engine_options == {}


def test_changing_the_engine_materializes_the_new_voice_profile(tmp_path: Path) -> None:
    saved: list[UserSettings] = []
    service: AppService = _service(tmp_path, UserSettings(), saved.append)

    switched: UserSettings = service.update_setting("tts_engine", "edge")

    assert switched.tts_voice_id == MAREK_VOICE_ID
    assert tts_profile_key("edge", MAREK_VOICE_ID) in switched.tts_voice_profiles
    assert switched.active_tts_profile.engine_options == {}
    assert saved[-1].tts_voice_id == MAREK_VOICE_ID


def test_removing_the_active_custom_voice_leaves_no_dangling_selection(tmp_path: Path) -> None:
    initial: UserSettings = UserSettings(tts_engine="elevenbytes")
    initial.add_elevenbytes_voice(alias="reader", label="Reader", voice_id="provider-id")
    initial.tts_voice_id = "reader"
    initial.ensure_active_tts_profile()
    saved: list[UserSettings] = []
    service: AppService = _service(tmp_path, initial, saved.append)

    switched: UserSettings = service.update_setting("elevenbytes_custom_voices", ())

    assert switched.elevenbytes_custom_voices == []
    assert switched.tts_voice_id == DALLIN_ALIAS
    assert switched.resolved_tts_voice_id == DALLIN_VOICE_ID
    assert tts_profile_key("elevenbytes", "reader") not in switched.tts_voice_profiles
    assert saved[-1].tts_voice_id == DALLIN_ALIAS


def test_active_run_snapshot_ignores_a_later_preference_update(tmp_path: Path) -> None:
    write_text_source(tmp_path / "Episode.txt", "Text")
    service: AppService = _service(tmp_path, UserSettings(), lambda value: None)
    group_id: str = service.discover().groups[0].group_id
    plan: ExecutionPlan = service.plan_auto(
        (group_id,),
        AutoPresetDraft("preview", "Preview", ProductIntent(frozenset({ProductKind.FULL_PL}))),
    )

    service.update_setting("translation_concurrency", 4)

    assert plan.settings.translation_concurrency == 1
    assert service.settings_snapshot().translation_concurrency == 4
